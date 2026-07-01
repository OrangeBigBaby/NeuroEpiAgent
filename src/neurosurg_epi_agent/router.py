"""Deterministic database router.

Routes a research question to a database purely from keywords + an explicit
capability table. NHANES-first for the MVP; other databases return PLANNED and
the router explains why they are not yet active. No LLM calls, no network.

Precedence order (deterministic):
  1. Explicit database name in question (NHANES, CHARLS, GBD, SEER)
  2. Explicit infeasible capability patterns (surgery, procedures, histology)
  3. Specialized intent patterns (regional burden, longitudinal trajectories)
  4. Supported NHANES domain match
  5. Conservative unknown refusal (never default to feasible)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import DatabaseStatus


@dataclass(frozen=True)
class RouteDecision:
    database: str
    status: DatabaseStatus
    feasible: bool
    rationale: str
    caveats: tuple[str, ...] = ()


# Static capability table. The MVP only marks NHANES feasible.
_CAPABILITY = {
    "NHANES": {
        "status": DatabaseStatus.SUPPORTED,
        "feasible": True,
        "domains": {"stroke", "tia", "cvd", "tbi", "head injury", "concussion",
                    "metabolic", "sarcopenia", "obesity", "mortality"},
        "limit": (
            "NHANES is a cross-sectional household survey (with linked mortality). "
            "It cannot identify elective neurosurgical caseload, tumor histology, or "
            "procedure volume. Stroke/TBI items are self-report; timing and severity "
            "are limited."
        ),
    },
    "CHARLS": {
        "status": DatabaseStatus.PLANNED,
        "feasible": False,
        "domains": {"stroke", "cvd", "cognitive"},
        "limit": "CHARLS adapter is planned post-MVP; routing is informational only.",
    },
    "GBD": {
        "status": DatabaseStatus.PLANNED,
        "feasible": False,
        "domains": {"tumor", "tbi", "stroke"},
        "limit": "GBD provides regional aggregate burden, not patient-level surgery data.",
    },
    "SEER": {
        "status": DatabaseStatus.PLANNED,
        "feasible": False,
        "domains": {"tumor", "cancer"},
        "limit": "SEER adapter is planned; registry access is out of MVP scope.",
    },
}


# Infeasible capability patterns - these indicate NHANES cannot answer
_INFEASIBLE_PATTERNS = {
    "surgery": r"(?:laparoscopic|bariatric|neurosurgical|surgical|craniotomy|resection)",
    "procedure": r"(?:procedure|operation|intervention)",
    "histology": r"(?:histology|histologic|tumor subtype|meningioma|glioblastoma)",
    "longitudinal": r"(?:follow-up|recurrence|5-year)",
}


def _extract_explicit_database(question: str) -> str | None:
    """Check if question explicitly names a database."""
    q_lower = question.lower()
    for db_name in ["NHANES", "CHARLS", "GBD", "SEER"]:
        if db_name.lower() in q_lower:
            return db_name
    return None


def _check_infeasible_patterns(question: str) -> tuple[bool, str]:
    """Check if question contains infeasible capability patterns.

    Returns:
        Tuple of (is_infeasible, matched_pattern_name)
    """
    q_lower = question.lower()
    for pattern_name, pattern_regex in _INFEASIBLE_PATTERNS.items():
        if re.search(pattern_regex, q_lower):
            return True, pattern_name
    return False, ""


def _score(question_lower: str, domains: set[str]) -> int:
    return sum(1 for d in domains if d in question_lower)


def route(question: str) -> RouteDecision:
    """Pick a database for a free-text research question.

    Rules (deterministic, in order):
      1. Explicit database name → route to that database with feasibility check
      2. Infeasible capability pattern → NHANES with feasible=False
      3. Specialized intent (regional/longitudinal) → corresponding planned DB
      4. Supported NHANES domain match → NHANES feasible=True
      5. No match → conservative refusal (NHANES with feasible=False)

    Args:
        question: Free-text research question

    Returns:
        RouteDecision with database, feasibility, rationale, and caveats
    """
    q = question.lower()

    # 1. Explicit non-NHANES databases are always informational in this MVP.
    explicit_db = _extract_explicit_database(question)
    if explicit_db and explicit_db != "NHANES":
        cfg = _CAPABILITY[explicit_db]
        return RouteDecision(
            database=explicit_db,
            status=cfg["status"],
            feasible=cfg["feasible"],
            rationale=f"Question explicitly mentions {explicit_db}.",
            caveats=(cfg["limit"],),
        )

    # 2. Specialized intents select the scientifically appropriate planned DB.
    if re.search(r"(?:global|regional|by region|aggregate burden|disability-adjusted|dalys?)", q):
        cfg = _CAPABILITY["GBD"]
        return RouteDecision(
            database="GBD", status=cfg["status"], feasible=False,
            rationale="GBD matches a regional/global aggregate-burden question but its adapter is PLANNED.",
            caveats=(cfg["limit"],),
        )

    if re.search(r"(?:post-concussion|concussion)", q) and re.search(
        r"(?:cognitive|trajectory|older adults?|longitudinal)", q
    ):
        cfg = _CAPABILITY["CHARLS"]
        return RouteDecision(
            database="CHARLS", status=cfg["status"], feasible=False,
            rationale="CHARLS matches an older-adult longitudinal cognitive question but its adapter is planned.",
            caveats=(cfg["limit"],),
        )

    if re.search(r"(?:registry data|glioblastoma|extent of resection|tumou?r survival)", q):
        cfg = _CAPABILITY["SEER"]
        return RouteDecision(
            database="SEER", status=cfg["status"], feasible=False,
            rationale="SEER matches a CNS-tumor registry/survival question but its adapter is planned.",
            caveats=(cfg["limit"],),
        )

    # NHANES lacks a stable, comparable lifetime TBI item across the pilot cycles.
    if re.search(r"(?:tbi|traumatic brain injury)", q) and "lifetime prevalence" in q:
        cfg = _CAPABILITY["NHANES"]
        return RouteDecision(
            database="NHANES", status=cfg["status"], feasible=False,
            rationale="The request did not match a known comparable cross-cycle NHANES TBI history item.",
            caveats=(cfg["limit"],),
        )

    # 3. Capability limits apply even when NHANES is named explicitly.
    is_infeasible, pattern_name = _check_infeasible_patterns(question)
    if is_infeasible:
        nhanes = _CAPABILITY["NHANES"]
        infeasible_reason = {
            "surgery": "NHANES has no procedure/surgery data",
            "procedure": "NHANES has no procedure/surgery data",
            "histology": "NHANES has no brain-tumor histology capture",
            "longitudinal": "NHANES is cross-sectional; it cannot support longitudinal analyses",
        }.get(pattern_name, f"NHANES cannot support: {pattern_name}")

        return RouteDecision(
            database="NHANES",
            status=nhanes["status"],
            feasible=False,
            rationale=infeasible_reason,
            caveats=(nhanes["limit"],),
        )

    # 4. An explicit NHANES request that passed capability checks is feasible.
    if explicit_db == "NHANES":
        nhanes = _CAPABILITY["NHANES"]
        return RouteDecision(
            database="NHANES", status=nhanes["status"], feasible=True,
            rationale="NHANES is explicitly requested and matches a known epidemiology domain.",
            caveats=(nhanes["limit"],),
        )

    # 5. Check for supported NHANES domain match
    nhanes = _CAPABILITY["NHANES"]
    if _score(q, nhanes["domains"]) > 0:
        return RouteDecision(
            database="NHANES",
            status=nhanes["status"],
            feasible=True,
            rationale="NHANES is the only SUPPORTED database in the MVP and matches a "
                      "known epidemiology domain in the question.",
            caveats=(nhanes["limit"],),
        )

    # 5. Check for planned database matches
    planned_hits = [
        (name, cfg) for name, cfg in _CAPABILITY.items()
        if cfg["status"] is DatabaseStatus.PLANNED and _score(q, cfg["domains"]) > 0
    ]
    if planned_hits:
        name, cfg = planned_hits[0]
        return RouteDecision(
            database=name,
            status=cfg["status"],
            feasible=False,
            rationale=f"{name} matches the question domain but is PLANNED, not supported.",
            caveats=(cfg["limit"],),
        )

    # 6. Conservative unknown refusal - do not default unknown to feasible
    return RouteDecision(
        database="NHANES",
        status=nhanes["status"],
        feasible=False,  # Conservative: unknown questions are infeasible
        rationale="Question did not match a known neuro-epi domain and cannot be "
                  "confirmed as feasible for NHANES analysis.",
        caveats=(
            "Question did not match a known domain; confirm NHANES actually "
            "captures the outcome before proceeding. " + nhanes["limit"],
        ),
    )
