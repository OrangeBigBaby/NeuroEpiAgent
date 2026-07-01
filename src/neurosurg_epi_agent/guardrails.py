"""Deterministic statistical and language guardrails.

These checks encode NHANES survey-design rules and causal-language policy that
an LLM planner routinely gets wrong. They are rules, not heuristics, and never
invent corrections: when a rule fires it points the human at the policy and the
codebook, it does not auto-rewrite variable names.
"""

from __future__ import annotations

import re

from .registry import variables_by_name
from .schemas import (
    AnalysisPlan,
    DatabaseConfig,
    Finding,
    GuardrailReport,
    Severity,
    VariableMapping,
    VariableStatus,
)

# NHANES survey-design canonical variable stems.
NHANES_PSU = "SDMVPSU"
NHANES_STRATA = "SDMVSTRA"
MEC_WEIGHT = "WTMEC2YR"
FASTING_WEIGHT = "WTSAF2YR"

# NHANES release suffix -> years (used only for cycle-counting, not assertions
# about which variables exist).
CYCLE_SUFFIXES = ("C", "D", "E", "F", "G", "H", "I", "J")


# --------------------------------------------------------------------------- #
# Causal language.
# --------------------------------------------------------------------------- #

_FORBIDDEN_CAUSAL = re.compile(
    r"\b(proves?|causes?|proven|establishes?|definitively|first ever|"
    r"comprehensive|unprecedented|cures?|guarantees?)\b",
    re.IGNORECASE,
)


def check_causal_language(plan: AnalysisPlan) -> list[Finding]:
    findings: list[Finding] = []
    for sentence in plan.causal_claims:
        m = _FORBIDDEN_CAUSAL.search(sentence)
        if m:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    code="CAUSAL_LANGUAGE",
                    message=f"Causal/overclaiming word '{m.group(0)!r}' in: {sentence!r}",
                    remediation=(
                        "Observational NHANES data cannot support causal claims. "
                        "Use 'is associated with', 'suggests', or 'may'."
                    ),
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Survey design.
# --------------------------------------------------------------------------- #

def check_survey_design(plan: AnalysisPlan) -> list[Finding]:
    findings: list[Finding] = []
    dv = plan.design_vars
    if plan.database.upper() != "NHANES":
        return findings  # non-NHANES design rules are adapter-specific (planned)

    if dv.get("id", "").upper() != NHANES_PSU:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code="NHANES_PSU",
                message=f"design_vars.id must be {NHANES_PSU}, got {dv.get('id')!r}",
                remediation="NHANES requires SDMVPSU as the cluster/PSU id.",
            )
        )
    if dv.get("strata", "").upper() != NHANES_STRATA:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code="NHANES_STRATA",
                message=f"design_vars.strata must be {NHANES_STRATA}, got {dv.get('strata')!r}",
                remediation="NHANES requires SDMVSTRA as the strata variable.",
            )
        )
    weight = dv.get("weight", "")
    if not weight:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code="NHANES_WEIGHT_MISSING",
                message="design_vars.weight is empty",
                remediation="Specify the analysis weight (WTMEC2YR or WTSAF2YR rescaled).",
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Multi-cycle weight rescaling.
# --------------------------------------------------------------------------- #

def _expected_weight(n_cycles: int, fasting: bool) -> str:
    base = FASTING_WEIGHT if fasting else MEC_WEIGHT
    if n_cycles <= 0:
        return base
    return f"{base}/{n_cycles}"


