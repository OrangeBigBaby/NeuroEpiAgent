"""Tests for evaluation module: scoring, hashing, and evaluation runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from neurosurg_epi_agent.evaluation import (
    ArmOutput,
    BenchmarkTask,
    EvaluationRun,
    MetricType,
    ProviderArm,
    _sha256_file,
    compute_summary_scores,
    create_evaluation_run,
    score_task,
)
from neurosurg_epi_agent.schemas import AnalysisPlan


class TestHashing:
    """Test SHA256 hashing utilities."""

    def test_sha256_hashing(self, tmp_path):
        """SHA256 hash computation is correct and deterministic."""
        test_file = tmp_path / "test.txt"
        with test_file.open("w") as f:
            f.write("test content")

        hash1 = _sha256_file(test_file)
        hash2 = _sha256_file(test_file)

        # Same file should produce same hash
        assert hash1 == hash2

        # Known content should produce known hash
        # SHA256 of "test content" (with newline as f.write adds it)
        expected = "6ae8a75555209fd6c44157c0aed8016e763ff435a19cf186f76863140143ff72"
        assert hash1 == expected

    def test_sha256_different_files(self, tmp_path):
        """SHA256 hash differs for different content."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        with file1.open("w") as f:
            f.write("content one")
        with file2.open("w") as f:
            f.write("content two")

        hash1 = _sha256_file(file1)
        hash2 = _sha256_file(file2)

        assert hash1 != hash2


