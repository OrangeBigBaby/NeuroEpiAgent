"""Command-line interface: route, validate-plan, manifest, plan, evaluate, run-pilot.

Usage:
    neurosurg-epi route --question "..."
    neurosurg-epi validate-plan --plan path/to/plan.yaml [--db config/databases.yaml]
    neurosurg-epi manifest --plan path/to/plan.yaml --out path/to/manifest.yaml
    neurosurg-epi plan --provider replay --task-id stroke_01 --fixtures benchmarks/fixtures
    neurosurg-epi plan --provider claude --question "..." [--prompt config/prompts/planner_v1.txt]
    neurosurg-epi evaluate --tasks benchmarks/tasks.example.yaml --outputs outputs.json ...
    neurosurg-epi run-pilot --tasks benchmarks/tasks.example.yaml --output results.json ...
    neurosurg-epi inspect-database --database CHARLS --data-root PATH --output out.json [--force]

The CLI loads registries from disk only; it makes no network calls and reads no
raw NHANES data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from .evaluation import (
    ArmOutput,
    BenchmarkTask,
    EvaluationRun,
    MetricType,
    ProviderArm,
    create_evaluation_run,
)
from .experiment import ExperimentRunner
from .guardrails import evaluate_plan
from .manifest import build_manifest, write_manifest
from .planner import ClaudeCodePlannerProvider, PlannerError, ReplayPlannerProvider
from .registry import load_database_registry, load_variable_registry
from .router import route
from .schemas import AnalysisPlan, Severity


def _load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise SystemExit(f"{p}: expected a YAML mapping at the top level")
    return data


def _plan_from_yaml(path: str | Path) -> AnalysisPlan:
    data = _load_yaml(path)
    payload = data.get("plan", data)
    return AnalysisPlan.model_validate(payload)


def _format_severity_report(report) -> str:
    lines = []
    for f in report.findings:
        lines.append(f"[{f.severity.value.upper()}] {f.code}: {f.message}")
        if f.remediation:
            lines.append(f"    -> {f.remediation}")
    lines.append(
        f"\nSummary: {len(report.errors)} error(s), {len(report.warnings)} warning(s); "
        f"plan {'PASSED' if report.passed else 'FAILED'}"
    )
    return "\n".join(lines)


def _prices_from_args(args: argparse.Namespace) -> dict[str, float | None] | None:
    """Build and validate an explicit-prices dict from CLI args.

    Returns None when no price was supplied. Raises ``ValueError`` on the first
    negative or non-finite rate (zero is permitted). Vendor prices are never
    hard-coded; this only packages the rates the caller passed.
    """
    from .telemetry import validate_prices

    if not any(
        v is not None
        for v in (
            args.price_input,
            args.price_output,
            args.price_cache_read,
            args.price_cache_creation,
        )
    ):
        return None
    prices = {
        "input": args.price_input,
        "output": args.price_output,
        "cache_read": args.price_cache_read,
        "cache_creation": args.price_cache_creation,
    }
    return validate_prices(prices)


def _format_overall_cost_line(label: str, overall: dict[str, Any], base: str) -> str:
    """Format an overall cost line so an incomplete total is never shown as $0.

    ``base`` is the shared field stem (``claude_cli_reported_cost`` or
    ``estimated_cost``); the total / partial / complete keys carry an ``_usd``
    segment while the coverage keys do not. Complete totals (including a genuine
    all-zero total) print as a dollar amount. Incomplete totals print as
    ``N/A (incomplete; partial $X over N reported, M missing)`` — the word
    "partial" always accompanies the partial observed sum — or
    ``N/A (no data; M missing)`` when nothing was observed.
    """
    total = overall.get(f"{base}_usd_total")
    partial = overall.get(f"{base}_usd_partial_sum_usd")
    available = overall.get(f"{base}_available", 0)
    missing = overall.get(f"{base}_missing", 0)
    if total is not None:
        return f"{label}: ${total:.6f} (complete; {available} reported)"
    if partial is not None:
        return (
            f"{label}: N/A (incomplete; partial ${partial:.6f} "
            f"over {available} reported, {missing} missing)"
        )
    return f"{label}: N/A (no data; {missing} missing)"


def cmd_route(args: argparse.Namespace) -> int:
    decision = route(args.question)
    print(f"database: {decision.database}")
    print(f"status:   {decision.status.value}")
    print(f"feasible: {decision.feasible}")
    print(f"rationale: {decision.rationale}")
    for c in decision.caveats:
        print(f"caveat:   {c}")
    return 0


def cmd_validate_plan(args: argparse.Namespace) -> int:
    plan = _plan_from_yaml(args.plan)
    database = None
    variables = None
    if args.db:
        database = load_database_registry(args.db)
    if args.variables:
        variables = load_variable_registry(args.variables)
    report = evaluate_plan(plan, database=database, variables=variables)
    print(_format_severity_report(report))
    return 0 if report.passed else 2


def cmd_manifest(args: argparse.Namespace) -> int:
    plan = _plan_from_yaml(args.plan)
    database = load_database_registry(args.db) if args.db else None
    variables = load_variable_registry(args.variables) if args.variables else None
    manifest = build_manifest(plan, database=database, variables=variables)
    out = write_manifest(manifest, args.out)
    print(f"wrote manifest -> {out}")
    print(f"errors={manifest.n_errors} warnings={manifest.n_warnings}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Generate a plan using the specified provider."""
    provider_name = args.provider

    if provider_name == "replay":
        if not args.task_id:
            print("ERROR: replay provider requires --task-id")
            return 2
        if not args.fixtures:
            print("ERROR: replay provider requires --fixtures")
            return 2

        provider = ReplayPlannerProvider(fixture_path=Path(args.fixtures))

        try:
            plan = provider.generate_plan(
                question=args.question or "",
                task_id=args.task_id,
            )
        except PlannerError as e:
            print(f"PLANNER ERROR: {e}")
            return 1

    elif provider_name == "claude":
        if not args.question:
            print("ERROR: claude provider requires --question")
            return 2

        prompt_path = Path(args.prompt or "config/prompts/planner_v1.txt")
        provider = ClaudeCodePlannerProvider(
            prompt_path=prompt_path,
            model=args.model or "claude-sonnet-4-6",
            timeout=args.timeout or 120,
        )

        registry_path = Path(args.registry) if args.registry else None

        try:
            plan = provider.generate_plan(
                question=args.question,
                registry_path=registry_path,
            )
        except PlannerError as e:
            print(f"PLANNER ERROR: {e}")
            return 1

    else:
        print(f"ERROR: unknown provider '{provider_name}'")
        return 2

    # Output the plan
    if args.output:
        out_path = Path(args.output)
        with out_path.open("w", encoding="utf-8") as f:
            yaml.dump({"plan": plan.model_dump()}, f, default_flow_style=False)
        print(f"wrote plan -> {out_path}")
    else:
        print(yaml.dump({"plan": plan.model_dump()}, default_flow_style=False))

    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate pre-generated planner outputs against benchmark tasks."""
    import importlib.metadata

    # Load benchmark tasks
    tasks_path = Path(args.tasks)
    try:
        with tasks_path.open("r", encoding="utf-8") as f:
            tasks_data = yaml.safe_load(f)

        tasks = [BenchmarkTask.model_validate(t) for t in tasks_data.get("tasks", [])]
    except Exception as e:
        print(f"ERROR: failed to load tasks from {tasks_path}: {e}")
        return 1

    # Load arm outputs
    outputs_path = Path(args.outputs)
    try:
        with outputs_path.open("r", encoding="utf-8") as f:
            outputs_data = json.load(f)

        arm_outputs = [ArmOutput.model_validate(o) for o in outputs_data.get("arm_outputs", [])]
    except Exception as e:
        print(f"ERROR: failed to load arm outputs from {outputs_path}: {e}")
        return 1

    # Load variable registry for allowed codes
    allowed_codes: set[str] = set()
    if args.variables:
        try:
            registry = load_variable_registry(args.variables)
            allowed_codes = {v.source_variable for v in registry}
        except Exception as e:
            print(f"WARNING: failed to load variable registry: {e}")

    # Get package version
    try:
        package_version = importlib.metadata.version("neurosurg-epi-agent")
    except Exception:
        package_version = "unknown"

    # Create evaluation run
    prompt_path = Path(args.prompt)
    registry_path = Path(args.registry) if args.registry else Path(args.variables or "config/variables/nhanes_demo.yaml")
    task_set_path = tasks_path

    try:
        eval_run = create_evaluation_run(
            tasks=tasks,
            arm_outputs=arm_outputs,
            prompt_path=prompt_path,
            registry_path=registry_path,
            task_set_path=task_set_path,
            package_version=package_version,
            model_label=args.model_label,
            allowed_variable_codes=allowed_codes,
        )
    except Exception as e:
        print(f"ERROR: evaluation run failed: {e}")
        return 1

    # Write JSON output
    json_path = Path(args.json_output)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(eval_run.model_dump(), f, indent=2)

    print(f"Wrote evaluation results -> {json_path}")

    # Write concise markdown summary with per-arm breakdown
    md_path = Path(args.markdown_output)
    with md_path.open("w", encoding="utf-8") as f:
        f.write(f"# NeuroSurgEpiAgent Evaluation Report\n\n")
        f.write(f"**Generated:** {eval_run.timestamp_utc} UTC  \n")
        f.write(f"**Package Version:** {eval_run.package_version}  \n")
        f.write(f"**Model Label:** {eval_run.model_label or 'N/A'}  \n\n")

        f.write("## Provenance Hashes\n\n")
        f.write(f"- **Prompt:** `{eval_run.prompt_hash[:16]}...`  \n")
        f.write(f"- **Registry:** `{eval_run.registry_hash[:16]}...`  \n")
        f.write(f"- **Task Set:** `{eval_run.task_set_hash[:16]}...`  \n\n")

        f.write("## Summary Statistics (Per-Arm)\n\n")

        # Per-arm summaries
        for arm_name, arm_summary in eval_run.summary.items():
            f.write(f"### {arm_name.upper()}\n\n")
            f.write("| Metric | Passed | Total | Proportion |\n")
            f.write("|--------|--------|-------|------------|\n")
            for metric_name, summary in arm_summary.items():
                f.write(
                    f"| {metric_name} | {summary['passed']} | {summary['total']} | {summary['proportion']:.2%} |\n"
                )
            f.write("\n")

        f.write("## Per-Task Details\n\n")
        f.write("| Task ID | Domain | Arm | Database Routing | Feasibility | Hard Error Free |\n")
        f.write("|---------|--------|------|-------------------|--------------|-----------------|\n")

        for task in eval_run.tasks:
            for arm in [ProviderArm.ARM_A, ProviderArm.ARM_B]:
                # Look up scores for this task and arm across all metrics
                arm_scores = eval_run.scores.get(arm.value, {})

                routing_score = None
                feasibility_score = None
                error_score = None

                # Find scores for this specific task
                for metric_type, score_list in arm_scores.items():
                    for score in score_list:
                        if score.task_id == task.id:
                            if metric_type == MetricType.DATABASE_ROUTING.value:
                                routing_score = score
                            elif metric_type == MetricType.FEASIBILITY.value:
                                feasibility_score = score
                            elif metric_type == MetricType.HARD_ERROR_FREE.value:
                                error_score = score

                routing = "PASS" if routing_score and routing_score.passed else "FAIL"
                feasibility = "PASS" if feasibility_score and feasibility_score.passed else "FAIL"
                error_free = "PASS" if error_score and error_score.passed else "FAIL"

                f.write(f"| {task.id} | {task.domain} | {arm.value} | {routing} | {feasibility} | {error_free} |\n")

        # Add coverage information
        f.write("\n## Experiment Coverage\n\n")
        total_expected = len(eval_run.tasks) * 2  # 2 arms per task
        outputs_present = len(eval_run.arm_outputs)
        coverage_pct = (outputs_present / total_expected * 100) if total_expected > 0 else 0

        f.write(f"- **Expected outputs:** {total_expected} ({len(eval_run.tasks)} tasks x 2 arms)  \n")
        f.write(f"- **Outputs present:** {outputs_present}  \n")
        f.write(f"- **Coverage:** {coverage_pct:.1f}%  \n")

        if outputs_present < total_expected:
            missing_tasks = set()
            for task in eval_run.tasks:
                for arm in [ProviderArm.ARM_A, ProviderArm.ARM_B]:
                    key = f"{task.id}:{arm.value}"
                    if key not in eval_run.arm_outputs:
                        missing_tasks.add(f"{task.id} ({arm.value})")
            f.write(f"⚠️ **Missing:** {sorted(missing_tasks)}  \n")

        f.write("\n> **Note:** This is a pilot evaluation with draft tasks. Results are not suitable for significance claims or publication.\n")

    print(f"Wrote markdown summary -> {md_path}")

    return 0


def cmd_run_pilot(args: argparse.Namespace) -> int:
    """Run live pilot experiment with checkpointing."""
    from .experiment import ExperimentRunner

    # Check for live run confirmation
    if not args.confirm_live and not args.dry_run:
        print("ERROR: Live runs require --confirm-live flag.")
        print("This will make real Claude API calls and incur costs.")
        print("Use --dry-run for zero-cost testing.")
        return 2

    # Setup paths
    tasks_path = Path(args.tasks)
    prompt_a_path = Path(args.prompt_a or "config/prompts/planner_v1.txt")
    prompt_b_path = Path(args.prompt_b or "config/prompts/baseline_v1.txt")
    registry_path = Path(args.registry)
    output_path = Path(args.output)
    checkpoint_path = Path(args.checkpoint) if args.checkpoint else None
    reuse_arm_b_from = Path(args.reuse_arm_b_from) if args.reuse_arm_b_from else None

    # Optional explicit per-million-token prices (USD). None for any rate the
    # caller did not supply; estimated cost stays None unless every required
    # rate is present. Negative / non-finite rates are rejected (zero allowed).
    # Vendor prices are never hard-coded here.
    try:
        prices = _prices_from_args(args)
    except ValueError as e:
        print(f"ERROR: invalid price: {e}")
        return 2

    # Create experiment runner
    try:
        runner = ExperimentRunner(
            tasks_path=tasks_path,
            prompt_a_path=prompt_a_path,
            prompt_b_path=prompt_b_path,
            registry_path=registry_path,
            model=args.model or "claude-sonnet-4-6",
            max_budget_usd_per_call=args.max_budget_usd_call,
            timeout=args.timeout or 120,
            max_tasks=args.max_tasks,
            checkpoint_file=checkpoint_path,
            reuse_arm_b_from=reuse_arm_b_from,
            prices=prices,
            backend_label=args.backend_label,
        )
    except Exception as e:
        print(f"ERROR: failed to initialize experiment runner: {e}")
        return 1

    # Run experiment
    try:
        print(f"Running pilot experiment...")
        print(f"Tasks: {len(runner.tasks)}")
        print(f"Model: {runner.model}")
        if args.backend_label:
            print(f"Backend label (declared): {args.backend_label}")
        print(f"Max budget per call: ${runner.max_budget_usd_per_call}")
        if prices:
            print(
                "Estimated-cost pricing (USD per 1M tokens): "
                f"input={prices['input']} output={prices['output']} "
                f"cache_read={prices['cache_read']} cache_creation={prices['cache_creation']}"
            )
        print(f"Dry run: {args.dry_run}")
        print(f"Checkpoint: {checkpoint_path}")

        outputs, metadata = runner.run_experiment(
            dry_run=args.dry_run,
            confirm_live=args.confirm_live,
        )

        # Write outputs
        output_data = {
            "metadata": metadata,
            "arm_outputs": [o.model_dump() for o in outputs],
        }

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)

        # Honestly-labeled efficiency summary (no GLM invoice / effectiveness claims)
        eff = metadata.get("efficiency_summary", {}) if isinstance(metadata.get("efficiency_summary"), dict) else {}
        overall = eff.get("overall", {}) if isinstance(eff.get("overall"), dict) else {}
        arm_a = eff.get("arm_a", {}) if isinstance(eff.get("arm_a"), dict) else {}
        arm_b = eff.get("arm_b", {}) if isinstance(eff.get("arm_b"), dict) else {}

        print(f"\nExperiment completed!")
        print(f"Total outputs: {len(outputs)}")
        print(f"Duration: {metadata.get('duration_seconds', 'N/A'):.1f}s")
        print(
            "Model calls this run (Arm A / Arm B / overall): "
            f"{arm_a.get('model_calls_this_run', 0)} / "
            f"{arm_b.get('model_calls_this_run', 0)} / "
            f"{overall.get('model_calls_this_run', 0)}"
        )
        print(_format_overall_cost_line(
            "Claude CLI reported cost (overall)", overall, "claude_cli_reported_cost"
        ))
        print(_format_overall_cost_line(
            "Estimated cost (overall)", overall, "estimated_cost"
        ))
        print(f"Output saved to: {output_path}")

        return 0

    except Exception as e:
        print(f"ERROR: experiment failed: {e}")
        return 1


def cmd_inspect_database(args: argparse.Namespace) -> int:
    """Metadata-only inspection of a local database directory.

    Writes a deterministic, UTF-8 JSON document describing archives/members
    (paths, sizes, SHA-256, row/column counts, variable names + labels). The
    output never contains participant values or the caller's real ``data_root``.
    Refuses to overwrite an existing output unless ``--force`` is given.
    """
    from .adapters import default_registry
    from .adapters.base import AdapterError
    from .adapters.charls import DEFAULT_MAX_MEMBER_BYTES
    from .adapters.seer import DEFAULT_MAX_MEMBER_BYTES as SEER_MAX_MEMBER_BYTES

    if args.database == "SEER":
        # SEER files are large; allow a separate cap.
        max_member_bytes = (
            args.max_member_bytes
            if args.max_member_bytes is not None
            else SEER_MAX_MEMBER_BYTES
        )
    else:
        max_member_bytes = (
            args.max_member_bytes
            if args.max_member_bytes is not None
            else DEFAULT_MAX_MEMBER_BYTES
        )
    if max_member_bytes <= 0:
        print("ERROR: --max-member-bytes must be a positive integer")
        return 2

    out_path = Path(args.output)
    if out_path.exists() and not args.force:
        print(
            f"ERROR: output already exists; refusing to overwrite without "
            f"--force: {out_path}"
        )
        return 2

    data_root = Path(args.data_root)
    if not data_root.exists():
        print(f"ERROR: --data-root does not exist: {data_root}")
        return 2

    registry = default_registry()
    try:
        adapter = registry.get(args.database)
    except AdapterError as exc:
        print(f"ERROR: {exc}")
        return 2

    inspect_kwargs: dict = {"max_member_bytes": max_member_bytes}
    if args.database == "SEER":
        inspect_kwargs["with_sha256"] = bool(getattr(args, "with_sha256", False))
        inspect_kwargs["sha256_max_bytes"] = (
            args.sha256_max_bytes
            if args.sha256_max_bytes is not None
            else SEER_MAX_MEMBER_BYTES
        )
        # Optional user-supplied data-version fields, all read from CLI kwargs.
        # Missing fields are recorded as ``needs_verification`` by the adapter.
        from .adapters.seer import _DATA_VERSION_FIELDS
        dv = {}
        for f in _DATA_VERSION_FIELDS:
            v = getattr(args, f"data_version_{f}", None)
            if v:
                dv[f] = v
        if dv:
            inspect_kwargs["data_version"] = dv

    try:
        result = adapter.inspect(data_root, **inspect_kwargs)
    except Exception as exc:  # adapter-layer failures (malformed/traversal/...)
        print(f"ERROR: inspection failed: {type(exc).__name__}: {exc}")
        return 1

    payload = result.to_dict()
    parent = out_path.parent
    if parent and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")

    print(f"wrote metadata -> {out_path}")
    print(
        f"database={payload['database']} "
        f"archives={len(payload['archives'])} "
        f"direct_files={len(payload['direct_files'])} "
        f"skipped={len(payload['skipped_roots'])}"
    )
    return 0


def cmd_efficiency_summary(args: argparse.Namespace) -> int:
    """Offline summarizer: read an experiment JSON, write Markdown + JSON."""
    from .telemetry import summarize_experiment_file

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: input experiment file not found: {input_path}")
        return 1

    prices = None
    try:
        prices = _prices_from_args(args)
    except ValueError as e:
        print(f"ERROR: invalid price: {e}")
        return 2

    try:
        md_path, json_path = summarize_experiment_file(
            input_path=input_path,
            markdown_path=Path(args.markdown_output),
            json_path=Path(args.json_output),
            prices=prices,
            backend_label=args.backend_label,
        )
    except Exception as e:
        print(f"ERROR: failed to summarize experiment: {e}")
        return 1

    print(f"Wrote efficiency markdown -> {md_path}")
    print(f"Wrote efficiency JSON    -> {json_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neurosurg-epi")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_route = sub.add_parser("route", help="Route a research question to a database.")
    p_route.add_argument("--question", required=True)
    p_route.set_defaults(func=cmd_route)

    p_val = sub.add_parser("validate-plan", help="Run deterministic guardrails on a plan.")
    p_val.add_argument("--plan", required=True)
    p_val.add_argument("--db", default=None)
    p_val.add_argument("--variables", default=None)
    p_val.set_defaults(func=cmd_validate_plan)

    p_man = sub.add_parser("manifest", help="Emit a reproducibility manifest.")
    p_man.add_argument("--plan", required=True)
    p_man.add_argument("--out", required=True)
    p_man.add_argument("--db", default=None)
    p_man.add_argument("--variables", default=None)
    p_man.set_defaults(func=cmd_manifest)

    p_plan = sub.add_parser("plan", help="Generate a plan using a planner provider.")
    p_plan.add_argument("--provider", required=True, choices=["replay", "claude"], help="Planner provider to use.")
    p_plan.add_argument("--question", default=None, help="Clinical question (required for claude provider)")
    p_plan.add_argument("--task-id", default=None, help="Task ID for replay provider")
    p_plan.add_argument("--fixtures", default=None, help="Fixture path for replay provider")
    p_plan.add_argument("--prompt", default=None, help="Prompt template path for claude provider")
    p_plan.add_argument("--model", default=None, help="Model for claude provider (default: claude-sonnet-4-6)")
    p_plan.add_argument("--timeout", type=int, default=None, help="Timeout for claude provider in seconds (default: 120)")
    p_plan.add_argument("--registry", default=None, help="Variable registry path for context")
    p_plan.add_argument("--output", "-o", default=None, help="Output YAML path (default: stdout)")
    p_plan.set_defaults(func=cmd_plan)

    p_eval = sub.add_parser("evaluate", help="Evaluate pre-generated planner outputs against benchmark tasks.")
    p_eval.add_argument("--tasks", required=True, help="Benchmark tasks YAML file")
    p_eval.add_argument("--outputs", required=True, help="Arm outputs JSON file")
    p_eval.add_argument("--prompt", required=True, help="Planner prompt template file for hash")
    p_eval.add_argument("--registry", required=True, help="Variable registry file for hash")
    p_eval.add_argument("--variables", default=None, help="Variable registry file for allowed codes")
    p_eval.add_argument("--model-label", default=None, help="User-supplied model identifier")
    p_eval.add_argument("--json-output", required=True, help="Output JSON file path")
    p_eval.add_argument("--markdown-output", required=True, help="Output markdown file path")
    p_eval.set_defaults(func=cmd_evaluate)

    p_pilot = sub.add_parser("run-pilot", help="Run live pilot experiment with checkpointing.")
    p_pilot.add_argument("--tasks", required=True, help="Benchmark tasks YAML file")
    p_pilot.add_argument("--prompt-a", default=None, help="Constrained prompt path (Arm A)")
    p_pilot.add_argument("--prompt-b", default=None, help="Baseline prompt path (Arm B)")
    p_pilot.add_argument("--registry", required=True, help="Variable registry file")
    p_pilot.add_argument("--model", default=None, help="Model identifier (default: claude-sonnet-4-6)")
    p_pilot.add_argument("--max-budget-usd-call", type=float, default=0.50, help="Max USD per model call")
    p_pilot.add_argument("--timeout", type=int, default=120, help="Timeout per call in seconds")
    p_pilot.add_argument("--max-tasks", type=int, default=None, help="Maximum tasks to run (default: all)")
    p_pilot.add_argument("--output", "-o", required=True, help="Output JSON file path")
    p_pilot.add_argument("--checkpoint", default=None, help="Checkpoint file path for resume")
    p_pilot.add_argument("--reuse-arm-b-from", default=None, help="Reuse Arm B outputs from previous run (JSON)")
    p_pilot.add_argument(
        "--backend-label",
        default=None,
        help=(
            "Descriptive provenance string recording the declared backend route "
            "(e.g. 'glm-5.2 via CC-Switch'). Descriptive only; not authentication data."
        ),
    )
    p_pilot.add_argument(
        "--price-input",
        type=float,
        default=None,
        help="Explicit USD price per 1M input tokens (for estimated cost)",
    )
    p_pilot.add_argument(
        "--price-output",
        type=float,
        default=None,
        help="Explicit USD price per 1M output tokens (for estimated cost)",
    )
    p_pilot.add_argument(
        "--price-cache-read",
        type=float,
        default=None,
        help="Explicit USD price per 1M cache-read input tokens (for estimated cost)",
    )
    p_pilot.add_argument(
        "--price-cache-creation",
        type=float,
        default=None,
        help="Explicit USD price per 1M cache-creation input tokens (for estimated cost)",
    )
    p_pilot.add_argument("--confirm-live", action="store_true", help="Required for live runs (incurs API costs)")
    p_pilot.add_argument("--dry-run", action="store_true", help="Zero-cost simulation (default behavior)")
    p_pilot.set_defaults(func=cmd_run_pilot)

    p_summ = sub.add_parser(
        "efficiency-summary",
        help="Summarize a run-pilot output JSON into a Markdown + JSON efficiency report.",
    )
    p_summ.add_argument("--input", required=True, help="Path to a run-pilot output JSON file")
    p_summ.add_argument("--markdown-output", required=True, help="Output Markdown report path")
    p_summ.add_argument("--json-output", required=True, help="Output machine-readable JSON summary path")
    p_summ.add_argument(
        "--backend-label",
        default=None,
        help="Optional declared backend provenance to record in the summary",
    )
    p_summ.add_argument("--price-input", type=float, default=None, help="USD per 1M input tokens")
    p_summ.add_argument("--price-output", type=float, default=None, help="USD per 1M output tokens")
    p_summ.add_argument("--price-cache-read", type=float, default=None, help="USD per 1M cache-read input tokens")
    p_summ.add_argument("--price-cache-creation", type=float, default=None, help="USD per 1M cache-creation input tokens")
    p_summ.set_defaults(func=cmd_efficiency_summary)

    p_inspect = sub.add_parser(
        "inspect-database",
        help="Emit metadata-only JSON for a local database directory (NHANES/CHARLS/CDC WONDER/SEER).",
    )
    p_inspect.add_argument(
        "--database",
        required=True,
        choices=["CDC_WONDER", "CHARLS", "NHANES", "SEER"],
        help="Which database adapter to use.",
    )
    p_inspect.add_argument(
        "--data-root",
        required=True,
        help="Directory (or single file) of authorized local data to inspect.",
    )
    p_inspect.add_argument(
        "--output",
        required=True,
        help="Output JSON path. Must not already exist unless --force is given.",
    )
    p_inspect.add_argument(
        "--max-member-bytes",
        type=int,
        default=None,
        help=(
            "Maximum bytes per inspected member (declared size before "
            "decompression and actual bytes after reading). Default: 2 GiB "
            "for NHANES/CHARLS/CDC WONDER; 8 GiB for SEER."
        ),
    )
    p_inspect.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting an existing --output file.",
    )
    # SEER-specific options. They are accepted but ignored for non-SEER adapters.
    p_inspect.add_argument(
        "--with-sha256",
        action="store_true",
        help="[SEER] Stream a SHA-256 over every file's bytes (off by default; files are large).",
    )
    p_inspect.add_argument(
        "--sha256-max-bytes",
        type=int,
        default=None,
        help="[SEER] Hard upper bound on bytes hashed per file (default 8 GiB).",
    )
    # SEER data-version fields (all optional; missing fields stay
    # needs_verification rather than being guessed).
    for f in (
        "release_submission", "product_type", "registry_set",
        "seerstat_version", "session_type", "export_date",
        "selection_statements", "export_data_dictionary",
    ):
        p_inspect.add_argument(
            f"--data-version-{f.replace('_', '-')}",
            default=None,
            help=f"[SEER] User-supplied {f} from the SEER*Stat session / DUA paperwork.",
        )
    p_inspect.set_defaults(func=cmd_inspect_database)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
