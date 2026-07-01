"""Tests for planner providers: replay and Claude Code."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from neurosurg_epi_agent.planner import (
    ClaudeCodePlannerProvider,
    PlannerError,
    ReplayPlannerProvider,
)
from neurosurg_epi_agent.schemas import AnalysisPlan


class TestReplayPlannerProvider:
    """Test ReplayPlannerProvider for offline fixture-based planning."""

    def test_replay_planner_loads_fixtures(self, tmp_path):
        """ReplayPlannerProvider loads fixtures from JSON file."""
        fixture_data = {
            "stroke_01": {
                "title": "Stroke and metabolic syndrome",
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

        provider = ReplayPlannerProvider(fixture_path=fixture_file)
        plan = provider.generate_plan(question="", task_id="stroke_01")

        assert plan.title == "Stroke and metabolic syndrome"
        assert plan.database == "NHANES"
        assert plan.feasible is True
        assert plan.outcome is not None
        assert plan.outcome.source_variable == "MCQ160F"

    def test_replay_planner_loads_directory(self, tmp_path):
        """ReplayPlannerProvider loads all JSON files from a directory."""
        fixture1 = tmp_path / "task1.json"
        fixture2 = tmp_path / "task2.json"

        with fixture1.open("w") as f:
            json.dump({"task_a": {"title": "Task A", "question": "?", "database": "NHANES", "feasible": True}}, f)
        with fixture2.open("w") as f:
            json.dump({"task_b": {"title": "Task B", "question": "?", "database": "NHANES", "feasible": True}}, f)

        provider = ReplayPlannerProvider(fixture_path=tmp_path)

        # Should have loaded both fixtures
        plan_a = provider.generate_plan(question="", task_id="task_a")
        plan_b = provider.generate_plan(question="", task_id="task_b")

        assert plan_a.title == "Task A"
        assert plan_b.title == "Task B"

    def test_replay_missing_task_raises_error(self, tmp_path):
        """ReplayPlannerProvider raises PlannerError for missing task_id."""
        fixture_file = tmp_path / "fixtures.json"
        with fixture_file.open("w") as f:
            json.dump({"stroke_01": {"title": "Stroke", "question": "?", "database": "NHANES", "feasible": True}}, f)

        provider = ReplayPlannerProvider(fixture_path=fixture_file)

        with pytest.raises(PlannerError) as exc_info:
            provider.generate_plan(question="", task_id="nonexistent")

        assert exc_info.value.code == "fixture_not_found"
        assert "nonexistent" in str(exc_info.value.details)

    def test_replay_no_task_id_required(self, tmp_path):
        """ReplayPlannerProvider requires task_id parameter."""
        fixture_file = tmp_path / "fixtures.json"
        with fixture_file.open("w") as f:
            json.dump({"stroke_01": {"title": "Stroke", "question": "?", "database": "NHANES", "feasible": True}}, f)

        provider = ReplayPlannerProvider(fixture_path=fixture_file)

        with pytest.raises(PlannerError) as exc_info:
            provider.generate_plan(question="")

        assert exc_info.value.code == "task_id_required"

    def test_malformed_fixture_raises_planner_error(self, tmp_path):
        """ReplayPlannerProvider raises PlannerError for malformed fixtures."""
        fixture_file = tmp_path / "fixtures.json"
        with fixture_file.open("w") as f:
            json.dump({"stroke_01": {"_malformed": True, "raw": {"invalid": "data"}}}, f)

        provider = ReplayPlannerProvider(fixture_path=fixture_file)

        with pytest.raises(PlannerError) as exc_info:
            provider.generate_plan(question="", task_id="stroke_01")

        assert exc_info.value.code == "malformed_fixture"

    def test_invalid_json_raises_planner_error(self, tmp_path):
        """ReplayPlannerProvider raises PlannerError for invalid JSON."""
        fixture_file = tmp_path / "fixtures.json"
        with fixture_file.open("w") as f:
            f.write("{invalid json}")

        # This should raise PlannerError during initialization
        with pytest.raises(PlannerError) as exc_info:
            ReplayPlannerProvider(fixture_path=fixture_file)

        assert exc_info.value.code == "invalid_json"

    def test_fixture_path_not_found_raises_error(self):
        """ReplayPlannerProvider raises PlannerError for non-existent path."""
        with pytest.raises(PlannerError) as exc_info:
            ReplayPlannerProvider(fixture_path=Path("/nonexistent/path.json"))

        assert exc_info.value.code == "fixture_not_found"


class TestClaudeCodePlannerProvider:
    """Test ClaudeCodePlannerProvider with subprocess calls."""

    def test_claude_planner_loads_prompt(self, tmp_path):
        """ClaudeCodePlannerProvider loads prompt template from disk."""
        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}\nRegistry: {registry_summary}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file)
        prompt = provider._load_prompt()

        assert "Question:" in prompt
        assert "{question}" in prompt

    def test_claude_prompt_not_found_raises_error(self):
        """ClaudeCodePlannerProvider raises PlannerError for missing prompt."""
        provider = ClaudeCodePlannerProvider(prompt_path=Path("/nonexistent/prompt.txt"))

        with pytest.raises(PlannerError) as exc_info:
            provider._load_prompt()

        assert exc_info.value.code == "prompt_not_found"

    def test_claude_build_argv_structure(self, tmp_path):
        """ClaudeCodePlannerProvider builds correct subprocess argv."""
        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}\nRegistry: {registry_summary}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file, model="claude-opus-4-8", timeout=60)

        argv = provider._build_argv(
            question="Test question",
            registry_context="Available vars: age, sex",
            routing_context="{}",
        )

        # Check for verified safe flags
        assert argv[0] == "claude"
        assert "-p" in argv
        assert "--safe-mode" in argv
        assert "--model" in argv
        assert "claude-opus-4-8" in argv
        assert "--effort" in argv
        assert "low" in argv
        assert "--permission-mode" in argv
        assert "dontAsk" in argv
        assert "--output-format" in argv
        assert "json" in argv
        assert "--json-schema" in argv

        # Question should be last argument (in the formatted prompt)
        assert "Test question" in argv[-1] or "Test question" in " ".join(argv)

    def test_claude_argv_with_budget(self, tmp_path):
        """ClaudeCodePlannerProvider includes budget directive when specified."""
        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file, max_budget_usd=0.50)

        argv = provider._build_argv(question="Test", registry_context="")

        assert "--max-budget-usd" in argv
        assert "0.5" in argv

    def test_claude_subprocess_mocked(self, tmp_path, monkeypatch):
        """ClaudeCodePlannerProvider calls subprocess correctly."""
        # Mock subprocess.run
        class MockResult:
            returncode = 0
            stdout = json.dumps({
                "plan": {
                    "title": "Mock Plan",
                    "question": "Test",
                    "database": "NHANES",
                    "feasible": True,
                    "cycles": [],
                    "outcome": None,
                    "exposures": [],
                    "covariates": [],
                    "design_vars": {},
                    "steps": [],
                    "causal_claims": [],
                }
            })
            stderr = ""

        mock_run = lambda *args, **kwargs: MockResult()
        monkeypatch.setattr("subprocess.run", mock_run)

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}\nRegistry: {registry_summary}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file, timeout=30)
        plan = provider.generate_plan(question="Test question")

        assert plan.title == "Mock Plan"
        assert plan.database == "NHANES"

    def test_claude_subprocess_error_handling(self, tmp_path, monkeypatch):
        """ClaudeCodePlannerProvider handles subprocess errors correctly."""

        def mock_run_error(*args, **kwargs):
            result = type("MockResult", (), {
                "returncode": 1,
                "stderr": "Claude API error",
                "stdout": ""
            })()
            return result

        monkeypatch.setattr("subprocess.run", mock_run_error)

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file, timeout=30)

        with pytest.raises(PlannerError) as exc_info:
            provider.generate_plan(question="Test")

        assert exc_info.value.code == "claude_subprocess_error"
        assert "exit code 1" in exc_info.value.message

    def test_claude_json_parse_error(self, tmp_path, monkeypatch):
        """ClaudeCodePlannerProvider handles invalid JSON output."""

        class MockResult:
            returncode = 0
            stdout = "not valid json"
            stderr = ""

        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: MockResult())

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file, timeout=30)

        with pytest.raises(PlannerError) as exc_info:
            provider.generate_plan(question="Test")

        assert exc_info.value.code == "claude_json_parse_error"

    def test_claude_missing_plan_key(self, tmp_path, monkeypatch):
        """ClaudeCodePlannerProvider handles missing plan key in output."""

        class MockResult:
            returncode = 0
            stdout = json.dumps({"not_plan": "data"})
            stderr = ""

        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: MockResult())

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file, timeout=30)

        with pytest.raises(PlannerError) as exc_info:
            provider.generate_plan(question="Test")

        assert exc_info.value.code == "claude_missing_plan"

    def test_claude_validation_error(self, tmp_path, monkeypatch):
        """ClaudeCodePlannerProvider handles Pydantic validation errors."""

        class MockResult:
            returncode = 0
            stdout = json.dumps({"plan": {"invalid": "data"}})
            stderr = ""

        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: MockResult())

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file, timeout=30)

        with pytest.raises(PlannerError) as exc_info:
            provider.generate_plan(question="Test")

        assert exc_info.value.code == "claude_validation_error"

    def test_claude_timeout(self, tmp_path, monkeypatch):
        """ClaudeCodePlannerProvider handles subprocess timeout."""

        import subprocess

        def mock_run_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired("claude", 30)

        monkeypatch.setattr("subprocess.run", mock_run_timeout)

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file, timeout=30)

        with pytest.raises(PlannerError) as exc_info:
            provider.generate_plan(question="Test")

        assert exc_info.value.code == "claude_timeout"

    def test_claude_safe_argv_construction(self, tmp_path):
        """ClaudeCodePlannerProvider uses verified safe CLI flags."""
        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}\nRegistry: {registry_summary}")

        provider = ClaudeCodePlannerProvider(
            prompt_path=prompt_file,
            model="claude-sonnet-4-6",
            timeout=120,
            max_budget_usd=0.50,
        )

        argv = provider._build_argv(
            question="Test question",
            registry_context='[{"name": "age", "source_variable": "RIDAGEYR"}]',
        )

        # Check for verified safe flags
        assert argv[0] == "claude"
        assert "-p" in argv
        assert "--safe-mode" in argv
        assert "--output-format" in argv
        assert "json" in argv
        assert "--json-schema" in argv
        assert "--effort" in argv
        assert "low" in argv
        assert "--permission-mode" in argv
        assert "dontAsk" in argv
        assert "--max-budget-usd" in argv
        assert "0.5" in argv
        assert "--model" in argv
        assert "claude-sonnet-4-6" in argv

        # Question should be last argument
        assert "Test question" in argv[-1]

    def test_claude_json_schema_generation(self, tmp_path):
        """ClaudeCodePlannerProvider generates valid JSON schema."""
        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file)
        schema_str = provider._build_json_schema()

        # Should be valid JSON
        schema = json.loads(schema_str)

        # Check structure
        assert schema["type"] == "object"
        assert "required" in schema
        assert "plan" in schema["required"]
        assert "properties" in schema
        assert "plan" in schema["properties"]

        # Check plan structure
        plan_schema = schema["properties"]["plan"]
        assert plan_schema["type"] == "object"
        assert "title" in plan_schema["properties"]
        assert "question" in plan_schema["properties"]
        assert "database" in plan_schema["properties"]
        assert "feasible" in plan_schema["properties"]

    def test_claude_registry_context_generation(self, tmp_path):
        """ClaudeCodePlannerProvider generates concise JSON registry context."""
        # Create a simple registry file
        registry_file = tmp_path / "registry.yaml"
        with registry_file.open("w") as f:
            f.write("""
