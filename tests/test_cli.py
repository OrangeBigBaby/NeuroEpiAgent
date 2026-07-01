"""Tests for CLI commands including Phase 2 plan and evaluate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neurosurg_epi_agent.cli import main


class TestPlanCommand:
    """Test the `plan` CLI command."""

    def test_plan_replay_command(self, tmp_path):
        """Plan command with replay provider generates plan from fixtures."""
        # Create fixture file
        fixture_data = {
            "stroke_01": {
                "title": "Stroke Plan",
                "question": "Is stroke associated with metabolic syndrome?",
                "database": "NHANES",
                "cycles": ["G", "H", "I", "J"],
                "feasible": True,
                "outcome": {
                    "name": "stroke_ever",
                    "label": "Ever told had a stroke",
                    "source_variable": "MCQ160F",
                    "source_module": "MCQ",
                    "status": "illustrative",
                    "nhanes_cycles": ["G", "H", "I", "J"],
                },
                "exposures": [],
                "covariates": [],
                "uses_fasting_subsample": False,
                "design_vars": {
                    "id": "SDMVPSU",
                    "strata": "SDMVSTRA",
                    "weight": "WTMEC2YR/4",
                },
                "steps": [],
                "causal_claims": [],
                "rationale": "Feasible cross-sectional analysis",
            }
        }

        fixture_file = tmp_path / "fixtures.json"
        with fixture_file.open("w") as f:
            json.dump(fixture_data, f)

        output_file = tmp_path / "output.yaml"

        result = main([
            "plan",
            "--provider", "replay",
            "--task-id", "stroke_01",
            "--fixtures", str(fixture_file),
            "--output", str(output_file),
        ])

        assert result == 0
        assert output_file.exists()

        # Check output contains expected plan
        output_content = output_file.read_text()
        assert "Stroke Plan" in output_content
        assert "NHANES" in output_content

    def test_plan_replay_missing_task_id(self, tmp_path):
        """Plan command with replay provider requires task-id."""
        fixture_file = tmp_path / "fixtures.json"
        with fixture_file.open("w") as f:
            json.dump({}, f)

        result = main([
            "plan",
            "--provider", "replay",
            "--fixtures", str(fixture_file),
        ])

        assert result == 2  # argparse returns 2 for missing required args

    def test_plan_replay_missing_fixtures(self):
        """Plan command with replay provider requires --fixtures."""
        result = main([
            "plan",
            "--provider", "replay",
            "--task-id", "stroke_01",
        ])

        assert result == 2  # argparse returns 2 for missing required args

    def test_plan_unknown_provider(self):
        """Plan command rejects unknown provider."""
        # argparse will call sys.exit(2) for invalid choices
        with pytest.raises(SystemExit) as exc_info:
            main([
                "plan",
                "--provider", "unknown_provider",
            ])
        assert exc_info.value.code == 2

    def test_plan_missing_question_for_claude(self, tmp_path):
        """Plan command with claude provider requires --question."""
        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Test prompt")

        result = main([
            "plan",
            "--provider", "claude",
            "--prompt", str(prompt_file),
        ])

        assert result == 2  # argparse returns 2 for missing required args


class TestEvaluateCommand:
    """Test the `evaluate` CLI command."""

    def test_evaluate_command(self, tmp_path):
        """Evaluate command produces JSON and markdown outputs."""
        # Create test files
        tasks_file = tmp_path / "tasks.yaml"
        tasks_content = """
registry_version: "1"
tasks:
  - id: test_01
    domain: stroke
    question: Test question
    expected_database: NHANES
    expected_feasible: true
    rationale: Test
    review_status: needs_expert_review
