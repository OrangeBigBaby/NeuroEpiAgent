"""Typed Pydantic schemas for plans, variable mappings, and guardrail findings.

These schemas are the contract boundary between the LLM planner and the
deterministic engine. The LLM proposes; these types validate.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# --------------------------------------------------------------------------- #
# Status enums - explicit provenance, never defaulted to "verified".
# --------------------------------------------------------------------------- #

class EvidenceStatus(str, Enum):
    SUPPORTED = "supported"
    NEEDS_EVIDENCE = "needs evidence"
    INFERRED = "inferred"


class VariableStatus(str, Enum):
    """Provenance of a variable mapping. Only VERIFIED is treated as ground truth."""

    VERIFIED = "verified"          # confirmed against an NHANES codebook release
    ILLUSTRATIVE = "illustrative"  # shape/format correct, code NOT independently confirmed
    NEEDS_REVIEW = "needs review"  # placeholder, must be resolved before analysis


class DatabaseStatus(str, Enum):
    SUPPORTED = "supported"
    PLANNED = "planned"      # adapter scaffolded but not active in MVP
    DISABLED = "disabled"


class Severity(str, Enum):
    ERROR = "error"      # blocks plan acceptance
    WARNING = "warning"  # plan accepted with caveat
    INFO = "info"


# --------------------------------------------------------------------------- #
# Variable + database registry models.
# --------------------------------------------------------------------------- #

class NHANESCycleInfo(BaseModel):
    cycle: str = Field(..., description="e.g. '2017-2018'")
    suffix: str = Field(..., description="NHANES release suffix, e.g. 'J'")


class VariableMapping(BaseModel):
    name: str = Field(..., description="Analysis-ready variable name, e.g. 'ldl'")
    label: str
    source_variable: str = Field(
        ..., description="Raw codebook stem, e.g. 'LBXBCD' (must match codebook)"
    )
    source_module: str = Field(..., description="NHANES component, e.g. 'LAB', 'DEMO', 'MCQ'")
    units: str | None = None
    transform: str | None = Field(
        default=None,
        description="Derivation note, e.g. 'mg/dL', 'appendicular lean / BMI'.",
    )
    status: VariableStatus
    nhanes_cycles: list[str] = Field(
        default_factory=list,
        description="Release suffixes where this stem is expected to exist, e.g. ['G','H','I','J'].",
    )
    ref_notes: str | None = Field(
        default=None,
        description="Free-text provenance; for VERIFIED this names the codebook. No PMIDs invented."
    )

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> Any:
        return v


class WeightScheme(BaseModel):
    base_weight: str = Field(..., description="e.g. WTMEC2YR, WTSAF2YR")
    rescale_rule: str = Field(
        ..., description="Human-readable rescaling rule applied deterministically."
    )


class SurveyDesign(BaseModel):
    id_var: str
    strata_var: str
    weight_var: str
    nest: bool = True
    weight_scheme: WeightScheme


class DatabaseConfig(BaseModel):
    name: str
    label: str
    data_type: str = Field(..., description="cross-sectional / panel / registry / aggregate")
    cycles: list[NHANESCycleInfo] = Field(default_factory=list)
    survey_design: SurveyDesign | None = None
    status: DatabaseStatus
    notes: str | None = None


# --------------------------------------------------------------------------- #
# Plan models - what the LLM proposes and the engine validates.
# --------------------------------------------------------------------------- #

class PlanStep(BaseModel):
    step: str
    description: str
    outputs: list[str] = Field(default_factory=list)


class AnalysisPlan(BaseModel):
    title: str
    question: str
    database: str
    cycles: list[str] = Field(default_factory=list, description="NHANES cycle suffixes")
    feasible: bool = True
    outcome: VariableMapping | None = None
    exposures: list[VariableMapping] = Field(default_factory=list)
    covariates: list[VariableMapping] = Field(default_factory=list)
    uses_fasting_subsample: bool = False
    design_vars: dict[str, str] = Field(
        default_factory=dict,
        description="id/strata/weight variable names expected for this plan.",
    )
    steps: list[PlanStep] = Field(default_factory=list)
    causal_claims: list[str] = Field(
        default_factory=list,
        description="Draft sentences to be screened for causal overstatement."
    )
    rationale: str | None = Field(
        default=None,
        description="Explanation of feasibility and variable mapping choices.",
    )
    guardrail_notes: str | None = Field(
        default=None,
        description="Any known issues or caveats about this plan.",
    )

    @model_validator(mode="after")
    def _check_design_keys(self) -> "AnalysisPlan":
        allowed = {"id", "strata", "weight"}
        bad = set(self.design_vars) - allowed
        if bad:
            raise ValueError(f"Unknown design_vars keys: {sorted(bad)}. Allowed: {sorted(allowed)}")
        return self


# --------------------------------------------------------------------------- #
# Guardrail findings + manifest.
# --------------------------------------------------------------------------- #

class Finding(BaseModel):
    severity: Severity
    code: str
    message: str
    remediation: str | None = None


class GuardrailReport(BaseModel):
    findings: list[Finding] = Field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


class ManifestEntry(BaseModel):
    key: str
    value: str


class Manifest(BaseModel):
    package_version: str
    database: str
    cycles: list[str]
    plan_title: str
    n_errors: int
    n_warnings: int
    variables: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
