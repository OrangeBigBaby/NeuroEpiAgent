"""Live experiment runner for pilot evaluation.

This module provides token-efficient execution of pilot A/B testing:
- Loads tasks from benchmarks/tasks.example.yaml
- Runs both arms (constrained + baseline) sequentially with same model
- Implements checkpoint/resume for interrupted runs
- Records raw envelope metadata without secrets
- Supports --confirm-live flag; default is dry-run with zero model calls
"""

from __future__ import annotations

import json
import hashlib
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from .evaluation import ArmOutput, BenchmarkTask, ProviderArm
from .guardrails import evaluate_plan
from .planner import ClaudeCodePlannerProvider, PlannerError
from .registry import load_variable_registry
from .router import route
from .schemas import AnalysisPlan, Severity
from .telemetry import (
    CallTelemetry,
    ZERO_CALL_TELEMETRY,
    build_efficiency_summary,
    estimate_cost,
    validate_prices,
)


class ExperimentRun(str, Enum):
    """Status of experiment run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ExperimentMetadata(BaseModel):
    """Metadata for an experiment run."""

    # Configuration
    model: str
    max_budget_usd_per_call: float | None
    timeout: int
    max_tasks: int | None

    # Manifest hashes
    prompt_hash_a: str
    prompt_hash_b: str
    registry_hash: str
    task_set_hash: str

    # Timing
    start_time_utc: str | None = None
    end_time_utc: str | None = None
    duration_seconds: float | None = None

    # Status
    status: ExperimentRun = ExperimentRun.PENDING

    # Task tracking
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    # Checkpointing
    checkpoint_file: str | None = None

    # Errors
    errors: list[str] = []


# Create a simple experiment runner
class ExperimentRunner:
    """Token-efficient live pilot runner with checkpoint/resume."""

    def __init__(
        self,
        tasks_path: Path,
        prompt_a_path: Path,
        prompt_b_path: Path,
        registry_path: Path,
        model: str = "claude-sonnet-4-6",
        max_budget_usd_per_call: float = 0.50,
        timeout: int = 120,
        max_tasks: int | None = None,
        checkpoint_file: Path | None = None,
        reuse_arm_b_from: Path | None = None,
        prices: dict[str, float | None] | None = None,
        backend_label: str | None = None,
    ):
        """Initialize experiment runner.

        Args:
            tasks_path: Path to benchmark tasks YAML
            prompt_a_path: Path to constrained prompt (Arm A)
            prompt_b_path: Path to baseline prompt (Arm B)
            registry_path: Path to variable registry
            model: Model identifier for Claude calls
            max_budget_usd_per_call: Maximum USD budget per model call
            timeout: Timeout in seconds for each call
            max_tasks: Maximum number of tasks to run (None = all)
            checkpoint_file: Path to checkpoint file for resume
            reuse_arm_b_from: Path to previous run outputs to reuse Arm B results
            prices: Optional explicit per-million-token USD prices keyed by
                ``input``/``output``/``cache_read``/``cache_creation``. When
                supplied, an estimated cost is computed per output. Vendor
                prices are never hard-coded by the runner.
            backend_label: Optional descriptive provenance string recording the
                declared backend route (e.g. ``"glm-5.2 via CC-Switch"``).
                Descriptive only; not authentication data.
        """
        self.tasks_path = tasks_path
        self.prompt_a_path = prompt_a_path
        self.prompt_b_path = prompt_b_path
        self.registry_path = registry_path
        self.model = model
        self.max_budget_usd_per_call = max_budget_usd_per_call
        self.timeout = timeout
        self.max_tasks = max_tasks
        self.checkpoint_file = checkpoint_file
        self.reuse_arm_b_from = reuse_arm_b_from
        # Validate any caller-supplied prices (negative / non-finite rejected;
        # zero permitted). Vendor prices are never hard-coded by the runner.
        self.prices = validate_prices(prices) or None
        self.backend_label = backend_label

        # Load resources
        self.tasks = self._load_tasks()
        self.variable_registry = load_variable_registry(registry_path)
        self.allowed_codes = {v.source_variable for v in self.variable_registry}

        # Compute hashes
        self.prompt_hash_a = self._sha256_file(prompt_a_path)
        self.prompt_hash_b = self._sha256_file(prompt_b_path)
        self.registry_hash = self._sha256_file(registry_path)
        self.task_set_hash = self._sha256_file(tasks_path)

        # Initialize providers
        self.provider_a = ClaudeCodePlannerProvider(
            prompt_path=prompt_a_path,
            model=model,
            timeout=timeout,
            max_budget_usd=max_budget_usd_per_call,
        )

        self.provider_b = ClaudeCodePlannerProvider(
            prompt_path=prompt_b_path,
            model=model,
            timeout=timeout,
            max_budget_usd=max_budget_usd_per_call,
        )

        # Outputs storage
        self.arm_outputs: list[ArmOutput] = []
        self.metadata: dict[str, Any] = {}

        # Load Arm B outputs for reuse if specified
        self.reused_arm_b_outputs: dict[str, ArmOutput] = {}
        if reuse_arm_b_from:
            self._load_reused_arm_b_outputs(reuse_arm_b_from)

    def _load_reused_arm_b_outputs(self, reuse_path: Path) -> None:
        """Load and validate Arm B outputs from previous run for reuse.

        Only successful Arm B outputs are reused. Validates task IDs and metadata.

        Args:
            reuse_path: Path to previous run outputs JSON
        """
        print(f"Loading Arm B outputs for reuse from {reuse_path}...")

        if not reuse_path.exists():
            raise ValueError(f"Reuse file not found: {reuse_path}")

        try:
            with reuse_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in reuse file: {e}")

        # Extract arm outputs from previous run
        previous_outputs = []
        for output_data in data.get("arm_outputs", []):
            try:
                output = ArmOutput.model_validate(output_data)
                previous_outputs.append(output)
            except Exception as e:
                print(f"WARNING: Failed to validate reused output: {e}")

        # Filter for successful Arm B outputs only
        reused_count = 0
        for output in previous_outputs:
            # Only reuse Arm B outputs
            if output.arm != ProviderArm.ARM_B:
                continue

            # Only reuse successful outputs (valid plan, no error)
            if output.plan is None or output.error is not None:
                print(f"  Skipping {output.task_id} Arm B: failed or missing plan")
                continue

            # Validate task ID exists in current task set
            task_ids = {t.id for t in self.tasks}
            if output.task_id not in task_ids:
                print(f"  Skipping {output.task_id} Arm B: task ID not in current task set")
                continue

            # Store reused output, marked so efficiency summaries do not
            # double-count it as a new model call in this run.
            output = output.model_copy(update={"reused": True})
            self.reused_arm_b_outputs[output.task_id] = output
            reused_count += 1
            print(f"  Reusing {output.task_id} Arm B output (model: {output.model_label})")

        print(f"Loaded {reused_count} Arm B outputs for reuse")

        # Record provenance in metadata
        self.metadata["reuse_provenance"] = {
            "path": str(reuse_path),
            "reused_count": reused_count,
            "previous_metadata": data.get("metadata", {}),
        }

    def _load_tasks(self) -> list[BenchmarkTask]:
        """Load benchmark tasks from YAML."""
        with self.tasks_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return [BenchmarkTask.model_validate(t) for t in data.get("tasks", [])]

    def _sha256_file(self, path: Path) -> str:
        """Compute SHA256 hash of a file."""
        hasher = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _read_call_telemetry(self, provider: ClaudeCodePlannerProvider) -> CallTelemetry | None:
        """Read the most recent CallTelemetry from a provider, if any.

        Returns None when the provider has no telemetry (e.g. a mock in unit
        tests, or a call that never reached the subprocess). The isinstance
        guard avoids treating auto-created mock attributes as telemetry.
        """
        t = getattr(provider, "last_call_telemetry", None)
        return t if isinstance(t, CallTelemetry) else None

    def _pricing_metadata(self) -> dict[str, Any]:
        """Build pricing + estimated-cost provenance metadata.

        Vendor prices are never hard-coded: rates are recorded only when the
        caller supplied them explicitly. The provenance note documents the
        rule (None unless every rate required by observed nonzero token
        categories is supplied).
        """
        if not self.prices:
            return {
                "configured": False,
                "rates_usd_per_million_tokens": None,
                "note": (
                    "No explicit per-million-token prices supplied; "
                    "estimated_cost_usd is None for all outputs."
                ),
            }
        return {
            "configured": True,
            "rates_usd_per_million_tokens": {
                "input": self.prices.get("input"),
                "output": self.prices.get("output"),
                "cache_read": self.prices.get("cache_read"),
                "cache_creation": self.prices.get("cache_creation"),
            },
            "note": (
                "estimated_cost_usd = sum(tokens * rate / 1e6) over observed "
                "nonzero categories; None for any call whose nonzero token "
                "categories lack a supplied rate. Rates are caller-supplied, "
                "not hard-coded vendor prices."
            ),
        }

    def _is_task_successful(self, output_a: ArmOutput, output_b: ArmOutput) -> bool:
        """Determine if a task completed successfully with both arms.

        A task is considered successful only when:
        - Both arm outputs contain valid plans (not None)
        - Neither arm has a provider error

        Args:
            output_a: Output from Arm A
            output_b: Output from Arm B

        Returns:
            True if task completed successfully, False otherwise
        """
        # Both arms must have valid plans
        if output_a.plan is None or output_b.plan is None:
            return False

        # Neither arm should have a provider error
        if output_a.error is not None or output_b.error is not None:
            return False

        return True

    def _load_checkpoint(self) -> tuple[set[str], list[ArmOutput]]:
        """Load checkpoint and return set of completed task IDs and previous outputs.

        Returns:
            Tuple of (completed_task_ids, previous_arm_outputs)
        """
        if self.checkpoint_file and self.checkpoint_file.exists():
            with self.checkpoint_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                completed = set(data.get("completed_tasks", []))
                self.metadata = data.get("metadata", {})

                # Load previous outputs if available
                previous_outputs = []
                for output_data in data.get("arm_outputs", []):
                    try:
                        output = ArmOutput.model_validate(output_data)
                        previous_outputs.append(output)
                    except Exception as e:
                        print(f"WARNING: Failed to load checkpoint output: {e}")

                return completed, previous_outputs
        return set(), []

    def _save_checkpoint(self, completed_tasks: set[str], arm_outputs: list[ArmOutput] | None = None) -> None:
        """Save checkpoint state including outputs.

        Args:
            completed_tasks: Set of completed task IDs
            arm_outputs: List of arm outputs to save (if None, uses current self.arm_outputs)
        """
        if self.checkpoint_file:
            outputs_to_save = arm_outputs if arm_outputs is not None else self.arm_outputs

            checkpoint_data = {
                "completed_tasks": sorted(completed_tasks),
                "metadata": self.metadata,
                "arm_outputs": [output.model_dump() for output in outputs_to_save],
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
            with self.checkpoint_file.open("w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, indent=2)

    def run_task(
        self,
        task: BenchmarkTask,
        arm: ProviderArm,
        provider: ClaudeCodePlannerProvider,
        dry_run: bool = False,
    ) -> ArmOutput:
        """Run a single task for a specific arm.

        Args:
            task: Benchmark task to run
            arm: Which arm to run (A or B)
            provider: Planner provider to use
            dry_run: If True, don't call the model, just simulate

        Returns:
            ArmOutput with results
        """
        start_time = time.time()
        timestamp_utc = datetime.now(timezone.utc).isoformat()

        if dry_run:
            # Simulate output without calling model. No call occurred, so attach
            # an explicit measured-zero telemetry (distinct from missing).
            return ArmOutput(
                task_id=task.id,
                arm=arm,
                provider_type="dry_run",
                timestamp_utc=timestamp_utc,
                plan=None,
                error="Dry run - no model call made",
                execution_time_seconds=0.0,
                validation_errors=[],
                guardrail_findings=[],
                call_telemetry=CallTelemetry(**ZERO_CALL_TELEMETRY),
            )

        try:
            # Arm A: Apply deterministic gate before any planner call
            if arm == ProviderArm.ARM_A:
                # Route the question deterministically
                route_decision = route(task.question)

                # If infeasible, create minimal valid AnalysisPlan without calling planner
                if not route_decision.feasible:
                    from .schemas import AnalysisPlan

                    # Create minimal plan with exact routing information
                    minimal_plan = AnalysisPlan(
                        title=f"Feasibility assessment: {task.id}",
                        question=task.question,
                        database=route_decision.database,
                        cycles=[],  # No cycles for infeasible questions
                        feasible=False,
                        outcome=None,  # No variables for infeasible questions
                        exposures=[],
                        covariates=[],
                        uses_fasting_subsample=False,
                        design_vars={},
                        steps=[
                            {
                                "step": "1",
                                "description": f"Deterministic routing assessment: {route_decision.rationale}",
                                "outputs": ["feasibility_refusal"],
                            }
                        ],
                        causal_claims=[],
                        rationale=route_decision.rationale,
                        guardrail_notes=f"Deterministic router: {route_decision.database} - {route_decision.rationale}",
                    )

                    execution_time = time.time() - start_time

                    # Skip guardrails for infeasible plans (no variables to validate).
                    # No model call occurred, so attach an explicit measured-zero
                    # telemetry (distinct from a missing-telemetry attempted call).
                    return ArmOutput(
                        task_id=task.id,
                        arm=arm,
                        provider_type="deterministic_router",
                        model_label=None,  # No model call for infeasible Arm A
                        timestamp_utc=timestamp_utc,
                        plan=minimal_plan,
                        error=None,
                        execution_time_seconds=execution_time,
                        validation_errors=[],
                        guardrail_findings=[],  # Skip guardrails for infeasible plans
                        call_telemetry=CallTelemetry(**ZERO_CALL_TELEMETRY),
                    )

                # If feasible, call planner with routing_context
                plan = provider.generate_plan(
                    question=task.question,
                    registry_path=self.registry_path,
                    routing_context={
                        "database": route_decision.database,
                        "feasible": route_decision.feasible,
                        "rationale": route_decision.rationale,
                        "caveats": route_decision.caveats,
                    },
                )

            # Arm B: Baseline, no routing_context
            else:
                plan = provider.generate_plan(
                    question=task.question,
                    registry_path=None,  # No registry for baseline
                    routing_context=None,  # No routing context for baseline
                )

            # Telemetry from the call just made (preserved whether or not plan
            # validation/guardrails later succeed). None when no envelope was
            # captured (e.g. subprocess failure), but model_call_attempted is
            # still True inside the telemetry object.
            telemetry = self._read_call_telemetry(provider)

            # Run guardrails if plan generated
            guardrail_findings = []
            if plan:
                try:
                    report = evaluate_plan(
                        plan,
                        database=None,
                        variables=self.variable_registry,
                    )
                    guardrail_findings = [
                        {
                            "severity": f.severity.value,
                            "code": f.code,
                            "message": f.message,
                            "remediation": f.remediation,
                        }
                        for f in report.findings
                    ]
                except Exception as e:
                    guardrail_findings = [
                        {
                            "severity": "error",
                            "code": "GUARDRAIL_ERROR",
                            "message": f"Guardrail evaluation failed: {e}",
                            "remediation": None,
                        }
                    ]

            execution_time = time.time() - start_time

            return ArmOutput(
                task_id=task.id,
                arm=arm,
                provider_type="claude_code",
                model_label=self.model,
                timestamp_utc=timestamp_utc,
                plan=plan,
                error=None,
                execution_time_seconds=execution_time,
                validation_errors=[],
                guardrail_findings=guardrail_findings,
                call_telemetry=telemetry,
            )

        except PlannerError as e:
            execution_time = time.time() - start_time
            # A live planner attempt counts as one model call even when parsing
            # or plan validation failed; preserve whatever telemetry was set.
            telemetry = self._read_call_telemetry(provider)
            return ArmOutput(
                task_id=task.id,
                arm=arm,
                provider_type="claude_code",
                model_label=self.model,
                timestamp_utc=timestamp_utc,
                plan=None,
                error=str(e),
                execution_time_seconds=execution_time,
                validation_errors=[],
                guardrail_findings=[],
                call_telemetry=telemetry,
            )
        except Exception as e:
            execution_time = time.time() - start_time
            telemetry = self._read_call_telemetry(provider)
            return ArmOutput(
                task_id=task.id,
                arm=arm,
                provider_type="claude_code",
                model_label=self.model,
                timestamp_utc=timestamp_utc,
                plan=None,
                error=f"Unexpected error: {e}",
                execution_time_seconds=execution_time,
                validation_errors=[],
                guardrail_findings=[],
                call_telemetry=telemetry,
            )

    def run_experiment(
        self,
        dry_run: bool = False,
        confirm_live: bool = False,
    ) -> tuple[list[ArmOutput], dict[str, Any]]:
        """Run the complete experiment.

        Args:
            dry_run: If True, simulate without model calls
            confirm_live: Required for live runs (must be True to make API calls)

        Returns:
            Tuple of (arm_outputs, metadata)

        Raises:
            ValueError: If live run requested without confirm_live flag
        """
        if not dry_run and not confirm_live:
            raise ValueError(
                "Live runs require --confirm-live flag. "
                "This will make real Claude API calls and incur costs. "
                "Use --dry-run for zero-cost testing."
            )

        start_time = time.time()
        start_time_utc = datetime.now(timezone.utc).isoformat()

        # Load checkpoint and previous outputs
        completed_tasks, previous_outputs = self._load_checkpoint()

        # Limit tasks if requested
        tasks_to_run = self.tasks[: self.max_tasks] if self.max_tasks else self.tasks

        # Filter out completed tasks from pending
        pending_tasks = [t for t in tasks_to_run if t.id not in completed_tasks]

        # Remove prior outputs for pending tasks (for retries)
        pending_task_ids = {t.id for t in pending_tasks}
        outputs = [output for output in previous_outputs if output.task_id not in pending_task_ids]

        metadata = {
            "model": self.model,
            "max_budget_usd_per_call": self.max_budget_usd_per_call,
            "timeout": self.timeout,
            "max_tasks": self.max_tasks,
            "prompt_hash_a": self.prompt_hash_a,
            "prompt_hash_b": self.prompt_hash_b,
            "registry_hash": self.registry_hash,
            "task_set_hash": self.task_set_hash,
            "start_time_utc": start_time_utc,
            "status": "running" if not dry_run else "dry_run",
            "total_tasks": len(tasks_to_run),
            "completed_tasks": len(completed_tasks),
            "pending_tasks": len(pending_tasks),
            "dry_run": dry_run,
            # Declared backend provenance (descriptive only, not auth). Records
            # both the Claude-facing model alias and any declared backend route.
            "backend_provenance": {
                "model_alias": self.model,
                "backend_label": self.backend_label,
            },
            # Arm B reuse configuration. A fresh contemporaneous paired run has
            # configured=False and is identifiable as same-run / no-reuse.
            "arm_b_reuse": {
                "configured": self.reuse_arm_b_from is not None,
                "reused_count": len(self.reused_arm_b_outputs),
                "reuse_source": str(self.reuse_arm_b_from) if self.reuse_arm_b_from else None,
            },
            # Execution design. Arms run sequentially within one run; this is
            # NOT parallel execution and the arms are NOT statistically
            # independent samples.
            "execution_design": {
                "mode": "sequential",
                "parallel": False,
                "statistically_independent": False,
                "same_run_paired": True,
                "arm_order": ["arm_a", "arm_b"],
            },
            # Optional explicit per-million-token prices and estimated-cost
            # provenance. Vendor prices are never hard-coded by the runner.
            "pricing": self._pricing_metadata(),
        }

        # Track failed tasks for this run
        failed_task_ids: set[str] = set()

        # Run tasks sequentially
        for i, task in enumerate(pending_tasks):
            print(f"Processing task {task.id} ({i+1}/{len(pending_tasks)} pending)...")

            # A pending task may have failed outputs from an earlier checkpoint.
            # Replace those attempts instead of duplicating them in the final run.
            outputs = [output for output in outputs if output.task_id != task.id]

            # Run Arm A (constrained)
            print(f"  Running Arm A (constrained)...")
            output_a = self.run_task(task, ProviderArm.ARM_A, self.provider_a, dry_run=dry_run)
            outputs.append(output_a)

            # Run Arm B (baseline)
            print(f"  Running Arm B (baseline)...")
            if task.id in self.reused_arm_b_outputs:
                # Reuse previous Arm B output
                output_b = self.reused_arm_b_outputs[task.id]
                print(f"    Reused Arm B output from previous run")
            else:
                # Generate new Arm B output
                output_b = self.run_task(task, ProviderArm.ARM_B, self.provider_b, dry_run=dry_run)
            outputs.append(output_b)

            # Only mark task as completed if both arms succeeded
            if self._is_task_successful(output_a, output_b):
                completed_tasks.add(task.id)
                print(f"  Task {task.id} completed successfully")
            else:
                failed_task_ids.add(task.id)
                print(f"  Task {task.id} failed (will remain pending for retry)")

            # Update checkpoint with current state
            self._save_checkpoint(completed_tasks, outputs)

            # Update metadata
            metadata["completed_tasks"] = len(completed_tasks)

        end_time = time.time()
        end_time_utc = datetime.now(timezone.utc).isoformat()

        # Calculate final metadata
        selected_task_ids = {t.id for t in tasks_to_run}
        successful_completed_ids = completed_tasks & selected_task_ids

        # Determine final status
        if dry_run:
            final_status = "dry_run_completed"
        elif failed_task_ids:
            final_status = "completed_with_errors"
        else:
            final_status = "completed"

        metadata["end_time_utc"] = end_time_utc
        metadata["duration_seconds"] = end_time - start_time
        metadata["status"] = final_status

        # Update task counts with final values
        metadata["completed_tasks"] = len(successful_completed_ids)
        metadata["failed_tasks"] = len(failed_task_ids)
        metadata["pending_tasks"] = len(selected_task_ids) - len(successful_completed_ids)

        # Compute estimated cost per output from explicit prices (mutates the
        # telemetry in place; only set when prices were supplied). Estimated
        # cost is None for any call whose observed nonzero token categories
        # lack a supplied rate. Reused outputs are not re-priced here, and
        # zero-call outputs (dry run / deterministic refusal) keep their
        # explicit measured-zero estimated_cost_usd rather than being reset.
        if self.prices:
            for output in outputs:
                tel = output.call_telemetry
                if tel is None or output.reused:
                    continue
                if not tel.model_call_attempted:
                    continue
                est = estimate_cost(tel, self.prices)
                output.call_telemetry = tel.model_copy(
                    update={"estimated_cost_usd": est}
                )

        # Build the deterministic efficiency summary (per-arm + overall). Token
        # and cost totals over missing values are never summed as zero;
        # availability/missing counts are reported alongside every total.
        output_dicts = [o.model_dump() for o in outputs]
        metadata["efficiency_summary"] = build_efficiency_summary(
            output_dicts,
            total_tasks=len(tasks_to_run),
            prices=self.prices,
        )

        self.arm_outputs = outputs
        self.metadata = metadata

        return outputs, metadata