"""
        with tasks_file.open("w") as f:
            f.write(tasks_content)

        outputs_file = tmp_path / "outputs.json"
        outputs_data = {
            "arm_outputs": [
                {
                    "task_id": "test_01",
                    "arm": "arm_a",
                    "provider_type": "neurosurg_epi_agent",
                    "plan": {
                        "title": "Test Plan",
                        "question": "Test question",
                        "database": "NHANES",
                        "feasible": True,
                        "cycles": [],
                        "outcome": None,
                        "exposures": [],
                        "covariates": [],
                        "design_vars": {},
                        "steps": [],
                        "causal_claims": [],
                    },
                    "error": None,
                    "timestamp_utc": "2026-06-29T12:00:00Z",
                }
            ]
        }
        with outputs_file.open("w") as f:
            json.dump(outputs_data, f)

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("test prompt")

        registry_file = tmp_path / "registry.yaml"
        with registry_file.open("w") as f:
            f.write("test registry")

        json_output = tmp_path / "results.json"
        markdown_output = tmp_path / "summary.md"

        result = main([
            "evaluate",
            "--tasks", str(tasks_file),
            "--outputs", str(outputs_file),
            "--prompt", str(prompt_file),
            "--registry", str(registry_file),
            "--json-output", str(json_output),
            "--markdown-output", str(markdown_output),
        ])

        assert result == 0
        assert json_output.exists()
        assert markdown_output.exists()

        # Check JSON output
        with json_output.open("r") as f:
            results = json.load(f)
        assert "tasks" in results
        assert "scores" in results
        assert "summary" in results

        # Check markdown output
        markdown_content = markdown_output.read_text(encoding='utf-8')
        assert "# NeuroSurgEpiAgent Evaluation Report" in markdown_content
        assert "## Summary Statistics" in markdown_content

    def test_evaluate_markdown_uses_ascii_pass_fail_no_mojibake(self, tmp_path):
        """Regression: per-task status must render as portable ASCII PASS/FAIL,
        never the Unicode check/cross marks that mojibake to '鉁?' under GBK,
        and the coverage line must use ASCII 'x' not the Unicode multiply sign.
        """
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(
            'registry_version: "1"\n'
            "tasks:\n"
            "  - id: test_01\n"
            "    domain: stroke\n"
            "    question: Test question\n"
            "    expected_database: NHANES\n"
            "    expected_feasible: true\n"
            "    rationale: Test\n"
        )
        outputs_file = tmp_path / "outputs.json"
        outputs_file.write_text(json.dumps({
            "arm_outputs": [{
                "task_id": "test_01",
                "arm": "arm_a",
                "provider_type": "neurosurg_epi_agent",
                "plan": {
                    "title": "Test Plan", "question": "Test question",
                    "database": "NHANES", "feasible": True, "cycles": [],
                    "outcome": None, "exposures": [], "covariates": [],
                    "design_vars": {}, "steps": [], "causal_claims": [],
                },
                "error": None,
                "timestamp_utc": "2026-06-29T12:00:00Z",
            }]
        }))
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("test prompt")
        registry_file = tmp_path / "registry.yaml"
        registry_file.write_text("test registry")
        markdown_output = tmp_path / "summary.md"

        result = main([
            "evaluate",
            "--tasks", str(tasks_file),
            "--outputs", str(outputs_file),
            "--prompt", str(prompt_file),
            "--registry", str(registry_file),
            "--json-output", str(tmp_path / "results.json"),
            "--markdown-output", str(markdown_output),
        ])
        assert result == 0

        md = markdown_output.read_text(encoding="utf-8")
        # arm_a passes -> PASS; arm_b missing -> FAIL: both labels must appear.
        assert "PASS" in md
        assert "FAIL" in md
        # No Unicode status/multiply glyphs whose GBK-misdecode produces the
        # '鉁?'-style mojibake; if the source glyphs are absent, the mojibake
        # cannot appear either.
        assert "✓" not in md  # check mark -> '鉁?' under GBK
        assert "✗" not in md  # cross mark
        assert "×" not in md  # multiplication sign in coverage text
        assert "tasks x 2 arms" in md  # ASCII multiply in coverage line

    def test_evaluate_missing_required_args(self):
        """Evaluate command requires all required arguments."""
        with pytest.raises(SystemExit) as exc_info:
            result = main(["evaluate"])
        assert exc_info.value.code == 2  # argparse returns 2 for missing required args

    def test_evaluate_invalid_tasks_file(self, tmp_path):
        """Evaluate command handles invalid tasks file."""
        tasks_file = tmp_path / "invalid.yaml"
        with tasks_file.open("w") as f:
            f.write("invalid: {{{")

        outputs_file = tmp_path / "outputs.json"
        with outputs_file.open("w") as f:
            json.dump({"arm_outputs": []}, f)

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("test")

        registry_file = tmp_path / "registry.yaml"
        with registry_file.open("w") as f:
            f.write("test")

        json_output = tmp_path / "results.json"
        markdown_output = tmp_path / "summary.md"

        result = main([
            "evaluate",
            "--tasks", str(tasks_file),
            "--outputs", str(outputs_file),
            "--prompt", str(prompt_file),
            "--registry", str(registry_file),
            "--json-output", str(json_output),
            "--markdown-output", str(markdown_output),
        ])

        assert result == 1  # Expected to fail on invalid YAML


class TestExistingCommands:
    """Test that existing Phase 1 commands still work."""

    def test_route_command(self):
        """Route command still works."""
        # Redirect stdout to capture output
        import sys
        from io import StringIO

        old_stdout = sys.stdout
        sys.stdout = StringIO()

        try:
            result = main([
                "route",
                "--question", "Is stroke associated with metabolic syndrome?",
            ])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert result == 0
        assert "database:" in output
        assert "NHANES" in output

    def test_validate_plan_command(self, tmp_path):
        """Validate-plan command still works."""
        plan_file = tmp_path / "plan.yaml"
        plan_content = """
