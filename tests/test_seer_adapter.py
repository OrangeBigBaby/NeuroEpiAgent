"""SEER adapter tests — synthetic data only.

The SEER adapter is metadata-only and must NEVER load or emit a SEER
participant record. Every test in this file uses fully synthetic CSVs
written into ``tmp_path``; the real SEER*Stat exports on the local
machine (typically hundreds of MB to several GB) are never read by these
tests.

The tests assert the four hard requirements of the adapter:

1. Streaming / bounded I/O — no full-file load.
2. No case row, no frequency, no unique value in any output.
3. Schema fingerprint is stable for identical headers, differs for
   different headers.
4. User-supplied data-version fields are recorded verbatim; missing
   fields are flagged ``needs_verification`` (never guessed).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from neurosurg_epi_agent.adapters import SEERAdapter, default_registry
from neurosurg_epi_agent.adapters.seer import (
    DATA_ROOT_TOKEN,
    _parse_header_columns,
    _schema_fingerprint,
)


# A representative slice of the real SEER*Stat CNS export header (the
# 269-column canonical schema). We use a smaller synthetic version here
# so the tests are fast and obvious; the real header is the same shape.
SYNTHETIC_CNS_HEADER = ",".join([
    '"Age recode with <1 year olds and 90+"',
    '"Sex"',
    '"Year of diagnosis"',
    '"Race recode (W, B, AI, API)"',
    '"Site recode ICD-O-3/WHO 2008"',
    '"Behavior code ICD-O-3"',
    '"SEER Brain and CNS Recode"',
    '"Histologic Type ICD-O-3"',
    '"Primary Site"',
    '"Survival months"',
    '"Vital status recode"',
])

# A few "data rows" we will NEVER inspect. The adapter must not load these
# or any field within them. The presence of these rows is just to prove
# that they are present on disk and never appear in any output field.
_SYNTHETIC_DATA_ROW = (
    ',"Female","2018","White","Brain","Malignant","9421","9421/3","C71.0",'
    '"35","Alive"'
)


def _synthetic_seer_csv(
    header: str = SYNTHETIC_CNS_HEADER,
    n_rows: int = 5,
    filename: str = "export_C69-C72.csv",
) -> bytes:
    """Return bytes of a synthetic SEER-shaped CSV (header + n_rows data rows)."""
    lines = [header] + [_SYNTHETIC_DATA_ROW] * n_rows
    return ("\n".join(lines) + "\n").encode("utf-8")


# --------------------------------------------------------------------------- #
# Bounded I/O — header read never loads the full file.
# --------------------------------------------------------------------------- #

class TestHeaderParsing:
    def test_parses_quoted_csv_headers_with_commas_in_values(self):
        header = (
            '"Race recode (W, B, AI, API)",'
            '"Site recode ICD-O-3/WHO 2008",'
            '"Year of diagnosis"'
        )
        cols = _parse_header_columns(header)
        assert cols == [
            "Race recode (W, B, AI, API)",
            "Site recode ICD-O-3/WHO 2008",
            "Year of diagnosis",
        ]

    def test_handles_chinese_filename(self, tmp_path):
        # A SEER*Stat export can be named in Chinese; the adapter must
        # not crash, must record the literal basename, and must not
        # attempt to decode the filename.
        header = SYNTHETIC_CNS_HEADER
        bytes_ = _synthetic_seer_csv(header=header, n_rows=0)
        p = tmp_path / "export_C15-C26消化器官恶性肿瘤.csv"
        p.write_bytes(bytes_)
        payload = SEERAdapter().inspect(tmp_path).to_dict()
        assert len(payload["direct_files"]) == 1
        assert payload["direct_files"][0]["member_name"].endswith("消化器官恶性肿瘤.csv")
        assert payload["data_root"] == DATA_ROOT_TOKEN

    def test_handles_very_wide_header(self):
        # Real SEER headers are ~9,686 chars / 269 columns with verbose
        # column names (e.g. ``"Race recode (W, B, AI, API)"``). We
        # construct a synthetic header here with similar total length
        # to confirm the parser does not truncate.
        cols = [f'"Column {i:04d} with some descriptive label"' for i in range(269)]
        wide_header = ",".join(cols)
        assert len(wide_header) > 5000
        parsed = _parse_header_columns(wide_header)
        assert len(parsed) == 269
        assert parsed[0] == "Column 0000 with some descriptive label"
        assert parsed[-1] == "Column 0268 with some descriptive label"


class TestSchemaFingerprint:
    def test_identical_headers_same_fingerprint(self):
        a = _schema_fingerprint(_parse_header_columns(SYNTHETIC_CNS_HEADER))
        b = _schema_fingerprint(_parse_header_columns(SYNTHETIC_CNS_HEADER))
        assert a == b
        assert len(a) == 32  # MD5 hex digest

    def test_different_headers_different_fingerprint(self):
        a = _schema_fingerprint(_parse_header_columns(SYNTHETIC_CNS_HEADER))
        b = _schema_fingerprint(_parse_header_columns(
            SYNTHETIC_CNS_HEADER.replace('"Year of diagnosis"', '"Year of death"')
        ))
        assert a != b


# --------------------------------------------------------------------------- #
# inspect() — metadata-only contract.
# --------------------------------------------------------------------------- #

class TestSEERInspect:
    def test_header_only_no_data_rows_in_output(self, tmp_path):
        # The synthetic CSV contains data rows that look like tumor
        # records. The adapter must NEVER carry any of those values into
        # the inspection result.
        (tmp_path / "export_C69-C72.csv").write_bytes(_synthetic_seer_csv(n_rows=5))
        payload = SEERAdapter().inspect(tmp_path).to_dict()
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        # The synthetic data row contains these planted tokens; they must
        # never appear in the output.
        assert "9421/3" not in text
        assert "C71.0" not in text
        assert "Female" not in text
        assert "Alive" not in text
        # Sanity: the header column names DO appear (variables are metadata).
        assert "Histologic Type ICD-O-3" in text

    def test_absolute_path_never_leaks(self, tmp_path):
        (tmp_path / "export_C69-C72.csv").write_bytes(_synthetic_seer_csv(n_rows=0))
        payload = SEERAdapter().inspect(tmp_path).to_dict()
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        assert str(tmp_path) not in text
        assert str(tmp_path).replace("\\", "/") not in text
        assert payload["data_root"] == DATA_ROOT_TOKEN

    def test_metadata_only_no_row_count(self, tmp_path):
        # The adapter's metadata-only contract forbids computing a row
        # count (it would require reading the whole file). Row count is
        # always None — the downstream pipeline must count rows only
        # after the user has filled in the study contract.
        (tmp_path / "export_C69-C72.csv").write_bytes(_synthetic_seer_csv(n_rows=10))
        payload = SEERAdapter().inspect(tmp_path).to_dict()
        mm = payload["direct_files"][0]
        assert mm["row_count"] is None
        # But the byte size is captured (that's just a stat() call).
        assert mm["byte_size"] > 0
        assert mm["column_count"] == 11

    def test_filename_site_range_labeled_not_assumed(self, tmp_path):
        # The filename embeds a site range. The adapter records the
        # range as a label and flags that rows may NOT all be in it.
        (tmp_path / "export_C69-C72.csv").write_bytes(_synthetic_seer_csv(n_rows=0))
        payload = SEERAdapter().inspect(tmp_path).to_dict()
        prov = payload["direct_files"][0]["provenance"]
        assert prov["filename_site_range"] == "C69-C72"
        assert "may NOT all be within that range" in prov["filename_site_range_note"]

    def test_sha256_off_by_default(self, tmp_path):
        (tmp_path / "export_C69-C72.csv").write_bytes(_synthetic_seer_csv(n_rows=0))
        payload = SEERAdapter().inspect(tmp_path).to_dict()
        # SHA-256 is opt-in. Default behavior must not stream the file.
        assert payload["direct_files"][0]["sha256"] == ""
        assert "sha256_note" not in payload["direct_files"][0]["provenance"]

    def test_sha256_opt_in(self, tmp_path):
        raw = _synthetic_seer_csv(n_rows=0)
        (tmp_path / "export_C69-C72.csv").write_bytes(raw)
        payload = SEERAdapter().inspect(tmp_path, with_sha256=True).to_dict()
        assert payload["direct_files"][0]["sha256"] == hashlib.sha256(raw).hexdigest()

    def test_sha256_size_limit(self, tmp_path):
        # When the file exceeds the cap, sha256 is recorded as empty and
        # an explanatory note is captured — never partial / never guessed.
        (tmp_path / "big.csv").write_bytes(_synthetic_seer_csv(n_rows=10))
        payload = SEERAdapter().inspect(
            tmp_path, with_sha256=True, sha256_max_bytes=100
        ).to_dict()
        mm = payload["direct_files"][0]
        assert mm["sha256"] == ""
        assert "exceeds sha256_max_bytes" in mm["provenance"]["sha256_note"]

    def test_non_csv_skipped(self, tmp_path):
        (tmp_path / "export_C69-C72.csv").write_bytes(_synthetic_seer_csv(n_rows=0))
        (tmp_path / "readme.txt").write_text("hi")
        payload = SEERAdapter().inspect(tmp_path).to_dict()
        names = [m["member_name"] for m in payload["direct_files"]]
        assert names == ["export_C69-C72.csv"]
        skipped_names = [s["member_name"] for s in payload["skipped_roots"]]
        assert "readme.txt" in skipped_names

    def test_symlink_not_followed(self, tmp_path):
        outside = tmp_path / "_outside"
        outside.mkdir()
        target = outside / "secret.csv"
        target.write_bytes(_synthetic_seer_csv(n_rows=0))
        link = tmp_path / "leak.csv"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            return
        payload = SEERAdapter().inspect(tmp_path).to_dict()
        assert payload["direct_files"] == []
        assert "leak.csv" in [s["member_name"] for s in payload["skipped_roots"]]


# --------------------------------------------------------------------------- #
# User-supplied data version — never guessed.
# --------------------------------------------------------------------------- #

class TestDataVersion:
    def test_all_fields_present_recorded_verbatim(self, tmp_path):
        (tmp_path / "export_C69-C72.csv").write_bytes(_synthetic_seer_csv(n_rows=0))
        dv = {
            "release_submission": "November 2024 Submission",
            "product_type": "Research Plus",
            "registry_set": "SEER 18 Regs",
            "seerstat_version": "8.4.4",
            "session_type": "Rate Session",
            "export_date": "2024-12-01",
            "selection_statements": "{Site and Morphology.Brain = 'Yes'}",
            "export_data_dictionary": "https://seer.cancer.gov/data-dict/",
        }
        payload = SEERAdapter().inspect(tmp_path, data_version=dv).to_dict()
        adapter_prov = payload["provenance"]
        assert adapter_prov["release_submission"] == "November 2024 Submission"
        assert adapter_prov["product_type"] == "Research Plus"
        assert adapter_prov["metadata_capability"] == "implemented"
        # Clinical capability remains planned regardless of user input.
        assert adapter_prov["clinical_capability"] == "planned"
        # When all fields are present, ``needs_verification`` is NOT added
        # (only added when fields are missing).
        assert "needs_verification" not in adapter_prov

    def test_missing_fields_marked_needs_verification(self, tmp_path):
        (tmp_path / "export_C69-C72.csv").write_bytes(_synthetic_seer_csv(n_rows=0))
        payload = SEERAdapter().inspect(tmp_path).to_dict()
        adapter_prov = payload["provenance"]
        # No fields provided → adapter records every field as needing
        # verification rather than guessing.
        assert "needs_verification" in adapter_prov
        nv = adapter_prov["needs_verification"]
        for field in (
            "release_submission", "product_type", "registry_set",
            "seerstat_version", "session_type", "export_date",
            "selection_statements", "export_data_dictionary",
        ):
            assert field in nv

    def test_partial_data_version_lists_only_missing(self, tmp_path):
        (tmp_path / "export_C69-C72.csv").write_bytes(_synthetic_seer_csv(n_rows=0))
        payload = SEERAdapter().inspect(
            tmp_path,
            data_version={"product_type": "Research"},
        ).to_dict()
        adapter_prov = payload["provenance"]
        assert adapter_prov["product_type"] == "Research"
        # Other fields still flagged.
        assert "release_submission" in adapter_prov["needs_verification"]
        assert "registry_set" in adapter_prov["needs_verification"]
        # The one we supplied is NOT in needs_verification.
        assert "product_type" not in adapter_prov["needs_verification"]


# --------------------------------------------------------------------------- #
# Capability split: metadata supported, clinical planned.
# --------------------------------------------------------------------------- #

class TestCapabilitySplit:
    def test_identity_advertises_only_metadata(self):
        ident = SEERAdapter().identity
        assert "metadata-inspection" in ident.capabilities
        # Clinical analysis is intentionally NOT in the capability tuple.
        assert not any("clinical" in c.lower() for c in ident.capabilities)

    def test_inspection_notes_call_out_split(self):
        notes = SEERAdapter()._inspection_notes()
        text = "\n".join(notes)
        assert "metadata-inspection" in text
        assert "planned" in text


# --------------------------------------------------------------------------- #
# Cross-file schema consistency — synthetic 13-file scenario.
# --------------------------------------------------------------------------- #

class TestCrossFileSchema:
    def test_thirteen_identical_headers_produce_identical_fingerprints(self, tmp_path):
        # Mirror the local SEER directory shape: 13 files, identical headers.
        for i in range(13):
            (tmp_path / f"export_{i:02d}.csv").write_bytes(_synthetic_seer_csv(n_rows=0))
        payload = SEERAdapter().inspect(tmp_path).to_dict()
        fps = sorted(
            m["provenance"]["schema_fingerprint"] for m in payload["direct_files"]
        )
        assert len(set(fps)) == 1

    def test_divergent_header_caught(self, tmp_path):
        (tmp_path / "a.csv").write_bytes(_synthetic_seer_csv(n_rows=0))
        # Replace one column header so the schema differs.
        alt = SYNTHETIC_CNS_HEADER.replace('"Year of diagnosis"', '"Year of death"')
        (tmp_path / "b.csv").write_bytes(_synthetic_seer_csv(header=alt, n_rows=0))
        payload = SEERAdapter().inspect(tmp_path).to_dict()
        fps = sorted(
            m["provenance"]["schema_fingerprint"] for m in payload["direct_files"]
        )
        assert len(set(fps)) == 2


# --------------------------------------------------------------------------- #
# CLI integration.
# --------------------------------------------------------------------------- #

class TestCLI:
    def test_cli_seer_inspect(self, tmp_path):
        from neurosurg_epi_agent.cli import main as cli_main
        (tmp_path / "export_C69-C72.csv").write_bytes(_synthetic_seer_csv(n_rows=0))
        out = tmp_path / "out.json"
        rc = cli_main([
            "inspect-database",
            "--database", "SEER",
            "--data-root", str(tmp_path),
            "--output", str(out),
        ])
        assert rc == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["database"] == "SEER"
        assert payload["data_root"] == DATA_ROOT_TOKEN
        assert len(payload["direct_files"]) == 1

    def test_cli_seer_in_default_registry(self):
        assert "SEER" in default_registry().names()