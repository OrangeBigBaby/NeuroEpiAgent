"""
Test suite for ablation study framework.

Tests for:
- Arm configuration definitions
- Dry-run mode functionality
- Checkpoint/resume operations
- Concurrency safeguards
- Model call tracking
- Report generation

Note: All tests use dry-run mode and do NOT call live LLMs.
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime

from neurosurg_epi_agent.ablation import (
    AblationArm,
    ArmConfiguration,
    ExperimentMetadata,
    ArmResult,
    AblationRunner,
    ABLATION_ARMS,
    create_experiment_id,
    create_runner
)


class TestAblationArmDefinitions:
    """Test ablation arm configuration definitions."""

    def test_all_arms_defined(self):
        """Test that all required arms are defined."""
        required_arms = {
            AblationArm.FULL_GATE,
            AblationArm.NO_ROUTER,
            AblationArm.NO_REGISTRY,
            AblationArm.NO_GUARDRAILS,
            AblationArm.UNCONSTRAINED_BASELINE
        }

        assert required_arms.issubset(ABLATION_ARMS.keys())

    def test_full_gate_configuration(self):
        """Test full gate arm has all components enabled."""
        config = ABLATION_ARMS[AblationArm.FULL_GATE]

        assert config.components['router'] is True
        assert config.components['registry'] is True
        assert config.components['guardrails'] is True
        assert config.components['planner'] is True

    def test_no_router_configuration(self):
        """Test no_router arm has router disabled."""
        config = ABLATION_ARMS[AblationArm.NO_ROUTER]

        assert config.components['router'] is False
        assert config.components['registry'] is True
        assert config.components['guardrails'] is True
        assert config.components['planner'] is True

    def test_no_registry_configuration(self):
        """Test no_registry arm has registry disabled."""
        config = ABLATION_ARMS[AblationArm.NO_REGISTRY]

        assert config.components['router'] is True
        assert config.components['registry'] is False
        assert config.components['guardrails'] is True
        assert config.components['planner'] is True

    def test_no_guardrails_configuration(self):
        """Test no_guardrails arm has guardrails disabled."""
        config = ABLATION_ARMS[AblationArm.NO_GUARDRAILS]

        assert config.components['router'] is True
        assert config.components['registry'] is True
        assert config.components['guardrails'] is False
        assert config.components['planner'] is True

    def test_unconstrained_baseline_configuration(self):
        """Test unconstrained baseline has all components disabled."""
        config = ABLATION_ARMS[AblationArm.UNCONSTRAINED_BASELINE]

        assert config.components['router'] is False
        assert config.components['registry'] is False
        assert config.components['guardrails'] is False
        assert config.components['planner'] is False

    def test_all_arms_expect_one_model_call(self):
        """Test that all arms expect exactly 1 model call per task."""
        for arm, config in ABLATION_ARMS.items():
            assert config.expected_model_calls == 1, f"Arm {arm} expects {config.expected_model_calls} calls, expected 1"


class TestExperimentIdGeneration:
    """Test experiment ID generation."""

    def test_experiment_id_unique(self):
        """Test that experiment IDs are unique."""
        id1 = create_experiment_id()
        id2 = create_experiment_id()

        assert id1 != id2

    def test_experiment_id_format(self):
        """Test that experiment ID follows expected format."""
        exp_id = create_experiment_id()

        assert exp_id.startswith("ablation_")
        assert "_" in exp_id


class TestAblationRunnerDryRun:
    """Test ablation runner in dry-run mode."""

    def test_dry_run_initialization(self):
        """Test dry-run runner initialization."""
        runner = create_runner(
            arms=[AblationArm.FULL_GATE],
            task_source="test.yaml",
            dry_run=True
        )

        assert runner.metadata.dry_run is True
        assert len(runner.metadata.arms) == 1

    def test_dry_run_single_task(self, capsys):
        """Test dry-run execution of single task."""
        runner = create_runner(
            arms=[AblationArm.FULL_GATE],
            task_source="test.yaml",
            dry_run=True
        )

        task_data = {
            'id': 'test_task',
            'question': 'Test question',
            'expected_database': 'NHANES',
            'expected_feasible': True
        }

        runner.run_task('test_task', task_data)

        # Check result was stored
        assert 'test_task' in runner.results
        assert AblationArm.FULL_GATE in runner.results['test_task']

        result = runner.results['test_task'][AblationArm.FULL_GATE]
        assert result.success is True
        assert result.output is not None
        assert result.output.get('dry_run') is True

        # Check dry-run output was printed
        captured = capsys.readouterr()
        assert '[DRY-RUN]' in captured.out
        assert 'test_task' in captured.out

    def test_dry_run_multiple_arms(self, capsys):
        """Test dry-run execution with multiple arms."""
        arms = [AblationArm.FULL_GATE, AblationArm.NO_ROUTER]
        runner = create_runner(
            arms=arms,
            task_source="test.yaml",
            dry_run=True
        )

        task_data = {
            'id': 'test_task',
            'question': 'Test question',
            'expected_database': 'NHANES',
            'expected_feasible': True
        }

        runner.run_task('test_task', task_data)

        # Check results for both arms
        assert 'test_task' in runner.results
        for arm in arms:
            assert arm in runner.results['test_task']
            assert runner.results['test_task'][arm].success is True

    def test_dry_run_all_arms(self):
        """Test dry-run execution with all defined arms."""
        arms = list(ABLATION_ARMS.keys())
        runner = create_runner(
            arms=arms,
            task_source="test.yaml",
            dry_run=True
        )

        task_data = {
            'id': 'test_task',
            'question': 'Test question',
            'expected_database': 'NHANES',
            'expected_feasible': True
        }

        runner.run_task('test_task', task_data)

        # Check results for all arms
        for arm in arms:
            assert arm in runner.results['test_task']


class TestCheckpointResume:
    """Test checkpoint and resume functionality."""

    def test_checkpoint_creation(self):
        """Test that checkpoint files are created."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            checkpoint_path = f.name

        try:
            runner = create_runner(
                arms=[AblationArm.FULL_GATE],
                task_source="test.yaml",
                dry_run=True,
                checkpoint_file=checkpoint_path
            )

            task_data = {
                'id': 'test_task',
                'question': 'Test question',
                'expected_database': 'NHANES',
                'expected_feasible': True
            }

            runner.run_task('test_task', task_data)

            # Check checkpoint file was created
            assert Path(checkpoint_path).exists()

            # Load and verify checkpoint content
            with open(checkpoint_path) as f:
                checkpoint_data = json.load(f)

            assert 'experiment_metadata' in checkpoint_data
            assert 'completed_tasks' in checkpoint_data
            assert 'test_task' in checkpoint_data['completed_tasks']

        finally:
            Path(checkpoint_path).unlink(missing_ok=True)

    def test_checkpoint_resume(self):
        """Test resuming from checkpoint."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            checkpoint_path = f.name

        try:
            # Create initial checkpoint
            runner1 = create_runner(
                arms=[AblationArm.FULL_GATE, AblationArm.NO_ROUTER],
                task_source="test.yaml",
                dry_run=True,
                checkpoint_file=checkpoint_path,
                resume=False
            )

            task_data = {
                'id': 'task1',
                'question': 'Question 1',
                'expected_database': 'NHANES',
                'expected_feasible': True
            }

            runner1.run_task('task1', task_data)

            # Resume from checkpoint
            runner2 = create_runner(
                arms=[AblationArm.FULL_GATE, AblationArm.NO_ROUTER],
                task_source="test.yaml",
                dry_run=True,
                checkpoint_file=checkpoint_path,
                resume=True,
                experiment_id=runner1.metadata.experiment_id
            )

            # Check that previous results were loaded
            assert 'task1' in runner2.results
            assert AblationArm.FULL_GATE in runner2.results['task1']

        finally:
            Path(checkpoint_path).unlink(missing_ok=True)


class TestConcurrencySafeguards:
    """Test concurrency validation safeguards."""

    def test_concurrent_validation_pass(self):
        """Test validation passes for concurrent execution."""
        runner = create_runner(
            arms=[AblationArm.FULL_GATE, AblationArm.NO_ROUTER],
            task_source="test.yaml",
            dry_run=True
        )

        # Run tasks on all arms
        for i in range(3):
            task_data = {
                'id': f'task_{i}',
                'question': f'Question {i}',
                'expected_database': 'NHANES',
                'expected_feasible': True
            }
            runner.run_task(f'task_{i}', task_data)

        validation = runner.validate_concurrency()

        assert validation['is_concurrent'] is True
        assert len(validation['issues']) == 0

    def test_concurrent_validation_fail_incomplete_arm(self):
        """Test validation fails when one arm is incomplete."""
        runner = create_runner(
            arms=[AblationArm.FULL_GATE, AblationArm.NO_ROUTER],
            task_source="test.yaml",
            dry_run=True
        )

        # Run only one arm
        task_data = {
            'id': 'task1',
            'question': 'Question 1',
            'expected_database': 'NHANES',
            'expected_feasible': True
        }

        # Only run FULL_GATE arm
        runner.run_task('task1', task_data, arms=[AblationArm.FULL_GATE])

        validation = runner.validate_concurrency()

        assert validation['is_concurrent'] is False
        assert len(validation['issues']) > 0
        assert any('missing results' in issue.lower() for issue in validation['issues'])

    def test_concurrent_validation_fail_mismatched_counts(self):
        """Test validation fails with mismatched task counts."""
        runner = create_runner(
            arms=[AblationArm.FULL_GATE, AblationArm.NO_ROUTER],
            task_source="test.yaml",
            dry_run=True
        )

        # Manually create mismatched results
        runner.results['task1'] = {
            AblationArm.FULL_GATE: ArmResult(
                task_id='task1',
                arm_id=AblationArm.FULL_GATE,
                success=True,
                duration_seconds=1.0,
                model_call_count=1
            )
        }
        # Missing NO_ROUTER result

        validation = runner.validate_concurrency()

        assert validation['is_concurrent'] is False
        assert len(validation['issues']) > 0


class TestModelCallTracking:
    """Test model call tracking and reporting."""

    def test_model_call_summary(self):
        """Test model call summary generation."""
        arms = [AblationArm.FULL_GATE, AblationArm.NO_ROUTER]
        runner = create_runner(
            arms=arms,
            task_source="test.yaml",
            dry_run=True
        )

        # Run multiple tasks
        for i in range(5):
            task_data = {
                'id': f'task_{i}',
                'question': f'Question {i}',
                'expected_database': 'NHANES',
                'expected_feasible': True
            }
            runner.run_task(f'task_{i}', task_data)

        summary = runner.get_model_call_summary()

        # Each arm should have 5 calls (1 per task)
        for arm in arms:
            assert summary[arm.value] == 5

    def test_model_call_count_in_results(self):
        """Test that model call counts are recorded in results."""
        runner = create_runner(
            arms=[AblationArm.FULL_GATE],
            task_source="test.yaml",
            dry_run=True
        )

        task_data = {
            'id': 'task1',
            'question': 'Test question',
            'expected_database': 'NHANES',
            'expected_feasible': True
        }

        runner.run_task('task1', task_data)

        result = runner.results['task1'][AblationArm.FULL_GATE]
        assert result.model_call_count == 1


class TestReportGeneration:
    """Test experiment report generation."""

    def test_report_structure(self):
        """Test report has required fields."""
        runner = create_runner(
            arms=[AblationArm.FULL_GATE],
            task_source="test.yaml",
            dry_run=True
        )

        task_data = {
            'id': 'task1',
            'question': 'Test question',
            'expected_database': 'NHANES',
            'expected_feasible': True
        }

        runner.run_task('task1', task_data)
        report = runner.generate_report()

        # Check required sections
        assert 'experiment_metadata' in report
        assert 'validation' in report
        assert 'model_calls' in report
        assert 'arm_results' in report
        assert 'warnings' in report

    def test_report_metadata(self):
        """Test report metadata accuracy."""
        runner = create_runner(
            arms=[AblationArm.FULL_GATE],
            task_source="test.yaml",
            dry_run=True
        )

        report = runner.generate_report()

        assert report['experiment_metadata']['dry_run'] is True
        assert 'experiment_id' in report['experiment_metadata']

    def test_report_warnings_incomplete(self):
        """Test report includes warnings for incomplete arms."""
        runner = create_runner(
            arms=[AblationArm.FULL_GATE, AblationArm.NO_ROUTER],
            task_source="test.yaml",
            dry_run=True
        )

        # Only run one arm
        task_data = {
            'id': 'task1',
            'question': 'Test question',
            'expected_database': 'NHANES',
            'expected_feasible': True
        }

        runner.run_task('task1', task_data, arms=[AblationArm.FULL_GATE])

        report = runner.generate_report()

        # Should have warning about incomplete arm
        assert len(report['warnings']) > 0
        assert any('incomplete' in warning.lower() for warning in report['warnings'])


class TestProductionModeSafety:
    """Test safety measures for production mode."""

    def test_production_mode_not_implemented(self):
        """Test that production mode raises NotImplementedError."""
        runner = create_runner(
            arms=[AblationArm.FULL_GATE],
            task_source="test.yaml",
            dry_run=False  # Production mode
        )

        task_data = {
            'id': 'task1',
            'question': 'Test question',
            'expected_database': 'NHANES',
            'expected_feasible': True
        }

        with pytest.raises(NotImplementedError, match="Production mode not yet implemented"):
            runner.run_task('task1', task_data)


class TestComponentCombinations:
    """Test specific component combinations for ablation logic."""

    def test_single_component_ablations(self):
        """Test that single-component ablations disable only target component."""
        # NO_ROUTER should only disable router
        no_router = ABLATION_ARMS[AblationArm.NO_ROUTER]
        assert no_router.components['router'] is False
        assert no_router.components['registry'] is True
        assert no_router.components['guardrails'] is True

        # NO_REGISTRY should only disable registry
        no_registry = ABLATION_ARMS[AblationArm.NO_REGISTRY]
        assert no_registry.components['router'] is True
        assert no_registry.components['registry'] is False
        assert no_registry.components['guardrails'] is True

        # NO_GUARDRAILS should only disable guardrails
        no_guard = ABLATION_ARMS[AblationArm.NO_GUARDRAILS]
        assert no_guard.components['router'] is True
        assert no_guard.components['registry'] is True
        assert no_guard.components['guardrails'] is False