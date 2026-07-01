"""Tests for telemetry capture, efficiency summary, and the offline summarizer.

Covers: successful usage parsing, missing usage, provider-failure telemetry,
zero-call deterministic refusal, zero-call dry run, summary aggregation with
missing values, optional price calculation, checkpoint/backward-compat, and
the offline summary output.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from neurosurg_epi_agent.evaluation import ArmOutput, BenchmarkTask, ProviderArm
from neurosurg_epi_agent.experiment import ExperimentRunner
from neurosurg_epi_agent.planner import ClaudeCodePlannerProvider, PlannerError
from neurosurg_epi_agent.schemas import AnalysisPlan
from neurosurg_epi_agent.telemetry import (
    CallTelemetry,
    ZERO_CALL_TELEMETRY,
    build_arm_efficiency,
    build_efficiency_summary,
    estimate_cost,
    parse_envelope_telemetry,
    render_efficiency_markdown,
    summarize_experiment_file,
    validate_prices,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _full_envelope() -> dict:
    return {
        "structured_output": {"plan": {"title": "P", "question": "q", "database": "NHANES",
                                       "feasible": True, "cycles": []}},
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_input_tokens": 200,
            "cache_creation_input_tokens": 50,
        },
        "total_cost_usd": 0.0123,
        "duration_ms": 4500,
        "duration_api_ms": 3200,
        "num_turns": 2,
        "session_id": "abc-123",
    }


def _minimal_resources(tmp_path: Path, tasks_yaml: str | None = None) -> dict:
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text(tasks_yaml or "tasks: []")
    prompt_a = tmp_path / "prompt_a.txt"
    prompt_a.write_text("Prompt A")
    prompt_b = tmp_path / "prompt_b.txt"
    prompt_b.write_text("Prompt B")
    registry = tmp_path / "registry.yaml"
    registry.write_text('registry_version: "1"\nvariables: []\n')
    return {"tasks": tasks_file, "prompt_a": prompt_a, "prompt_b": prompt_b, "registry": registry}


# --------------------------------------------------------------------------- #
# parse_envelope_telemetry
# --------------------------------------------------------------------------- #

class TestParseEnvelopeTelemetry:
    def test_successful_usage_parsing(self):
        t = parse_envelope_telemetry(_full_envelope())
        assert t.model_call_attempted is True
        assert t.input_tokens == 1000
        assert t.output_tokens == 500
        assert t.cache_read_input_tokens == 200
        assert t.cache_creation_input_tokens == 50
        assert t.claude_cli_reported_cost_usd == pytest.approx(0.0123)
        assert t.duration_ms == 4500
        assert t.duration_api_ms == 3200
        assert t.num_turns == 2
        assert t.session_id == "abc-123"

    def test_missing_usage_fields_remain_none(self):
        # Envelope exists but has no usage / cost / timing fields.
        t = parse_envelope_telemetry({"structured_output": {"plan": {}}})
        assert t.model_call_attempted is True
        assert t.input_tokens is None
        assert t.output_tokens is None
        assert t.cache_read_input_tokens is None
        assert t.cache_creation_input_tokens is None
        assert t.claude_cli_reported_cost_usd is None
        assert t.duration_ms is None
        assert t.num_turns is None
        assert t.session_id is None

    def test_partial_usage_fields(self):
        t = parse_envelope_telemetry({"usage": {"input_tokens": 10}})
        assert t.input_tokens == 10
        assert t.output_tokens is None

    def test_non_dict_envelope(self):
        t = parse_envelope_telemetry("not a dict")
        assert t.model_call_attempted is True
        assert t.input_tokens is None

    def test_no_secrets_retained(self):
        # Even if env-like or prompt-like strings are present, they are ignored.
        env = {
            "usage": {"input_tokens": 1},
            "ANTHROPIC_API_KEY": "sk-secret",
            "prompt": "secret prompt text",
            "stdout": "raw stdout",
        }
        t = parse_envelope_telemetry(env)
        dumped = t.model_dump()
        assert "sk-secret" not in json.dumps(dumped)
        assert "secret prompt text" not in json.dumps(dumped)
        assert "raw stdout" not in json.dumps(dumped)


# --------------------------------------------------------------------------- #
# estimate_cost
# --------------------------------------------------------------------------- #

class TestEstimateCost:
    def test_all_required_rates_supplied(self):
        t = CallTelemetry(input_tokens=1_000_000, output_tokens=500_000)
        prices = {"input": 3.0, "output": 15.0}
        # 1M * 3 / 1M + 0.5M * 15 / 1M = 3 + 7.5 = 10.5
        assert estimate_cost(t, prices) == pytest.approx(10.5)

    def test_missing_required_rate_returns_none(self):
        # input tokens nonzero but no input rate supplied -> None
        t = CallTelemetry(input_tokens=100, output_tokens=0)
        assert estimate_cost(t, {"output": 15.0}) is None

    def test_no_nonzero_tokens_returns_none(self):
        t = CallTelemetry(input_tokens=0, output_tokens=0)
        assert estimate_cost(t, {"input": 3.0, "output": 15.0}) is None

    def test_missing_token_counts_do_not_require_rate(self):
        # cache_read tokens are None; only output is nonzero and has a rate.
        t = CallTelemetry(output_tokens=1_000_000)
        assert estimate_cost(t, {"output": 15.0}) == pytest.approx(15.0)

    def test_cache_categories_priced(self):
        t = CallTelemetry(
            input_tokens=1_000_000,
            cache_read_input_tokens=2_000_000,
            cache_creation_input_tokens=500_000,
        )
        prices = {"input": 3.0, "cache_read": 0.3, "cache_creation": 3.75}
        # 3 + 0.6 + 1.875 = 5.475
        assert estimate_cost(t, prices) == pytest.approx(5.475)

    def test_none_telemetry(self):
        assert estimate_cost(None, {"input": 3.0}) is None


# --------------------------------------------------------------------------- #
# build_efficiency_summary
# --------------------------------------------------------------------------- #

class TestEfficiencySummary:
    def test_aggregation_with_missing_values(self):
        # Two outputs: one with full telemetry, one with none.
        outputs = [
            {
                "arm": "arm_a",
                "execution_time_seconds": 4.0,
                "call_telemetry": {
                    "model_call_attempted": True,
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cache_read_input_tokens": None,
                    "cache_creation_input_tokens": None,
                    "claude_cli_reported_cost_usd": 0.01,
                    "estimated_cost_usd": None,
                },
                "reused": False,
            },
            {
                "arm": "arm_a",
                "execution_time_seconds": None,
                "call_telemetry": None,
                "reused": False,
            },
        ]
        s = build_efficiency_summary(outputs, total_tasks=2)
        arm_a = s["arm_a"]

        assert arm_a["total_task_arm_outputs"] == 2
        assert arm_a["model_calls_this_run"] == 1
        assert arm_a["calls_per_task"] == pytest.approx(0.5)
        assert arm_a["elapsed_seconds_total"] == pytest.approx(4.0)
        assert arm_a["elapsed_available"] == 1
        assert arm_a["elapsed_missing"] == 1

        tok_in = arm_a["tokens"]["input_tokens"]
        assert tok_in["sum"] == 1000
        assert tok_in["available"] == 1
        assert tok_in["missing"] == 1

        # cache_read has no nonzero observations; sum must be None (not 0)
        assert arm_a["tokens"]["cache_read_input_tokens"]["sum"] is None
        assert arm_a["tokens"]["cache_read_input_tokens"]["available"] == 0
        assert arm_a["tokens"]["cache_read_input_tokens"]["missing"] == 2

        # CLI cost: one output reports 0.01, one is missing -> INCOMPLETE.
        # The total is None (not 0.01); the observed 0.01 is the partial sum.
        assert arm_a["claude_cli_reported_cost_usd_total"] is None
        assert arm_a["claude_cli_reported_cost_usd_partial_sum_usd"] == pytest.approx(0.01)
        assert arm_a["claude_cli_reported_cost_usd_complete"] is False
        assert arm_a["claude_cli_reported_cost_available"] == 1
        assert arm_a["claude_cli_reported_cost_missing"] == 1

        # Estimated cost all-missing -> None (never zero)
        assert arm_a["estimated_cost_usd_total"] is None
        assert arm_a["estimated_cost_usd_complete"] is False
        assert arm_a["estimated_cost_missing"] == 2

    def test_reused_outputs_excluded_from_this_run_totals(self):
        # A reused Arm B output must contribute nothing to this-run elapsed,
        # token, CLI-cost, or estimated-cost totals. It is still reported via
        # reused_outputs and counted in total_task_arm_outputs.
        outputs = [
            {
                "arm": "arm_b",
                "execution_time_seconds": 5.0,
                "call_telemetry": {
                    "model_call_attempted": True,
                    "input_tokens": 100,
                    "output_tokens": 40,
                    "cache_read_input_tokens": 10,
                    "cache_creation_input_tokens": 5,
                    "claude_cli_reported_cost_usd": 0.02,
                    "estimated_cost_usd": 0.01,
                },
                "reused": True,  # reused from a prior run
            },
            {
                "arm": "arm_b",
                "execution_time_seconds": 2.0,
                "call_telemetry": {
                    "model_call_attempted": True,
                    "input_tokens": 50,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 4,
                    "cache_creation_input_tokens": 2,
                    "claude_cli_reported_cost_usd": 0.01,
                    "estimated_cost_usd": 0.005,
                },
                "reused": False,
            },
        ]
        s = build_efficiency_summary(outputs, total_tasks=2)
        arm_b = s["arm_b"]

        # The reused output is present and reported, but counts as zero calls.
        assert arm_b["total_task_arm_outputs"] == 2
        assert arm_b["reused_outputs"] == 1
        assert arm_b["model_calls_this_run"] == 1
        assert arm_b["calls_per_task"] == pytest.approx(0.5)

        # Elapsed: only the non-reused 2.0s contributes.
        assert arm_b["elapsed_seconds_total"] == pytest.approx(2.0)
        assert arm_b["elapsed_seconds_mean_per_task"] == pytest.approx(2.0)
        assert arm_b["elapsed_available"] == 1
        assert arm_b["elapsed_missing"] == 0  # measured_n = 1 (non-reused)

        # Tokens: only the non-reused output's tokens are summed.
        for cat, field, expected in (
            ("input_tokens", "input_tokens", 50),
            ("output_tokens", "output_tokens", 20),
            ("cache_read_input_tokens", "cache_read_input_tokens", 4),
            ("cache_creation_input_tokens", "cache_creation_input_tokens", 2),
        ):
            assert arm_b["tokens"][cat]["sum"] == expected
            assert arm_b["tokens"][cat]["available"] == 1
            assert arm_b["tokens"][cat]["missing"] == 0

        # Costs: only the non-reused values contribute.
        assert arm_b["claude_cli_reported_cost_usd_total"] == pytest.approx(0.01)
        assert arm_b["claude_cli_reported_cost_available"] == 1
        assert arm_b["claude_cli_reported_cost_missing"] == 0
        assert arm_b["estimated_cost_usd_total"] == pytest.approx(0.005)
        assert arm_b["estimated_cost_available"] == 1
        assert arm_b["estimated_cost_missing"] == 0

        # Overall mirrors arm_b (no arm_a present): reused excluded everywhere.
        overall = s["overall"]
        assert overall["reused_outputs"] == 1
        assert overall["model_calls_this_run"] == 1
        assert overall["elapsed_seconds_total"] == pytest.approx(2.0)
        assert overall["tokens"]["input_tokens"]["sum"] == 50
        assert overall["claude_cli_reported_cost_usd_total"] == pytest.approx(0.01)

    def test_overall_uses_distinct_task_count(self):
        outputs = [
            {"arm": "arm_a", "call_telemetry": {"model_call_attempted": True}, "reused": False},
            {"arm": "arm_b", "call_telemetry": {"model_call_attempted": True}, "reused": False},
        ]
        s = build_efficiency_summary(outputs, total_tasks=1)
        assert s["overall"]["model_calls_this_run"] == 2
        assert s["overall"]["total_tasks"] == 1
        assert s["overall"]["calls_per_task"] == pytest.approx(2.0)


# --------------------------------------------------------------------------- #
# Planner telemetry capture (real provider, mocked subprocess)
# --------------------------------------------------------------------------- #

class TestPlannerTelemetry:
    def test_telemetry_captured_on_success(self, tmp_path, monkeypatch):
        class MockResult:
            returncode = 0
            stdout = json.dumps(_full_envelope())
            stderr = ""
        monkeypatch.setattr("subprocess.run", lambda *a, **k: MockResult())

        prompt = tmp_path / "p.txt"
        prompt.write_text("Q: {question}")
        provider = ClaudeCodePlannerProvider(prompt_path=prompt, timeout=30)
        plan = provider.generate_plan(question="q")
        assert plan.database == "NHANES"
        assert provider.last_call_telemetry is not None
        assert provider.last_call_telemetry.input_tokens == 1000
        assert provider.last_call_telemetry.model_call_attempted is True

    def test_telemetry_preserved_on_validation_failure(self, tmp_path, monkeypatch):
        # Envelope has usage but the plan is invalid -> PlannerError, yet the
        # parsed usage telemetry must be preserved on the provider.
        envelope = {
            "structured_output": {"plan": {"invalid": "no required fields"}},
            "usage": {"input_tokens": 700, "output_tokens": 80},
        }

        class MockResult:
            returncode = 0
            stdout = json.dumps(envelope)
            stderr = ""
        monkeypatch.setattr("subprocess.run", lambda *a, **k: MockResult())

        prompt = tmp_path / "p.txt"
        prompt.write_text("Q: {question}")
        provider = ClaudeCodePlannerProvider(prompt_path=prompt, timeout=30)

        with pytest.raises(PlannerError):
            provider.generate_plan(question="q")

        # A live attempt counts as one call; usage captured from the envelope.
        assert provider.last_call_telemetry is not None
        assert provider.last_call_telemetry.model_call_attempted is True
        assert provider.last_call_telemetry.input_tokens == 700
        assert provider.last_call_telemetry.output_tokens == 80

    def test_telemetry_on_subprocess_error(self, tmp_path, monkeypatch):
        # Subprocess returns nonzero exit -> no envelope -> tokens None but
        # model_call_attempted stays True.
        def mock_run(*a, **k):
            return type("R", (), {"returncode": 1, "stderr": "boom", "stdout": ""})()

        monkeypatch.setattr("subprocess.run", mock_run)

        prompt = tmp_path / "p.txt"
        prompt.write_text("Q: {question}")
        provider = ClaudeCodePlannerProvider(prompt_path=prompt, timeout=30)

        with pytest.raises(PlannerError) as exc:
            provider.generate_plan(question="q")
        assert exc.value.code == "claude_subprocess_error"

        tel = provider.last_call_telemetry
        assert tel is not None
        assert tel.model_call_attempted is True
        assert tel.input_tokens is None
        assert tel.claude_cli_reported_cost_usd is None


# --------------------------------------------------------------------------- #
# Experiment-level telemetry wiring
# --------------------------------------------------------------------------- #

class TestExperimentTelemetry:
    def _runner(self, tmp_path, tasks_yaml):
        res = _minimal_resources(tmp_path, tasks_yaml)
        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            return ExperimentRunner(
                tasks_path=res["tasks"],
                prompt_a_path=res["prompt_a"],
                prompt_b_path=res["prompt_b"],
                registry_path=res["registry"],
            )

    def test_zero_call_deterministic_refusal(self, tmp_path):
        tasks_yaml = """