class TestScoringMetrics:
    """Test individual scoring metrics."""

    def test_score_database_routing_correct(self):
        """Database routing score passes for correct routing."""
        task = BenchmarkTask(
            id="test_01",
            domain="stroke",
            question="Stroke and metabolic syndrome?",
            expected_database="NHANES",
            expected_feasible=True,
            rationale="Feasible analysis",
        )

        plan = AnalysisPlan(
            title="Stroke Plan",
            question="Stroke and metabolic syndrome?",
            database="NHANES",
            feasible=True,
            cycles=["G", "H", "I", "J"],
        )

        arm_output = ArmOutput(
            task_id="test_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=plan,
        )

        scores = score_task(task, arm_output, allowed_variable_codes=set())

        routing_score = next(s for s in scores if s.metric == MetricType.DATABASE_ROUTING)
        assert routing_score.passed is True
        assert routing_score.score_value == 1.0

    def test_score_database_routing_incorrect(self):
        """Database routing score fails for incorrect routing."""
        task = BenchmarkTask(
            id="test_01",
            domain="stroke",
            question="Stroke and metabolic syndrome?",
            expected_database="NHANES",
            expected_feasible=True,
            rationale="Feasible analysis",
        )

        plan = AnalysisPlan(
            title="Stroke Plan",
            question="Stroke and metabolic syndrome?",
            database="GBD",  # Wrong database
            feasible=True,
            cycles=[],
        )

        arm_output = ArmOutput(
            task_id="test_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=plan,
        )

        scores = score_task(task, arm_output, allowed_variable_codes=set())

        routing_score = next(s for s in scores if s.metric == MetricType.DATABASE_ROUTING)
        assert routing_score.passed is False
        assert routing_score.score_value == 0.0

    def test_score_feasibility_correct(self):
        """Feasibility score passes for correct assessment."""
        task = BenchmarkTask(
            id="test_01",
            domain="stroke",
            question="Feasible question?",
            expected_database="NHANES",
            expected_feasible=True,
            rationale="Feasible",
        )

        plan = AnalysisPlan(
            title="Plan",
            question="Feasible question?",
            database="NHANES",
            feasible=True,
            cycles=[],
        )

        arm_output = ArmOutput(
            task_id="test_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=plan,
        )

        scores = score_task(task, arm_output, allowed_variable_codes=set())

        feasibility_score = next(s for s in scores if s.metric == MetricType.FEASIBILITY)
        assert feasibility_score.passed is True
        assert feasibility_score.score_value == 1.0

    def test_score_hard_error_free(self):
        """Hard-error-free score checks for provider errors."""
        task = BenchmarkTask(
            id="test_01",
            domain="stroke",
            question="Test?",
            expected_database="NHANES",
            expected_feasible=True,
            rationale="Test",
        )

        # Test with no error
        arm_output_ok = ArmOutput(
            task_id="test_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=AnalysisPlan(
                title="Plan",
                question="Test?",
                database="NHANES",
                feasible=True,
                cycles=[],
            ),
            error=None,
        )

        scores_ok = score_task(task, arm_output_ok, allowed_variable_codes=set())
        error_score_ok = next(s for s in scores_ok if s.metric == MetricType.HARD_ERROR_FREE)
        assert error_score_ok.passed is True

        # Test with error
        arm_output_err = ArmOutput(
            task_id="test_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=None,
            error="Provider crashed",
        )

        scores_err = score_task(task, arm_output_err, allowed_variable_codes=set())
        error_score_err = next(s for s in scores_err if s.metric == MetricType.HARD_ERROR_FREE)
        assert error_score_err.passed is False

    def test_score_hard_error_free_with_validation_errors(self):
        """Hard-error-free score incorporates validation errors."""
        task = BenchmarkTask(
            id="test_01",
            domain="stroke",
            question="Test?",
            expected_database="NHANES",
            expected_feasible=True,
            rationale="Test",
        )

        arm_output = ArmOutput(
            task_id="test_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=None,
            error=None,
            validation_errors=["Invalid variable code", "Missing required field"],
        )

        scores = score_task(task, arm_output, allowed_variable_codes=set())
        error_score = next(s for s in scores if s.metric == MetricType.HARD_ERROR_FREE)
        assert error_score.passed is False
        assert "Validation errors" in error_score.details

    def test_score_hard_error_free_with_guardrail_errors(self):
        """Hard-error-free score incorporates guardrail ERROR findings."""
        task = BenchmarkTask(
            id="test_01",
            domain="stroke",
            question="Test?",
            expected_database="NHANES",
            expected_feasible=True,
            rationale="Test",
        )

        arm_output = ArmOutput(
            task_id="test_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=AnalysisPlan(
                title="Plan",
                question="Test?",
                database="NHANES",
                feasible=True,
                cycles=[],
            ),
            error=None,
            validation_errors=[],
            guardrail_findings=[
                {"severity": "error", "code": "CAUSAL_LANGUAGE", "message": "Causal claim detected"},
                {"severity": "warning", "code": "OTHER", "message": "Warning message"},
            ],
        )

        scores = score_task(task, arm_output, allowed_variable_codes=set())
        error_score = next(s for s in scores if s.metric == MetricType.HARD_ERROR_FREE)
        assert error_score.passed is False
        assert "Guardrail errors" in error_score.details

    def test_correct_refusal_provider_error_and_missing_plan_fail_when_infeasible(self):
        """Regression: a provider/validation failure (plan is None) is NOT an
        explained refusal and must never receive credit on correct_refusal,
        even when the task is expected infeasible. Only a successfully parsed,
        error-free plan with feasible=False passes for an infeasible task.
        """
        task = BenchmarkTask(
            id="infeas_01",
            domain="tumor",
            question="Infeasible question?",
            expected_database="NHANES",
            expected_feasible=False,
            rationale="Not feasible",
        )

        # Provider error + missing plan: the exact case the old logic credited.
        provider_failed = ArmOutput(
            task_id="infeas_01",
            arm=ProviderArm.ARM_A,
            provider_type="claude_code",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=None,
            error="provider timed out",
        )
        score = next(
            s for s in score_task(task, provider_failed, allowed_variable_codes=set())
            if s.metric == MetricType.CORRECT_REFUSAL
        )
        assert score.passed is False
        assert score.score_value == 0.0

        # Missing plan with no explicit error must also fail (not credit).
        missing_plan = ArmOutput(
            task_id="infeas_01",
            arm=ProviderArm.ARM_A,
            provider_type="claude_code",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=None,
            error=None,
        )
        score = next(
            s for s in score_task(task, missing_plan, allowed_variable_codes=set())
            if s.metric == MetricType.CORRECT_REFUSAL
        )
        assert score.passed is False

    def test_correct_refusal_validation_errors_fail_even_if_feasible_matches(self):
        """Validation errors present -> not a clean parsed plan -> must fail."""
        task = BenchmarkTask(
            id="infeas_01",
            domain="tumor",
            question="Infeasible question?",
            expected_database="NHANES",
            expected_feasible=False,
            rationale="Not feasible",
        )
        plan = AnalysisPlan(
            title="Refusal",
            question="Infeasible?",
            database="NHANES",
            feasible=False,
            cycles=[],
        )
        with_validation_errors = ArmOutput(
            task_id="infeas_01",
            arm=ProviderArm.ARM_A,
            provider_type="claude_code",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=plan,
            error=None,
            validation_errors=["bad field"],
        )
        score = next(
            s for s in score_task(task, with_validation_errors, allowed_variable_codes=set())
            if s.metric == MetricType.CORRECT_REFUSAL
        )
        assert score.passed is False

    def test_correct_refusal_valid_infeasible_plan_passes(self):
        """An explicit, error-free, parsed plan with feasible=False passes for
        an expected-infeasible task; a feasible=True plan for the same task fails."""
        task = BenchmarkTask(
            id="infeas_01",
            domain="tumor",
            question="Infeasible question?",
            expected_database="NHANES",
            expected_feasible=False,
            rationale="Not feasible",
        )

        plan_refused = AnalysisPlan(
            title="Refusal",
            question="Infeasible?",
            database="NHANES",
            feasible=False,
            cycles=[],
        )
        refused_output = ArmOutput(
            task_id="infeas_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=plan_refused,
        )
        score = next(
            s for s in score_task(task, refused_output, allowed_variable_codes=set())
            if s.metric == MetricType.CORRECT_REFUSAL
        )
        assert score.passed is True
        assert score.score_value == 1.0

        # Same task but the plan wrongly accepted it (feasible=True) -> fail.
        plan_accepted = plan_refused.model_copy(update={"feasible": True})
        accepted_output = refused_output.model_copy(update={"plan": plan_accepted})
        score = next(
            s for s in score_task(task, accepted_output, allowed_variable_codes=set())
            if s.metric == MetricType.CORRECT_REFUSAL
        )
        assert score.passed is False

    def test_correct_refusal_feasible_task_requires_parsed_feasible_plan(self):
        """Expected-feasible task: missing plan fails; feasible=True plan passes."""
        task = BenchmarkTask(
            id="feas_01",
            domain="stroke",
            question="Feasible question?",
            expected_database="NHANES",
            expected_feasible=True,
            rationale="Feasible",
        )
        missing = ArmOutput(
            task_id="feas_01",
            arm=ProviderArm.ARM_A,
            provider_type="claude_code",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=None,
            error=None,
        )
        score = next(
            s for s in score_task(task, missing, allowed_variable_codes=set())
            if s.metric == MetricType.CORRECT_REFUSAL
        )
        assert score.passed is False

        plan_ok = AnalysisPlan(
            title="P",
            question="Feasible?",
            database="NHANES",
            feasible=True,
            cycles=[],
        )
        ok_output = ArmOutput(
            task_id="feas_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=plan_ok,
        )
        score = next(
            s for s in score_task(task, ok_output, allowed_variable_codes=set())
            if s.metric == MetricType.CORRECT_REFUSAL
        )
        assert score.passed is True

    def test_score_correct_refusal(self):
        """Correct refusal score validates refusal behavior."""
        # Infeasible task should be refused
        task_infeasible = BenchmarkTask(
            id="test_01",
            domain="stroke",
            question="Infeasible question?",
            expected_database="NHANES",
            expected_feasible=False,
            rationale="Not feasible",
        )

        # Plan correctly marked as infeasible
        plan_refused = AnalysisPlan(
            title="Refusal",
            question="Infeasible?",
            database="NHANES",
            feasible=False,
            cycles=[],
        )

        arm_output_refused = ArmOutput(
            task_id="test_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=plan_refused,
        )

        scores_refused = score_task(task_infeasible, arm_output_refused, allowed_variable_codes=set())
        refusal_score = next(s for s in scores_refused if s.metric == MetricType.CORRECT_REFUSAL)
        assert refusal_score.passed is True

        # Feasible task incorrectly refused
        task_feasible = BenchmarkTask(
            id="test_02",
            domain="stroke",
            question="Feasible question?",
            expected_database="NHANES",
            expected_feasible=True,
            rationale="Feasible",
        )

        scores_wrong_refusal = score_task(task_feasible, arm_output_refused, allowed_variable_codes=set())
        refusal_score_wrong = next(s for s in scores_wrong_refusal if s.metric == MetricType.CORRECT_REFUSAL)
        assert refusal_score_wrong.passed is False

    def test_score_variable_codes(self):
        """Variable codes score checks against allowed registry set."""
        task = BenchmarkTask(
            id="test_01",
            domain="stroke",
            question="Test?",
            expected_database="NHANES",
            expected_feasible=True,
            rationale="Test",
        )

        # Plan with allowed codes
        plan_ok = AnalysisPlan(
            title="Plan",
            question="Test?",
            database="NHANES",
            feasible=True,
            cycles=[],
            outcome={
                "name": "age",
                "label": "Age",
                "source_variable": "RIDAGEYR",
                "source_module": "DEMO",
                "status": "verified",
                "nhanes_cycles": ["G"],
            },
        )

        arm_output_ok = ArmOutput(
            task_id="test_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=plan_ok,
        )

        scores_ok = score_task(task, arm_output_ok, allowed_variable_codes={"RIDAGEYR", "MCQ160F"})
        code_score_ok = next(s for s in scores_ok if s.metric == MetricType.VARIABLE_CODES)
        assert code_score_ok.passed is True

        # Plan with disallowed codes
        plan_bad = AnalysisPlan(
            title="Plan",
            question="Test?",
            database="NHANES",
            feasible=True,
            cycles=[],
            outcome={
                "name": "invented_var",
                "label": "Invented",
                "source_variable": "INVENTED123",
                "source_module": "MCQ",
                "status": "illustrative",  # Changed from needs_review to illustrative
                "nhanes_cycles": [],
            },
        )

        arm_output_bad = ArmOutput(
            task_id="test_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=plan_bad,
        )

        scores_bad = score_task(task, arm_output_bad, allowed_variable_codes={"RIDAGEYR", "MCQ160F"})
        code_score_bad = next(s for s in scores_bad if s.metric == MetricType.VARIABLE_CODES)
        assert code_score_bad.passed is False

    def test_score_manifest_reconstructability(self):
        """Manifest reconstructability score tests serialization."""
        task = BenchmarkTask(
            id="test_01",
            domain="stroke",
            question="Test?",
            expected_database="NHANES",
            expected_feasible=True,
            rationale="Test",
        )

        plan = AnalysisPlan(
            title="Plan",
            question="Test?",
            database="NHANES",
            feasible=True,
            cycles=[],
        )

        arm_output = ArmOutput(
            task_id="test_01",
            arm=ProviderArm.ARM_A,
            provider_type="neurosurg_epi_agent",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            plan=plan,
        )

        scores = score_task(task, arm_output, allowed_variable_codes=set())
        recon_score = next(s for s in scores if s.metric == MetricType.MANIFEST_RECONSTRUCTABILITY)
        assert recon_score.passed is True
        assert recon_score.score_value == 1.0