plan:
  title: Test Plan
  question: Test question?
  database: NHANES
  cycles: [G, H, I, J]
  feasible: true
  outcome:
    name: stroke_ever
    label: Stroke
    source_variable: MCQ160F
    source_module: MCQ
    status: illustrative
    nhanes_cycles: [G, H, I, J]
  exposures: []
  covariates: []
  uses_fasting_subsample: false
  design_vars:
    id: SDMVPSU
    strata: SDMVSTRA
    weight: WTMEC2YR/4
  steps: []
  causal_claims: []
"""
        with plan_file.open("w") as f:
            f.write(plan_content)

        # Redirect stdout to capture output
        import sys
        from io import StringIO

        old_stdout = sys.stdout
        sys.stdout = StringIO()

        try:
            result = main([
                "validate-plan",
                "--plan", str(plan_file),
            ])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert result == 0
        assert "PASSED" in output

    def test_manifest_command(self, tmp_path):
        """Manifest command still works."""
        plan_file = tmp_path / "plan.yaml"
        plan_content = """
plan:
  title: Test Plan
  question: Test question?
  database: NHANES
  cycles: [G, H, I, J]
  feasible: true
  outcome:
    name: stroke_ever
    label: Stroke
    source_variable: MCQ160F
    source_module: MCQ
    status: illustrative
    nhanes_cycles: [G, H, I, J]
  exposures: []
  covariates: []
  uses_fasting_subsample: false
  design_vars:
    id: SDMVPSU
    strata: SDMVSTRA
    weight: WTMEC2YR/4
  steps: []
  causal_claims: []
"""
        with plan_file.open("w") as f:
            f.write(plan_content)

        db_file = tmp_path / "databases.yaml"
        db_content = """
registry_version: "1"
databases:
  NHANES:
    name: NHANES
    label: NHANES
    data_type: cross-sectional
    status: supported
    cycles: []
    survey_design: null
    notes: null
"""
        with db_file.open("w") as f:
            f.write(db_content)

        var_file = tmp_path / "variables.yaml"
        var_content = """
