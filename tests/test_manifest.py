from pathlib import Path

import yaml

from neurosurg_epi_agent.manifest import build_manifest, write_manifest
from neurosurg_epi_agent.schemas import AnalysisPlan, PlanStep, VariableMapping, VariableStatus

CONFIG = Path(__file__).resolve().parents[1] / "config"


def _clean_plan():
    return AnalysisPlan(
        title="demo plan",
        question="q",
        database="NHANES",
        cycles=["G", "H", "I", "J"],
        design_vars={"id": "SDMVPSU", "strata": "SDMVSTRA", "weight": "WTMEC2YR/4"},
        outcome=VariableMapping(name="stroke", label="Stroke", source_variable="MCQ160F",
                                source_module="MCQ", status=VariableStatus.ILLUSTRATIVE),
        steps=[PlanStep(step="1", description="merge")],
    )


def test_manifest_records_findings_and_provenance():
    plan = _clean_plan()
    m = build_manifest(plan)
    assert m.database == "NHANES"
    assert m.cycles == ["G", "H", "I", "J"]
    assert m.variables[0]["name"] == "stroke"
    assert m.variables[0]["status"] == "illustrative"
    assert m.n_warnings >= 1  # illustrative outcome -> warning
    assert m.n_errors == 0
    # no fabricated results
    assert any("no statistical estimates" in n for n in m.notes)


def test_manifest_write_roundtrip(tmp_path):
    plan = _clean_plan()
    m = build_manifest(plan)
    out = write_manifest(m, tmp_path / "out" / "manifest.yaml")
    assert out.exists()
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["database"] == "NHANES"
    assert "content_sha256_short" in data
    assert len(data["content_sha256_short"]) == 16


def test_manifest_with_failed_plan_counts_errors(tmp_path):
    plan = AnalysisPlan(
        title="bad", question="q", database="NHANES", cycles=["G", "H"],
        design_vars={},
        causal_claims=["This proves everything."],
        outcome=VariableMapping(name="x", label="X", source_variable="LBXTC",
                                source_module="LAB", status=VariableStatus.NEEDS_REVIEW),
    )
    m = build_manifest(plan)
    assert m.n_errors >= 1
