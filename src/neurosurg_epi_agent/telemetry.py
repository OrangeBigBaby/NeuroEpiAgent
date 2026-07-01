"""Publication-auditable telemetry and efficiency summarization.

This module captures Claude Code JSON-envelope usage / cost / timing fields
*without secrets*, computes an optional price-based estimated cost from
explicit per-million-token rates, and builds a deterministic efficiency
summary for Arm A / Arm B / overall suitable for a same-run A/B experiment.

Security contract
------------------
Only scalar envelope fields are retained. This module never persists API
keys, auth tokens, prompts, raw environment variables, stdout/stderr payloads,
or participant data. Missing envelope fields stay ``None``; they are NEVER
silently coerced to zero (that would fabricate measurements).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel

# Token categories we know how to price, in a stable order. A "category" is
# considered "observed" only when its token count is a positive integer.
TOKEN_CATEGORIES = ("input", "output", "cache_read", "cache_creation")


# A measured structural zero: no model call was attempted (dry run or a
# deterministic Arm A refusal), so token and cost fields are explicitly 0
# rather than None. This is distinct from a call that was attempted but whose
# telemetry could not be captured (those stay None and count as missing).
ZERO_CALL_TELEMETRY = dict(
    model_call_attempted=False,
    input_tokens=0,
    output_tokens=0,
    cache_read_input_tokens=0,
    cache_creation_input_tokens=0,
    claude_cli_reported_cost_usd=0.0,
    estimated_cost_usd=0.0,
)


class CallTelemetry(BaseModel):
    """Telemetry for a single planner model call.

    All envelope-derived fields default to ``None`` when absent in the CLI
    output and are never coerced to zero. ``model_call_attempted`` records
    whether the Claude Code subprocess was actually invoked for this output,
    which is distinct from whether usage/cost was successfully captured (a
    call can be attempted yet yield no envelope, e.g. a subprocess error).
    """

    # Whether the Claude Code subprocess was invoked for this output.
    model_call_attempted: bool = False

    # Token usage from the JSON envelope ``usage`` object (None when absent).
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None

    # Cost as REPORTED by the Claude CLI. Honestly named: this is the CLI's own
    # accounting for the session, NOT a vendor invoice and NOT evidence of
    # cost-effectiveness. It is None when the CLI does not report a cost.
    claude_cli_reported_cost_usd: float | None = None

    # Timing / turn metadata reported by the CLI envelope (None when absent).
    duration_ms: int | None = None
    duration_api_ms: int | None = None
    num_turns: int | None = None
    session_id: str | None = None

    # Optional estimated cost derived from explicit per-million-token prices.
    # None unless every rate required by the observed nonzero token categories
    # is supplied (see :func:`estimate_cost`). Not a vendor price.
    estimated_cost_usd: float | None = None


def _get_int(d: dict[str, Any], key: str) -> int | None:
    v = d.get(key)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _get_float(d: dict[str, Any], key: str) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_envelope_telemetry(envelope: Any) -> CallTelemetry:
    """Parse scalar usage/cost/timing fields from a Claude Code JSON envelope.

    Missing fields remain ``None``. Only scalar envelope fields are read; no
    stdout, prompts, auth material, or other secrets are retained. A non-dict
    envelope (e.g. a parse failure upstream) still records that a call was
    attempted but yields no usage fields.
    """
    if not isinstance(envelope, dict):
        return CallTelemetry(model_call_attempted=True)

    usage = envelope.get("usage")
    usage_dict: dict[str, Any] = usage if isinstance(usage, dict) else {}

    session_id = envelope.get("session_id")
    if not isinstance(session_id, str):
        session_id = None

    return CallTelemetry(
        model_call_attempted=True,
        input_tokens=_get_int(usage_dict, "input_tokens"),
        output_tokens=_get_int(usage_dict, "output_tokens"),
        cache_read_input_tokens=_get_int(usage_dict, "cache_read_input_tokens"),
        cache_creation_input_tokens=_get_int(usage_dict, "cache_creation_input_tokens"),
        claude_cli_reported_cost_usd=_get_float(envelope, "total_cost_usd"),
        duration_ms=_get_int(envelope, "duration_ms"),
        duration_api_ms=_get_int(envelope, "duration_api_ms"),
        num_turns=_get_int(envelope, "num_turns"),
        session_id=session_id,
    )


def _tokens_by_category(telemetry: Any) -> dict[str, int | None]:
    """Return a {category: token_count_or_None} view from a telemetry model/dict."""
    if isinstance(telemetry, CallTelemetry):
        return {
            "input": telemetry.input_tokens,
            "output": telemetry.output_tokens,
            "cache_read": telemetry.cache_read_input_tokens,
            "cache_creation": telemetry.cache_creation_input_tokens,
        }
    if isinstance(telemetry, dict):
        return {
            "input": telemetry.get("input_tokens"),
            "output": telemetry.get("output_tokens"),
            "cache_read": telemetry.get("cache_read_input_tokens"),
            "cache_creation": telemetry.get("cache_creation_input_tokens"),
        }
    return {c: None for c in TOKEN_CATEGORIES}


def estimate_cost(
    telemetry: Any,
    prices: dict[str, float | None] | None,
) -> float | None:
    """Estimate USD cost from explicit per-million-token prices.

    Returns ``None`` unless every rate required by the observed nonzero token
    categories is supplied. A category is "observed" only when its token count
    is a positive integer; zero or missing token categories do not require a
    rate. If no nonzero token category is observed, returns ``None`` (there is
    nothing to price and we will not fabricate a zero). Vendor prices are never
    hard-coded: callers must supply every rate explicitly.
    """
    if telemetry is None:
        return None
    rates = prices or {}
    tokens = _tokens_by_category(telemetry)

    total = 0.0
    observed_any = False
    for cat in TOKEN_CATEGORIES:
        count = tokens.get(cat)
        if count is None or count == 0:
            continue
        observed_any = True
        rate = rates.get(cat)
        if rate is None:
            return None
        try:
            rate_f = float(rate)
        except (TypeError, ValueError):
            return None
        total += count * rate_f / 1_000_000.0

    if not observed_any:
        return None
    return round(total, 8)


def validate_prices(prices: dict[str, float | None] | None) -> dict[str, float | None] | None:
    """Validate explicit per-million-token prices.

    Each supplied rate must be a finite, non-negative number. Zero is permitted
    (a genuinely-free category). ``None`` entries mean "rate not supplied" and
    are allowed. Raises ``ValueError`` on the first invalid rate. Vendor prices
    are never hard-coded; this only checks rates the caller supplied.
    """
    if not prices:
        return prices
    for cat in TOKEN_CATEGORIES:
        rate = prices.get(cat)
        if rate is None:
            continue
        try:
            rate_f = float(rate)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Price for '{cat}' is not numeric: {rate!r}") from exc
        if not math.isfinite(rate_f):
            raise ValueError(f"Price for '{cat}' must be finite, got {rate!r}")
        if rate_f < 0:
            raise ValueError(f"Price for '{cat}' must be >= 0, got {rate!r}")
    return prices


def _nonnull(values: list[Any]) -> list[Any]:
    return [v for v in values if v is not None]


def _sum_or_none(values: list[Any]) -> float | int | None:
    present = _nonnull(values)
    if not present:
        return None
    return sum(present)


def _token_field_summary(values: list[Any]) -> dict[str, Any]:
    """Summarize one token field across outputs without masking missing data.

    ``sum`` is None when no output reports the field (we do NOT treat missing
    as zero). ``available`` / ``missing`` make the coverage explicit.
    """
    present = _nonnull(values)
    return {
        "sum": sum(present) if present else None,
        "available": len(present),
        "missing": len(values) - len(present),
    }


def _cost_field_summary(values: list[Any], measured_n: int) -> dict[str, Any]:
    """Summarize one cost field, distinguishing a complete total from a partial sum.

    Coverage is over the ``measured_n`` non-reused outputs eligible for this-run
    measurement. Missing values are never summed as zero. The fields are:

    - ``total``: the sum when every measured output reported a cost (``complete``
      is True), else ``None``. A genuinely-zero complete total — e.g. all outputs
      are deterministic zero-call results reporting an explicit measured 0 — is
      returned as ``0.0`` and is NOT treated as missing.
    - ``partial_sum_usd``: the sum of the available (non-None) observations;
      ``None`` when no measured output reported the field. Shown to humans only
      with the word "partial" so it is never mistaken for a complete total.
    - ``complete``: True iff no measured output is missing the field and at
      least one output was measured.
    - ``available`` / ``missing``: counts over the measured outputs.
    """
    present = _nonnull(values)
    available = len(present)
    missing = measured_n - available
    partial_sum = sum(present) if present else None
    complete = missing == 0 and measured_n > 0
    return {
        "total": partial_sum if complete else None,
        "partial_sum_usd": partial_sum,
        "complete": complete,
        "available": available,
        "missing": missing,
    }


def build_arm_efficiency(
    outputs: list[dict[str, Any]],
    prices: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    """Build an efficiency summary for one arm from arm-output dicts.

    Reused outputs (``reused == True``) are excluded from every this-run
    measurement — model calls, elapsed time, token totals, CLI-reported cost,
    and estimated cost — so a cross-run reused Arm B result is never counted
    twice. Their count is still reported via ``reused_outputs`` and they remain
    in ``total_task_arm_outputs``. Availability/missing counts are relative to
    the this-run (non-reused) outputs only, so a reused output is neither
    "available" nor "missing" — it was simply not measured again this run.
    Missing token/cost values are never summed as zero.
    """
    n = len(outputs)
    model_calls = 0
    reused_count = 0
    measured_n = 0  # non-reused outputs eligible for this-run measurement
    elapsed_values: list[float] = []
    token_values: dict[str, list[Any]] = {c: [] for c in TOKEN_CATEGORIES}
    cli_cost_values: list[Any] = []
    est_cost_values: list[Any] = []

    cat_map = {
        "input": "input_tokens",
        "output": "output_tokens",
        "cache_read": "cache_read_input_tokens",
        "cache_creation": "cache_creation_input_tokens",
    }

    for o in outputs:
        if bool(o.get("reused")):
            # Contributes nothing to this-run totals; only counted as reused.
            reused_count += 1
            continue

        measured_n += 1

        tel = o.get("call_telemetry")
        if isinstance(tel, dict) and tel.get("model_call_attempted"):
            model_calls += 1

        et = o.get("execution_time_seconds")
        if et is not None:
            try:
                elapsed_values.append(float(et))
            except (TypeError, ValueError):
                pass

        if isinstance(tel, dict):
            for cat, field in cat_map.items():
                token_values[cat].append(tel.get(field))
            cli_cost_values.append(tel.get("claude_cli_reported_cost_usd"))

            est = tel.get("estimated_cost_usd")
            if est is None and prices is not None:
                est = estimate_cost(tel, prices)
            est_cost_values.append(est)
        else:
            for cat in TOKEN_CATEGORIES:
                token_values[cat].append(None)
            cli_cost_values.append(None)
            est_cost_values.append(None)

    elapsed_total = sum(elapsed_values) if elapsed_values else None
    mean_elapsed = (sum(elapsed_values) / len(elapsed_values)) if elapsed_values else None
    cli_cost_summary = _cost_field_summary(cli_cost_values, measured_n)
    est_cost_summary = _cost_field_summary(est_cost_values, measured_n)

    return {
        "total_task_arm_outputs": n,
        "model_calls_this_run": model_calls,
        "reused_outputs": reused_count,
        "calls_per_task": round(model_calls / n, 6) if n else None,
        "elapsed_seconds_total": elapsed_total,
        "elapsed_seconds_mean_per_task": mean_elapsed,
        "elapsed_available": len(elapsed_values),
        "elapsed_missing": measured_n - len(elapsed_values),
        "tokens": {
            "input_tokens": _token_field_summary(token_values["input"]),
            "output_tokens": _token_field_summary(token_values["output"]),
            "cache_read_input_tokens": _token_field_summary(token_values["cache_read"]),
            "cache_creation_input_tokens": _token_field_summary(token_values["cache_creation"]),
        },
        "claude_cli_reported_cost_usd_total": cli_cost_summary["total"],
        "claude_cli_reported_cost_usd_partial_sum_usd": cli_cost_summary["partial_sum_usd"],
        "claude_cli_reported_cost_usd_complete": cli_cost_summary["complete"],
        "claude_cli_reported_cost_available": cli_cost_summary["available"],
        "claude_cli_reported_cost_missing": cli_cost_summary["missing"],
        "estimated_cost_usd_total": est_cost_summary["total"],
        "estimated_cost_usd_partial_sum_usd": est_cost_summary["partial_sum_usd"],
        "estimated_cost_usd_complete": est_cost_summary["complete"],
        "estimated_cost_available": est_cost_summary["available"],
        "estimated_cost_missing": est_cost_summary["missing"],
    }


def _combine_token_summary(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Combine two per-arm token summaries into an overall summary.

    Sums are added only when at least one arm observed the field (None arms
    contribute nothing); availability/missing counts always add so partial
    coverage is visible rather than hidden behind a single total.
    """
    total = _sum_or_none([a.get("sum"), b.get("sum")])
    return {
        "sum": total,
        "available": a.get("available", 0) + b.get("available", 0),
        "missing": a.get("missing", 0) + b.get("missing", 0),
    }


