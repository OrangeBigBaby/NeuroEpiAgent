import json

import pytest

pd = pytest.importorskip("pandas")

from neurosurg_epi_agent.case_studies.nhanes_stroke_2017_2018 import (
    build_provenance,
    prepare_analysis_dataset,
    summarize_stroke_prevalence,
    write_outputs,
)


def synthetic_demo():
    return pd.DataFrame(
        {
            "SEQN": [1, 2, 3, 4, 5],
            "RIAGENDR": [1, 2, 1, 2, 2],
            "WTINT2YR": [1.0, 2.0, 3.0, 4.0, None],
            "SDMVPSU": [1, 1, 2, 2, 1],
            "SDMVSTRA": [100, 100, 101, 101, 102],
        }
    )


def synthetic_mcq():
    return pd.DataFrame(
        {
            "SEQN": [1, 2, 3, 4, 5],
            "MCQ160F": [1, 2, 1, 7, 2],
        }
    )


def test_prepare_and_summarize_stroke_prevalence():
    analysis_df = prepare_analysis_dataset(synthetic_demo(), synthetic_mcq())
    results = summarize_stroke_prevalence(analysis_df)

    assert results["analysis_type"] == "exploratory_descriptive"
    assert results["overall"]["eligible_n"] == 4
    assert results["overall"]["stroke_yes_n"] == 2
    assert results["overall"]["stroke_no_n"] == 2
    assert results["overall"]["missing_or_noninformative_mcq160f_n"] == 1
    assert results["overall"]["invalid_or_missing_weight_among_eligible_n"] == 1
    assert results["overall"]["weighted_numerator"] == pytest.approx(4.0)
    assert results["overall"]["weighted_denominator"] == pytest.approx(6.0)
    assert results["overall"]["weighted_prevalence"] == pytest.approx(4.0 / 6.0)

    assert results["by_sex"]["Male"]["eligible_n"] == 2
    assert results["by_sex"]["Male"]["weighted_prevalence"] == pytest.approx(1.0)
    assert results["by_sex"]["Female"]["eligible_n"] == 2
    assert results["by_sex"]["Female"]["weighted_prevalence"] == pytest.approx(0.0)


def test_missing_required_columns_are_reported():
    demo = synthetic_demo().drop(columns=["WTINT2YR"])
    with pytest.raises(ValueError, match="WTINT2YR"):
        prepare_analysis_dataset(demo, synthetic_mcq())


def test_provenance_shape_and_privacy_note():
    provenance = build_provenance(
        file_metadata={
            "DEMO_J.XPT": {"url": "https://example.org/demo", "sha256": "a", "size_bytes": 1},
            "MCQ_J.XPT": {"url": "https://example.org/mcq", "sha256": "b", "size_bytes": 2},
        },
        demo_rows=5,
        mcq_rows=5,
        merged_rows=5,
    )

    assert provenance["row_counts"]["merged"] == 5
    assert "MCQ160F" in provenance["variables_used"]["MCQ_J.XPT"]
    assert "aggregate" in provenance["privacy_note"].lower()
    assert "SEQN values" in provenance["privacy_note"]


def test_write_outputs_are_aggregate_only(tmp_path):
    analysis_df = prepare_analysis_dataset(synthetic_demo(), synthetic_mcq())
    results = summarize_stroke_prevalence(analysis_df)
    provenance = build_provenance(
        file_metadata={
            "DEMO_J.XPT": {"url": "https://example.org/demo", "sha256": "a", "size_bytes": 1},
            "MCQ_J.XPT": {"url": "https://example.org/mcq", "sha256": "b", "size_bytes": 2},
        },
        demo_rows=5,
        mcq_rows=5,
        merged_rows=5,
    )

    outputs = write_outputs(tmp_path, results, provenance)

    assert outputs["results"].exists()
    assert outputs["provenance"].exists()
    assert outputs["report"].exists()
    assert not list(tmp_path.glob("*.csv"))
    assert not list(tmp_path.glob("*.xpt"))
    assert not list(tmp_path.glob("*.parquet"))

    combined_text = "\n".join(path.read_text(encoding="utf-8") for path in outputs.values())
    assert "SEQN" not in json.dumps(json.loads(outputs["results"].read_text(encoding="utf-8")))
    assert "participant-level records" in combined_text