registry_version: "1"
variables: []
"""
        with var_file.open("w") as f:
            f.write(var_content)

        manifest_out = tmp_path / "manifest.yaml"

        # Redirect stdout to capture output
        import sys
        from io import StringIO

        old_stdout = sys.stdout
        sys.stdout = StringIO()

        try:
            result = main([
                "manifest",
                "--plan", str(plan_file),
                "--db", str(db_file),
                "--variables", str(var_file),
                "--out", str(manifest_out),
            ])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert result == 0
        assert manifest_out.exists()


class TestRunPilotDryRun:
    """Test the `run-pilot` CLI command with dry-run mode."""

    def test_dry_run_with_real_tasks_example(self, tmp_path):
        """Dry-run with real tasks.example.yaml and max-tasks=1 produces exactly two arm outputs."""
        # Use real task file paths
        from pathlib import Path
        import sys
        from io import StringIO

        # Get the actual tasks.example.yaml path
        tasks_file = Path(__file__).parent.parent / "benchmarks" / "tasks.example.yaml"
        registry_file = Path(__file__).parent.parent / "config" / "variables" / "nhanes_demo.yaml"
        output_file = tmp_path / "temp_output.json"

        # Verify files exist
        assert tasks_file.exists(), f"Tasks file not found: {tasks_file}"
        assert registry_file.exists(), f"Registry file not found: {registry_file}"

        # Capture stdout to check execution
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        try:
            result = main([
                "run-pilot",
                "--tasks", str(tasks_file),
                "--registry", str(registry_file),
                "--max-tasks", "1",
                "--output", str(output_file),
                "--dry-run",
            ])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert result == 0, f"Command failed with output: {output}"
        assert output_file.exists(), f"Output file not created: {output_file}"

        # Check output file contains exactly two arm outputs (arm_a and arm_b for 1 task)
        with output_file.open("r") as f:
            results = json.load(f)

        assert "arm_outputs" in results, "Results should contain arm_outputs"
        arm_outputs = results["arm_outputs"]

        # Should have exactly 2 outputs (arm_a + arm_b for 1 task)
        assert len(arm_outputs) == 2, f"Expected 2 arm outputs, got {len(arm_outputs)}"

        # Verify both outputs are for the same task
        task_ids = {out["task_id"] for out in arm_outputs}
        assert len(task_ids) == 1, f"Expected outputs for 1 task, got outputs for tasks: {task_ids}"

        # Verify dry-run mode (no actual provider calls)
        for output in arm_outputs:
            assert output["provider_type"] == "dry_run", f"Expected dry_run provider type, got {output['provider_type']}"
            assert output["error"] == "Dry run - no model call made", f"Dry run should have no-model-call error"

        # Verify we got both arms
        arms = {out["arm"] for out in arm_outputs}
        assert arms == {"arm_a", "arm_b"}, f"Expected both arms, got {arms}"

    def test_dry_run_loads_real_tasks_example_successfully(self):
        """Verify that tasks.example.yaml loads successfully with all required fields."""
        from pathlib import Path

        tasks_file = Path(__file__).parent.parent / "benchmarks" / "tasks.example.yaml"

        # Try to load and validate the tasks
        from neurosurg_epi_agent.experiment import ExperimentRunner
        from pathlib import Path as PathlibPath

        # This should not raise an exception
        try:
            # Create a temporary registry file for testing
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write("registry_version: '1'\nvariables: []\n")
                temp_registry = f.name

            try:
                # Just test loading - don't run
                import yaml
                with tasks_file.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                from neurosurg_epi_agent.evaluation import BenchmarkTask
                tasks = [BenchmarkTask.model_validate(t) for t in data.get("tasks", [])]

                # Verify all tasks have required rationale field
                for task in tasks:
                    assert hasattr(task, 'rationale'), f"Task {task.id} missing rationale field"
                    assert task.rationale, f"Task {task.id} has empty rationale"

                # Verify we have all expected tasks
                task_ids = {t.id for t in tasks}
                expected_tasks = {
                    "stroke_01", "stroke_02", "stroke_03",
                    "tbi_01", "tbi_02", "tbi_03",
                    "tumor_01", "tumor_02", "tumor_03",
                    "cross_01"
                }
                assert task_ids == expected_tasks, f"Expected {expected_tasks}, got {task_ids}"

            finally:
                import os
                os.unlink(temp_registry)

        except Exception as e:
            pytest.fail(f"Failed to load tasks.example.yaml: {e}")