tasks:
  - id: t1
    domain: tumor
    question: Is meningioma prevalence captured in NHANES?
    expected_database: NHANES
    expected_feasible: false
    rationale: Histology unavailable
"""
        runner = self._runner(tmp_path, tasks_yaml)
        task = BenchmarkTask(
            id="t1", domain="tumor",
            question="Is meningioma prevalence captured in NHANES?",
            expected_database="NHANES", expected_feasible=False,
            rationale="Histology unavailable",
        )
        out = runner.run_task(task, ProviderArm.ARM_A, runner.provider_a, dry_run=False)
        # Deterministic refusal: minimal plan, zero model calls, and an explicit
        # measured-zero telemetry (NOT None — distinct from missing telemetry).
        assert out.plan is not None and out.plan.feasible is False
        assert out.provider_type == "deterministic_router"
        assert out.call_telemetry is not None
        assert out.call_telemetry.model_call_attempted is False
        assert out.call_telemetry.input_tokens == 0
        assert out.call_telemetry.output_tokens == 0
        assert out.call_telemetry.cache_read_input_tokens == 0
        assert out.call_telemetry.cache_creation_input_tokens == 0
        assert out.call_telemetry.claude_cli_reported_cost_usd == 0.0
        assert out.call_telemetry.estimated_cost_usd == 0.0

    def test_zero_call_dry_run(self, tmp_path):
        tasks_yaml = """