def _combine_cost_summary(
    a_partial: float | None,
    a_available: int,
    a_missing: int,
    b_partial: float | None,
    b_available: int,
    b_missing: int,
) -> dict[str, Any]:
    """Combine two per-arm cost summaries into an overall cost summary.

    Completeness is over the union of measured outputs: the overall total is
    complete only when NO measured output is missing the field. The partial
    observed sum adds the available observations from each arm (an arm whose
    partial sum is None contributes nothing); it is None only when neither arm
    observed the field. A genuinely-zero complete total is preserved as 0.0.
    """
    available = a_available + b_available
    missing = a_missing + b_missing
    measured_n = available + missing
    partial_sum = _sum_or_none([a_partial, b_partial])
    complete = missing == 0 and measured_n > 0
    return {
        "total": partial_sum if complete else None,
        "partial_sum_usd": partial_sum,
        "complete": complete,
        "available": available,
        "missing": missing,
    }


def build_efficiency_summary(
    outputs: list[dict[str, Any]],
    total_tasks: int,
    prices: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    """Build per-arm and overall efficiency summaries.

    ``total_tasks`` is the number of distinct tasks (not 2x arm-outputs) and is
    used only for the overall ``calls_per_task`` denominator.

    The overall block carries the same coverage fields as each arm (elapsed
    mean/task, token totals with availability/missing for all four categories,
    and availability/missing for both cost kinds) so that an overall total built
    from one available arm and one missing arm is never mistaken for complete.

    For both cost kinds, ``*_total`` is ``None`` whenever any non-reused output
    is missing that field (an incomplete total is never shown as ``$0``). The
    observed ``*_partial_sum_usd``, ``*_complete`` flag, and availability/missing
    counts make the gap explicit. A genuinely-zero complete total — every
    measured output reports the field, including structural zeros — is preserved
    as ``0.0`` and is not treated as missing.
    """
    arm_a = [o for o in outputs if o.get("arm") == "arm_a"]
    arm_b = [o for o in outputs if o.get("arm") == "arm_b"]

    summary_a = build_arm_efficiency(arm_a, prices)
    summary_b = build_arm_efficiency(arm_b, prices)

    overall_calls = summary_a["model_calls_this_run"] + summary_b["model_calls_this_run"]
    overall_reused = summary_a["reused_outputs"] + summary_b["reused_outputs"]

    overall_elapsed_total = _sum_or_none(
        [summary_a["elapsed_seconds_total"], summary_b["elapsed_seconds_total"]]
    )
    overall_elapsed_available = (
        summary_a["elapsed_available"] + summary_b["elapsed_available"]
    )
    overall_elapsed_missing = (
        summary_a["elapsed_missing"] + summary_b["elapsed_missing"]
    )
    # Mean over the available elapsed measurements (consistent with per-arm).
    overall_mean_elapsed = (
        overall_elapsed_total / overall_elapsed_available
        if (overall_elapsed_total is not None and overall_elapsed_available > 0)
        else None
    )

    overall_cli = _combine_cost_summary(
        summary_a["claude_cli_reported_cost_usd_partial_sum_usd"],
        summary_a["claude_cli_reported_cost_available"],
        summary_a["claude_cli_reported_cost_missing"],
        summary_b["claude_cli_reported_cost_usd_partial_sum_usd"],
        summary_b["claude_cli_reported_cost_available"],
        summary_b["claude_cli_reported_cost_missing"],
    )
    overall_est = _combine_cost_summary(
        summary_a["estimated_cost_usd_partial_sum_usd"],
        summary_a["estimated_cost_available"],
        summary_a["estimated_cost_missing"],
        summary_b["estimated_cost_usd_partial_sum_usd"],
        summary_b["estimated_cost_available"],
        summary_b["estimated_cost_missing"],
    )
    overall = {
        "total_tasks": total_tasks,
        "total_task_arm_outputs": len(arm_a) + len(arm_b),
        "model_calls_this_run": overall_calls,
        "reused_outputs": overall_reused,
        "calls_per_task": round(overall_calls / total_tasks, 6) if total_tasks else None,
        "elapsed_seconds_total": overall_elapsed_total,
        "elapsed_seconds_mean_per_task": overall_mean_elapsed,
        "elapsed_available": overall_elapsed_available,
        "elapsed_missing": overall_elapsed_missing,
        "tokens": {
            "input_tokens": _combine_token_summary(
                summary_a["tokens"]["input_tokens"], summary_b["tokens"]["input_tokens"]
            ),
            "output_tokens": _combine_token_summary(
                summary_a["tokens"]["output_tokens"], summary_b["tokens"]["output_tokens"]
            ),
            "cache_read_input_tokens": _combine_token_summary(
                summary_a["tokens"]["cache_read_input_tokens"],
                summary_b["tokens"]["cache_read_input_tokens"],
            ),
            "cache_creation_input_tokens": _combine_token_summary(
                summary_a["tokens"]["cache_creation_input_tokens"],
                summary_b["tokens"]["cache_creation_input_tokens"],
            ),
        },
        "claude_cli_reported_cost_usd_total": overall_cli["total"],
        "claude_cli_reported_cost_usd_partial_sum_usd": overall_cli["partial_sum_usd"],
        "claude_cli_reported_cost_usd_complete": overall_cli["complete"],
        "claude_cli_reported_cost_available": overall_cli["available"],
        "claude_cli_reported_cost_missing": overall_cli["missing"],
        "estimated_cost_usd_total": overall_est["total"],
        "estimated_cost_usd_partial_sum_usd": overall_est["partial_sum_usd"],
        "estimated_cost_usd_complete": overall_est["complete"],
        "estimated_cost_available": overall_est["available"],
        "estimated_cost_missing": overall_est["missing"],
    }

    return {
        "arm_a": summary_a,
        "arm_b": summary_b,
        "overall": overall,
    }


# --------------------------------------------------------------------------- #
# Offline summarizer: experiment JSON -> Markdown + JSON
# --------------------------------------------------------------------------- #

_CAVEATS = [
    "Tasks are authored development items (benchmarks/tasks.example.yaml), not "
    "expert-validated gold standard; results are not suitable for publication "
    "or comparative-effectiveness claims.",
    "Arms were executed sequentially within a single run (Arm A then Arm B per "
    "task). This is NOT parallel execution and the two arms are NOT "
    "statistically independent samples.",
    "'claude_cli_reported_cost_usd' is the cost reported by the Claude CLI for "
    "the session. It is NOT a vendor invoice and NOT evidence of "
    "cost-effectiveness.",
    "'estimated_cost_usd' is computed only from caller-supplied "
    "per-million-token prices and is None unless every rate required by the "
    "observed nonzero token categories was supplied. Vendor prices are never "
    "hard-coded by the tool.",
    "Missing token/cost fields are never summed as zero; availability and "
    "missing counts are reported alongside every total.",
    "When any non-reused output is missing a cost field, the corresponding "
    "cost '*_total' is None (an incomplete total is never displayed as $0); "
    "the observed '*_partial_sum_usd', the '*_complete' flag, and the "
    "availability/missing counts make the gap explicit. A genuinely-zero "
    "complete total (all measured outputs report the field, including "
    "structural zeros) is reported as 0.",
]


def _fmt_cost(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        return f"${float(v):.6f}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_num(v: Any) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def _fmt_cost_block(summary: dict[str, Any], base: str) -> str:
    """Render one cost block for humans, never showing an incomplete total as $0.

    ``base`` is the shared field stem (``claude_cli_reported_cost`` or
    ``estimated_cost``). The total / partial / complete keys carry an ``_usd``
    segment (e.g. ``estimated_cost_usd_total``) while the coverage keys do not
    (e.g. ``estimated_cost_available``); both are read off the same summary.

    - Complete (including a genuine all-zero total): the total with coverage.
    - Incomplete with observations: ``N/A (incomplete; partial $X ...)`` — the
      word "partial" always accompanies the partial observed sum.
    - Incomplete with no observations: ``N/A (incomplete; N missing)``.
    """
    s = summary if isinstance(summary, dict) else {}
    total = s.get(f"{base}_usd_total")
    partial = s.get(f"{base}_usd_partial_sum_usd")
    available = s.get(f"{base}_available", 0)
    missing = s.get(f"{base}_missing", 0)
    if total is not None:
        return f"{_fmt_cost(total)} (complete; {available} reported)"
    if partial is not None:
        return (
            f"N/A (incomplete; partial {_fmt_cost(partial)} "
            f"over {available} reported, {missing} missing)"
        )
    return f"N/A (incomplete; {missing} missing)"


def render_efficiency_markdown(
    exp_data: dict[str, Any],
    summary: dict[str, Any],
    prices: dict[str, float | None] | None = None,
    backend_label: str | None = None,
) -> str:
    """Render a publication-oriented Markdown efficiency table with caveats."""
    metadata = exp_data.get("metadata", {}) if isinstance(exp_data.get("metadata"), dict) else {}
    # Always render the freshly-computed summary (which incorporates any prices
    # supplied to this call) so the Markdown and JSON outputs agree.
    meta_summary = summary

    lines: list[str] = []
    lines.append("# NeuroSurgEpiAgent Efficiency Summary")
    lines.append("")
    lines.append("> Publication-oriented efficiency telemetry. See caveats below.")
    lines.append("")

    model = metadata.get("model", "N/A")
    exec_design = metadata.get("execution_design", {}) if isinstance(metadata.get("execution_design"), dict) else {}
    reuse = metadata.get("arm_b_reuse", {}) if isinstance(metadata.get("arm_b_reuse"), dict) else {}

    lines.append(f"- **Model alias:** `{model}`")
    if backend_label:
        lines.append(f"- **Backend provenance (declared):** `{backend_label}`")
    lines.append(f"- **Execution mode:** {exec_design.get('mode', 'sequential')}")
    lines.append(f"- **Parallel:** {exec_design.get('parallel', False)}")
    lines.append(f"- **Statistically independent:** {exec_design.get('statistically_independent', False)}")
    lines.append(f"- **Arm B reuse configured:** {reuse.get('configured', False)}")
    lines.append("")

    lines.append("## Per-arm efficiency")
    lines.append("")
    lines.append(
        "| Arm | Task outputs | Model calls (this run) | Calls/task | "
        "Elapsed total (s) | Mean elapsed/task (s) | Input tokens | "
        "Output tokens | CLI-reported cost | Estimated cost |"
    )
    lines.append(
        "|-----|--------------|------------------------|------------|"
        "-------------------|-----------------------|--------------|"
        "---------------|-------------------|----------------|"
    )

    for arm in ("arm_a", "arm_b"):
        s = meta_summary.get(arm, {})
        tok_in = s.get("tokens", {}).get("input_tokens", {})
        tok_out = s.get("tokens", {}).get("output_tokens", {})
        lines.append(
            f"| {arm} | {s.get('total_task_arm_outputs', 0)} | "
            f"{s.get('model_calls_this_run', 0)} | "
            f"{_fmt_num(s.get('calls_per_task'))} | "
            f"{_fmt_num(s.get('elapsed_seconds_total'))} | "
            f"{_fmt_num(s.get('elapsed_seconds_mean_per_task'))} | "
            f"{_fmt_num(tok_in.get('sum'))} ({tok_in.get('available', 0)}/{s.get('total_task_arm_outputs', 0)} avail) | "
            f"{_fmt_num(tok_out.get('sum'))} ({tok_out.get('available', 0)}/{s.get('total_task_arm_outputs', 0)} avail) | "
            f"{_fmt_cost_block(s, 'claude_cli_reported_cost')} | "
            f"{_fmt_cost_block(s, 'estimated_cost')} |"
        )

    overall = meta_summary.get("overall", {})
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append(f"- **Total tasks:** {overall.get('total_tasks', 'N/A')}")
    lines.append(f"- **Total task-arm outputs:** {overall.get('total_task_arm_outputs', 'N/A')}")
    lines.append(f"- **Model calls this run:** {overall.get('model_calls_this_run', 'N/A')}")
    lines.append(f"- **Reused outputs:** {overall.get('reused_outputs', 'N/A')}")
    lines.append(f"- **Calls/task (overall):** {_fmt_num(overall.get('calls_per_task'))}")
    lines.append(f"- **Elapsed total (s):** {_fmt_num(overall.get('elapsed_seconds_total'))}")
    lines.append(
        f"- **Mean elapsed/task (s):** {_fmt_num(overall.get('elapsed_seconds_mean_per_task'))} "
        f"(available {overall.get('elapsed_available', 0)}/{overall.get('elapsed_missing', 0)} missing)"
    )
    otok = overall.get("tokens", {}) if isinstance(overall.get("tokens"), dict) else {}
    for field, label in (
        ("input_tokens", "Input"),
        ("output_tokens", "Output"),
        ("cache_read_input_tokens", "Cache-read"),
        ("cache_creation_input_tokens", "Cache-creation"),
    ):
        t = otok.get(field, {}) if isinstance(otok.get(field), dict) else {}
        lines.append(
            f"- **{label} tokens (overall):** {_fmt_num(t.get('sum'))} "
            f"(available {t.get('available', 0)}/{t.get('missing', 0)} missing)"
        )
    lines.append(
        f"- **CLI-reported cost (overall):** {_fmt_cost_block(overall, 'claude_cli_reported_cost')}"
    )
    lines.append(
        f"- **Estimated cost (overall):** {_fmt_cost_block(overall, 'estimated_cost')}"
    )
    lines.append(
        "_Totals omit reused outputs and never sum missing values as zero; an "
        "incomplete cost total is shown as N/A with its partial observed sum and "
        "coverage, never as $0._"
    )

    if prices:
        lines.append("")
        lines.append("## Pricing used for estimated cost (caller-supplied, USD per 1M tokens)")
        lines.append("")
        for cat in TOKEN_CATEGORIES:
            lines.append(f"- {cat}: {prices.get(cat)}")
        lines.append("")
        lines.append(
            "_Estimated cost is None for any call whose observed nonzero token "
            "categories lacked a supplied rate._"
        )

    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    for i, c in enumerate(_CAVEATS, 1):
        lines.append(f"{i}. {c}")

    return "\n".join(lines) + "\n"


def summarize_experiment_file(
    input_path: str | Path,
    markdown_path: str | Path,
    json_path: str | Path,
    prices: dict[str, float | None] | None = None,
    backend_label: str | None = None,
) -> tuple[Path, Path]:
    """Read an experiment output JSON and write Markdown + JSON summaries.

    Returns the (markdown_path, json_path) actually written.
    """
    in_path = Path(input_path)
    md_path = Path(markdown_path)
    json_out = Path(json_path)

    # Validate any caller-supplied prices before use (negative / non-finite
    # rejected; zero permitted). Vendor prices are never hard-coded here.
    prices = validate_prices(prices)

    with in_path.open("r", encoding="utf-8") as f:
        exp_data = json.load(f)

    if not isinstance(exp_data, dict):
        raise ValueError(f"Expected a JSON object at top level of {in_path}")

    arm_outputs = exp_data.get("arm_outputs", [])
    if not isinstance(arm_outputs, list):
        arm_outputs = []

    metadata = exp_data.get("metadata", {}) if isinstance(exp_data.get("metadata"), dict) else {}
    total_tasks = metadata.get("total_tasks")
    if not isinstance(total_tasks, int):
        # Fallback: distinct task ids across outputs
        total_tasks = len({o.get("task_id") for o in arm_outputs if isinstance(o, dict)})

    summary = build_efficiency_summary(arm_outputs, total_tasks, prices=prices)

    # Replace any stale derived ``efficiency_summary`` carried in the source
    # metadata with the freshly recomputed summary, so the emitted JSON never
    # holds two contradictory summaries (a corrected top-level one and a stale
    # nested one). Copy first to avoid mutating the in-memory source dict.
    metadata = dict(metadata)
    metadata["efficiency_summary"] = summary

    markdown = render_efficiency_markdown(
        exp_data, summary, prices=prices, backend_label=backend_label
    )

    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_out.parent.mkdir(parents=True, exist_ok=True)

    with md_path.open("w", encoding="utf-8") as f:
        f.write(markdown)

    payload = {
        "source_experiment": str(in_path),
        "backend_label": backend_label,
        "pricing_usd_per_million_tokens": prices,
        "efficiency_summary": summary,
        "metadata": metadata,
        "caveats": _CAVEATS,
    }
    with json_out.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return md_path, json_out
