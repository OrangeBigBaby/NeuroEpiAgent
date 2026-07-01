"""CDC WONDER synthetic case study: disclosure-checked aggregate workflow.

This case study is fully SYNTHETIC. It demonstrates the disclosure-checked
aggregate workflow that any real CDC WONDER analysis would follow, using
numbers and trends invented for the test. It does NOT load any real CDC
WONDER file, and it does NOT emit any cell with `Deaths <= 9`.

The case study follows the analysis-implementation principles in
`docs/ANALYSIS_IMPLEMENTATION_PRINCIPLES.md`:

- Step-numbered, independently runnable.
- Provenance + schema fingerprint + software versions recorded.
- Disclosure guardrail: cells with `Deaths <= 9` are never written; cells
  with `Deaths < 20` carry an `unstable / unreliable` flag.
- Conservative language policy applied to the rendered report.

Run:

```powershell
python -m neurosurg_epi_agent.case_studies.cdc_wonder_synthetic_demo `
    --output-dir case_studies/cdc_wonder_synthetic_demo/results
```
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


# Synthetic input — entirely invented for the demo. Numbers are NOT real
# WONDER data. The trend is monotonically increasing because that is
# useful for a demonstration; real CDC WONDER cerebrovascular-mortality
# trends have varied across the period.
SYNTHETIC_INPUT: Tuple[Tuple[int, int, str, str], ...] = (
    # (year, deaths, dataset_label, database_family)
    (1999, 150_000, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2000, 148_500, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2001, 145_800, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2002, 142_300, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2003, 138_900, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2004, 134_200, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2005, 130_400, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2006, 127_100, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2007, 124_500, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2008, 122_900, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2009, 120_400, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2010, 118_700, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2011, 117_800, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2012, 117_900, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2013, 118_700, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2014, 119_900, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2015, 121_500, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2016, 123_400, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2017, 125_300, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    (2018, 126_900, "Underlying Cause of Death, 1999-2020, Single Race", "UCD"),
    # A synthetic MCD row illustrating the UCD/MCD distinction.
    (2018, 7, "Multiple Cause of Death, 1999-2020", "MCD"),
)


# Disclosure thresholds — copy of CDC WONDER's own policy.
SUPPRESSED_MAX_DEATHS = 9
UNRELIABLE_MAX_DEATHS = 19


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def disclosure_status(deaths: int) -> str:
    """Return CDC WONDER's disclosure status for a cell with ``deaths`` deaths.

    - ``Suppressed`` if ``deaths <= 9`` (per WONDER's policy)
    - ``Unreliable`` if ``10 <= deaths < 20``
    - ``OK`` otherwise
    """
    if deaths <= SUPPRESSED_MAX_DEATHS:
        return "Suppressed"
    if deaths <= UNRELIABLE_MAX_DEATHS:
        return "Unreliable"
    return "OK"


def annotate_rows(
    rows: Tuple[Tuple[int, int, str, str], ...],
) -> List[Dict[str, Any]]:
    """Walk every row and assign disclosure status; drop suppressed rows.

    The output is a list of dicts ready for JSON. Suppressed rows are
    dropped entirely so they cannot leak into a downstream artifact.
    Unreliable rows are kept with a status flag so a reviewer can
    see the count and decide whether to include it.
    """
    annotated: List[Dict[str, Any]] = []
    for year, deaths, dataset, family in rows:
        status = disclosure_status(deaths)
        if status == "Suppressed":
            # Hard stop: never emit a Suppressed cell.
            continue
        annotated.append(
            {
                "year": year,
                "deaths": deaths,
                "dataset_label": dataset,
                "database_family": family,
                "disclosure_status": status,
            }
        )
    return annotated


def compute_year_over_year(
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compute the year-over-year change in deaths.

    Conservative-language policy: we report `change` and `relative_change`
    but do NOT claim the trend proves anything; the report.md uses
    `suggest`, `is consistent with`.
    """
    by_year = {r["year"]: r for r in rows if r["database_family"] == "UCD"}
    years = sorted(by_year)
    out: List[Dict[str, Any]] = []
    prev = None
    for y in years:
        d = by_year[y]["deaths"]
        if prev is None:
            change = None
            relative_change = None
        else:
            change = d - prev
            relative_change = (d - prev) / prev if prev else None
        out.append({
            "year": y,
            "deaths": d,
            "change_from_prior_year": change,
            "relative_change_from_prior_year": relative_change,
            "disclosure_status": by_year[y]["disclosure_status"],
        })
        prev = d
    return out


def render_report(
    results: Dict[str, Any],
    provenance: Dict[str, Any],
) -> str:
    """Render the case-study Markdown report.

    Conservative language only: no `proves`, `causes`, `first ever`,
    `comprehensive`, `unprecedented`.
    """
    lines: List[str] = [
        "# CDC WONDER synthetic-data case study",
        "",
        "> **This case study is fully synthetic.** The numbers below are",
        "> invented to demonstrate the disclosure-checked aggregate",
        "> workflow. They are NOT real CDC WONDER data and MUST NOT be",
        "> cited as such.",
        "",
        "## Data summary",
        "",
        f"- Source: {provenance['source']['label']} (synthetic)",
        f"- Database family: {results['aggregate_by_family']['UCD']['family']}",
        f"- Year range: {provenance['source']['year_range']}",
        f"- Cells annotated: {len(results['annotated_rows'])} "
        f"({results['disclosure_counts']['OK']} OK, "
        f"{results['disclosure_counts']['Unreliable']} Unreliable, "
        f"{results['disclosure_counts']['Suppressed_dropped']} Suppressed + dropped)",
        "",
        "## Year-over-year change (synthetic UCD series)",
        "",
        "| Year | Deaths | YoY change | Disclosure |",
        "| ---: | ---: | ---: | :--- |",
    ]
    for row in results["year_over_year"]:
        change = row["change_from_prior_year"]
        change_text = "—" if change is None else f"{change:+,}"
        lines.append(
            f"| {row['year']} | {row['deaths']:,} | {change_text} | "
            f"{row['disclosure_status']} |"
        )
    lines.extend(
        [
            "",
            "## Conservative-language summary",
            "",
            "The synthetic series is consistent with a long-term decline",
            "in the underlying-cause cerebrovascular death count followed",
            "by a plateau / modest rise after 2012. This pattern SUGGESTS",
            "(it does not prove) that the trajectory changed around 2012.",
            "",
            "## Disclosure posture",
            "",
            f"- Cells with `Deaths <= {SUPPRESSED_MAX_DEATHS}` were dropped before",
            "  any output was written.",
            f"- Cells with `Deaths <= {UNRELIABLE_MAX_DEATHS}` are kept but flagged",
            "  `Unreliable` so a reviewer can decide whether to include them.",
            "- UCD and MCD rows are kept in separate tables; they are not",
            "  combined into the same chart without an in-figure note that",
            "  the case-selection basis differs.",
            "",
            "## Reproducibility",
            "",
            f"- Generated at: `{provenance['generated_at']}`",
            f"- Python version: `{provenance['python_version']}`",
            f"- Package version: `{provenance['package_versions']['neurosurg_epi_agent']}`",
            f"- Random seed: `{provenance['random_seed']}` (unused in this run;",
            "  recorded for forward compatibility with bootstrap-style",
            "  extensions).",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    output_dir: Path,
    results: Dict[str, Any],
    provenance: Dict[str, Any],
    report_md: str,
) -> Dict[str, Path]:
    """Write the three canonical case-study artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "results.json"
    provenance_path = output_dir / "provenance.json"
    report_path = output_dir / "report.md"

    results_path.write_text(
        json.dumps(results, indent=2, sort_keys=True), encoding="utf-8"
    )
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8"
    )
    report_path.write_text(report_md, encoding="utf-8")

    return {
        "results": results_path,
        "provenance": provenance_path,
        "report": report_path,
    }


def build_provenance(
    source_label: str,
    year_range: str,
    random_seed: int,
) -> Dict[str, Any]:
    """Build the provenance dict per the analysis-implementation principles."""
    return {
        "case_study": "cdc_wonder_synthetic_demo",
        "generated_at": utc_now_iso(),
        "python_version": platform.python_version(),
        "package_versions": {
            "neurosurg_epi_agent": "0.2.0",
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "source": {
            "label": source_label,
            "year_range": year_range,
            "is_real_data": False,
            "synthetic_note": (
                "Numbers in this case study are invented to demonstrate "
                "the disclosure-checked aggregate workflow. They MUST NOT "
                "be cited as real CDC WONDER data."
            ),
        },
        "random_seed": random_seed,
        "input_schema_fingerprint": (
            # In a real run this comes from the inspected WONDER file.
            "synthetic-fixed-v1"
        ),
        "limitations": [
            "The numbers are entirely synthetic.",
            "This case study demonstrates the disclosure posture; it does NOT "
            "demonstrate a real-world clinical finding.",
        ],
    }


def build_results(annotated_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate the annotated rows into the case-study results structure."""
    by_family: Dict[str, List[Dict[str, Any]]] = {}
    for row in annotated_rows:
        by_family.setdefault(row["database_family"], []).append(row)
    aggregate_by_family: Dict[str, Dict[str, Any]] = {}
    for family, rs in by_family.items():
        if not rs:
            continue
        aggregate_by_family[family] = {
            "family": family,
            "row_count": len(rs),
            "year_min": min(r["year"] for r in rs),
            "year_max": max(r["year"] for r in rs),
            "deaths_min": min(r["deaths"] for r in rs),
            "deaths_max": max(r["deaths"] for r in rs),
        }
    # Counts of disclosure statuses across the input set (including
    # suppressed rows that we dropped).
    suppressed_dropped = sum(
        1
        for _, d, _, _ in SYNTHETIC_INPUT
        if d <= SUPPRESSED_MAX_DEATHS
    )
    unreliable_kept = sum(
        1
        for r in annotated_rows
        if r["disclosure_status"] == "Unreliable"
    )
    ok_kept = sum(
        1
        for r in annotated_rows
        if r["disclosure_status"] == "OK"
    )
    return {
        "annotated_rows": annotated_rows,
        "aggregate_by_family": aggregate_by_family,
        "year_over_year": compute_year_over_year(annotated_rows),
        "disclosure_counts": {
            "OK": ok_kept,
            "Unreliable": unreliable_kept,
            "Suppressed_dropped": suppressed_dropped,
        },
    }


def run_case_study(output_dir: Path, seed: int = 2026) -> Dict[str, Path]:
    """Run the case study end-to-end."""
    random.seed(seed)  # For forward-compat with bootstrap extensions.
    annotated = annotate_rows(SYNTHETIC_INPUT)
    results = build_results(annotated)
    year_range = (
        f"{min(r['year'] for r in annotated)}-{max(r['year'] for r in annotated)}"
        if annotated
        else "(empty)"
    )
    provenance = build_provenance(
        source_label="CDC WONDER synthetic UCD cerebrovascular series",
        year_range=year_range,
        random_seed=seed,
    )
    report_md = render_report(results, provenance)
    return write_outputs(output_dir, results, provenance, report_md)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("case_studies/cdc_wonder_synthetic_demo/results"),
        help="Directory for aggregate outputs.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=2026,
        help="Random seed (recorded in provenance; unused in this run).",
    )
    args = parser.parse_args(argv)

    outputs = run_case_study(args.output_dir, seed=args.seed)
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())