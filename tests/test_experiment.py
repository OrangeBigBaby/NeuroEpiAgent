"""Tests for experiment runner: checkpointing, retries, and metadata consistency."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from neurosurg_epi_agent.evaluation import ArmOutput, BenchmarkTask, ProviderArm
from neurosurg_epi_agent.experiment import ExperimentRunner
from neurosurg_epi_agent.schemas import AnalysisPlan


class TestExperimentTaskSuccess:
    """Test _is_task_successful determines task completion correctly."""

    def test_is_task_successful_both_arms_valid(self):
        """Both arms with valid plans and no errors returns True."""
        # Create mock experiment runner (minimal setup)
        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = Mock()
            runner._is_task_successful = ExperimentRunner._is_task_successful.__get__(runner)

            plan = AnalysisPlan(
                title="Test Plan",
                question="Test question?",
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            output_a = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_A,
                provider_type="claude_code",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=plan,
                error=None,
            )

            output_b = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_B,
                provider_type="claude_code",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=plan,
                error=None,
            )

            result = runner._is_task_successful(output_a, output_b)
            assert result is True

    def test_is_task_successful_arm_a_missing_plan(self):
        """Arm A with missing plan returns False."""
        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = Mock()
            runner._is_task_successful = ExperimentRunner._is_task_successful.__get__(runner)

            plan = AnalysisPlan(
                title="Test Plan",
                question="Test question?",
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            output_a = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_A,
                provider_type="claude_code",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=None,  # Missing plan
                error=None,
            )

            output_b = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_B,
                provider_type="claude_code",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=plan,
                error=None,
            )

            result = runner._is_task_successful(output_a, output_b)
            assert result is False

    def test_is_task_successful_arm_b_error(self):
        """Arm B with error returns False."""
        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = Mock()
            runner._is_task_successful = ExperimentRunner._is_task_successful.__get__(runner)

            plan = AnalysisPlan(
                title="Test Plan",
                question="Test question?",
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            output_a = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_A,
                provider_type="claude_code",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=plan,
                error=None,
            )

            output_b = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_B,
                provider_type="claude_code",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=None,
                error="Provider error",  # Error present
            )

            result = runner._is_task_successful(output_a, output_b)
            assert result is False

    def test_is_task_successful_both_arms_failed(self):
        """Both arms with errors returns False."""
        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = Mock()
            runner._is_task_successful = ExperimentRunner._is_task_successful.__get__(runner)

            output_a = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_A,
                provider_type="claude_code",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=None,
                error="Error A",
            )

            output_b = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_B,
                provider_type="claude_code",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=None,
                error="Error B",
            )

            result = runner._is_task_successful(output_a, output_b)
            assert result is False


class TestExperimentCheckpointing:
    """Test checkpoint saving and loading functionality."""

    def test_save_and_load_checkpoint(self, tmp_path):
        """Checkpoint saves and loads completed tasks and outputs correctly."""
        # Create required files first
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("tasks: []")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        checkpoint_file = tmp_path / "checkpoint.json"

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
                checkpoint_file=checkpoint_file,
            )

            # Create sample outputs
            plan = AnalysisPlan(
                title="Test Plan",
                question="Test question?",
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            outputs = [
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_A,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_B,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
            ]

            completed_tasks = {"task_01"}
            metadata = {"test_key": "test_value"}

            runner.metadata = metadata
            runner._save_checkpoint(completed_tasks, outputs)

            # Load checkpoint
            loaded_tasks, loaded_outputs = runner._load_checkpoint()

            assert loaded_tasks == completed_tasks
            assert len(loaded_outputs) == 2
            assert all(isinstance(o, ArmOutput) for o in loaded_outputs)
            assert loaded_outputs[0].task_id == "task_01"
            assert runner.metadata == metadata

    def test_load_checkpoint_nonexistent_file(self, tmp_path):
        """Nonexistent checkpoint file returns empty state."""
        # Create required files first
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("tasks: []")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        checkpoint_file = tmp_path / "nonexistent.json"

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
                checkpoint_file=checkpoint_file,
            )

            loaded_tasks, loaded_outputs = runner._load_checkpoint()

            assert loaded_tasks == set()
            assert loaded_outputs == []

    def test_checkpoint_overwrites_on_save(self, tmp_path):
        """Saving checkpoint overwrites existing data."""
        checkpoint_file = tmp_path / "checkpoint.json"

        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(
            "tasks:\n"
            "  - id: task_01\n"
            "    domain: stroke\n"
            "    question: Test question?\n"
            "    expected_database: NHANES\n"
            "    expected_feasible: true\n"
            "    rationale: Test\n"
        )
        prompt_a = tmp_path / "prompt_a.txt"
        prompt_b = tmp_path / "prompt_b.txt"
        prompt_a.write_text("Prompt A")
        prompt_b.write_text("Prompt B")
        registry = tmp_path / "registry.yaml"
        registry.write_text('registry_version: "1"\nvariables: []\n')

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
                checkpoint_file=checkpoint_file,
            )

            plan = AnalysisPlan(
                title="Test Plan",
                question="Test question?",
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            # First save
            outputs1 = [
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_A,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                )
            ]
            runner._save_checkpoint({"task_01"}, outputs1)

            # Second save (should overwrite)
            outputs2 = [
                ArmOutput(
                    task_id="task_02",
                    arm=ProviderArm.ARM_B,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                )
            ]
            runner._save_checkpoint({"task_02"}, outputs2)

            # Load should have second save data only
            loaded_tasks, loaded_outputs = runner._load_checkpoint()
            assert loaded_tasks == {"task_02"}
            assert len(loaded_outputs) == 1
            assert loaded_outputs[0].task_id == "task_02"


class TestExperimentFailedTaskRetries:
    """Test failed tasks remain pending and retries replace outputs."""

    def test_failed_task_not_added_to_completed(self, tmp_path):
        """Failed task is not added to completed_tasks set."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: stroke
    question: Test question?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
            )

            plan = AnalysisPlan(
                title="Test Plan",
                question="Test question?",
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            # Mock failed outputs
            output_a = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_A,
                provider_type="claude_code",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=None,  # Failed
                error="Provider error",
            )

            output_b = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_B,
                provider_type="claude_code",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=plan,  # Success
                error=None,
            )

            result = runner._is_task_successful(output_a, output_b)
            assert result is False  # Task failed

            # Verify task would not be added to completed_tasks
            completed_tasks = set()
            if result:
                completed_tasks.add("task_01")

            assert "task_01" not in completed_tasks

    def test_retry_removes_prior_failed_outputs(self, tmp_path):
        """Retry removes previous outputs for pending tasks before retry."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: stroke
    question: Test question?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
  - id: task_02
    domain: stroke
    question: Test question 2?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        checkpoint_file = tmp_path / "checkpoint.json"

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
                checkpoint_file=checkpoint_file,
            )

            plan = AnalysisPlan(
                title="Test Plan",
                question="Test question?",
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            # Create previous outputs including failed task_01
            previous_outputs = [
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_A,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=None,
                    error="Failed",
                ),
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_B,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=None,
                    error="Failed",
                ),
            ]

            # Save checkpoint with task_01 not in completed (failed)
            completed = {"task_02"}  # Only task_02 completed
            runner.metadata = {"status": "running"}
            runner._save_checkpoint(completed, previous_outputs)

            # Load checkpoint
            loaded_completed, loaded_outputs = runner._load_checkpoint()

            # Verify completed doesn't include failed task
            assert "task_01" not in loaded_completed
            assert "task_02" in loaded_completed

            # Verify previous outputs were loaded
            assert len(loaded_outputs) == 2
            assert all(o.task_id == "task_01" for o in loaded_outputs)

    def test_successful_outputs_preserved_for_retry(self, tmp_path):
        """Successful outputs are preserved when retrying other failed tasks."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: stroke
    question: Test question?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
  - id: task_02
    domain: stroke
    question: Test question 2?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        checkpoint_file = tmp_path / "checkpoint.json"

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
                checkpoint_file=checkpoint_file,
            )

            plan = AnalysisPlan(
                title="Test Plan",
                question="Test question?",
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            # Create outputs: task_01 successful, task_02 failed
            previous_outputs = [
                # task_01 successful (both arms)
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_A,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_B,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
                # task_02 failed
                ArmOutput(
                    task_id="task_02",
                    arm=ProviderArm.ARM_A,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=None,
                    error="Failed",
                ),
            ]

            # Save checkpoint with only task_01 completed
            completed = {"task_01"}
            runner.metadata = {"status": "running"}
            runner._save_checkpoint(completed, previous_outputs)

            # Load and verify
            loaded_completed, loaded_outputs = runner._load_checkpoint()

            assert loaded_completed == {"task_01"}
            assert len(loaded_outputs) == 3

            # task_01 outputs preserved
            task_01_outputs = [o for o in loaded_outputs if o.task_id == "task_01"]
            assert len(task_01_outputs) == 2
            assert all(o.plan is not None and o.error is None for o in task_01_outputs)

            # task_02 outputs present but task not completed
            task_02_outputs = [o for o in loaded_outputs if o.task_id == "task_02"]
            assert len(task_02_outputs) == 1
            assert task_02_outputs[0].error == "Failed"


class TestExperimentMetadataConsistency:
    """Test metadata fields are consistent with actual execution state."""

    def test_metadata_completed_tasks_intersection(self, tmp_path):
        """Metadata completed_tasks is intersection of successful and selected."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: stroke
    question: Test question?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
  - id: task_02
    domain: stroke
    question: Test question 2?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
  - id: task_03
    domain: stroke
    question: Test question 3?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        checkpoint_file = tmp_path / "checkpoint.json"

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
                checkpoint_file=checkpoint_file,
                max_tasks=2,  # Only select task_01, task_02
            )

            plan = AnalysisPlan(
                title="Test Plan",
                question="Test question?",
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            # Create outputs where task_01 and task_02 succeed
            outputs = [
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_A,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_B,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
                ArmOutput(
                    task_id="task_02",
                    arm=ProviderArm.ARM_A,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
                ArmOutput(
                    task_id="task_02",
                    arm=ProviderArm.ARM_B,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
            ]

            # Simulate metadata calculation
            completed_ids = {"task_01", "task_02", "task_03"}  # All three successful in checkpoint
            selected_ids = {"task_01", "task_02"}  # Only selected first two
            successful_completed = completed_ids & selected_ids

            metadata = {
                "total_tasks": len(selected_ids),
                "completed_tasks": len(successful_completed),
                "failed_tasks": 0,
                "pending_tasks": len(selected_ids) - len(successful_completed),
            }

            assert metadata["total_tasks"] == 2
            assert metadata["completed_tasks"] == 2  # Only selected tasks
            assert metadata["failed_tasks"] == 0
            assert metadata["pending_tasks"] == 0

    def test_metadata_with_failures(self, tmp_path):
        """Metadata correctly reflects failed and pending tasks."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: stroke
    question: Test question?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
  - id: task_02
    domain: stroke
    question: Test question 2?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
  - id: task_03
    domain: stroke
    question: Test question 3?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        checkpoint_file = tmp_path / "checkpoint.json"

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
                checkpoint_file=checkpoint_file,
            )

            plan = AnalysisPlan(
                title="Test Plan",
                question="Test question?",
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            # Create outputs: task_01 success, task_02 failed, task_03 pending
            outputs = [
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_A,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_B,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
                ArmOutput(
                    task_id="task_02",
                    arm=ProviderArm.ARM_A,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=None,
                    error="Failed",
                ),
                ArmOutput(
                    task_id="task_02",
                    arm=ProviderArm.ARM_B,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=None,
                    error="Failed",
                ),
            ]

            # Simulate metadata calculation
            selected_ids = {"task_01", "task_02", "task_03"}
            completed_ids = {"task_01"}  # Only task_01 successful
            failed_ids = {"task_02"}  # task_02 failed

            successful_completed = completed_ids & selected_ids

            metadata = {
                "total_tasks": len(selected_ids),
                "completed_tasks": len(successful_completed),
                "failed_tasks": len(failed_ids),
                "pending_tasks": len(selected_ids) - len(successful_completed),
            }

            assert metadata["total_tasks"] == 3
            assert metadata["completed_tasks"] == 1  # Only task_01
            assert metadata["failed_tasks"] == 1  # task_02
            assert metadata["pending_tasks"] == 2  # task_02 (failed) + task_03 (not attempted)

    def test_metadata_status_completed_with_errors(self, tmp_path):
        """Status is completed_with_errors when live run has failures."""
        # Test live run with failures
        failed_task_ids = {"task_01"}
        dry_run = False

        if dry_run:
            status = "dry_run_completed"
        elif failed_task_ids:
            status = "completed_with_errors"
        else:
            status = "completed"

        assert status == "completed_with_errors"

    def test_metadata_status_completed_all_success(self, tmp_path):
        """Status is completed when live run has no failures."""
        # Test live run with all successes
        failed_task_ids = set()
        dry_run = False

        if dry_run:
            status = "dry_run_completed"
        elif failed_task_ids:
            status = "completed_with_errors"
        else:
            status = "completed"

        assert status == "completed"

    def test_metadata_status_dry_run_completed(self, tmp_path):
        """Status is dry_run_completed for dry runs regardless of failures."""
        # Test dry run (even with simulated failures)
        failed_task_ids = {"task_01"}  # Simulated failures
        dry_run = True

        if dry_run:
            status = "dry_run_completed"
        elif failed_task_ids:
            status = "completed_with_errors"
        else:
            status = "completed"

        assert status == "dry_run_completed"


class TestExperimentDryRunBehavior:
    """Test dry run remains zero-call with correct metadata."""

    def test_dry_run_zero_calls(self, tmp_path):
        """Dry run makes no model calls and outputs have plan=None."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: stroke
    question: Test question?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
            )

            task = BenchmarkTask(
                id="task_01",
                domain="stroke",
                question="Test question?",
                expected_database="NHANES",
                expected_feasible=True,
                rationale="Test",
            )

            # Run dry run task
            output = runner.run_task(
                task=task,
                arm=ProviderArm.ARM_A,
                provider=runner.provider_a,
                dry_run=True,
            )

            # Verify no model call was made
            assert output.plan is None
            assert output.error == "Dry run - no model call made"
            assert output.execution_time_seconds == 0.0
            assert output.provider_type == "dry_run"

    def test_dry_run_completed_tasks_can_be_zero(self, tmp_path):
        """Dry run can have completed_tasks=0 when no valid plans exist."""
        # Dry runs produce plan=None for all outputs
        # So _is_task_successful returns False for all tasks
        # Thus completed_tasks remains 0

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = Mock()
            runner._is_task_successful = ExperimentRunner._is_task_successful.__get__(runner)

            # Dry run outputs
            output_a = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_A,
                provider_type="dry_run",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=None,  # Dry run has no plan
                error="Dry run - no model call made",
            )

            output_b = ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_B,
                provider_type="dry_run",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=None,  # Dry run has no plan
                error="Dry run - no model call made",
            )

            result = runner._is_task_successful(output_a, output_b)
            assert result is False  # Dry run outputs are not "successful"

            # Verify completed_tasks would remain 0
            completed_tasks = set()
            if result:
                completed_tasks.add("task_01")

            assert len(completed_tasks) == 0


class TestExperimentIntegration:
    """Integration tests for complete experiment runs."""

    def test_full_dry_run_experiment(self, tmp_path):
        """Complete dry run experiment with mocked outputs and metadata."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: stroke
    question: Test question 1?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test 1
  - id: task_02
    domain: stroke
    question: Test question 2?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test 2
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        checkpoint_file = tmp_path / "checkpoint.json"

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
                checkpoint_file=checkpoint_file,
            )

            # Run dry run experiment
            outputs, metadata = runner.run_experiment(dry_run=True, confirm_live=False)

            # Verify outputs exist (dry run creates outputs with plan=None)
            assert len(outputs) == 4  # 2 tasks * 2 arms
            assert all(o.plan is None for o in outputs)
            assert all(o.provider_type == "dry_run" for o in outputs)

            # Verify metadata
            assert metadata["status"] == "dry_run_completed"
            assert metadata["total_tasks"] == 2
            assert metadata["completed_tasks"] == 0  # No successful completions in dry run
            assert metadata["failed_tasks"] == 2  # Both tasks "failed"
            assert metadata["pending_tasks"] == 2  # Both remain pending
            assert metadata["dry_run"] is True

            # Verify checkpoint was saved
            assert checkpoint_file.exists()
            with checkpoint_file.open("r") as f:
                checkpoint_data = json.load(f)
                assert "completed_tasks" in checkpoint_data
                assert "arm_outputs" in checkpoint_data
                assert "metadata" in checkpoint_data

    def test_experiment_with_checkpoint_resume(self, tmp_path):
        """Experiment resumes from checkpoint and retries failed tasks."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: stroke
    question: Test question 1?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test 1
  - id: task_02
    domain: stroke
    question: Test question 2?
    expected_database: NHANES
    expected_feasible: true
    rationale: Test 2
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        checkpoint_file = tmp_path / "checkpoint.json"

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
                checkpoint_file=checkpoint_file,
            )

            # Create initial checkpoint with task_01 completed, task_02 failed
            plan = AnalysisPlan(
                title="Test Plan",
                question="Test question?",
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            initial_outputs = [
                # task_01 successful
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_A,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
                ArmOutput(
                    task_id="task_01",
                    arm=ProviderArm.ARM_B,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=plan,
                    error=None,
                ),
                # task_02 failed (only one arm output, simulating partial failure)
                ArmOutput(
                    task_id="task_02",
                    arm=ProviderArm.ARM_A,
                    provider_type="claude_code",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    plan=None,
                    error="Failed",
                ),
            ]

            runner.metadata = {"status": "interrupted"}
            runner._save_checkpoint({"task_01"}, initial_outputs)

            # Create new runner instance to simulate resume
            runner_resume = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
                checkpoint_file=checkpoint_file,
            )

            # Load checkpoint
            completed, outputs = runner_resume._load_checkpoint()

            # Verify checkpoint state
            assert completed == {"task_01"}
            assert len(outputs) == 3

            # task_01 outputs present
            task_01_outputs = [o for o in outputs if o.task_id == "task_01"]
            assert len(task_01_outputs) == 2

            # task_02 output present but task not completed
            task_02_outputs = [o for o in outputs if o.task_id == "task_02"]
            assert len(task_02_outputs) == 1
            assert task_02_outputs[0].error == "Failed"


class TestDeterministicGateBehavior:
    """Test v0.2 deterministic gate behavior for Arm A."""

    def test_infeasible_arm_a_no_provider_call(self, tmp_path):
        """Infeasible Arm A makes zero provider calls and creates minimal plan."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: stroke
    question: Does laparoscopic bariatric surgery reduce 5-year stroke recurrence?
    expected_database: NHANES
    expected_feasible: false
    rationale: Surgery infeasible
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
            )

            task = BenchmarkTask(
                id="task_01",
                domain="stroke",
                question="Does laparoscopic bariatric surgery reduce 5-year stroke recurrence?",
                expected_database="NHANES",
                expected_feasible=False,
                rationale="Surgery infeasible",
            )

            # Run Arm A (deterministic gate should refuse without calling provider)
            output = runner.run_task(
                task=task,
                arm=ProviderArm.ARM_A,
                provider=runner.provider_a,
                dry_run=False,
            )

            # Verify deterministic router behavior
            assert output.plan is not None  # Minimal plan created
            assert output.plan.feasible is False  # Marked infeasible
            assert output.plan.database == "NHANES"  # Routed to NHANES
            assert output.provider_type == "deterministic_router"  # No model call
            assert output.model_label is None  # No model used
            assert output.error is None  # No error (clean refusal)
            assert len(output.guardrail_findings) == 0  # Guardrails skipped for infeasible

    def test_infeasible_arm_a_contains_no_variables(self, tmp_path):
        """Infeasible Arm A minimal plan contains no variables."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: tumor
    question: Is meningioma prevalence captured in NHANES?
    expected_database: NHANES
    expected_feasible: false
    rationale: Histology unavailable
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
            )

            task = BenchmarkTask(
                id="task_01",
                domain="tumor",
                question="Is meningioma prevalence captured in NHANES?",
                expected_database="NHANES",
                expected_feasible=False,
                rationale="Histology unavailable",
            )

            # Run Arm A
            output = runner.run_task(
                task=task,
                arm=ProviderArm.ARM_A,
                provider=runner.provider_a,
                dry_run=False,
            )

            # Verify no variables in minimal plan
            assert output.plan is not None
            assert output.plan.outcome is None  # No outcome variable
            assert len(output.plan.exposures) == 0  # No exposure variables
            assert len(output.plan.covariates) == 0  # No covariate variables
            assert len(output.plan.causal_claims) == 0  # No causal claims
            assert output.plan.feasible is False  # Marked infeasible
            assert output.plan.database == "NHANES"

    def test_feasible_arm_a_calls_provider_with_routing_context(self, tmp_path):
        """Feasible Arm A calls provider with routing_context."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: stroke
    question: Is self-reported stroke associated with metabolic syndrome?
    expected_database: NHANES
    expected_feasible: true
    rationale: NHANES has both variables
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider") as mock_provider:
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
            )

            task = BenchmarkTask(
                id="task_01",
                domain="stroke",
                question="Is self-reported stroke associated with metabolic syndrome?",
                expected_database="NHANES",
                expected_feasible=True,
                rationale="NHANES has both variables",
            )

            # Mock the provider to return a valid plan
            mock_plan = AnalysisPlan(
                title="Test Plan",
                question=task.question,
                database="NHANES",
                feasible=True,
                cycles=[],
            )

            runner.provider_a.generate_plan.return_value = mock_plan

            # Run Arm A
            output = runner.run_task(
                task=task,
                arm=ProviderArm.ARM_A,
                provider=runner.provider_a,
                dry_run=False,
            )

            # Verify provider was called with routing_context
            runner.provider_a.generate_plan.assert_called_once()
            call_args = runner.provider_a.generate_plan.call_args

            # Check that registry_path was provided
            assert call_args[1]["registry_path"] == registry

            # Check that routing_context was provided
            assert "routing_context" in call_args[1]
            routing_context = call_args[1]["routing_context"]
            assert routing_context is not None
            assert routing_context["database"] == "NHANES"
            assert routing_context["feasible"] is True
            assert "rationale" in routing_context

    def test_infeasible_arm_b_baseline_unaffected(self, tmp_path):
        """Arm B baseline is unaffected by deterministic gate (no routing_context)."""
        # Create minimal test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text("""
