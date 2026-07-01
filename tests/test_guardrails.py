from neurosurg_epi_agent.guardrails import (
    check_causal_language,
    check_cycle_coverage,
    check_fasting_subsample,
    check_multi_cycle_weights,
    check_survey_design,
    check_variable_provenance,
    evaluate_plan,
)
from neurosurg_epi_agent.schemas import (
    AnalysisPlan,
    PlanStep,
    Severity,
    VariableMapping,
    VariableStatus,
)


def vm(name="x", source="LBXTC", status=VariableStatus.ILLUSTRATIVE, label="X", module="LAB"):
    return VariableMapping(
        name=name, label=label, source_variable=source,
        source_module=module, status=status,
    )


def base_plan(**kw):
    defaults = dict(
        title="t", question="q", database="NHANES",
        cycles=["G", "H", "I", "J"],
        design_vars={"id": "SDMVPSU", "strata": "SDMVSTRA", "weight": "WTMEC2YR/4"},
        steps=[PlanStep(step="1", description="merge")],
    )
    defaults.update(kw)
    return AnalysisPlan(**defaults)


# ---- causal language -------------------------------------------------------

def test_causal_overclaim_flagged():
    p = base_plan(causal_claims=["Surgery proves stroke recurrence drops."])
    fs = check_causal_language(p)
    assert any(f.code == "CAUSAL_LANGUAGE" and f.severity is Severity.ERROR for f in fs)


def test_association_language_ok():
    p = base_plan(causal_claims=["Sarcopenia is associated with stroke."])
    assert check_causal_language(p) == []


# ---- survey design ---------------------------------------------------------

def test_missing_design_vars_flagged():
    p = base_plan(design_vars={})
    codes = {f.code for f in check_survey_design(p)}
    assert {"NHANES_PSU", "NHANES_STRATA", "NHANES_WEIGHT_MISSING"} <= codes


def test_correct_design_passes():
    assert check_survey_design(base_plan()) == []


# ---- weight rescaling ------------------------------------------------------

def test_weight_correct_divisor_passes():
    assert check_multi_cycle_weights(base_plan()) == []


def test_weight_wrong_divisor_flagged():
    p = base_plan(design_vars={"id": "SDMVPSU", "strata": "SDMVSTRA", "weight": "WTMEC2YR/2"})
    fs = check_multi_cycle_weights(p)
    assert any(f.code == "WEIGHT_RESCALE" and f.severity is Severity.ERROR for f in fs)


def test_weight_not_rescaled_flagged():
    p = base_plan(design_vars={"id": "SDMVPSU", "strata": "SDMVSTRA", "weight": "WTMEC2YR"})
    fs = check_multi_cycle_weights(p)
    assert any(f.code == "WEIGHT_RESCALE" for f in fs)


def test_fasting_subsample_uses_wtsaf():
    p = base_plan(
        uses_fasting_subsample=True,
        design_vars={"id": "SDMVPSU", "strata": "SDMVSTRA", "weight": "WTSAF2YR/4"},
    )
    assert check_multi_cycle_weights(p) == []


def test_fasting_flag_without_wtsaf_flagged():
    p = base_plan(
        uses_fasting_subsample=True,
        design_vars={"id": "SDMVPSU", "strata": "SDMVSTRA", "weight": "WTMEC2YR/4"},
    )
    fs = check_multi_cycle_weights(p)
    assert any(f.code == "FASTING_WEIGHT_MISMATCH" for f in fs)


# ---- fasting subsample detection ------------------------------------------

def test_fasting_lab_without_subsample_flagged():
    lab = vm(name="fglu", source="LBXGLU", label="Fasting glucose")
    p = base_plan(exposures=[lab], uses_fasting_subsample=False)
    fs = check_fasting_subsample(p)
    assert any(f.code == "FASTING_SUBSAMPLE_UNDECLARED" for f in fs)


def test_fasting_lab_with_subsample_ok():
    lab = vm(name="fglu", source="LBXGLU", label="Fasting glucose")
    p = base_plan(exposures=[lab], uses_fasting_subsample=True,
                  design_vars={"id": "SDMVPSU", "strata": "SDMVSTRA", "weight": "WTSAF2YR/4"})
    assert check_fasting_subsample(p) == []


# ---- variable provenance ---------------------------------------------------

