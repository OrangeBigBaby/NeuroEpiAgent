import pytest
from neurosurg_epi_agent.router import route


# Table-driven tests for benchmark tasks
# Exact expected behavior from tasks.example.yaml
BENCHMARK_TEST_CASES = [
    # stroke_01 - NHANES true
    {
        "task_id": "stroke_01",
        "question": (
            "Is self-reported stroke history in US adults associated with metabolic "
            "syndrome components, pooling NHANES 2011-2018?"
        ),
        "expected_database": "NHANES",
        "expected_feasible": True,
        "expected_rationale_contains": "known epidemiology domain",
    },
    # stroke_02 - NHANES false (surgery/5-year recurrence unavailable)
    {
        "task_id": "stroke_02",
        "question": (
            "Does laparoscopic bariatric surgery reduce 5-year stroke recurrence?"
        ),
        "expected_database": "NHANES",
        "expected_feasible": False,
        "expected_rationale_contains": "surgery",
    },
    # stroke_03 - NHANES true
    {
        "task_id": "stroke_03",
        "question": (
            "Stroke prevalence by sarcopenia status, adults 60+, NHANES 2013-2018."
        ),
        "expected_database": "NHANES",
        "expected_feasible": True,
        "expected_rationale_contains": "known epidemiology domain",
    },
    # tbi_01 - NHANES false (no comparable cross-cycle TBI item)
    {
        "task_id": "tbi_01",
        "question": (
            "Lifetime prevalence of traumatic brain injury in US adults, NHANES."
        ),
        "expected_database": "NHANES",
        "expected_feasible": False,
        "expected_rationale_contains": "did not match a known",
    },
    # tbi_02 - GBD false (regional incidence/burden; adapter planned)
    {
        "task_id": "tbi_02",
        "question": (
            "Regional TBI incidence by age band (aggregate burden)."
        ),
        "expected_database": "GBD",
        "expected_feasible": False,
        "expected_rationale_contains": "PLANNED",
    },
    # tbi_03 - CHARLS false (older adult longitudinal cognitive trajectories; adapter planned)
    {
        "task_id": "tbi_03",
        "question": (
            "Post-concussion cognitive trajectories in older adults."
        ),
        "expected_database": "CHARLS",
        "expected_feasible": False,
        "expected_rationale_contains": "PLANNED",
    },
    # tumor_01 - SEER false (survival/resection registry; adapter planned)
    {
        "task_id": "tumor_01",
        "question": (
            "Glioblastoma survival by extent of resection, US registry data."
        ),
        "expected_database": "SEER",
        "expected_feasible": False,
        "expected_rationale_contains": "PLANNED",
    },
    # tumor_02 - NHANES false (meningioma/histology unavailable)
    {
        "task_id": "tumor_02",
        "question": (
            "Is meningioma prevalence captured in NHANES?"
        ),
        "expected_database": "NHANES",
        "expected_feasible": False,
        "expected_rationale_contains": "histology",
    },
    # tumor_03 - GBD false (global DALYs/burden; adapter planned)
    {
        "task_id": "tumor_03",
        "question": (
            "Global brain/CNS cancer disability-adjusted life-years by region."
        ),
        "expected_database": "GBD",
        "expected_feasible": False,
        "expected_rationale_contains": "PLANNED",
    },
    # cross_01 - NHANES true
    {
        "task_id": "cross_01",
        "question": (
            "Fasting glucose and insulin resistance (HOMA-IR) association with "
            "self-reported stroke, NHANES 2011-2014."
        ),
        "expected_database": "NHANES",
        "expected_feasible": True,
        "expected_rationale_contains": "known epidemiology domain",
    },
]


@pytest.mark.parametrize("test_case", BENCHMARK_TEST_CASES)
def test_benchmark_routing_exact_behavior(test_case):
    """Test exact routing behavior for all 10 benchmark tasks."""
    decision = route(test_case["question"])

    assert decision.database == test_case["expected_database"], \
        f"Task {test_case['task_id']}: expected {test_case['expected_database']}, got {decision.database}"

    assert decision.feasible == test_case["expected_feasible"], \
        f"Task {test_case['task_id']}: expected feasible={test_case['expected_feasible']}, got {decision.feasible}"

    assert test_case["expected_rationale_contains"].lower() in decision.rationale.lower(), \
        f"Task {test_case['task_id']}: expected rationale to contain '{test_case['expected_rationale_contains']}', got '{decision.rationale}'"


def test_stroke_routes_to_nhanes_feasible():
    d = route("Is self-reported stroke associated with metabolic syndrome in US adults?")
    assert d.database == "NHANES"
    assert d.feasible is True
    assert any("cross-sectional" in c for c in d.caveats)


def test_tbi_keyword_routes_to_nhanes_with_caveat():
    d = route("tbi prevalence in adults")
    assert d.database == "NHANES"
    assert d.feasible is True
    # NHANES limitation caveat always attaches for the supported DB
    assert len(d.caveats) >= 1


def test_tumor_aggregate_routes_to_planned_gbd():
    d = route("global tumor burden by region")
    assert d.feasible is False
    assert d.status.value == "planned"
    assert d.database in {"GBD", "SEER"}  # both planned; router returns first match


def test_cancer_registry_routes_to_planned_seer():
    d = route("cancer survival in registry data")
    assert d.feasible is False
    assert d.status.value == "planned"
    assert d.database == "SEER"


def test_no_match_defaults_to_nhanes_infeasible():
    """Conservative refusal: unknown questions are infeasible."""
    d = route("something completely unrelated xyzzy")
    assert d.database == "NHANES"
    assert d.feasible is False  # Changed from True to False (conservative)
    assert any("did not match" in c for c in d.caveats)


def test_surgery_question_infeasible():
    """Surgery-related questions are infeasible for NHANES."""
    d = route("Does laparoscopic bariatric surgery reduce stroke recurrence?")
    assert d.database == "NHANES"
    assert d.feasible is False
    assert "surgery" in d.rationale.lower()


def test_longitudinal_question_infeasible():
    """Longitudinal questions are infeasible for cross-sectional NHANES."""
    d = route("5-year stroke recurrence after surgery")
    assert d.database == "NHANES"
    assert d.feasible is False
    assert "longitudinal" in d.rationale.lower() or "cross-sectional" in d.rationale.lower()


def test_regional_question_infeasible():
    """Regional/global burden questions are infeasible for US-only NHANES."""
    d = route("Regional TBI incidence by age band")
    assert d.database == "GBD"  # Routes to GBD but infeasible
    assert d.feasible is False
    assert "PLANNED" in d.rationale


def test_histology_question_infeasible():
    """Histology questions are infeasible for NHANES."""
    d = route("Is meningioma prevalence captured in NHANES?")
    assert d.database == "NHANES"
    assert d.feasible is False
    assert "histology" in d.rationale.lower()


def test_explicit_database_name():
    """Explicit database name should be honored."""
    d = route("Stroke prevalence in NHANES 2011-2018")
    assert d.database == "NHANES"
    assert d.feasible is True