class TestEvaluationRun:
    """Test complete evaluation run creation."""

    def test_compute_summary_scores_per_arm(self):
        """Summary statistics are computed per-arm instead of pooled."""
        # Create per-arm score structure
        scores = {
            "arm_a": {
                "database_routing": [
                    type("Score", (), {"passed": True})(),
                    type("Score", (), {"passed": False})(),
                    type("Score", (), {"passed": True})(),
                ],
                "feasibility": [
                    type("Score", (), {"passed": True})(),
                    type("Score", (), {"passed": True})(),
                ],
            },
            "arm_b": {
                "database_routing": [
                    type("Score", (), {"passed": True})(),
                    type("Score", (), {"passed": True})(),
                ],
                "feasibility": [
                    type("Score", (), {"passed": False})(),
                ],
            },
        }

        summary = compute_summary_scores(scores)

        # Check per-arm structure
        assert "arm_a" in summary
        assert "arm_b" in summary

        # Arm A stats
        assert summary["arm_a"]["database_routing"]["passed"] == 2
        assert summary["arm_a"]["database_routing"]["total"] == 3
        assert summary["arm_a"]["feasibility"]["passed"] == 2
        assert summary["arm_a"]["feasibility"]["total"] == 2

        # Arm B stats (separate from A)
        assert summary["arm_b"]["database_routing"]["passed"] == 2
        assert summary["arm_b"]["database_routing"]["total"] == 2
        assert summary["arm_b"]["feasibility"]["passed"] == 0
        assert summary["arm_b"]["feasibility"]["total"] == 1

    def test_create_evaluation_run_per_arm_structure(self, tmp_path):
        """Complete evaluation run creates per-arm score structure."""
        # Create test files for hashing
        prompt_file = tmp_path / "prompt.txt"
        registry_file = tmp_path / "registry.yaml"
        task_file = tmp_path / "tasks.yaml"

        with prompt_file.open("w") as f:
            f.write("test prompt")
        with registry_file.open("w") as f:
            f.write("test registry")
        with task_file.open("w") as f:
            f.write("test tasks")

        # Create mock data
        tasks = [
            BenchmarkTask(
                id="task_01",
                domain="stroke",
                question="Test?",
                expected_database="NHANES",
                expected_feasible=True,
                rationale="Test",
            )
        ]

        arm_outputs = [
            ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_A,
                provider_type="neurosurg_epi_agent",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=AnalysisPlan(
                    title="Plan",
                    question="Test?",
                    database="NHANES",
                    feasible=True,
                    cycles=[],
                ),
            ),
            ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_B,
                provider_type="gpt-4_direct",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=AnalysisPlan(
                    title="Plan B",
                    question="Test?",
                    database="NHANES",
                    feasible=True,
                    cycles=[],
                ),
            ),
        ]

        eval_run = create_evaluation_run(
            tasks=tasks,
            arm_outputs=arm_outputs,
            prompt_path=prompt_file,
            registry_path=registry_file,
            task_set_path=task_file,
            package_version="0.1.0",
            model_label="test-model",
            allowed_variable_codes={"RIDAGEYR"},
        )

        # Check per-arm score structure
        assert "arm_a" in eval_run.scores
        assert "arm_b" in eval_run.scores

        # Check per-arm summary structure
        assert "arm_a" in eval_run.summary
        assert "arm_b" in eval_run.summary

        # Each arm should have database_routing scores
        assert "database_routing" in eval_run.scores["arm_a"]
        assert "database_routing" in eval_run.scores["arm_b"]

        # Summary should have per-arm breakdown
        assert "database_routing" in eval_run.summary["arm_a"]
        assert "database_routing" in eval_run.summary["arm_b"]

    def test_missing_output_scored_as_failure(self, tmp_path):
        """Missing output for either arm is scored as failure."""
        # Create test files for hashing
        prompt_file = tmp_path / "prompt.txt"
        registry_file = tmp_path / "registry.yaml"
        task_file = tmp_path / "tasks.yaml"

        with prompt_file.open("w") as f:
            f.write("test prompt")
        with registry_file.open("w") as f:
            f.write("test registry")
        with task_file.open("w") as f:
            f.write("test tasks")

        # Create two tasks
        tasks = [
            BenchmarkTask(
                id="task_01",
                domain="stroke",
                question="Test?",
                expected_database="NHANES",
                expected_feasible=True,
                rationale="Test",
            ),
            BenchmarkTask(
                id="task_02",
                domain="stroke",
                question="Test?",
                expected_database="NHANES",
                expected_feasible=True,
                rationale="Test",
            ),
        ]

        # Only provide output for task_01 Arm A (missing task_01 Arm B and all task_02)
        arm_outputs = [
            ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_A,
                provider_type="neurosurg_epi_agent",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=AnalysisPlan(
                    title="Plan",
                    question="Test?",
                    database="NHANES",
                    feasible=True,
                    cycles=[],
                ),
            )
        ]

        eval_run = create_evaluation_run(
            tasks=tasks,
            arm_outputs=arm_outputs,
            prompt_path=prompt_file,
            registry_path=registry_file,
            task_set_path=task_file,
            package_version="0.1.0",
            model_label="test-model",
            allowed_variable_codes={"RIDAGEYR"},
        )

        # Should have scores for both arms across all tasks
        assert "arm_a" in eval_run.scores
        assert "arm_b" in eval_run.scores

        # Each arm should have scores for both tasks
        assert len(eval_run.scores["arm_a"]["database_routing"]) == 2
        assert len(eval_run.scores["arm_b"]["database_routing"]) == 2

        # Missing outputs should have failed scores
        task_01_arm_b_routing = next(
            (s for s in eval_run.scores["arm_b"]["database_routing"] if s.task_id == "task_01"),
            None
        )
        assert task_01_arm_b_routing is not None
        assert task_01_arm_b_routing.passed is False  # Failed due to missing output

        # task_02 should also be failed for both arms (missing)
        task_02_arm_a_routing = next(
            (s for s in eval_run.scores["arm_a"]["database_routing"] if s.task_id == "task_02"),
            None
        )
        assert task_02_arm_a_routing is not None
        assert task_02_arm_a_routing.passed is False

    def test_create_evaluation_run(self, tmp_path):
        """Complete evaluation run is created with all fields."""
        # Create test files for hashing
        prompt_file = tmp_path / "prompt.txt"
        registry_file = tmp_path / "registry.yaml"
        task_file = tmp_path / "tasks.yaml"

        with prompt_file.open("w") as f:
            f.write("test prompt")
        with registry_file.open("w") as f:
            f.write("test registry")
        with task_file.open("w") as f:
            f.write("test tasks")

        # Create mock data
        tasks = [
            BenchmarkTask(
                id="task_01",
                domain="stroke",
                question="Test?",
                expected_database="NHANES",
                expected_feasible=True,
                rationale="Test",
            )
        ]

        arm_outputs = [
            ArmOutput(
                task_id="task_01",
                arm=ProviderArm.ARM_A,
                provider_type="neurosurg_epi_agent",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                plan=AnalysisPlan(
                    title="Plan",
                    question="Test?",
                    database="NHANES",
                    feasible=True,
                    cycles=[],
                ),
            )
        ]

        eval_run = create_evaluation_run(
            tasks=tasks,
            arm_outputs=arm_outputs,
            prompt_path=prompt_file,
            registry_path=registry_file,
            task_set_path=task_file,
            package_version="0.1.0",
            model_label="test-model",
            allowed_variable_codes={"RIDAGEYR"},
        )

        # Check structure
        assert len(eval_run.tasks) == 1
        assert eval_run.package_version == "0.1.0"
        assert eval_run.model_label == "test-model"
        assert eval_run.prompt_hash == _sha256_file(prompt_file)
        assert eval_run.registry_hash == _sha256_file(registry_file)
        assert eval_run.task_set_hash == _sha256_file(task_file)

        # Check scores were computed with per-arm structure
        assert "arm_a" in eval_run.scores
        assert "arm_b" in eval_run.scores
        assert "database_routing" in eval_run.scores["arm_a"]
        assert "database_routing" in eval_run.scores["arm_b"]
        assert len(eval_run.scores["arm_a"]["database_routing"]) == 1
        assert len(eval_run.scores["arm_b"]["database_routing"]) == 1

        # Arm B should be scored as failure (missing output)
        arm_b_routing_score = eval_run.scores["arm_b"]["database_routing"][0]
        assert arm_b_routing_score.passed is False
        assert arm_b_routing_score.task_id == "task_01"

        # Check summary was computed with per-arm structure
        assert "arm_a" in eval_run.summary
        assert "arm_b" in eval_run.summary
        assert "database_routing" in eval_run.summary["arm_a"]
        assert "database_routing" in eval_run.summary["arm_b"]