def test_needs_review_blocks():
    p = base_plan(outcome=vm(name="s", status=VariableStatus.NEEDS_REVIEW))
    fs = check_variable_provenance(p)
    assert any(f.code == "UNRESOLVED_VARIABLE" and f.severity is Severity.ERROR for f in fs)


def test_illustrative_warns():
    p = base_plan(outcome=vm(name="s", status=VariableStatus.ILLUSTRATIVE))
    fs = check_variable_provenance(p)
    assert any(f.code == "ILLUSTRATIVE_VARIABLE" and f.severity is Severity.WARNING for f in fs)


# ---- cycle coverage --------------------------------------------------------

def test_cycle_coverage_warns_on_missing_cycle():
    reg_var = vm(name="bmi", source="BMXBMI", status=VariableStatus.ILLUSTRATIVE)
    reg_var.nhanes_cycles = ["G", "H"]  # only registered for 2 cycles
    p = base_plan(cycles=["G", "H", "I", "J"], exposures=[reg_var])
    fs = check_cycle_coverage(p, [reg_var])
    assert any(f.code == "CYCLE_COVERAGE" for f in fs)


# ---- aggregate -------------------------------------------------------------

def test_aggregate_failed_plan_reports_errors():
    p = base_plan(
        design_vars={},
        causal_claims=["This proves causation."],
        outcome=vm(name="s", status=VariableStatus.NEEDS_REVIEW),
    )
    report = evaluate_plan(p)
    assert not report.passed
    assert len(report.errors) >= 4  # psu + strata + weight + causal + unresolved


def test_aggregate_clean_plan_passes():
    p = base_plan(
        outcome=vm(name="s", status=VariableStatus.VERIFIED),
    )
    report = evaluate_plan(p)
    assert report.passed, [f.model_dump() for f in report.findings]


# ---- v0.2 infeasible plan guardrail skips -----------------------------------

def test_infeasible_plan_skips_analysis_execution_guardrails():
    """Infeasible plans skip survey design, weights, fasting, and variable guardrails."""
    p = base_plan(
        feasible=False,
        design_vars={},  # Missing design vars (would normally fail)
        causal_claims=["This proves causation."],  # Causal overstatement (still checked)
    )

    report = evaluate_plan(p)

    # Should still have causal language error
    assert any(f.code == "CAUSAL_LANGUAGE" for f in report.findings)

    # Should NOT have survey design errors (skipped for infeasible)
    assert not any(f.code.startswith("NHANES_") for f in report.findings)

    # Should NOT have weight errors (skipped for infeasible)
    assert not any(f.code in {"MULTICYCLE_WEIGHT_RESCALE", "FASTING_SUBSAMPLE_MISMATCH"} for f in report.findings)

    # Should NOT have variable provenance errors (skipped for infeasible)
    assert not any(f.code == "VARIABLE_STATUS_NEEDS_REVIEW" for f in report.findings)


def test_infeasible_plan_still_checks_causal_language():
    """Infeasible plans still check causal language."""
    p = base_plan(
        feasible=False,
        causal_claims=["Surgery proves stroke recurrence drops."],
    )

    report = evaluate_plan(p)

    # Should still flag causal language
    assert any(f.code == "CAUSAL_LANGUAGE" and f.severity is Severity.ERROR for f in report.findings)


def test_infeasible_plan_still_checks_database_integrity():
    """Infeasible plans still check database integrity."""
    from neurosurg_epi_agent.schemas import DatabaseConfig

    p = base_plan(
        feasible=False,
        database="GBD",  # Mismatch with NHANES database config
    )

    db_config = DatabaseConfig(
        name="NHANES",
        label="NHANES",
        data_type="cross-sectional",
        status="supported",
    )

    report = evaluate_plan(p, database=db_config)

    # Should flag database mismatch
    assert any(f.code == "DATABASE_MISMATCH" for f in report.findings)


def test_infeasible_plan_clean_refusal():
    """Clean infeasible refusal without variables should have no guardrail errors."""
    p = AnalysisPlan(
        title="Feasibility assessment",
        question="Does bariatric surgery reduce stroke recurrence?",
        database="NHANES",
        cycles=[],
        feasible=False,
        outcome=None,  # No variables
        exposures=[],
        covariates=[],
        design_vars={},
        steps=[],
        causal_claims=[],  # No causal claims
    )

    report = evaluate_plan(p)

    # Should have no findings (clean refusal)
    assert len(report.findings) == 0
    assert report.passed
