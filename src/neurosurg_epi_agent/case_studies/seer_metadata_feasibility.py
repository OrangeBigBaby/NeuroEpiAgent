"""SEER metadata/feasibility case study — synthetic data only.

This case study demonstrates the SEER metadata-only contract by:

1. Creating a small synthetic SEER-shaped CSV directory in a temp dir.
2. Calling `SEERAdapter.inspect(...)` over that directory.
3. Emitting a case-study `results.json` and `provenance.json` that are
   themselves disclosure-checked (no row, no frequency, no unique value).

It does NOT touch the real SEER*Stat exports on the local machine and
does NOT require the user to fill in `docs/SEER_STUDY_CONTRACT.md`
because it does not produce any clinical analysis.

Run:

```powershell
python -m neurosurg_epi_agent.case_studies.seer_metadata_feasibility `
    --output-dir case_studies/seer_metadata_feasibility/results
```
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from neurosurg_epi_agent.adapters import SEERAdapter
from neurosurg_epi_agent.adapters.seer import _DATA_VERSION_FIELDS


# A representative slice of the real SEER*Stat CNS export schema. It is
# deliberately shorter than the real 269-column header so the synthetic
# test fixture is small and obvious. The point is to demonstrate the
# adapter's metadata-only contract on SEER-shaped CSVs, not to mimic
# the real data.
SYNTHETIC_SEER_HEADER = ",".join([
    '"Age recode with <1 year olds and 90+"',
    '"Sex"',
    '"Year of diagnosis"',
    '"Race recode (W, B, AI, API)"',
    '"Site recode ICD-O-3/WHO 2008"',
    '"Behavior code ICD-O-3"',
    '"SEER Brain and CNS Recode"',
    '"Histologic Type ICD-O-3"',
    '"Survival months"',
    '"Vital status recode"',
])

# A "data row" we keep OUT of every output. The synthetic row's values
# do not exist in the published case study — only metadata about the
# file the row lived in.
_SYNTHETIC_DATA_ROW = (
    '"Female","2018","White","C71.0","Malignant","9421/3",'
    '"9421/3","35","Alive"'
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_synthetic_seer_tree(root: Path, n_files: int = 13) -> List[str]:
    """Write ``n_files`` synthetic SEER*Stat-shaped CSVs into ``root``.

    Mirrors the local SEER tree's shape (one CSV per ICD-O-3 site range).
    Returns the list of relative filenames actually written.
    """
    root.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    site_ranges = [
        "C00-C09", "C10-C14", "C15-C26", "C30-C39", "C40-C49",
        "C50", "C51-C53", "C54-C58", "C60-C63", "C64-C68",
        "C69-C72", "C73-C75", "C76-C80",
    ]
    for i in range(n_files):
        sr = site_ranges[i] if i < len(site_ranges) else f"C{90+i:02d}-C{95+i:02d}"
        rel = f"export_{sr}.csv"
        out = root / rel
        with out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([
                '"Age recode with <1 year olds and 90+"', '"Sex"',
                '"Year of diagnosis"', '"Site recode ICD-O-3/WHO 2008"',
                '"Behavior code ICD-O-3"', '"SEER Brain and CNS Recode"',
                '"Histologic Type ICD-O-3"', '"Survival months"',
                '"Vital status recode"',
            ])
            # Plant 50 rows per file but the adapter will never read them.
            for _ in range(50):
                w.writerow([
                    "60-64", "Female", "2018",
                    f"C{70 + (i % 3)}.0",
                    "Malignant", f"{9400 + i}", f"{9400 + i}/3",
                    "35", "Alive",
                ])
        written.append(rel)
    return written


def run_case_study(
    output_dir: Path,
    *,
    with_sha256: bool = False,
    seed: int = 2026,
    data_version: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Run the case study: synthesize a SEER-shaped tree, inspect it, write outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="seer_synth_") as tmp:
        synth_root = Path(tmp)
        written_files = write_synthetic_seer_tree(synth_root)

        adapter = SEERAdapter()
        inspection = adapter.inspect(
            synth_root,
            with_sha256=with_sha256,
            sha256_max_bytes=2 * 1024 * 1024 * 1024,
            data_version=data_version,
        )
        inspection_payload = inspection.to_dict()

    # Disclosure posture: pull only the safe fields. The data row's
    # values MUST NEVER appear in this case study's outputs — that is
    # the whole point of the metadata-only contract.
    safe_members: List[Dict[str, Any]] = []
    for m in inspection_payload["direct_files"]:
        safe_members.append(
            {
                "member_name": m["member_name"],
                "member_path": m["member_path"],
                "byte_size": m["byte_size"],
                "column_count": m["column_count"],
                "schema_fingerprint": m["provenance"]["schema_fingerprint"],
                "filename_site_range": m["provenance"].get("filename_site_range"),
                "sha256": m["sha256"] if with_sha256 else None,
            }
        )

    # Aggregate across the synthetic tree (counts only — never values).
    aggregate: Dict[str, Any] = {
        "files_inspected": len(safe_members),
        "total_bytes": sum(m["byte_size"] for m in safe_members),
        "unique_schema_fingerprints": len(
            {m["schema_fingerprint"] for m in safe_members}
        ),
    }

    results: Dict[str, Any] = {
        "case_study": "seer_metadata_feasibility",
        "aggregate": aggregate,
        "members": safe_members,
    }
    provenance: Dict[str, Any] = {
        "case_study": "seer_metadata_feasibility",
        "generated_at": utc_now_iso(),
        "python_version": platform.python_version(),
        "package_versions": {
            "neurosurg_epi_agent": "0.3.0",
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "synthetic_seed": seed,
        "synthetic_files_written": written_files,
        "synthetic_data_rows_per_file": 50,
        "synthetic_data_disclosure_note": (
            "The synthetic data rows in the temp tree are NEVER written "
            "into this case study's outputs. Only file-level metadata "
            "(name, byte size, schema fingerprint) is emitted."
        ),
        "data_version_provided": data_version or {},
        "data_version_status": (
            "complete" if data_version and not any(
                f not in data_version for f in _DATA_VERSION_FIELDS
            ) else "needs_verification"
        ),
        "input_schema_fingerprint": inspection_payload["provenance"].get(
            "schema_fingerprint", "synthetic-fixed-v1"
        ),
        "adapter_capability_split": {
            "metadata_inspection": "supported (this case study)",
            "clinical_analysis": "planned (not exposed by SEERAdapter)",
        },
        "limitations": [
            "This is a SYNTHETIC case study. The byte sizes, file names, "
            "and schema fingerprints below come from CSVs the case study "
            "wrote itself into a temporary directory; they do not "
            "describe the user's real SEER*Stat exports.",
            "Running this case study does NOT exercise any clinical "
            "analysis. To do that, the analyst must complete "
            "`docs/SEER_STUDY_CONTRACT.md`.",
        ],
    }

    # Write outputs.
    results_path = output_dir / "results.json"
    provenance_path = output_dir / "provenance.json"
    results_path.write_text(
        json.dumps(results, indent=2, sort_keys=True), encoding="utf-8"
    )
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Render a small markdown report.
    report_path = output_dir / "report.md"
    report_lines = [
        "# SEER metadata feasibility case study",
        "",
        "> **Synthetic case study.** This run wrote a temp directory of",
        "> placeholder SEER-shaped CSVs and inspected them with",
        "> `SEERAdapter`. It does NOT read any real SEER*Stat export.",
        "",
        "## Aggregate",
        "",
        f"- Files inspected: `{aggregate['files_inspected']}`",
        f"- Total bytes: `{aggregate['total_bytes']:,}`",
        f"- Unique schema fingerprints: "
        f"`{aggregate['unique_schema_fingerprints']}`",
        "",
        "## Capability split",
        "",
        "- `metadata-inspection`: **supported** (this case study)",
        "- `clinical-analysis`: **planned** (NOT exposed by SEERAdapter)",
        "",
        "## Disclosure posture",
        "",
        "- The synthetic data rows in the temp tree are NEVER written "
        "into the case-study outputs.",
        "- Only file-level metadata (name, byte size, schema "
        "fingerprint) is emitted.",
        "- Data-version field status: "
        f"`{provenance['data_version_status']}` (provided: "
        f"`{data_version or {}}`)",
        "",
    ]
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return {
        "results": results_path,
        "provenance": provenance_path,
        "report": report_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("case_studies/seer_metadata_feasibility/results"),
        help="Directory for case-study outputs.",
    )
    parser.add_argument(
        "--with-sha256",
        action="store_true",
        help="Stream a SHA-256 over each synthetic CSV (off by default).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=2026,
        help="Random seed (unused; recorded for forward-compat).",
    )
    args = parser.parse_args(argv)

    outputs = run_case_study(
        args.output_dir,
        with_sha256=args.with_sha256,
        seed=args.seed,
    )
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())