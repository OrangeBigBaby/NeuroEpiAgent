"""CDC WONDER adapter tests.

CDC WONDER exports are public aggregated CSVs (no pandas needed — the adapter
parses with the stdlib ``csv`` module), so these tests run in the minimal
install. All data here is SYNTHETIC; a sentinel death count is planted in the
data rows to prove the adapter is metadata-only and never carries cell values
into its output.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from neurosurg_epi_agent.adapters import CDCWonderAdapter, default_registry
from neurosurg_epi_agent.adapters.cdc_wonder import parse_wonder_csv
from neurosurg_epi_agent.cli import main as cli_main

# A synthetic death count planted in a data row. It must NEVER appear in the
# metadata output (the adapter emits schema + provenance, not cell values).
SENTINEL = 9999937


def _wonder_csv(
    *,
    dataset: str = "Underlying Cause of Death, 2018-2024, Single Race",
    cause_line: str = '"ICD-10 113 Cause List: #Cerebrovascular diseases (I60-I69)"',
    rows: tuple[tuple[str, int], ...] = (("2018", SENTINEL), ("2019", 200)),
) -> bytes:
    """Build a minimal but structurally faithful WONDER export as bytes."""
    data_lines = [
        '"Notes","Year","Year Code",Deaths,Population,Crude Rate,'
        'Crude Rate Lower 95% Confidence Interval,Crude Rate Upper 95% Confidence Interval,'
        "Age Adjusted Rate,Age Adjusted Rate Lower 95% Confidence Interval,"
        'Age Adjusted Rate Upper 95% Confidence Interval'
    ]
    for year, deaths in rows:
        data_lines.append(
            f',"{year}","{year}",{deaths},300000000,5.0,4.9,5.1,4.0,3.9,4.1'
        )
    meta = [
        '"---"',
        f'"Dataset: {dataset}"',
        '"Query Parameters:"',
        cause_line,
        '"Group By: Year"',
        '"Show Totals: False"',
        '"Show Zero Values: False"',
        '"Show Suppressed: False"',
        '"Standard Population: 2000 U.S. Std. Population"',
        '"Calculate Rates Per: 100,000"',
        '"Rate Options: Default intercensal populations for years 2001-2009 (except Infant Age Groups)"',
        '"---"',
        '"Help: See http://wonder.cdc.gov/wonder/help/ucd-expanded.html for more information."',
        '"---"',
        '"Query Date: Jul 1, 2026 11:05:05 AM"',
        '"---"',
        '"Suggested Citation: Centers for Disease Control and Prevention, NCHS. Accessed on Jul 1, 2026."',
        '"---"',
        "Caveats:",
        '"1. Synthetic caveat line for tests only."',
    ]
    return ("\n".join(data_lines + meta) + "\n").encode("utf-8")


def _assert_no_leak(payload: dict, real_root: Path) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert payload["data_root"] == "<user-supplied>"
    assert str(real_root) not in text
    assert str(real_root).replace("\\", "/") not in text
    # Metadata-only: the planted cell value never appears in the inventory.
    assert str(SENTINEL) not in text


# --------------------------------------------------------------------------- #
# parse_wonder_csv unit behavior
# --------------------------------------------------------------------------- #

class TestParseWonderCsv:
    def test_ucd_export_parsed(self):
        parsed = parse_wonder_csv(_wonder_csv())
        assert parsed["recognized"] is True
        assert parsed["row_count"] == 2
        assert parsed["columns"][0] == "Notes"
        assert "Deaths" in parsed["columns"]
        prov = parsed["provenance"]
        assert prov["dataset"] == "Underlying Cause of Death, 2018-2024, Single Race"
        assert prov["cause"] == "#Cerebrovascular diseases (I60-I69)"
        assert prov["group_by"] == "Year"
        assert prov["query_date"] == "Jul 1, 2026 11:05:05 AM"
        assert prov["database_family"] == "UCD"
        assert prov["years"] == "2018-2019"
        assert "Deaths" in prov["measures"]

    def test_mcd_export_detected(self):
        raw = _wonder_csv(
            dataset="Multiple Cause of Death, 1999-2020",
            cause_line='"ICD-10 Codes: S06 (Intracranial injury)"',
        )
        prov = parse_wonder_csv(raw)["provenance"]
        assert prov["database_family"] == "MCD"
        assert prov["cause"] == "S06 (Intracranial injury)"

    def test_non_wonder_csv_not_recognized_but_still_inventoried(self):
        raw = b"a,b,c\n1,2,3\n4,5,6\n"
        parsed = parse_wonder_csv(raw)
        assert parsed["recognized"] is False
        assert parsed["row_count"] == 2
        assert parsed["columns"] == ["a", "b", "c"]
        assert parsed["provenance"] == {}

    def test_trailing_space_in_year_trimmed(self):
        # WONDER emits "2024 " with a trailing space; year-range must be clean.
        raw = _wonder_csv(rows=(("2024 ", 150), ("2018", 140)))
        assert parse_wonder_csv(raw)["provenance"]["years"] == "2018-2024"


# --------------------------------------------------------------------------- #
# Adapter inspect() happy path + security posture
# --------------------------------------------------------------------------- #

class TestCDCWonderInspect:
    def test_single_csv_in_root(self, tmp_path):
        root = tmp_path
        (root / "wonder_stroke_us.csv").write_bytes(_wonder_csv())
        payload = CDCWonderAdapter().inspect(root).to_dict()

        assert payload["data_root"] == "<user-supplied>"
        assert payload["archives"] == []
        assert len(payload["direct_files"]) == 1
        mm = payload["direct_files"][0]
        assert mm["member_name"] == "wonder_stroke_us.csv"
        assert mm["member_path"] == "wonder_stroke_us.csv"
        assert mm["format"] == "wonder-csv"
        assert len(mm["sha256"]) == 64
        assert mm["row_count"] == 2
        assert mm["column_count"] == 11
        assert {v["name"] for v in mm["variables"]} >= {"Year", "Deaths", "Age Adjusted Rate"}
        assert mm["provenance"]["recognized"] == "true"
        assert mm["provenance"]["database_family"] == "UCD"
        assert mm["dataset_label"].startswith("Underlying Cause of Death")
        _assert_no_leak(payload, root)

    def test_sha256_matches_file_bytes(self, tmp_path):
        root = tmp_path
        raw = _wonder_csv()
        (root / "x.csv").write_bytes(raw)
        payload = CDCWonderAdapter().inspect(root).to_dict()
        assert payload["direct_files"][0]["sha256"] == hashlib.sha256(raw).hexdigest()

    def test_multiple_csvs_each_inventoried(self, tmp_path):
        root = tmp_path
        (root / "stroke.csv").write_bytes(_wonder_csv())
        (root / "tumor.csv").write_bytes(_wonder_csv(
            cause_line='"ICD-10 113 Cause List: Malignant neoplasms of meninges, brain and other parts of central nervous system (C70-C72)"',
        ))
        payload = CDCWonderAdapter().inspect(root).to_dict()
        names = sorted(m["member_name"] for m in payload["direct_files"])
        assert names == ["stroke.csv", "tumor.csv"]
        causes = {m["member_name"]: m["provenance"]["cause"] for m in payload["direct_files"]}
        assert "C70-C72" in causes["tumor.csv"]
        assert "I60-I69" in causes["stroke.csv"]

    def test_non_csv_skipped(self, tmp_path):
        root = tmp_path
        (root / "wonder.csv").write_bytes(_wonder_csv())
        (root / "readme.txt").write_text("hi")
        payload = CDCWonderAdapter().inspect(root).to_dict()
        assert [m["member_name"] for m in payload["direct_files"]] == ["wonder.csv"]
        assert payload["skipped_roots"][0]["member_name"] == "readme.txt"
        assert "unsupported file type" in payload["skipped_roots"][0]["reason"]

    def test_oversize_csv_skipped_before_read(self, tmp_path):
        root = tmp_path
        (root / "big.csv").write_bytes(_wonder_csv())
        payload = CDCWonderAdapter().inspect(root, max_member_bytes=10).to_dict()
        assert payload["direct_files"] == []
        assert len(payload["skipped_roots"]) == 1
        assert payload["skipped_roots"][0]["reason"].startswith("size ")

    def test_single_file_root(self, tmp_path):
        csv_path = tmp_path / "solo.csv"
        csv_path.write_bytes(_wonder_csv())
        payload = CDCWonderAdapter().inspect(csv_path).to_dict()
        assert len(payload["direct_files"]) == 1
        assert payload["direct_files"][0]["member_name"] == "solo.csv"

    def test_members_filter(self, tmp_path):
        root = tmp_path
        (root / "a.csv").write_bytes(_wonder_csv())
        (root / "b.csv").write_bytes(_wonder_csv())
        payload = CDCWonderAdapter().inspect(root, members={"a.csv"}).to_dict()
        assert [m["member_name"] for m in payload["direct_files"]] == ["a.csv"]


# --------------------------------------------------------------------------- #
# Symlink escape (skipped where the OS cannot create symlinks)
# --------------------------------------------------------------------------- #

class TestSymlinks:
    def test_symlinked_file_not_followed(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "_outside"
        outside.mkdir()
        target = outside / "secret.csv"
        target.write_bytes(_wonder_csv())
        link = root / "leak.csv"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("not supported on this platform/privilege — trivially inert")
        payload = CDCWonderAdapter().inspect(root).to_dict()
        assert payload["direct_files"] == []
        assert "leak.csv" in [s["member_name"] for s in payload["skipped_roots"]]
        secret_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        assert secret_hash not in json.dumps(payload)

    def test_symlink_recorded_without_os_symlink_support(self, tmp_path, monkeypatch):
        # Regression guard for the CI failure: on runners that support
        # symlinks, a symlinked file must be recorded in skipped_roots rather
        # than silently dropped by _walk_files. Force is_symlink()==True so the
        # path runs on hosts that cannot otherwise create symlinks.
        import pathlib
        root = tmp_path / "root"
        root.mkdir()
        fake = root / "looks_like_symlink.csv"
        fake.write_bytes(_wonder_csv())
        target = str(fake)
        orig = pathlib.Path.is_symlink

        def patched_is_symlink(self):
            return True if str(self) == target else orig(self)

        monkeypatch.setattr(pathlib.Path, "is_symlink", patched_is_symlink)
        payload = CDCWonderAdapter().inspect(root).to_dict()
        assert payload["direct_files"] == []
        assert "looks_like_symlink.csv" in [
            s["member_name"] for s in payload["skipped_roots"]
        ]


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

class TestDeterminism:
    def test_repeat_inspection_byte_identical(self, tmp_path):
        root = tmp_path
        (root / "a.csv").write_bytes(_wonder_csv())
        (root / "sub").mkdir()
        (root / "sub" / "b.csv").write_bytes(_wonder_csv())
        a = CDCWonderAdapter().inspect(root).to_dict()
        b = CDCWonderAdapter().inspect(root).to_dict()
        assert json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(
            b, sort_keys=True, ensure_ascii=False
        )


# --------------------------------------------------------------------------- #
# CLI: inspect-database --database CDC_WONDER
# --------------------------------------------------------------------------- #

class TestInspectDatabaseCLI:
    def test_cli_happy_path(self, tmp_path):
        root = tmp_path / "data"
        root.mkdir()
        (root / "wonder_stroke_us.csv").write_bytes(_wonder_csv())
        out = tmp_path / "out.json"
        rc = cli_main([
            "inspect-database",
            "--database", "CDC_WONDER",
            "--data-root", str(root),
            "--output", str(out),
        ])
        assert rc == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["data_root"] == "<user-supplied>"
        assert str(root) not in out.read_text(encoding="utf-8")
        assert len(payload["direct_files"]) == 1
        assert payload["direct_files"][0]["provenance"]["recognized"] == "true"
        assert str(SENTINEL) not in out.read_text(encoding="utf-8")

    def test_cli_in_default_registry(self, tmp_path):
        # CDC_WONDER is a first-class member of the default registry.
        assert "CDC_WONDER" in default_registry().names()


# --------------------------------------------------------------------------- #
# Disclosure guardrails — synthetic fixtures that exercise the cell-status
# re-enforcement code paths. Every fixture is fully synthetic.
# --------------------------------------------------------------------------- #

class TestDisclosureGuardrails:
    """These tests prove the adapter's disclosure posture: it counts and
    buckets WONDER Notes statuses without ever returning a participant cell
    value, and it never tries to recover a Suppressed count."""

    def _wonder_csv_with_notes(self, *, notes_values, rows, dataset="Underlying Cause of Death, 2018-2024, Single Race") -> bytes:
        header = (
            '"Notes","Year","Year Code",Deaths,Population,Crude Rate,'
            'Crude Rate Lower 95% Confidence Interval,Crude Rate Upper 95% Confidence Interval,'
            "Age Adjusted Rate,Age Adjusted Rate Lower 95% Confidence Interval,"
            'Age Adjusted Rate Upper 95% Confidence Interval'
        )
        data_lines = [header]
        for note, year, deaths in rows:
            data_lines.append(
                f'"{note}","{year}","{year}",{deaths},300000000,5.0,4.9,5.1,4.0,3.9,4.1'
            )
        meta = [
            '"---"',
            f'"Dataset: {dataset}"',
            '"Query Parameters:"',
            '"ICD-10 113 Cause List: #Cerebrovascular diseases (I60-I69)"',
            '"Group By: Year"',
            '"Show Totals: False"',
            '"Show Zero Values: False"',
            '"Show Suppressed: False"',
            '"Standard Population: 2000 U.S. Std. Population"',
            '"Calculate Rates Per: 100,000"',
            '"Rate Options: Default intercensal populations"',
            '"---"',
            '"Query Date: Jul 1, 2026 11:05:05 AM"',
            '"---"',
            '"Suggested Citation: Centers for Disease Control and Prevention, NCHS."',
            '"---"',
            "Caveats:",
            '"1. Synthetic caveat."',
        ]
        return ("\n".join(data_lines + meta) + "\n").encode("utf-8")

    def test_suppressed_cells_are_counted_not_recovered(self, tmp_path):
        # WONDER writes "Suppressed" in the Notes column when Deaths <= 9.
        # The adapter should count these rows and propagate the phrase;
        # it must NEVER try to recover the underlying cell value.
        raw = self._wonder_csv_with_notes(
            notes_values=(),
            rows=[
                ("Suppressed", "2018", 0),  # WONDER leaves the cell at 0 / blank
                ("", "2019", 200),
            ],
        )
        (tmp_path / "x.csv").write_bytes(raw)
        payload = CDCWonderAdapter().inspect(tmp_path).to_dict()
        prov = payload["direct_files"][0]["provenance"]
        assert prov["suppressed_row_count"] == "1"
        # Phrase must be propagated verbatim — no rewrites.
        assert "Suppressed" in prov["notes_phrases"]

    def test_unreliable_rates_for_deaths_lt_20(self, tmp_path):
        # Deaths < 20 = WONDER "Unreliable" rows.
        raw = self._wonder_csv_with_notes(
            notes_values=(),
            rows=[
                ("Unreliable", "2018", 15),
                ("", "2019", 200),
            ],
        )
        (tmp_path / "x.csv").write_bytes(raw)
        payload = CDCWonderAdapter().inspect(tmp_path).to_dict()
        prov = payload["direct_files"][0]["provenance"]
        assert prov["unreliable_row_count"] == "1"
        assert prov["deaths_lt_20_row_count"] == "1"

    def test_malformed_footer_does_not_crash(self, tmp_path):
        # A truncated export that stops mid-data with no provenance block:
        # the adapter should still inventory columns + row count and emit
        # recognized=False so downstream tooling can react.
        bad = b'"Notes","Year","Deaths"\n"Something","2018",100\n'
        (tmp_path / "broken.csv").write_bytes(bad)
        payload = CDCWonderAdapter().inspect(tmp_path).to_dict()
        mm = payload["direct_files"][0]
        assert mm["provenance"]["recognized"] == "false"
        assert mm["row_count"] == 1
        # No provenance captured → query params stay empty, not invented.
        assert mm["provenance"].get("dataset", "") == ""

    def test_missing_query_parameters_recorded(self, tmp_path):
        # An export with a Dataset line but no Query Parameters block.
        header = '"Notes","Year","Year Code",Deaths,Population'
        rows = "\n".join([
            header,
            ',"2018","2018",100,300000000',
            ',"2019","2019",120,300000000',
            '"---"',
            '"Dataset: Underlying Cause of Death, 2018-2024"',
            "Caveats:",
            '"1. Truncated export."',
        ]).encode("utf-8")
        (tmp_path / "no_params.csv").write_bytes(rows)
        payload = CDCWonderAdapter().inspect(tmp_path).to_dict()
        prov = payload["direct_files"][0]["provenance"]
        assert prov["dataset"].startswith("Underlying")
        # No cause / group_by / standard_population → stays empty, never guessed.
        assert prov.get("cause", "") == ""
        assert prov.get("group_by", "") == ""
        assert prov.get("standard_population", "") == ""

    def test_ucd_vs_mcd_distinction_preserved(self, tmp_path):
        # Two files, one UCD and one MCD. Provenance must clearly differentiate
        # so a downstream artifact never silently mixes them.
        ucd_raw = self._wonder_csv_with_notes(
            notes_values=(),
            rows=[("", "2018", 200)],
            dataset="Underlying Cause of Death, 2018-2024, Single Race",
        )
        mcd_raw = self._wonder_csv_with_notes(
            notes_values=(),
            rows=[("", "2018", 350)],
            dataset="Multiple Cause of Death, 2018-2024",
        )
        (tmp_path / "ucd.csv").write_bytes(ucd_raw)
        (tmp_path / "mcd.csv").write_bytes(mcd_raw)
        payload = CDCWonderAdapter().inspect(tmp_path).to_dict()
        by_name = {m["member_name"]: m for m in payload["direct_files"]}
        assert by_name["ucd.csv"]["provenance"]["database_family"] == "UCD"
        assert by_name["mcd.csv"]["provenance"]["database_family"] == "MCD"
        # Both should have a dataset_version captured.
        assert by_name["ucd.csv"]["provenance"]["dataset_version"].startswith("Underlying")
        assert by_name["mcd.csv"]["provenance"]["dataset_version"].startswith("Multiple")

    def test_filename_anomaly_recorded_not_renamed(self, tmp_path):
        raw = self._wonder_csv_with_notes(
            notes_values=(),
            rows=[("", "2018", 100)],
        )
        # Doubled .csv suffix — recorded as a filename_note, not rewritten.
        (tmp_path / "wonder_neuro_injury_us.csv.csv").write_bytes(raw)
        payload = CDCWonderAdapter().inspect(tmp_path).to_dict()
        mm = payload["direct_files"][0]
        assert mm["member_name"] == "wonder_neuro_injury_us.csv.csv"
        assert "filename_note" in mm["provenance"]
        assert ".csv.csv" in mm["provenance"]["filename_note"]
        # SHA-256 reflects the bytes as stored under that exact name.
        assert len(mm["sha256"]) == 64

    def test_no_absolute_path_leak_in_disclosure_section(self, tmp_path):
        # Belt-and-suspenders: the disclosure summary, like the rest of the
        # metadata, must never embed the caller's real data_root path.
        raw = self._wonder_csv_with_notes(
            notes_values=(),
            rows=[
                ("Suppressed", "2018", 0),
                ("Unreliable", "2019", 15),
            ],
        )
        (tmp_path / "x.csv").write_bytes(raw)
        payload = CDCWonderAdapter().inspect(tmp_path).to_dict()
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        assert str(tmp_path) not in text
        assert str(tmp_path).replace("\\", "/") not in text
        # Disclosure phrase counted, not echoed as cell value.
        assert "Suppressed" in text  # appears as bucket count
        assert str(SENTINEL) not in text