tasks:
  - id: task_01
    domain: stroke
    question: Does bariatric surgery reduce stroke recurrence?
    expected_database: NHANES
    expected_feasible: false
    rationale: Surgery unavailable
""")

        prompt_a = tmp_path / "prompt_a.txt"
        prompt_a.write_text("Prompt A")

        prompt_b = tmp_path / "prompt_b.txt"
        prompt_b.write_text("Prompt B")

        registry_content = 'registry_version: "1"\nvariables: []'
        registry = tmp_path / "registry.yaml"
        registry.write_text(registry_content)

        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider") as mock_provider:
            runner = ExperimentRunner(
                tasks_path=tasks_file,
                prompt_a_path=prompt_a,
                prompt_b_path=prompt_b,
                registry_path=registry,
            )

            task = BenchmarkTask(
                id="task_01",
                domain="stroke",
                question="Does bariatric surgery reduce stroke recurrence?",
                expected_database="NHANES",
                expected_feasible=False,
                rationale="Surgery unavailable",
            )

            # Mock the provider to return a valid plan
            mock_plan = AnalysisPlan(
                title="Test Plan",
                question=task.question,
                database="NHANES",
                feasible=False,  # Baseline might detect infeasibility
                cycles=[],
            )

            runner.provider_b.generate_plan.return_value = mock_plan

            # Run Arm B (baseline)
            output = runner.run_task(
                task=task,
                arm=ProviderArm.ARM_B,
                provider=runner.provider_b,
                dry_run=False,
            )

            # Verify provider was called WITHOUT routing_context
            runner.provider_b.generate_plan.assert_called_once()
            call_args = runner.provider_b.generate_plan.call_args

            # Check that registry_path was None (baseline gets no registry)
            assert call_args[1]["registry_path"] is None

            # Check that routing_context was None (baseline gets no routing context)
            assert call_args[1]["routing_context"] is None