tasks:
  - id: t1
    domain: stroke
    question: q?
    expected_database: NHANES
    expected_feasible: true
    rationale: r
"""
        runner = self._runner(tmp_path, tasks_yaml)
        outputs, metadata = runner.run_experiment(dry_run=True, confirm_live=False)
        # Dry run carries an explicit measured-zero telemetry on every output.
        assert all(o.call_telemetry is not None for o in outputs)
        assert all(not o.call_telemetry.model_call_attempted for o in outputs)
        assert all(o.call_telemetry.input_tokens == 0 for o in outputs)
        assert all(o.call_telemetry.claude_cli_reported_cost_usd == 0.0 for o in outputs)
        assert all(o.call_telemetry.estimated_cost_usd == 0.0 for o in outputs)
        eff = metadata["efficiency_summary"]
        assert eff["arm_a"]["model_calls_this_run"] == 0
        assert eff["arm_b"]["model_calls_this_run"] == 0
        assert eff["overall"]["model_calls_this_run"] == 0
        # Structural zeros are MEASURED (available, sum 0), not missing.
        assert eff["arm_a"]["tokens"]["input_tokens"]["sum"] == 0
        assert eff["arm_a"]["tokens"]["input_tokens"]["available"] == 1
        assert eff["arm_a"]["tokens"]["input_tokens"]["missing"] == 0
        assert eff["overall"]["tokens"]["input_tokens"]["sum"] == 0
        assert eff["overall"]["tokens"]["input_tokens"]["available"] == 2
        # Execution design is sequential, not parallel/independent.
        assert metadata["execution_design"]["parallel"] is False
        assert metadata["execution_design"]["statistically_independent"] is False
        assert metadata["arm_b_reuse"]["configured"] is False

    def test_live_call_attaches_telemetry(self, tmp_path):
        # Feasible Arm A: mock generate_plan to return a plan AND set
        # last_call_telemetry on the mock so run_task picks it up.
        tasks_yaml = """
