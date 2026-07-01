"""Reproducibility manifest builder + writer.

A manifest is a plain-text record of exactly which rules fired, which variable
mappings were used, and their provenance status, so a reviewer (human or LLM)
can reproduce or audit a plan. It deliberately records *findings*, not
*results* - there are no numbers to fabricate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from . import __version__
from .guardrails import evaluate_plan
from .registry import unverified
from .schemas import (
    AnalysisPlan,
    DatabaseConfig,
    GuardrailReport,
    Manifest,
    VariableMapping,
)


def _variable_record(v: VariableMapping) -> dict:
    return {
        "name": v.name,
        "source_variable": v.source_variable,
        "source_module": v.source_module,
        "status": v.status.value,
    }


def build_manifest(
    plan: AnalysisPlan,
    *,
    database: DatabaseConfig | None = None,
    variables: list[VariableMapping] | None = None,
    report: GuardrailReport | None = None,
    extra_notes: list[str] | None = None,
) -> Manifest:
    if report is None:
        report = evaluate_plan(plan, database=database, variables=variables)

    vs: list[VariableMapping] = []
    if plan.outcome is not None:
        vs.append(plan.outcome)
    vs.extend(plan.exposures)
    vs.extend(plan.covariates)

    notes: list[str] = []
    if variables is not None:
        bad = unverified(variables)
        if bad:
            notes.append(
                f"{len(bad)} registry variable(s) are not VERIFIED: "
                + ", ".join(v.name for v in bad)
            )
    notes.append(
        "This manifest records plan/rules/variable provenance only; it contains no "
        "statistical estimates or fabricated results."
    )
    if extra_notes:
        notes.extend(extra_notes)

    return Manifest(
        package_version=__version__,
        database=plan.database,
        cycles=list(plan.cycles),
        plan_title=plan.title,
        n_errors=len(report.errors),
        n_warnings=len(report.warnings),
        variables=[_variable_record(v) for v in vs],
        findings=[f.model_dump(mode="json") for f in report.findings],
        notes=notes,
    )


def _content_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def write_manifest(manifest: Manifest, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump(mode="json")
    payload["content_sha256_short"] = _content_hash(payload)
    with p.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False, allow_unicode=True)
    return p