def check_multi_cycle_weights(plan: AnalysisPlan) -> list[Finding]:
    findings: list[Finding] = []
    if plan.database.upper() != "NHANES":
        return findings

    n_cycles = len(plan.cycles)
    if n_cycles == 0:
        findings.append(
            Finding(
                severity=Severity.WARNING,
                code="NO_CYCLES",
                message="No NHANES cycles declared; cannot verify weight rescaling.",
                remediation="Declare the cycle suffixes pooled, e.g. ['G','H','I','J'].",
            )
        )
        return findings

    weight = plan.design_vars.get("weight", "")
    expected = _expected_weight(n_cycles, plan.uses_fasting_subsample)

    # Detect a literal "WTXXX2YR / <n>" expression; the engine checks the
    # divisor, not the base name (base-name correctness is a codebook concern).
    m = re.match(r"^(WT(?:MEC|SAF)2YR)\s*/\s*(\d+)$", weight.strip(), re.IGNORECASE)
    if not m:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code="WEIGHT_RESCALE",
                message=(
                    f"weight {weight!r} is not expressed as WTMEC2YR or WTSAF2YR divided "
                    f"by the number of cycles."
                ),
                remediation=(
                    f"Expected rescaled weight expression: {expected} "
                    f"({n_cycles} cycle(s) pooled)."
                ),
            )
        )
        return findings

    declared_divisor = int(m.group(2))
    if declared_divisor != n_cycles:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code="WEIGHT_RESCALE",
                message=(
                    f"weight divisor {declared_divisor} != number of cycles pooled ({n_cycles})"
                ),
                remediation=f"Use {expected}.",
            )
        )

    if plan.uses_fasting_subsample and not weight.upper().startswith("WTSAF2YR"):
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code="FASTING_WEIGHT_MISMATCH",
                message="Fasting subsample selected but weight base is not WTSAF2YR.",
                remediation="Fasting labs require WTSAF2YR, not WTMEC2YR.",
            )
        )
    if (not plan.uses_fasting_subsample) and weight.upper().startswith("WTSAF2YR"):
        findings.append(
            Finding(
                severity=Severity.WARNING,
                code="FASTING_WEIGHT_UNEXPECTED",
                message="WTSAF2YR used but plan does not declare a fasting subsample.",
                remediation="Confirm fasting labs are actually used; otherwise switch to WTMEC2YR.",
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Fasting subsample mismatch (a second, design-level check).
# --------------------------------------------------------------------------- #

FASTING_LAB_HINTS = ("fasting", "glucose", "insulin", "homa", "ldl_direct", "triglyceride")


def check_fasting_subsample(plan: AnalysisPlan) -> list[Finding]:
    findings: list[Finding] = []
    all_vars = list(plan.exposures) + list(plan.covariates)
    if plan.outcome is not None:
        all_vars.append(plan.outcome)
    labels = " ".join(
        (v.label + " " + (v.name or "") + " " + (v.transform or "")).lower()
        for v in all_vars
    )
    looks_fasting = any(h in labels for h in FASTING_LAB_HINTS)

    if looks_fasting and not plan.uses_fasting_subsample:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code="FASTING_SUBSAMPLE_UNDECLARED",
                message="Plan references fasting-lab variables but uses_fasting_subsample is False.",
                remediation=(
                    "NHANES fasting labs (glucose, insulin, etc.) are only measured on the "
                    "morning subsample; set uses_fasting_subsample=True and use WTSAF2YR."
                ),
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Variable-status provenance.
# --------------------------------------------------------------------------- #

def check_variable_provenance(plan: AnalysisPlan) -> list[Finding]:
    findings: list[Finding] = []
    vs: list[VariableMapping] = []
    if plan.outcome is not None:
        vs.append(plan.outcome)
    vs.extend(plan.exposures)
    vs.extend(plan.covariates)
    for v in vs:
        if v.status is VariableStatus.NEEDS_REVIEW:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    code="UNRESOLVED_VARIABLE",
                    message=f"Variable {v.name!r} ({v.source_variable}) is status 'needs review'.",
                    remediation="Confirm the codebook stem against the NHANES release before analysis.",
                )
            )
        elif v.status is VariableStatus.ILLUSTRATIVE:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="ILLUSTRATIVE_VARIABLE",
                    message=f"Variable {v.name!r} ({v.source_variable}) is illustrative, not verified.",
                    remediation="Acceptable for scaffolding; resolve before any reported result.",
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Cycle-coverage cross-check (declared cycles vs. variable registry).
# --------------------------------------------------------------------------- #

def check_cycle_coverage(
    plan: AnalysisPlan, variables: list[VariableMapping] | None
) -> list[Finding]:
    if not variables or not plan.cycles:
        return []
    by_name = variables_by_name(variables)
    findings: list[Finding] = []
    names: list[VariableMapping] = []
    if plan.outcome is not None:
        names.append(plan.outcome)
    names.extend(plan.exposures)
    names.extend(plan.covariates)
    for v in names:
        reg = by_name.get(v.name)
        if reg is None or not reg.nhanes_cycles:
            continue
        missing = sorted(set(plan.cycles) - set(reg.nhanes_cycles))
        if missing:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="CYCLE_COVERAGE",
                    message=(
                        f"Variable {v.name!r} registry lists cycles {reg.nhanes_cycles}; "
                        f"plan requests {plan.cycles} (missing {missing})."
                    ),
                    remediation="Confirm the stem exists in every requested cycle's codebook.",
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Aggregate.
# --------------------------------------------------------------------------- #

def evaluate_plan(
    plan: AnalysisPlan,
    *,
    database: DatabaseConfig | None = None,
    variables: list[VariableMapping] | None = None,
) -> GuardrailReport:
    """Evaluate a plan against guardrails.

    For infeasible plans (plan.feasible=False), skips analysis-execution guardrails
    that require survey design, weights, fasting declarations, and variable resolution.
    Still checks causal overstatement and database integrity where applicable.

    Args:
        plan: Analysis plan to evaluate
        database: Optional database configuration for integrity checks
        variables: Optional variable registry for provenance checks

    Returns:
        GuardrailReport with findings
    """
    findings: list[Finding] = []

    # Always check causal language (even for infeasible plans)
    findings.extend(check_causal_language(plan))

    # Check database integrity if database config provided
    if database is not None and plan.database.upper() != database.name.upper():
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code="DATABASE_MISMATCH",
                message=f"plan.database={plan.database!r} but routed/registry database={database.name!r}",
            )
        )

    # For infeasible plans, skip analysis-execution guardrails
    # These require survey design, weights, fasting, and variable resolution
    if not plan.feasible:
        return GuardrailReport(findings=findings)

    # For feasible plans, run all guardrails
    findings.extend(check_survey_design(plan))
    findings.extend(check_multi_cycle_weights(plan))
    findings.extend(check_fasting_subsample(plan))
    findings.extend(check_variable_provenance(plan))
    findings.extend(check_cycle_coverage(plan, variables))

    return GuardrailReport(findings=findings)