tasks:
  - id: t1
    domain: stroke
    question: Is self-reported stroke associated with metabolic syndrome?
    expected_database: NHANES
    expected_feasible: true
    rationale: r
"""
        runner = self._runner(tmp_path, tasks_yaml)
        task = BenchmarkTask(
            id="t1", domain="stroke",
            question="Is self-reported stroke associated with metabolic syndrome?",
            expected_database="NHANES", expected_feasible=True, rationale="r",
        )
        mock_plan = AnalysisPlan(title="T", question=task.question, database="NHANES",
                                 feasible=True, cycles=[])
        runner.provider_a.generate_plan.return_value = mock_plan
        tel = CallTelemetry(model_call_attempted=True, input_tokens=1234, output_tokens=567)
        runner.provider_a.last_call_telemetry = tel

        out = runner.run_task(task, ProviderArm.ARM_A, runner.provider_a, dry_run=False)
        assert out.call_telemetry is not None
        assert out.call_telemetry.input_tokens == 1234
        assert out.call_telemetry.model_call_attempted is True

    def test_prices_populate_estimated_cost(self, tmp_path):
        tasks_yaml = """
tasks:
  - id: t1
    domain: stroke
    question: Is self-reported stroke associated with metabolic syndrome?
    expected_database: NHANES
    expected_feasible: true
    rationale: r
