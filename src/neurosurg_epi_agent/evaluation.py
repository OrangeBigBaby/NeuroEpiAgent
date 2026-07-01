"""Offline evaluation module for benchmark task scoring.

This module provides typed schemas and scoring logic for comparing pre-generated
planner outputs against a gold standard benchmark. It never calls models or
executes plans — it only evaluates existing outputs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .schemas import AnalysisPlan, VariableStatus
from .telemetry import CallTelemetry


class MetricType(str, Enum):
    """Scoring metric types."""

    DATABASE_ROUTING = "database_routing"
    FEASIBILITY = "feasibility"
    HARD_ERROR_FREE = "hard_error_free"
    CORRECT_REFUSAL = "correct_refusal"
    VARIABLE_CODES = "variable_codes"
    MANIFEST_RECONSTRUCTABILITY = "manifest_reconstructability"


class ProviderArm(str, Enum):
    """Evaluation arms."""

    ARM_A = "arm_a"  # NeuroSurgEpiAgent
    ARM_B = "arm_b"  # Unconstrained LLM baseline


# --------------------------------------------------------------------------- #
# Benchmark task schemas
# --------------------------------------------------------------------------- #

class BenchmarkTask(BaseModel):
    """A single benchmark task with expected behavior."""

    id: str = Field(..., description="Task identifier, e.g., 'stroke_01'")
    domain: str = Field(..., description="Clinical domain: stroke, tbi, tumor, etc.")
    question: str = Field(..., description="Free-text research question")

    # Expected deterministic behavior
    expected_database: str = Field(..., description="Expected database routing")
    expected_feasible: bool = Field(..., description="Expected feasibility assessment")
    rationale: str = Field(..., description="Rationale for expected behavior")

    # Metadata
    domain_specific_notes: str | None = None
    review_status: str = Field(
        default="needs_expert_review",
        description="Validation status: needs_expert_review, expert_validated, draft",
    )
    requires_nhanes_codebook: bool = Field(
        default=False,
        description="Whether NHANES codebook verification is expected",
    )


class ArmOutput(BaseModel):
    """Output from a single provider arm for a single task."""

    task_id: str
    arm: ProviderArm
    provider_type: str = Field(..., description="e.g., 'neurosurg_epi_agent', 'gpt-4_direct'")
    model_label: str | None = Field(
        default=None,
        description="User-supplied model identifier for external LLMs",
    )

    # Generated plan (may be partial/failed)
    plan: AnalysisPlan | None = None

    # Execution metadata
    error: str | None = Field(
        default=None,
        description="Provider error message if plan generation failed",
    )
    execution_time_seconds: float | None = None
    timestamp_utc: str = Field(..., description="ISO 8601 timestamp")

    # Intermediate outputs (for debugging)
    raw_output: str | None = Field(
        default=None,
        description="Raw LLM output if available",
    )
    validation_errors: list[str] = Field(default_factory=list)

    # Guardrail findings (if applicable)
    guardrail_findings: list[dict[str, Any]] = Field(default_factory=list)

    # Publication-auditable model-call telemetry (optional; None for dry runs
    # and deterministic refusals where no model call was attempted). Backward
    # compatible: older experiment JSON without this field validates as None.
    call_telemetry: CallTelemetry | None = Field(
        default=None,
        description="Scalar usage/cost/timing telemetry for the model call, if any",
    )

    # Provenance flag: True when this output was reused from a prior run rather
    # than generated in the current run. Prevents cross-run double counting in
    # efficiency summaries. Backward compatible (defaults False).
    reused: bool = Field(
        default=False,
        description="True if this output was reused from a prior run (not a new call)",
    )


class TaskScore(BaseModel):
    """Scoring result for a single task on a single metric."""

    task_id: str
    metric: MetricType
    passed: bool
    details: str | None = None
    score_value: float | None = Field(
        default=None,
        description="Numeric score for this metric (0-1 or count)",
    )


class EvaluationRun(BaseModel):
    """Manifest for a complete evaluation run."""

    # Provenance hashes
    prompt_hash: str = Field(..., description="SHA256 of planner prompt template")
    registry_hash: str = Field(..., description="SHA256 of variable registry file")
    task_set_hash: str = Field(..., description="SHA256 of benchmark task set")

    # Configuration
    package_version: str = Field(..., description="NeuroSurgEpiAgent version")
    model_label: str | None = Field(
        default=None,
        description="User-supplied model identifier for external LLMs",
    )

    # Timestamps
    timestamp_utc: str = Field(..., description="ISO 8601 timestamp")

    # Results
    tasks: list[BenchmarkTask] = Field(default_factory=list)
    arm_outputs: dict[str, ArmOutput] = Field(
        default_factory=dict,
        description="task_id:arm -> ArmOutput",
    )
    scores: dict[str, dict[str, list[TaskScore]]] = Field(
        default_factory=dict,
        description="arm -> metric -> list of TaskScore",
    )

    # Summary statistics
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-arm, per-metric aggregate counts and proportions",
    )


# --------------------------------------------------------------------------- #
# Scoring functions
# --------------------------------------------------------------------------- #

@dataclass
class ScoringContext:
    """Context for scoring a single task."""

    task: BenchmarkTask
    arm_output: ArmOutput
    allowed_variable_codes: set[str]  # From registry


def _sha256_file(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def _score_database_routing(ctx: ScoringContext) -> TaskScore:
    """Score database routing correctness."""
    if ctx.arm_output.plan is None:
        return TaskScore(
            task_id=ctx.task.id,
            metric=MetricType.DATABASE_ROUTING,
            passed=False,
            details="No plan generated to evaluate routing",
            score_value=0.0,
        )

    plan_db = ctx.arm_output.plan.database
    expected_db = ctx.task.expected_database

    passed = plan_db == expected_db
    return TaskScore(
        task_id=ctx.task.id,
        metric=MetricType.DATABASE_ROUTING,
        passed=passed,
        details=f"Plan routed to {plan_db}, expected {expected_db}",
        score_value=1.0 if passed else 0.0,
    )


def _score_feasibility(ctx: ScoringContext) -> TaskScore:
    """Score feasibility assessment correctness."""
    if ctx.arm_output.plan is None:
        return TaskScore(
            task_id=ctx.task.id,
            metric=MetricType.FEASIBILITY,
            passed=False,
            details="No plan generated to evaluate feasibility",
            score_value=0.0,
        )

    plan_feasible = ctx.arm_output.plan.feasible
    expected_feasible = ctx.task.expected_feasible

    passed = plan_feasible == expected_feasible
    return TaskScore(
        task_id=ctx.task.id,
        metric=MetricType.FEASIBILITY,
        passed=passed,
        details=f"Plan feasible={plan_feasible}, expected {expected_feasible}",
        score_value=1.0 if passed else 0.0,
    )


def _score_hard_error_free(ctx: ScoringContext) -> TaskScore:
    """Score that plan generation completed without hard errors.

    A hard error includes:
    - Provider error that prevented plan generation
    - Validation errors during plan validation
    - ERROR-severity guardrail findings
    """
    # Check for provider error
    has_provider_error = ctx.arm_output.error is not None

    # Check for validation errors
    has_validation_errors = len(ctx.arm_output.validation_errors) > 0

    # Check for ERROR-severity guardrail findings
    has_guardrail_errors = any(
        f.get("severity") == "error" or f.get("severity") == "ERROR"
        for f in ctx.arm_output.guardrail_findings
    )

    has_hard_error = has_provider_error or has_validation_errors or has_guardrail_errors

    error_details = []
    if has_provider_error:
        error_details.append(f"Provider error: {ctx.arm_output.error}")
    if has_validation_errors:
        error_details.append(f"Validation errors: {ctx.arm_output.validation_errors}")
    if has_guardrail_errors:
        error_details.append(f"Guardrail errors: {sum(1 for f in ctx.arm_output.guardrail_findings if f.get('severity') in ['error', 'ERROR'])} findings")

    passed = not has_hard_error
    return TaskScore(
        task_id=ctx.task.id,
        metric=MetricType.HARD_ERROR_FREE,
        passed=passed,
        details="; ".join(error_details) if has_hard_error else "Plan generated successfully without hard errors",
        score_value=1.0 if passed else 0.0,
    )


def _score_correct_refusal(ctx: ScoringContext) -> TaskScore:
    """Score correct refusal / acceptance of feasibility.

    Credit requires a successfully parsed, error-free plan whose ``feasible``
    flag matches the task expectation: ``feasible=False`` for an
    expected-infeasible task (an explained refusal) and ``feasible=True`` for
    an expected-feasible task. A provider error, a validation error, or a
    missing plan is a failure mode — not an explained refusal — and must never
    receive credit on this metric.
    """
    plan = ctx.arm_output.plan
    expected_feasible = ctx.task.expected_feasible

    if plan is None:
        passed = False
        detail = "Missing plan (provider/validation failure) - not a correct refusal"
    elif ctx.arm_output.error is not None:
        passed = False
        detail = f"Provider error present - not a correct refusal: {ctx.arm_output.error}"
    elif ctx.arm_output.validation_errors:
        passed = False
        detail = (
            "Validation errors present - not a correct refusal: "
            f"{ctx.arm_output.validation_errors}"
        )
    else:
        passed = plan.feasible == expected_feasible
        detail = f"plan.feasible={plan.feasible}, expected_feasible={expected_feasible}"

    return TaskScore(
        task_id=ctx.task.id,
        metric=MetricType.CORRECT_REFUSAL,
        passed=passed,
        details=detail,
        score_value=1.0 if passed else 0.0,
    )


def _score_variable_codes(ctx: ScoringContext) -> TaskScore:
    """Score that variable codes come from the allowed registry set."""
    if ctx.arm_output.plan is None:
        return TaskScore(
            task_id=ctx.task.id,
            metric=MetricType.VARIABLE_CODES,
            passed=False,
            details="No plan generated to evaluate variable codes",
            score_value=0.0,
        )

    plan = ctx.arm_output.plan

    # Collect all variable codes from the plan
    all_codes = set()
    if plan.outcome:
        all_codes.add(plan.outcome.source_variable)
    for exp in plan.exposures:
        all_codes.add(exp.source_variable)
    for cov in plan.covariates:
        all_codes.add(cov.source_variable)

    # Check if all codes are in the allowed set
    disallowed = all_codes - ctx.allowed_variable_codes

    passed = len(disallowed) == 0
    return TaskScore(
        task_id=ctx.task.id,
        metric=MetricType.VARIABLE_CODES,
        passed=passed,
        details=f"All {len(all_codes)} codes from registry" if passed else f"Disallowed codes: {sorted(disallowed)}",
        score_value=1.0 if passed else 0.0,
    )


def _score_manifest_reconstructability(ctx: ScoringContext) -> TaskScore:
    """Score that the plan can be serialized and reconstructed."""
    if ctx.arm_output.plan is None:
        return TaskScore(
            task_id=ctx.task.id,
            metric=MetricType.MANIFEST_RECONSTRUCTABILITY,
            passed=False,
            details="No plan generated to evaluate reconstructability",
            score_value=0.0,
        )

    plan = ctx.arm_output.plan

    try:
        # Try to serialize and deserialize
        serialized = plan.model_dump_json()
        reconstructed = AnalysisPlan.model_validate_json(serialized)

        # Basic sanity checks
        passed = (
            reconstructed.question == plan.question
            and reconstructed.database == plan.database
            and reconstructed.feasible == plan.feasible
        )
    except Exception as e:
        passed = False

    return TaskScore(
        task_id=ctx.task.id,
        metric=MetricType.MANIFEST_RECONSTRUCTABILITY,
        passed=passed,
        details="Plan successfully serialized and reconstructed" if passed else "Plan reconstruction failed",
        score_value=1.0 if passed else 0.0,
    )


def score_task(
    task: BenchmarkTask,
    arm_output: ArmOutput,
    allowed_variable_codes: set[str],
) -> list[TaskScore]:
    """Score a single task on all metrics."""
    ctx = ScoringContext(
        task=task,
        arm_output=arm_output,
        allowed_variable_codes=allowed_variable_codes,
    )

    scores = [
        _score_database_routing(ctx),
        _score_feasibility(ctx),
        _score_hard_error_free(ctx),
        _score_correct_refusal(ctx),
        _score_variable_codes(ctx),
        _score_manifest_reconstructability(ctx),
    ]

    return scores


def compute_summary_scores(scores: dict[str, dict[str, list[TaskScore]]]) -> dict[str, Any]:
    """Compute aggregate summary statistics from scores.

    Args:
        scores: Nested dict of arm -> metric -> list of TaskScore

    Returns:
        Summary dict with per-arm, per-metric aggregates
    """
    summary = {}

    for arm, metric_scores in scores.items():
        arm_summary = {}
        for metric_type, score_list in metric_scores.items():
            if not score_list:
                continue

            passed_count = sum(1 for s in score_list if s.passed)
            total_count = len(score_list)
            proportion = passed_count / total_count if total_count > 0 else 0.0

            arm_summary[metric_type] = {
                "passed": passed_count,
                "total": total_count,
                "proportion": round(proportion, 3),
            }

        summary[arm] = arm_summary

    return summary


def create_evaluation_run(
    tasks: list[BenchmarkTask],
    arm_outputs: list[ArmOutput],
    prompt_path: Path,
    registry_path: Path,
    task_set_path: Path,
    package_version: str,
    model_label: str | None = None,
    allowed_variable_codes: set[str] | None = None,
) -> EvaluationRun:
    """Create a complete evaluation run with scoring."""

    # Compute hashes
    prompt_hash = _sha256_file(prompt_path)
    registry_hash = _sha256_file(registry_path)
    task_set_hash = _sha256_file(task_set_path)

    # Create timestamp
    timestamp_utc = datetime.now(timezone.utc).isoformat()

    # Organize arm outputs by task and arm
    outputs_by_task: dict[str, dict[ProviderArm, ArmOutput]] = {}
    for output in arm_outputs:
        if output.task_id not in outputs_by_task:
            outputs_by_task[output.task_id] = {}
        outputs_by_task[output.task_id][output.arm] = output

    # Score all tasks with per-arm structure
    all_scores: dict[str, dict[str, list[TaskScore]]] = {
        arm.value: {metric.value: [] for metric in MetricType}
        for arm in ProviderArm
    }

    for task in tasks:
        for arm in [ProviderArm.ARM_A, ProviderArm.ARM_B]:
            # Check if output exists for this task-arm combination
            if task.id in outputs_by_task and arm in outputs_by_task[task.id]:
                arm_output = outputs_by_task[task.id][arm]
                task_scores = score_task(
                    task=task,
                    arm_output=arm_output,
                    allowed_variable_codes=allowed_variable_codes or set(),
                )
                for score in task_scores:
                    all_scores[arm.value][score.metric.value].append(score)
            else:
                # Missing output: score as failure for all metrics
                missing_output = ArmOutput(
                    task_id=task.id,
                    arm=arm,
                    provider_type="missing",
                    timestamp_utc=timestamp_utc,
                    plan=None,
                    error="Missing output for this task-arm combination",
                    validation_errors=[],
                    guardrail_findings=[],
                )

                task_scores = score_task(
                    task=task,
                    arm_output=missing_output,
                    allowed_variable_codes=allowed_variable_codes or set(),
                )
                for score in task_scores:
                    all_scores[arm.value][score.metric.value].append(score)

    # Build arm outputs dict
    arm_outputs_dict: dict[str, ArmOutput] = {}
    for output in arm_outputs:
        key = f"{output.task_id}:{output.arm.value}"
        arm_outputs_dict[key] = output

    # Compute summary with per-arm structure
    summary = compute_summary_scores(all_scores)

    return EvaluationRun(
        prompt_hash=prompt_hash,
        registry_hash=registry_hash,
        task_set_hash=task_set_hash,
        package_version=package_version,
        model_label=model_label,
        timestamp_utc=timestamp_utc,
        tasks=tasks,
        arm_outputs=arm_outputs_dict,
        scores=all_scores,
        summary=summary,
    )