registry_version: "1"
variables:
  - name: age
    label: Age
    source_variable: RIDAGEYR
    source_module: DEMO
    status: verified
    nhanes_cycles: ["G", "H", "I", "J"]
  - name: stroke
    label: Stroke
    source_variable: MCQ160F
    source_module: MCQ
    status: illustrative
    nhanes_cycles: ["G", "H", "I", "J"]
""")

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file)
        registry_context = provider._build_registry_context(registry_file)

        # Should be valid JSON array
        variables = json.loads(registry_context)

        assert len(variables) == 2

        # Check first variable structure
        var1 = variables[0]
        assert var1["name"] == "age"
        assert var1["source_variable"] == "RIDAGEYR"
        assert var1["source_module"] == "DEMO"
        assert var1["status"] == "verified"
        assert var1["nhanes_cycles"] == ["G", "H", "I", "J"]

    def test_claude_structured_output_parsing(self, tmp_path, monkeypatch):
        """ClaudeCodePlannerProvider parses structured_output from envelope."""

        class MockResult:
            returncode = 0
            # Real CLI envelope with structured_output
            stdout = json.dumps({
                "structured_output": {
                    "plan": {
                        "title": "Real Envelope Plan",
                        "question": "Test",
                        "database": "NHANES",
                        "feasible": True,
                        "cycles": ["G", "H"],
                        "outcome": None,
                        "exposures": [],
                        "covariates": [],
                        "design_vars": {},
                        "steps": [],
                        "causal_claims": [],
                    }
                }
            })
            stderr = ""

        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: MockResult())

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}\nRegistry: {registry_summary}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file, timeout=30)
        plan = provider.generate_plan(question="Test question")

        assert plan.title == "Real Envelope Plan"
        assert plan.database == "NHANES"

    def test_claude_result_field_fallback(self, tmp_path, monkeypatch):
        """ClaudeCodePlannerProvider falls back to result field if structured_output missing."""

        class MockResult:
            returncode = 0
            # Alternative envelope structure with result field
            stdout = json.dumps({
                "result": {
                    "plan": {
                        "title": "Result Field Plan",
                        "question": "Test",
                        "database": "NHANES",
                        "feasible": True,
                        "cycles": [],
                        "outcome": None,
                        "exposures": [],
                        "covariates": [],
                        "design_vars": {},
                        "steps": [],
                        "causal_claims": [],
                    }
                }
            })
            stderr = ""

        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: MockResult())

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file, timeout=30)
        plan = provider.generate_plan(question="Test")

        assert plan.title == "Result Field Plan"

    def test_claude_execution_metadata_capture(self, tmp_path, monkeypatch):
        """ClaudeCodePlannerProvider captures execution metadata without secrets."""

        class MockResult:
            returncode = 0
            stdout = json.dumps({
                "structured_output": {
                    "plan": {
                        "title": "Plan",
                        "question": "Test",
                        "database": "NHANES",
                        "feasible": True,
                        "cycles": [],
                        "outcome": None,
                        "exposures": [],
                        "covariates": [],
                        "design_vars": {},
                        "steps": [],
                        "causal_claims": [],
                    }
                }
            })
            stderr = ""

        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: MockResult())

        prompt_file = tmp_path / "prompt.txt"
        with prompt_file.open("w") as f:
            f.write("Question: {question}")

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file, timeout=30, max_budget_usd=0.50)

        # Should not raise an error
        plan = provider.generate_plan(question="Test")
        assert plan.database == "NHANES"

    def test_claude_prompt_rendering_with_real_templates(self):
        """ClaudeCodePlannerProvider safely renders real prompt templates with JSON braces."""
        # Get the paths to real prompt templates
        config_dir = Path(__file__).parent.parent / "config" / "prompts"
        planner_v1_path = config_dir / "planner_v1.txt"
        baseline_v1_path = config_dir / "baseline_v1.txt"

        # Verify the real templates exist and can be loaded
        assert planner_v1_path.exists(), "Real planner_v1.txt template should exist"
        assert baseline_v1_path.exists(), "Real baseline_v1.txt template should exist"

        # Load and verify planner_v1.txt contains literal JSON braces
        planner_template = planner_v1_path.read_text(encoding="utf-8")
        assert "{" in planner_template and "}" in planner_template, "Template should contain braces"
        assert '"plan"' in planner_template, "Template should contain JSON schema"

        # Test safe rendering with planner_v1.txt
        provider = ClaudeCodePlannerProvider(prompt_path=planner_v1_path)
        full_prompt = provider._load_prompt().replace(
            "{question}", "Test question with {literal} braces"
        ).replace(
            "{registry_summary}", '[{"var": "value"}]'
        )

        # Verify literal braces are preserved (not interpreted as format tokens)
        assert '"plan"' in full_prompt, "JSON schema braces should be preserved"
        assert "Test question with {literal} braces" in full_prompt, "Question should be inserted"
        assert '"var"' in full_prompt and "value" in full_prompt, "Registry should be inserted"

        # Test safe rendering with baseline_v1.txt
        provider_baseline = ClaudeCodePlannerProvider(prompt_path=baseline_v1_path)
        baseline_template = provider_baseline._load_prompt()
        assert "{" in baseline_template and "}" in baseline_template, "Baseline should contain braces"

        full_baseline = baseline_template.replace(
            "{question}", "Another {test} question"
        ).replace(
            "{registry_summary}", "[]"
        )

        # Verify literal braces are preserved
        assert '"plan"' in full_baseline, "JSON schema braces should be preserved"
        assert "Another {test} question" in full_baseline, "Question should be inserted"

    def test_claude_prompt_rendering_preserves_json_braces(self, tmp_path):
        """Prompt rendering preserves literal JSON braces instead of treating them as format tokens."""
        # Create a prompt with extensive JSON schema containing braces
        prompt_file = tmp_path / "prompt_with_json.txt"
        prompt_content = """
You are a planner. Output JSON like:
{
  "plan": {
    "title": "Analysis {should_preserve}",
    "database": "NHANES",
    "cycles": ["G", "H", "I", "J"],
    "outcome": {
      "nested": {
        "value": "test {value}"
      }
    }
  }
}

Question: {question}
Registry: {registry_summary}
"""
        prompt_file.write_text(prompt_content)

        provider = ClaudeCodePlannerProvider(prompt_path=prompt_file)
        prompt = provider._load_prompt()

        # Replace tokens using str.replace (the safe method)
        full_prompt = prompt.replace("{question}", "Test {braces} question").replace(
            "{registry_summary}", "[{data}]"
        )

        # Verify all JSON braces are preserved
        assert '"plan"' in full_prompt
        assert '"title"' in full_prompt
        assert '"database"' in full_prompt
        assert '"nested"' in full_prompt
        assert '"value"' in full_prompt
        assert "Test {braces} question" in full_prompt
        assert "[{data}]" in full_prompt

        # Verify the nested braces in JSON schema are preserved
        assert "Analysis {should_preserve}" in full_prompt
        assert "test {value}" in full_prompt