"""
        res = _minimal_resources(tmp_path, tasks_yaml)
        from unittest.mock import MagicMock
        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=res["tasks"],
                prompt_a_path=res["prompt_a"],
                prompt_b_path=res["prompt_b"],
                registry_path=res["registry"],
                prices={"input": 3.0, "output": 15.0},
            )
        # patch() makes provider_a/provider_b the same Mock instance; assign
        # distinct mocks so each arm reads its own telemetry.
        runner.provider_a = MagicMock()
        runner.provider_b = MagicMock()
        task = runner.tasks[0]
        mock_plan = AnalysisPlan(title="T", question=task.question, database="NHANES",
                                 feasible=True, cycles=[])
        runner.provider_a.generate_plan.return_value = mock_plan
        runner.provider_a.last_call_telemetry = CallTelemetry(
            model_call_attempted=True, input_tokens=1_000_000, output_tokens=500_000
        )
        runner.provider_b.generate_plan.return_value = mock_plan
        runner.provider_b.last_call_telemetry = CallTelemetry(
            model_call_attempted=True, input_tokens=2_000_000, output_tokens=1_000_000
        )

        outputs, metadata = runner.run_experiment(dry_run=False, confirm_live=True)
        a = [o for o in outputs if o.arm == ProviderArm.ARM_A][0]
        b = [o for o in outputs if o.arm == ProviderArm.ARM_B][0]
        # 1M*3/1M + 0.5M*15/1M = 10.5
        assert a.call_telemetry.estimated_cost_usd == pytest.approx(10.5)
        # 2M*3/1M + 1M*15/1M = 21
        assert b.call_telemetry.estimated_cost_usd == pytest.approx(21.0)

        eff = metadata["efficiency_summary"]
        assert eff["arm_a"]["estimated_cost_usd_total"] == pytest.approx(10.5)
        assert eff["overall"]["estimated_cost_usd_total"] == pytest.approx(31.5)
        assert metadata["pricing"]["configured"] is True


# --------------------------------------------------------------------------- #
# Checkpoint / backward compatibility
# --------------------------------------------------------------------------- #

class TestCheckpointCompat:
    def test_old_arm_output_json_validates(self):
        # An ArmOutput dict from before telemetry fields existed must still
        # validate (call_telemetry / reused default to None / False).
        old = {
            "task_id": "t1",
            "arm": "arm_a",
            "provider_type": "claude_code",
            "model_label": "claude-sonnet-4-6",
            "plan": None,
            "error": None,
            "execution_time_seconds": 1.0,
            "timestamp_utc": "2026-06-29T12:00:00Z",
            "raw_output": None,
            "validation_errors": [],
            "guardrail_findings": [],
        }
        out = ArmOutput.model_validate(old)
        assert out.call_telemetry is None
        assert out.reused is False

    def test_checkpoint_round_trips_telemetry(self, tmp_path):
        res = _minimal_resources(tmp_path, "tasks: []")
        checkpoint_file = tmp_path / "checkpoint.json"
        tel = CallTelemetry(model_call_attempted=True, input_tokens=10, output_tokens=5,
                            claude_cli_reported_cost_usd=0.001)
        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            runner = ExperimentRunner(
                tasks_path=res["tasks"], prompt_a_path=res["prompt_a"],
                prompt_b_path=res["prompt_b"], registry_path=res["registry"],
                checkpoint_file=checkpoint_file,
            )
            outputs = [
                ArmOutput(task_id="t1", arm=ProviderArm.ARM_A, provider_type="claude_code",
                          timestamp_utc=datetime.now(timezone.utc).isoformat(),
                          plan=None, error=None, call_telemetry=tel),
            ]
            runner._save_checkpoint({"t1"}, outputs)

            loaded_completed, loaded_outputs = runner._load_checkpoint()
            assert loaded_completed == {"t1"}
            assert len(loaded_outputs) == 1
            assert loaded_outputs[0].call_telemetry is not None
            assert loaded_outputs[0].call_telemetry.input_tokens == 10
            assert loaded_outputs[0].call_telemetry.claude_cli_reported_cost_usd == pytest.approx(0.001)


# --------------------------------------------------------------------------- #
# Offline summarizer
# --------------------------------------------------------------------------- #

class TestOfflineSummary:
    def test_summary_output_files_and_content(self, tmp_path):
        exp_data = {
            "metadata": {
                "model": "claude-sonnet-4-6",
                "total_tasks": 1,
                "execution_design": {"mode": "sequential", "parallel": False,
                                     "statistically_independent": False},
                "arm_b_reuse": {"configured": False},
                "efficiency_summary": build_efficiency_summary(
                    [
                        {"arm": "arm_a", "execution_time_seconds": 3.0,
                         "call_telemetry": {"model_call_attempted": True,
                                            "input_tokens": 1000, "output_tokens": 500},
                         "reused": False},
                        {"arm": "arm_b", "execution_time_seconds": 2.0,
                         "call_telemetry": {"model_call_attempted": True,
                                            "input_tokens": 800, "output_tokens": 400},
                         "reused": False},
                    ],
                    total_tasks=1,
                ),
            },
            "arm_outputs": [
                {"arm": "arm_a", "execution_time_seconds": 3.0,
                 "call_telemetry": {"model_call_attempted": True,
                                    "input_tokens": 1000, "output_tokens": 500},
                 "reused": False},
                {"arm": "arm_b", "execution_time_seconds": 2.0,
                 "call_telemetry": {"model_call_attempted": True,
                                    "input_tokens": 800, "output_tokens": 400},
                 "reused": False},
            ],
        }
        in_path = tmp_path / "exp.json"
        in_path.write_text(json.dumps(exp_data))
        md_path = tmp_path / "out.md"
        json_path = tmp_path / "out.json"

        ret_md, ret_json = summarize_experiment_file(
            input_path=in_path, markdown_path=md_path, json_path=json_path,
            prices={"input": 3.0, "output": 15.0},
            backend_label="glm-5.2 via CC-Switch",
        )
        assert ret_md == md_path
        assert ret_json == json_path
        assert md_path.exists() and json_path.exists()

        md = md_path.read_text(encoding="utf-8")
        # Required caveats present.
        assert "authored development items" in md
        assert "sequentially within a single run" in md
        assert "NOT parallel execution" in md
        assert "NOT a vendor invoice" in md
        # Honest cost naming.
        assert "claude_cli_reported_cost" in md
        # Backend provenance recorded.
        assert "glm-5.2 via CC-Switch" in md
        # Estimated cost populated from caller prices.
        assert "Estimated cost" in md

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["backend_label"] == "glm-5.2 via CC-Switch"
        assert payload["pricing_usd_per_million_tokens"]["input"] == 3.0
        assert payload["efficiency_summary"]["overall"]["model_calls_this_run"] == 2

    def test_summary_missing_telemetry_stays_missing(self, tmp_path):
        # An arm-output whose telemetry is genuinely absent (e.g. an attempted
        # call that captured nothing) must stay MISSING — sum None, not zero.
        exp_data = {
            "metadata": {"model": "claude-sonnet-4-6", "total_tasks": 2},
            "arm_outputs": [
                {"arm": "arm_a", "call_telemetry": None, "reused": False},
                {"arm": "arm_b", "call_telemetry": None, "reused": False},
            ],
        }
        in_path = tmp_path / "exp.json"
        in_path.write_text(json.dumps(exp_data))
        md_path = tmp_path / "out.md"
        json_path = tmp_path / "out.json"
        summarize_experiment_file(in_path, md_path, json_path)

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["efficiency_summary"]["overall"]["model_calls_this_run"] == 0
        # All-missing token sums must be None, not zero.
        assert payload["efficiency_summary"]["arm_a"]["tokens"]["input_tokens"]["sum"] is None
        assert payload["efficiency_summary"]["arm_a"]["tokens"]["input_tokens"]["available"] == 0
        assert payload["efficiency_summary"]["arm_a"]["tokens"]["input_tokens"]["missing"] == 1

    def test_summary_structural_zeros_distinguished_from_missing(self, tmp_path):
        # A real dry run now emits explicit zero-call telemetry. These zeros are
        # MEASURED (available, sum 0), distinct from the missing telemetry above.
        zero_tel = dict(ZERO_CALL_TELEMETRY)
        exp_data = {
            "metadata": {"model": "claude-sonnet-4-6", "total_tasks": 1},
            "arm_outputs": [
                {"arm": "arm_a", "execution_time_seconds": 0.0,
                 "call_telemetry": zero_tel, "reused": False},
                {"arm": "arm_b", "execution_time_seconds": 0.0,
                 "call_telemetry": zero_tel, "reused": False},
            ],
        }
        in_path = tmp_path / "exp.json"
        in_path.write_text(json.dumps(exp_data))
        md_path = tmp_path / "out.md"
        json_path = tmp_path / "out.json"
        summarize_experiment_file(in_path, md_path, json_path)

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        eff = payload["efficiency_summary"]
        assert eff["overall"]["model_calls_this_run"] == 0  # not attempted
        # Structural zeros: sum is 0 (not None) and every field is available.
        for cat in ("input_tokens", "output_tokens",
                    "cache_read_input_tokens", "cache_creation_input_tokens"):
            assert eff["arm_a"]["tokens"][cat]["sum"] == 0
            assert eff["arm_a"]["tokens"][cat]["available"] == 1
            assert eff["arm_a"]["tokens"][cat]["missing"] == 0
        assert eff["arm_a"]["claude_cli_reported_cost_usd_total"] == 0.0
        assert eff["arm_a"]["claude_cli_reported_cost_available"] == 1
        assert eff["arm_a"]["estimated_cost_usd_total"] == 0.0
        assert eff["arm_a"]["estimated_cost_available"] == 1
        # Overall coverage: both arms available, zero missing.
        assert eff["overall"]["tokens"]["input_tokens"]["sum"] == 0
        assert eff["overall"]["tokens"]["input_tokens"]["available"] == 2
        assert eff["overall"]["tokens"]["input_tokens"]["missing"] == 0

    def test_summary_replaces_stale_nested_metadata_efficiency_summary(self, tmp_path):
        """Regression: the emitted summary JSON must carry exactly one,
        consistent, recomputed efficiency summary. The source metadata's stale
        pre-fix nested ``efficiency_summary`` must NOT be copied through.
        """
        arm_outputs = [
            {"arm": "arm_a", "execution_time_seconds": 3.0,
             "call_telemetry": {"model_call_attempted": True,
                                "input_tokens": 1000, "output_tokens": 500},
             "reused": False},
            {"arm": "arm_b", "execution_time_seconds": 2.0,
             "call_telemetry": {"model_call_attempted": True,
                                "input_tokens": 800, "output_tokens": 400},
             "reused": False},
        ]
        # A deliberately stale nested summary that contradicts the real outputs.
        stale_nested = {
            "__stale_marker": True,
            "overall": {"model_calls_this_run": 99999, "sentinel": "pre-fix"},
        }
        exp_data = {
            "metadata": {
                "model": "claude-sonnet-4-6",
                "total_tasks": 1,
                "efficiency_summary": stale_nested,
            },
            "arm_outputs": arm_outputs,
        }
        in_path = tmp_path / "exp.json"
        in_path.write_text(json.dumps(exp_data))
        md_path = tmp_path / "out.md"
        json_path = tmp_path / "out.json"

        summarize_experiment_file(in_path, md_path, json_path)

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        top = payload["efficiency_summary"]
        nested = payload["metadata"]["efficiency_summary"]

        # Exactly one consistent summary: top-level and nested must agree.
        assert top == nested
        # The stale pre-fix value must not survive anywhere in the output.
        assert top != stale_nested
        assert nested != stale_nested
        assert json.dumps(payload).count("__stale_marker") == 0
        # The recomputed value reflects the real outputs (2 attempted calls).
        assert top["overall"]["model_calls_this_run"] == 2


# --------------------------------------------------------------------------- #
# Overall summary completeness + coverage honesty
# --------------------------------------------------------------------------- #

class TestOverallSummary:
    def _full(self, arm, et, inp, out, cli):
        return {
            "arm": arm,
            "execution_time_seconds": et,
            "call_telemetry": {
                "model_call_attempted": True,
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "claude_cli_reported_cost_usd": cli,
                "estimated_cost_usd": None,
            },
            "reused": False,
        }

    def test_overall_has_complete_field_set(self):
        outputs = [
            self._full("arm_a", 4.0, 1000, 500, 0.01),
            self._full("arm_b", 2.0, 800, 400, 0.02),
        ]
        s = build_efficiency_summary(outputs, total_tasks=1)
        o = s["overall"]

        # Required overall scalar fields.
        assert o["total_tasks"] == 1
        assert o["total_task_arm_outputs"] == 2
        assert o["model_calls_this_run"] == 2
        assert o["reused_outputs"] == 0
        assert o["calls_per_task"] == pytest.approx(2.0)

        # Elapsed mean/task + coverage.
        assert o["elapsed_seconds_total"] == pytest.approx(6.0)
        assert o["elapsed_seconds_mean_per_task"] == pytest.approx(3.0)
        assert o["elapsed_available"] == 2
        assert o["elapsed_missing"] == 0

        # All four token categories carry sum + availability + missing.
        for cat, expected_sum in (
            ("input_tokens", 1800),
            ("output_tokens", 900),
            ("cache_read_input_tokens", 0),
            ("cache_creation_input_tokens", 0),
        ):
            t = o["tokens"][cat]
            assert t["sum"] == expected_sum
            assert t["available"] == 2
            assert t["missing"] == 0

        # CLI-reported cost total + coverage.
        assert o["claude_cli_reported_cost_usd_total"] == pytest.approx(0.03)
        assert o["claude_cli_reported_cost_available"] == 2
        assert o["claude_cli_reported_cost_missing"] == 0

        # Estimated cost was None on every output -> total None, all missing.
        assert o["estimated_cost_usd_total"] is None
        assert o["estimated_cost_available"] == 0
        assert o["estimated_cost_missing"] == 2

    def test_one_available_one_missing_arm_shows_coverage(self):
        # arm_a reports cost; arm_b has no telemetry. The overall total must
        # NOT look complete — coverage fields must expose arm_b as missing.
        outputs = [
            self._full("arm_a", 4.0, 1000, 500, 0.01),
            {"arm": "arm_b", "execution_time_seconds": None,
             "call_telemetry": None, "reused": False},
        ]
        s = build_efficiency_summary(outputs, total_tasks=1)
        o = s["overall"]

        # Only arm_a contributes; totals reflect just arm_a.
        assert o["elapsed_seconds_total"] == pytest.approx(4.0)
        assert o["tokens"]["input_tokens"]["sum"] == 1000
        # CLI cost: arm_a reported 0.01, arm_b missing -> INCOMPLETE overall.
        # The total is None; the observed 0.01 is the partial sum.
        assert o["claude_cli_reported_cost_usd_total"] is None
        assert o["claude_cli_reported_cost_usd_partial_sum_usd"] == pytest.approx(0.01)
        assert o["claude_cli_reported_cost_usd_complete"] is False

        # But coverage makes the partial measurement visible, not hidden.
        assert o["elapsed_available"] == 1
        assert o["elapsed_missing"] == 1
        assert o["tokens"]["input_tokens"]["available"] == 1
        assert o["tokens"]["input_tokens"]["missing"] == 1
        assert o["claude_cli_reported_cost_available"] == 1
        assert o["claude_cli_reported_cost_missing"] == 1
        assert o["estimated_cost_available"] == 0
        assert o["estimated_cost_missing"] == 2

    def test_overall_reused_excluded(self):
        outputs = [
            self._full("arm_a", 1.0, 10, 5, 0.001),
            {**self._full("arm_b", 9.0, 999, 99, 9.99), "reused": True},
        ]
        s = build_efficiency_summary(outputs, total_tasks=1)
        o = s["overall"]
        # arm_b is reused -> excluded from this-run totals everywhere.
        assert o["reused_outputs"] == 1
        assert o["model_calls_this_run"] == 1
        assert o["elapsed_seconds_total"] == pytest.approx(1.0)
        assert o["tokens"]["input_tokens"]["sum"] == 10
        assert o["claude_cli_reported_cost_usd_total"] == pytest.approx(0.001)


# --------------------------------------------------------------------------- #
# Regression: incomplete cost totals must never display as $0
# --------------------------------------------------------------------------- #

class TestIncompleteCostRegression:
    """Reproduces the pilot_glm52_concurrent_cost_v03 reporting bug.

    The live run had 13 attempted model calls whose ``estimated_cost_usd`` was
    missing (no explicit price table supplied) plus 7 deterministic zero-call
    outputs whose estimated cost is a structural 0.0. The old aggregation summed
    the seven zeros and printed ``Estimated cost (overall): $0.000000`` even
    though 13/20 outputs were missing. The fix requires ``*_total`` to be None
    whenever any non-reused output is missing the field, with the observed
    ``*_partial_sum_usd`` and a ``*_complete`` flag making the gap explicit.
    """

    def _live_pattern_outputs(self) -> list[dict]:
        zero_tel = dict(ZERO_CALL_TELEMETRY)  # estimated_cost_usd == 0.0 (measured)
        attempted_tel = {
            "model_call_attempted": True,
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
            "claude_cli_reported_cost_usd": 0.01,
            "estimated_cost_usd": None,  # missing: no price table supplied
        }
        outputs: list[dict] = []
        # 7 structural-zero outputs split across arms.
        for arm in (["arm_a"] * 4 + ["arm_b"] * 3):
            outputs.append({
                "arm": arm, "execution_time_seconds": 0.0,
                "call_telemetry": dict(zero_tel), "reused": False,
            })
        # 13 attempted calls whose estimated cost is missing.
        for arm in (["arm_a"] * 6 + ["arm_b"] * 7):
            outputs.append({
                "arm": arm, "execution_time_seconds": 2.0,
                "call_telemetry": dict(attempted_tel), "reused": False,
            })
        return outputs

    def test_live_pattern_estimated_cost_total_is_none_with_partial_zero(self):
        outputs = self._live_pattern_outputs()
        s = build_efficiency_summary(outputs, total_tasks=10)
        o = s["overall"]

        # Estimated cost: 7 structural zeros available, 13 missing -> incomplete.
        assert o["estimated_cost_usd_total"] is None
        # The observed partial sum is 0.0 (seven measured zeros), NOT a total.
        assert o["estimated_cost_usd_partial_sum_usd"] == 0.0
        assert o["estimated_cost_usd_complete"] is False
        assert o["estimated_cost_available"] == 7
        assert o["estimated_cost_missing"] == 13

    def test_live_pattern_cli_cost_complete_when_all_reported(self):
        # In the live run, CLI-reported cost WAS fully available (13 calls plus
        # 7 structural zeros all reported it) -> a complete total is fine here.
        outputs = self._live_pattern_outputs()
        o = build_efficiency_summary(outputs, total_tasks=10)["overall"]
        assert o["claude_cli_reported_cost_usd_complete"] is True
        # 13 attempted * 0.01 + 7 zeros = 0.13
        assert o["claude_cli_reported_cost_usd_total"] == pytest.approx(0.13)
        assert o["claude_cli_reported_cost_usd_partial_sum_usd"] == pytest.approx(0.13)
        assert o["claude_cli_reported_cost_missing"] == 0

    def test_live_pattern_report_never_shows_estimated_total_as_zero(self):
        outputs = self._live_pattern_outputs()
        s = build_efficiency_summary(outputs, total_tasks=10)
        md = render_efficiency_markdown(
            {"metadata": {"model": "claude-sonnet-4-6", "total_tasks": 10}}, s,
        )
        # The incomplete estimated cost must never read as a $0 total.
        assert "Estimated cost (overall): $0.000000" not in md
        # The partial observed sum is shown only with the word 'partial'.
        assert "incomplete" in md.lower()
        assert "partial" in md.lower()
        # Coverage counts must be the real ones, not 0 from a key-prefix bug.
        assert "over 7 reported, 13 missing" in md

    def test_cli_reported_cost_also_incomplete_when_missing(self):
        # Requirement: the same completeness semantics apply to CLI-reported cost
        # when it has missing outputs (not only to estimated cost).
        outputs = [
            {"arm": "arm_a", "execution_time_seconds": 1.0,
             "call_telemetry": {"model_call_attempted": True,
                                "claude_cli_reported_cost_usd": 0.05,
                                "estimated_cost_usd": None}, "reused": False},
            {"arm": "arm_b", "execution_time_seconds": 1.0,
             "call_telemetry": {"model_call_attempted": True,
                                "claude_cli_reported_cost_usd": None,
                                "estimated_cost_usd": None}, "reused": False},
        ]
        o = build_efficiency_summary(outputs, total_tasks=1)["overall"]
        assert o["claude_cli_reported_cost_usd_complete"] is False
        assert o["claude_cli_reported_cost_usd_total"] is None
        assert o["claude_cli_reported_cost_usd_partial_sum_usd"] == pytest.approx(0.05)
        assert o["claude_cli_reported_cost_available"] == 1
        assert o["claude_cli_reported_cost_missing"] == 1

    def test_genuine_all_zero_total_is_complete_zero(self):
        # Requirement #4: if every measured output reports cost (including
        # genuine structural zeros), the total may legitimately be 0.
        zero_tel = dict(ZERO_CALL_TELEMETRY)
        outputs = [
            {"arm": "arm_a", "execution_time_seconds": 0.0,
             "call_telemetry": dict(zero_tel), "reused": False},
            {"arm": "arm_b", "execution_time_seconds": 0.0,
             "call_telemetry": dict(zero_tel), "reused": False},
        ]
        o = build_efficiency_summary(outputs, total_tasks=1)["overall"]
        assert o["estimated_cost_usd_complete"] is True
        assert o["estimated_cost_usd_total"] == 0.0
        assert o["estimated_cost_usd_partial_sum_usd"] == 0.0
        assert o["estimated_cost_missing"] == 0


# --------------------------------------------------------------------------- #
# Price calculation + missing-rate behavior in the summary
# --------------------------------------------------------------------------- #

class TestPriceCalculationInSummary:
    def test_missing_rate_marks_estimated_cost_missing(self):
        # Output has nonzero input+output tokens but only an input rate is
        # supplied -> estimated cost is None and counts as missing.
        outputs = [{
            "arm": "arm_a",
            "execution_time_seconds": 1.0,
            "call_telemetry": {
                "model_call_attempted": True,
                "input_tokens": 1_000_000,
                "output_tokens": 500_000,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "claude_cli_reported_cost_usd": None,
                "estimated_cost_usd": None,
            },
            "reused": False,
        }]
        s = build_efficiency_summary(outputs, total_tasks=1,
                                     prices={"input": 3.0})  # no output rate
        arm_a = s["arm_a"]
        # estimate_cost returns None because the output rate is missing.
        assert arm_a["estimated_cost_usd_total"] is None
        assert arm_a["estimated_cost_available"] == 0
        assert arm_a["estimated_cost_missing"] == 1

    def test_all_rates_supplied_sums_estimated_cost(self):
        outputs = [{
            "arm": "arm_a",
            "execution_time_seconds": 1.0,
            "call_telemetry": {
                "model_call_attempted": True,
                "input_tokens": 1_000_000,
                "output_tokens": 500_000,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "claude_cli_reported_cost_usd": None,
                "estimated_cost_usd": None,
            },
            "reused": False,
        }]
        s = build_efficiency_summary(
            outputs, total_tasks=1, prices={"input": 3.0, "output": 15.0}
        )
        # 1M*3/1M + 0.5M*15/1M = 10.5
        assert s["arm_a"]["estimated_cost_usd_total"] == pytest.approx(10.5)
        assert s["arm_a"]["estimated_cost_available"] == 1


# --------------------------------------------------------------------------- #
# Price validation (run-pilot + offline paths + CLI)
# --------------------------------------------------------------------------- #

class TestPriceValidation:
    def test_validate_prices_rejects_negative(self):
        with pytest.raises(ValueError):
            validate_prices({"input": -1.0})

    def test_validate_prices_rejects_nonfinite(self):
        with pytest.raises(ValueError):
            validate_prices({"input": float("nan")})
        with pytest.raises(ValueError):
            validate_prices({"output": float("inf")})

    def test_validate_prices_permits_zero_and_none(self):
        # Zero is a genuine free category; None means "not supplied".
        assert validate_prices({"input": 0.0, "output": None}) == {
            "input": 0.0, "output": None
        }

    def test_validate_prices_none_passes_through(self):
        assert validate_prices(None) is None

    def test_runner_rejects_invalid_prices(self, tmp_path):
        # The run-pilot path validates at ExperimentRunner construction.
        res = _minimal_resources(tmp_path, "tasks: []")
        with patch("neurosurg_epi_agent.experiment.ClaudeCodePlannerProvider"):
            with pytest.raises(ValueError):
                ExperimentRunner(
                    tasks_path=res["tasks"], prompt_a_path=res["prompt_a"],
                    prompt_b_path=res["prompt_b"], registry_path=res["registry"],
                    prices={"input": -5.0},
                )

    def test_offline_summarizer_rejects_invalid_prices(self, tmp_path):
        # The offline-summary path validates before reading outputs.
        in_path = tmp_path / "exp.json"
        in_path.write_text(json.dumps({"metadata": {}, "arm_outputs": []}))
        with pytest.raises(ValueError):
            summarize_experiment_file(
                input_path=in_path,
                markdown_path=tmp_path / "o.md",
                json_path=tmp_path / "o.json",
                prices={"input": float("nan")},
            )

    def test_cli_efficiency_summary_rejects_negative_price(self, tmp_path):
        from neurosurg_epi_agent.cli import main

        in_path = tmp_path / "exp.json"
        in_path.write_text(json.dumps({"metadata": {}, "arm_outputs": []}))
        rc = main([
            "efficiency-summary",
            "--input", str(in_path),
            "--markdown-output", str(tmp_path / "o.md"),
            "--json-output", str(tmp_path / "o.json"),
            "--price-input", "-1.0",
        ])
        assert rc == 2

    def test_cli_run_pilot_rejects_negative_price(self, tmp_path):
        from neurosurg_epi_agent.cli import main

        res = _minimal_resources(tmp_path, "tasks: []")
        rc = main([
            "run-pilot",
            "--tasks", str(res["tasks"]),
            "--registry", str(res["registry"]),
            "--prompt-a", str(res["prompt_a"]),
            "--prompt-b", str(res["prompt_b"]),
            "--output", str(tmp_path / "out.json"),
            "--dry-run",
            "--price-output", "-2.5",
        ])
        assert rc == 2
        assert not (tmp_path / "out.json").exists()

