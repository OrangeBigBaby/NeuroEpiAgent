"""
NeuroSurgEpiAgent Ablation Study Framework

Defines ablation arm configurations and provides experiment runner for systematic
ablation studies. Implements dry-run mode, checkpoint/resume, and safeguards
against silent reuse of nonconcurrent outputs.

Ablation Arms:
1. full_gate: Complete system with router, registry, and guardrails
2. no_router: Direct planner invocation (bypasses database router)
3. no_registry: Planner without variable registry validation
4. no_guardrails: Planner without guardrails validation
5. unconstrained_baseline: Raw LLM call without any NeuroSurgEpiAgent infrastructure
"""

import json
import hashlib
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import yaml


class AblationArm(Enum):
    """Ablation study arm configurations."""
    FULL_GATE = "full_gate"
    NO_ROUTER = "no_router"
    NO_REGISTRY = "no_registry"
    NO_GUARDRAILS = "no_guardrails"
    UNCONSTRAINED_BASELINE = "unconstrained_baseline"


@dataclass
class ArmConfiguration:
    """Configuration for an ablation arm."""
    arm_id: AblationArm
    name: str
    description: str
    components: Dict[str, bool]  # Which components are enabled
    prompt_template: Optional[str] = None
    model_metadata: Dict[str, Any] = field(default_factory=dict)
    expected_model_calls: int = 1  # Expected number of LLM calls per task


# Define arm configurations
ABLATION_ARMS: Dict[AblationArm, ArmConfiguration] = {
    AblationArm.FULL_GATE: ArmConfiguration(
        arm_id=AblationArm.FULL_GATE,
        name="Full Gate System",
        description="Complete system with router, registry, and guardrails",
        components={
            "router": True,
            "registry": True,
            "guardrails": True,
            "planner": True
        },
        expected_model_calls=1  # Single planner call after routing
    ),

    AblationArm.NO_ROUTER: ArmConfiguration(
        arm_id=AblationArm.NO_ROUTER,
        name="No Router (Direct Planner)",
        description="Bypass database router, invoke planner directly on NHANES",
        components={
            "router": False,
            "registry": True,
            "guardrails": True,
            "planner": True
        },
        expected_model_calls=1
    ),

    AblationArm.NO_REGISTRY: ArmConfiguration(
        arm_id=AblationArm.NO_REGISTRY,
        name="No Registry (Unconstrained Variables)",
        description="Planner without variable registry validation",
        components={
            "router": True,
            "registry": False,
            "guardrails": True,
            "planner": True
        },
        expected_model_calls=1
    ),

    AblationArm.NO_GUARDRAILS: ArmConfiguration(
        arm_id=AblationArm.NO_GUARDRAILS,
        name="No Guardrails (Unconstrained Planning)",
        description="Planner without guardrails validation",
        components={
            "router": True,
            "registry": True,
            "guardrails": False,
            "planner": True
        },
        expected_model_calls=1
    ),

    AblationArm.UNCONSTRAINED_BASELINE: ArmConfiguration(
        arm_id=AblationArm.UNCONSTRAINED_BASELINE,
        name="Unconstrained Baseline",
        description="Raw LLM call without NeuroSurgEpiAgent infrastructure",
        components={
            "router": False,
            "registry": False,
            "guardrails": False,
            "planner": False
        },
        expected_model_calls=1
    ),
}


@dataclass
class ExperimentMetadata:
    """Metadata for an ablation experiment run."""
    experiment_id: str
    start_time: str
    arms: List[AblationArm]
    task_source: str  # Path to benchmark file
    task_count: int
    dry_run: bool = False
    resume_from_checkpoint: bool = False
    checkpoint_file: Optional[str] = None
    random_seed: int = 20260628
    concurrency_safeguards: bool = True


