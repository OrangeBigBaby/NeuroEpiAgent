"""Tests for the synthetic CDC WONDER case study.

The case study under test is fully synthetic; the tests verify that the
disclosure posture (Suppressed dropped, Unreliable flagged) holds and that
the artifacts are emitted to the requested output directory.
"""

from __future__ import annotations

import json
from pathlib import Path

from neurosurg_epi_agent.case_studies import cdc_wonder_synthetic_demo as demo
from neurosurg_epi_agent.case_studies.cdc_wonder_synthetic_demo import (
    SUPPRESSED_MAX_DEATHS,
    UNRELIABLE_MAX_DEATHS,
    annotate_rows,
    disclosure_status,
    run_case_study,
)


class TestDisclosureStatus:
    def test_zero_or_under_nine_is_suppressed(self):
        for d in range(0, SUPPRESSED_MAX_DEATHS + 1):
            assert disclosure_status(d) == "Suppressed"

    def test_ten_through_nineteen_is_unreliable(self):
        for d in range(SUPPRESSED_MAX_DEATHS + 1, UNRELIABLE_MAX_DEATHS + 1):
            assert disclosure_status(d) == "Unreliable"

    def test_twenty_or_more_is_ok(self):
        for d in (UNRELIABLE_MAX_DEATHS + 1, 100, 100_000):
            assert disclosure_status(d) == "OK"


class TestAnnotateRows:
    def test_suppressed_rows_are_dropped(self):
        rows = ((2018, 5, "UCD", "Underlying"),)
        annotated = annotate_rows(rows)
        assert annotated == []

    def test_unreliable_rows_are_kept_with_flag(self):
        rows = ((2018, 15, "UCD", "Underlying"),)
        annotated = annotate_rows(rows)
        assert len(annotated) == 1
        assert annotated[0]["disclosure_status"] == "Unreliable"

    def test_database_family_propagated(self):
        rows = (
            (2018, 100, "Underlying Cause of Death, 2018-2024", "UCD"),
            (2018, 100, "Multiple Cause of Death, 2018-2024", "MCD"),
        )
        annotated = annotate_rows(rows)
        families = {r["database_family"] for r in annotated}
        assert families == {"UCD", "MCD"}


class TestRunCaseStudy:
    def test_writes_three_artifacts(self, tmp_path):
        out = tmp_path / "results"
        paths = run_case_study(out, seed=2026)
        assert (out / "results.json").exists()
        assert (out / "provenance.json").exists()
        assert (out / "report.md").exists()
        for label, p in paths.items():
            assert p.exists()

    def test_results_never_carry_suppressed_cell(self, tmp_path):
        out = tmp_path / "results"
        run_case_study(out, seed=2026)
        payload = json.loads((out / "results.json").read_text(encoding="utf-8"))
        # No annotated row is allowed to have a death count <= 9.
        for row in payload["annotated_rows"]:
            assert row["deaths"] > SUPPRESSED_MAX_DEATHS, row
        # Disclosure counts must reflect the dropped row.
        assert payload["disclosure_counts"]["Suppressed_dropped"] >= 1

    def test_provenance_records_python_and_versions(self, tmp_path):
        out = tmp_path / "results"
        run_case_study(out, seed=2026)
        prov = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
        assert prov["python_version"]
        assert "0.2.0" in prov["package_versions"]["neurosurg_epi_agent"]
        assert prov["random_seed"] == 2026

    def test_report_markdown_is_conservative_language(self, tmp_path):
        out = tmp_path / "results"
        run_case_study(out, seed=2026)
        report = (out / "report.md").read_text(encoding="utf-8")
        for forbidden in (
            "proves", "causes", "first ever", "comprehensive", "unprecedented",
        ):
            assert forbidden.lower() not in report.lower(), (
                f"forbidden language {forbidden!r} appeared in report.md"
            )

    def test_no_absolute_path_in_outputs(self, tmp_path):
        out = tmp_path / "results"
        # Use a path that contains a user-style subdirectory; we still
        # require no path leakage.
        run_case_study(out, seed=2026)
        for fn in ("results.json", "provenance.json", "report.md"):
            text = (out / fn).read_text(encoding="utf-8")
            assert str(out).replace("\\", "/") not in text
            assert str(out) not in text


def test_module_is_discoverable():
    # The case study must be importable as a submodule.
    assert hasattr(demo, "run_case_study")