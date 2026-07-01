"""NHANES 2017-2018 exploratory stroke prevalence case study.

This module intentionally writes aggregate summaries only. It does not persist
merged participant-level data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping


DEMO_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DEMO_J.XPT"
MCQ_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/MCQ_J.XPT"

SOURCE_FILES = {
    "DEMO_J.XPT": DEMO_URL,
    "MCQ_J.XPT": MCQ_URL,
}

VARIABLES_USED = {
    "DEMO_J.XPT": ["SEQN", "RIAGENDR", "WTINT2YR", "SDMVPSU", "SDMVSTRA"],
    "MCQ_J.XPT": ["SEQN", "MCQ160F"],
}

STROKE_LABELS = {
    1: "Yes",
    2: "No",
    7: "Refused",
    9: "Don't know",
}

SEX_LABELS = {
    1: "Male",
    2: "Female",
}


class OptionalDependencyError(RuntimeError):
    """Raised when optional case-study dependencies are unavailable."""


def require_pandas():
    """Import pandas lazily so the core package has a light dependency set."""
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only without pandas
        raise OptionalDependencyError(
            "The NHANES case study requires pandas. Install with "
            "`pip install neurosurg-epi-agent[case-study]` or `pip install pandas`."
        ) from exc
    return pd


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 for a local file."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, destination: Path) -> Dict[str, Any]:
    """Download a public file if absent and return provenance metadata."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    existed = destination.exists()
    redownload_reason = None
    if existed and not looks_like_xport(destination):
        redownload_reason = "cached file did not have an XPORT header"
        destination.unlink()
        existed = False
    if not existed:
        request = urllib.request.Request(url, headers={"User-Agent": "NeuroSurgEpiAgent/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            destination.write_bytes(response.read())
    if not looks_like_xport(destination):
        raise ValueError(
            f"Downloaded file does not appear to be a SAS XPORT file: {destination}. "
            f"Check source URL: {url}"
        )

    return {
        "url": url,
        "local_name": destination.name,
        "cached": existed,
        "redownload_reason": redownload_reason,
        "downloaded_at": None if existed else utc_now_iso(),
        "sha256": compute_sha256(destination),
        "size_bytes": destination.stat().st_size,
    }


def looks_like_xport(path: Path) -> bool:
    """Return True if a file begins with the expected SAS XPORT header."""
    if not path.exists() or path.stat().st_size < 32:
        return False
    return path.read_bytes()[:32].startswith(b"HEADER RECORD")


def load_xpt(path: Path):
    """Load an NHANES XPT file with pandas."""
    pd = require_pandas()
    return pd.read_sas(path, format="xport")


def _assert_required_columns(frame, required: list[str], frame_name: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{frame_name} is missing required columns: {missing}")


def prepare_analysis_dataset(demo, mcq):
    """Merge DEMO and MCQ records and derive analysis columns.

    The returned DataFrame is used only in memory. Callers should write only
    aggregate summaries.
    """
    pd = require_pandas()
    _assert_required_columns(demo, ["SEQN", "RIAGENDR", "WTINT2YR"], "DEMO_J")
    _assert_required_columns(mcq, ["SEQN", "MCQ160F"], "MCQ_J")

    demo_columns = [
        column
        for column in ["SEQN", "RIAGENDR", "WTINT2YR", "SDMVPSU", "SDMVSTRA"]
        if column in demo.columns
    ]
    merged = demo[demo_columns].merge(mcq[["SEQN", "MCQ160F"]], on="SEQN", how="inner")
    merged["stroke_code"] = pd.to_numeric(merged["MCQ160F"], errors="coerce")
    merged["stroke_yes"] = merged["stroke_code"] == 1
    merged["stroke_no"] = merged["stroke_code"] == 2
    merged["stroke_eligible"] = merged["stroke_code"].isin([1, 2])
    merged["sex"] = merged["RIAGENDR"].map(SEX_LABELS).fillna("Unknown")
    merged["valid_weight"] = pd.to_numeric(merged["WTINT2YR"], errors="coerce").gt(0)
    return merged


def _safe_weighted_prevalence(frame) -> Dict[str, Any]:
    weighted = frame[frame["valid_weight"]].copy()
    denominator = float(weighted["WTINT2YR"].sum())
    numerator = float((weighted["WTINT2YR"] * weighted["stroke_yes"].astype(float)).sum())
    prevalence = numerator / denominator if denominator > 0 else None
    return {
        "weighted_numerator": numerator,
        "weighted_denominator": denominator,
        "weighted_prevalence": prevalence,
    }


def _clean_for_json(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {key: _clean_for_json(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_clean_for_json(inner) for inner in value]
    return value


def summarize_stroke_prevalence(analysis_df) -> Dict[str, Any]:
    """Compute aggregate exploratory stroke prevalence summaries."""
    eligible = analysis_df[analysis_df["stroke_eligible"]].copy()
    overall_weighted = _safe_weighted_prevalence(eligible)

    by_sex: Dict[str, Dict[str, Any]] = {}
    for sex, group in eligible.groupby("sex", dropna=False):
        sex_key = str(sex)
        weighted = _safe_weighted_prevalence(group)
        by_sex[sex_key] = {
            "eligible_n": int(len(group)),
            "stroke_yes_n": int(group["stroke_yes"].sum()),
            "stroke_no_n": int(group["stroke_no"].sum()),
            **weighted,
        }

    results = {
        "case_study": "NHANES 2017-2018 self-reported stroke prevalence",
        "analysis_type": "exploratory_descriptive",
        "statistical_note": (
            "Weighted prevalence uses WTINT2YR among participants with MCQ160F "
            "coded yes/no and positive interview weights. Confidence intervals "
            "are not reported because complex survey variance estimation with "
            "strata and PSU is not implemented in this case study."
        ),
        "overall": {
            "eligible_n": int(len(eligible)),
            "stroke_yes_n": int(eligible["stroke_yes"].sum()),
            "stroke_no_n": int(eligible["stroke_no"].sum()),
            "missing_or_noninformative_mcq160f_n": int((~analysis_df["stroke_eligible"]).sum()),
            "invalid_or_missing_weight_among_eligible_n": int((~eligible["valid_weight"]).sum()),
            **overall_weighted,
        },
        "by_sex": by_sex,
    }
    return _clean_for_json(results)


def build_provenance(
    file_metadata: Mapping[str, Mapping[str, Any]],
    demo_rows: int,
    mcq_rows: int,
    merged_rows: int,
) -> Dict[str, Any]:
    """Build aggregate-only provenance metadata."""
    return {
        "case_study": "nhanes_stroke_2017_2018",
        "generated_at": utc_now_iso(),
        "source_files": file_metadata,
        "row_counts": {
            "DEMO_J": int(demo_rows),
            "MCQ_J": int(mcq_rows),
            "merged": int(merged_rows),
        },
        "variables_used": VARIABLES_USED,
        "privacy_note": (
            "Only aggregate summaries and source-file hashes are written. "
            "No merged participant-level records, SEQN values, or raw XPT data "
            "are written to the case_studies output directory."
        ),
        "limitations": [
            "Self-reported stroke history may be subject to recall or reporting error.",
            "This descriptive case study does not implement Taylor-linearized complex survey variance.",
            "The output is a reproducibility demonstration, not a clinical decision-support result.",
        ],
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write formatted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def render_report(results: Mapping[str, Any], provenance: Mapping[str, Any]) -> str:
    """Render a compact Markdown report."""
    overall = results["overall"]
    by_sex = results["by_sex"]

    lines = [
        "# NHANES 2017-2018 stroke prevalence case study",
        "",
        "This is an aggregate-only reproducibility demonstration for NeuroSurgEpiAgent.",
        "",
        "## Data sources",
        "",
    ]
    for name, metadata in provenance["source_files"].items():
        lines.append(f"- `{name}`: {metadata['url']}")
        lines.append(f"  - SHA-256: `{metadata['sha256']}`")
    lines.extend(
        [
            "",
            "## Results",
            "",
            f"- Eligible participants with MCQ160F yes/no: {overall['eligible_n']}",
            f"- Unweighted stroke yes/no counts: {overall['stroke_yes_n']} / {overall['stroke_no_n']}",
            f"- Weighted stroke prevalence: {overall['weighted_prevalence']:.6f}",
            "",
            "| Sex | Eligible n | Stroke yes n | Stroke no n | Weighted prevalence |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for sex, row in by_sex.items():
        prevalence = row["weighted_prevalence"]
        prevalence_text = "NA" if prevalence is None else f"{prevalence:.6f}"
        lines.append(
            f"| {sex} | {row['eligible_n']} | {row['stroke_yes_n']} | "
            f"{row['stroke_no_n']} | {prevalence_text} |"
        )
    lines.extend(
        [
            "",
            "## Statistical note",
            "",
            str(results["statistical_note"]),
            "",
            "## Privacy and reproducibility",
            "",
            str(provenance["privacy_note"]),
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(output_dir: Path, results: Mapping[str, Any], provenance: Mapping[str, Any]) -> Dict[str, Path]:
    """Write aggregate result artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "results.json"
    provenance_path = output_dir / "provenance.json"
    report_path = output_dir / "report.md"

    write_json(results_path, results)
    write_json(provenance_path, provenance)
    report_path.write_text(render_report(results, provenance), encoding="utf-8")
    return {
        "results": results_path,
        "provenance": provenance_path,
        "report": report_path,
    }


def run_case_study(output_dir: Path, cache_dir: Path) -> Dict[str, Path]:
    """Run the full public-data case study."""
    file_metadata: Dict[str, Dict[str, Any]] = {}
    local_paths: Dict[str, Path] = {}
    for filename, url in SOURCE_FILES.items():
        local_path = cache_dir / filename
        file_metadata[filename] = download_file(url, local_path)
        local_paths[filename] = local_path

    demo = load_xpt(local_paths["DEMO_J.XPT"])
    mcq = load_xpt(local_paths["MCQ_J.XPT"])
    analysis_df = prepare_analysis_dataset(demo, mcq)
    results = summarize_stroke_prevalence(analysis_df)
    provenance = build_provenance(
        file_metadata=file_metadata,
        demo_rows=len(demo),
        mcq_rows=len(mcq),
        merged_rows=len(analysis_df),
    )
    return write_outputs(output_dir, results, provenance)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("case_studies/nhanes_stroke_2017_2018"),
        help="Directory for aggregate outputs.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/cache/nhanes"),
        help="Directory for cached public XPT files.",
    )
    args = parser.parse_args(argv)

    outputs = run_case_study(output_dir=args.output_dir, cache_dir=args.cache_dir)
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