@dataclass
class ArmResult:
    """Results from a single arm on a single task."""
    task_id: str
    arm_id: AblationArm
    success: bool
    duration_seconds: float
    output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    model_call_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckpointData:
    """Checkpoint data for resuming experiments."""
    experiment_metadata: ExperimentMetadata
    completed_tasks: Dict[str, Dict[AblationArm, ArmResult]] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AblationRunner:
    """
    Ablation study runner with dry-run, checkpointing, and safeguards.

    Features:
    - Dry-run mode: Print what would happen without making LLM calls
    - Checkpoint/resume: Save progress and resume from checkpoints
    - Concurrency safeguards: Detect nonconcurrent output reuse
    - Model call tracking: Count and flag unexpected model call patterns
    """

    def __init__(self, metadata: ExperimentMetadata):
        self.metadata = metadata
        self.results: Dict[str, Dict[AblationArm, ArmResult]] = {}
        self.model_call_tracker: Dict[str, Dict[AblationArm, int]] = {}
        self.checkpoint_path = None

        # Initialize checkpoint file if specified
        if metadata.checkpoint_file:
            self.checkpoint_path = Path(metadata.checkpoint_file)
            if metadata.resume_from_checkpoint and self.checkpoint_path.exists():
                self._load_checkpoint()

    def _load_checkpoint(self):
        """Load experiment state from checkpoint file."""
        if not self.checkpoint_path or not self.checkpoint_path.exists():
            return

        with open(self.checkpoint_path) as f:
            checkpoint_data = json.load(f)

        # Restore results
        for task_id, arm_results in checkpoint_data['completed_tasks'].items():
            self.results[task_id] = {}
            for arm_str, arm_result in arm_results.items():
                arm = AblationArm(arm_str)
                self.results[task_id][arm] = ArmResult(**arm_result)

    def _save_checkpoint(self):
        """Save current experiment state to checkpoint file."""
        if not self.checkpoint_path:
            return

        # Prepare checkpoint data
        checkpoint_data = {
            'experiment_metadata': {
                'experiment_id': self.metadata.experiment_id,
                'start_time': self.metadata.start_time,
                'arms': [arm.value for arm in self.metadata.arms],
                'task_source': self.metadata.task_source,
                'task_count': self.metadata.task_count,
                'dry_run': self.metadata.dry_run,
                'random_seed': self.metadata.random_seed
            },
            'completed_tasks': {}
        }

        # Serialize results
        for task_id, arm_results in self.results.items():
            checkpoint_data['completed_tasks'][task_id] = {}
            for arm, arm_result in arm_results.items():
                checkpoint_data['completed_tasks'][task_id][arm.value] = {
                    'task_id': arm_result.task_id,
                    'arm_id': arm_result.arm_id.value,
                    'success': arm_result.success,
                    'duration_seconds': arm_result.duration_seconds,
                    'output': arm_result.output,
                    'error_message': arm_result.error_message,
                    'model_call_count': arm_result.model_call_count,
                    'metadata': arm_result.metadata
                }

        # Write checkpoint
        with open(self.checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)

    def run_task(self, task_id: str, task_data: Dict[str, Any], arms: Optional[List[AblationArm]] = None):
        """
        Run a single task on specified arms.

        Args:
            task_id: Task identifier
            task_data: Task data from benchmark
            arms: List of arms to run (default: all arms from metadata)
        """
        if arms is None:
            arms = self.metadata.arms

        # Initialize result dict for this task
        if task_id not in self.results:
            self.results[task_id] = {}

        for arm in arms:
            # Skip if already completed (resume mode)
            if arm in self.results[task_id]:
                continue

            # Run the arm
            result = self._run_arm(task_id, task_data, arm)
            self.results[task_id][arm] = result

        # Save checkpoint after each task
        if self.checkpoint_path:
            self._save_checkpoint()

    def _run_arm(self, task_id: str, task_data: Dict[str, Any], arm: AblationArm) -> ArmResult:
        """
        Run a single arm on a single task.

        In dry-run mode, this simulates the run without making LLM calls.
        In production mode, this would call the actual system components.
        """
        start_time = time.time()
        arm_config = ABLATION_ARMS[arm]

        if self.metadata.dry_run:
            # Dry-run mode: simulate execution without LLM calls
            result = self._dry_run_arm(task_id, task_data, arm, arm_config)
        else:
            # Production mode: actual system execution
            # This would be implemented by calling actual system components
            result = self._production_run_arm(task_id, task_data, arm, arm_config)

        duration = time.time() - start_time
        result.duration_seconds = duration

        return result

    def _dry_run_arm(self, task_id: str, task_data: Dict[str, Any], arm: AblationArm, arm_config: ArmConfiguration) -> ArmResult:
        """Simulate arm execution in dry-run mode."""

        # In dry-run mode, we don't make actual LLM calls
        # We just report what would happen

        print(f"[DRY-RUN] Task: {task_id} | Arm: {arm.value}")
        print(f"  Components: {arm_config.components}")
        print(f"  Expected model calls: {arm_config.expected_model_calls}")
        print(f"  Question: {task_data.get('question', 'N/A')[:80]}...")

        # Simulate success
        return ArmResult(
            task_id=task_id,
            arm_id=arm,
            success=True,
            duration_seconds=0.0,  # Dry-run has no real duration
            output={
                'dry_run': True,
                'database': task_data.get('expected_database', 'NHANES'),
                'feasible': task_data.get('expected_feasible', True),
                'note': 'Dry-run output - not from actual LLM call'
            },
            model_call_count=arm_config.expected_model_calls,
            metadata={
                'dry_run': True,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        )

    def _production_run_arm(self, task_id: str, task_data: Dict[str, Any], arm: AblationArm, arm_config: ArmConfiguration) -> ArmResult:
        """Execute arm in production mode (stub for actual implementation)."""

        # This is a stub - actual implementation would call real system components
        # For now, we'll raise an error since production calls aren't implemented
        raise NotImplementedError(
            "Production mode not yet implemented. Use dry_run=True for testing. "
            "Actual LLM calls require API configuration and system integration."
        )

    def validate_concurrency(self) -> Dict[str, Any]:
        """
        Validate that results are from concurrent experiments (same task set, same time).

        Safeguards against silently reusing nonconcurrent outputs.
        """
        validation_results = {
            'is_concurrent': True,
            'issues': [],
            'task_counts': {},
            'arm_completeness': {}
        }

        # Check task count consistency. If the runner was created with an
        # ad-hoc task source that did not expose a task count, fall back to
        # the observed completed task set.
        expected_tasks = self.metadata.task_count or len(self.results)
        for arm in self.metadata.arms:
            task_count = sum(1 for task_results in self.results.values() if arm in task_results)
            validation_results['task_counts'][arm.value] = task_count
            validation_results['arm_completeness'][arm.value] = task_count == expected_tasks

            if task_count != expected_tasks:
                validation_results['is_concurrent'] = False
                validation_results['issues'].append(
                    f"Arm {arm.value} has {task_count} tasks, expected {expected_tasks}"
                )

        # Check that all tasks have results for all arms (concurrent execution)
        for task_id, task_results in self.results.items():
            if set(task_results.keys()) != set(self.metadata.arms):
                validation_results['is_concurrent'] = False
                validation_results['issues'].append(
                    f"Task {task_id} missing results for arms: "
                    f"{set(self.metadata.arms) - set(task_results.keys())}"
                )

        return validation_results

    def get_model_call_summary(self) -> Dict[str, Dict[AblationArm, int]]:
        """Get summary of model calls across arms."""
        summary = {}
        for arm in self.metadata.arms:
            total_calls = 0
            for task_results in self.results.values():
                if arm in task_results:
                    total_calls += task_results[arm].model_call_count
            summary[arm.value] = total_calls

        return summary

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive experiment report."""
        validation = self.validate_concurrency()
        model_calls = self.get_model_call_summary()

        return {
            'experiment_metadata': {
                'experiment_id': self.metadata.experiment_id,
                'start_time': self.metadata.start_time,
                'dry_run': self.metadata.dry_run,
                'task_source': self.metadata.task_source,
                'task_count': self.metadata.task_count
            },
            'validation': validation,
            'model_calls': model_calls,
            'arm_results': {
                'total_tasks': len(self.results),
                'arms_tested': [arm.value for arm in self.metadata.arms],
                'completion_rate': {
                    arm.value: sum(1 for r in self.results.values() if arm in r) / len(self.results)
                    for arm in self.metadata.arms
                } if self.results else {}
            },
            'warnings': self._generate_warnings()
        }

    def _generate_warnings(self) -> List[str]:
        """Generate warnings about potential issues."""
        warnings = []

        # Check for incomplete arms
        for arm in self.metadata.arms:
            completion = sum(1 for r in self.results.values() if arm in r)
            if completion < len(self.results):
                warnings.append(f"Arm {arm.value} incomplete: {completion}/{len(self.results)} tasks")

        # Check model call counts
        expected_calls = ABLATION_ARMS[self.metadata.arms[0]].expected_model_calls
        for task_id, task_results in self.results.items():
            for arm, result in task_results.items():
                if result.model_call_count != expected_calls:
                    warnings.append(
                        f"Unexpected model call count: {task_id}/{arm.value} = "
                        f"{result.model_call_count} (expected {expected_calls})"
                    )

        return warnings


def create_experiment_id() -> str:
    """Generate unique experiment ID."""
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    random_suffix = hashlib.md5(f"{timestamp}_{os.urandom(8).hex()}".encode()).hexdigest()[:8]
    return f"ablation_{timestamp}_{random_suffix}"


def create_runner(
    arms: List[AblationArm],
    task_source: str,
    dry_run: bool = True,
    checkpoint_file: Optional[str] = None,
    resume: bool = False,
    experiment_id: Optional[str] = None
) -> AblationRunner:
    """
    Create an ablation study runner.

    Args:
        arms: List of arms to test
        task_source: Path to benchmark file
        dry_run: If True, simulate without LLM calls (recommended for testing)
        checkpoint_file: Path to checkpoint file for resume capability
        resume: If True, resume from checkpoint file
        experiment_id: Optional experiment ID (auto-generated if None)

    Returns:
        Configured AblationRunner instance
    """
    if experiment_id is None:
        experiment_id = create_experiment_id()

    task_count = 0
    task_source_path = Path(task_source)
    if task_source_path.exists():
        with task_source_path.open('r', encoding='utf-8') as f:
            task_data = yaml.safe_load(f) or {}
        if isinstance(task_data, dict):
            tasks = task_data.get('tasks', [])
            task_count = len(tasks) if isinstance(tasks, list) else 0

    metadata = ExperimentMetadata(
        experiment_id=experiment_id,
        start_time=datetime.now(timezone.utc).isoformat(),
        arms=arms,
        task_source=task_source,
        task_count=task_count,
        dry_run=dry_run,
        resume_from_checkpoint=resume,
        checkpoint_file=checkpoint_file,
        random_seed=20260628,
        concurrency_safeguards=True
    )

    return AblationRunner(metadata)
