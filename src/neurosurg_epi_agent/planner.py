"""Planner layer: typed providers and offline replay.

This module provides the protocol and implementations for planning providers:
- PlannerProvider: abstract protocol
- ReplayPlannerProvider: offline fixture-based provider for testing/evaluation
- ClaudeCodePlannerProvider: subprocess-based Claude Code integration

Providers convert clinical questions into validated AnalysisPlan objects.
"""

from __future__ import annotations

import json
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .schemas import AnalysisPlan
from .registry import load_variable_registry
from .telemetry import CallTelemetry, parse_envelope_telemetry


class PlannerProvider(ABC):
    """Protocol for planning providers.

    A provider takes a clinical question and optional registry context,
    then returns a validated AnalysisPlan or raises a structured error.
    """

    @abstractmethod
    def generate_plan(
        self,
        question: str,
        registry_path: Path | None = None,
        routing_context: dict[str, Any] | None = None,
    ) -> AnalysisPlan:
        """Generate an analysis plan from a clinical question.

        Args:
            question: Free-text clinical question
            registry_path: Optional path to variable registry for context
            routing_context: Optional routing information from deterministic router

        Returns:
            Validated AnalysisPlan object

        Raises:
            PlannerError: Structured planning failure
            ValidationError: Invalid plan structure (Pydantic)
        """
        pass


class PlannerError(Exception):
    """Structured planner error with code and message."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code}] {message}")


class ReplayPlannerProvider(PlannerProvider):
    """Offline fixture-based provider for testing and evaluation.

    Loads pre-generated plans from JSON fixtures, keyed by task ID.
    Supports both perfect plans and malformed outputs for testing validation.
    """

    def __init__(self, fixture_path: Path):
        """Initialize with fixture directory or file.

        Args:
            fixture_path: Path to fixture JSON file or directory of fixtures
        """
        self.fixture_path = fixture_path
        self._fixtures: dict[str, dict[str, Any]] = {}

        self._load_fixtures()

    def _load_fixtures(self) -> None:
        """Load fixtures from disk.

        Accepts either a single JSON file or a directory of JSON files.
        """
        if self.fixture_path.is_file():
            self._load_single_file(self.fixture_path)
        elif self.fixture_path.is_dir():
            for path in self.fixture_path.glob("*.json"):
                self._load_single_file(path)
        else:
            raise PlannerError(
                "fixture_not_found",
                f"Fixture path does not exist: {self.fixture_path}",
            )

    def _load_single_file(self, path: Path) -> None:
        """Load a single fixture file."""
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise PlannerError(
                    "invalid_fixture_format",
                    f"Fixture must be a dict, got {type(data).__name__}",
                    {"path": str(path)},
                )

            # Support both task_id-keyed and flat "plan" structures
            if "plan" in data and isinstance(data["plan"], dict):
                # Single plan fixture
                task_id = data.get("task_id", path.stem)
                self._fixtures[task_id] = data["plan"]
            else:
                # Task-indexed fixture dict
                for task_id, plan_data in data.items():
                    if isinstance(plan_data, dict) and "plan" in plan_data:
                        self._fixtures[task_id] = plan_data["plan"]
                    elif isinstance(plan_data, dict):
                        self._fixtures[task_id] = plan_data

        except json.JSONDecodeError as e:
            raise PlannerError(
                "invalid_json",
                f"Invalid JSON in fixture file: {e}",
                {"path": str(path)},
            )

    def generate_plan(
        self,
        question: str,
        registry_path: Path | None = None,
        routing_context: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> AnalysisPlan:
        """Generate a plan from fixtures.

        Args:
            question: Free-text clinical question (ignored for fixtures)
            registry_path: Optional path to variable registry (ignored)
            routing_context: Optional routing information (ignored for fixtures)
            task_id: Optional task ID to look up in fixtures

        Returns:
            Validated AnalysisPlan object

        Raises:
            PlannerError: If task_id not found or fixture is malformed
        """
        if task_id is None:
            # Try to infer task_id from question if it looks like a task ID
            words = question.strip().split()
            if words and len(words[0]) < 50:
                task_id = words[0].lower().strip()
            else:
                raise PlannerError(
                    "task_id_required",
                    "ReplayPlannerProvider requires task_id parameter",
                )

        if task_id not in self._fixtures:
            available = sorted(self._fixtures.keys())
            raise PlannerError(
                "fixture_not_found",
                f"No fixture found for task_id: {task_id}",
                {"task_id": task_id, "available": available[:10]},
            )

        plan_data = self._fixtures[task_id]

        # Check for malformed fixture marker
        if plan_data.get("_malformed") is True:
            raw = plan_data.get("raw", {})
            raise PlannerError(
                "malformed_fixture",
                "Intentionally malformed fixture for testing",
                {"raw": raw, "task_id": task_id},
            )

        try:
            return AnalysisPlan.model_validate(plan_data)
        except ValidationError as e:
            raise PlannerError(
                "invalid_fixture_plan",
                f"Fixture does not validate as AnalysisPlan: {e}",
                {"task_id": task_id, "errors": e.errors()},
            )


class ClaudeCodePlannerProvider(PlannerProvider):
    """Subprocess-based Claude Code planner provider.

    Calls Claude Code CLI as a subprocess with safe-mode and structured output.
    Uses verified CLI flags: -p --safe-mode --output-format json --json-schema.

    No fallback, no retries — explicit failures for research transparency.
    """

    def __init__(
        self,
        prompt_path: Path,
        model: str = "claude-sonnet-4-6",
        timeout: int = 120,
        max_budget_usd: float | None = None,
    ):
        """Initialize Claude Code planner provider.

        Args:
            prompt_path: Path to planner prompt template
            model: Model identifier (claude-sonnet-4-6, claude-opus-4-8, etc.)
            timeout: Subprocess timeout in seconds
            max_budget_usd: Optional maximum budget in USD for API calls
        """
        self.prompt_path = prompt_path
        self.model = model
        self.timeout = timeout
        self.max_budget_usd = max_budget_usd

        # Telemetry from the most recent generate_plan() call. None before any
        # call, or when context building failed before the subprocess ran. Set
        # to a CallTelemetry(model_call_attempted=True) once the subprocess is
        # invoked, and refreshed with parsed usage when an envelope is returned.
        # Read by ExperimentRunner.run_task; preserved across success and
        # parsing/validation failures.
        self.last_call_telemetry: CallTelemetry | None = None

    def _load_prompt(self) -> str:
        """Load prompt template from disk."""
        try:
            with self.prompt_path.open("r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise PlannerError(
                "prompt_not_found",
                f"Prompt file not found: {self.prompt_path}",
            )
        except Exception as e:
            raise PlannerError(
                "prompt_load_error",
                f"Failed to load prompt: {e}",
                {"path": str(self.prompt_path)},
            )

    def _build_json_schema(self) -> str:
        """Build JSON schema for structured output.

        Returns a strict schema compatible with AnalysisPlan validation.
        """
        schema = {
            "type": "object",
            "required": ["plan"],
            "properties": {
                "plan": {
                    "type": "object",
                    "required": ["title", "question", "database", "cycles", "feasible"],
                    "properties": {
                        "title": {"type": "string"},
                        "question": {"type": "string"},
                        "database": {"type": "string"},
                        "cycles": {"type": "array", "items": {"type": "string"}},
                        "feasible": {"type": "boolean"},
                        "outcome": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "label": {"type": "string"},
                                "source_variable": {"type": "string"},
                                "source_module": {"type": "string"},
                                "status": {"type": "string", "enum": ["verified", "illustrative", "needs review"]},
                                "nhanes_cycles": {"type": "array", "items": {"type": "string"}},
                                "transform": {"type": ["string", "null"]},
                                "units": {"type": ["string", "null"]},
                                "ref_notes": {"type": ["string", "null"]},
                            },
                        },
                        "exposures": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "label": {"type": "string"},
                                    "source_variable": {"type": "string"},
                                    "source_module": {"type": "string"},
                                    "status": {"type": "string", "enum": ["verified", "illustrative", "needs review"]},
                                    "nhanes_cycles": {"type": "array", "items": {"type": "string"}},
                                    "transform": {"type": ["string", "null"]},
                                    "units": {"type": ["string", "null"]},
                                    "ref_notes": {"type": ["string", "null"]},
                                },
                            },
                        },
                        "covariates": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "label": {"type": "string"},
                                    "source_variable": {"type": "string"},
                                    "source_module": {"type": "string"},
                                    "status": {"type": "string", "enum": ["verified", "illustrative", "needs review"]},
                                    "nhanes_cycles": {"type": "array", "items": {"type": "string"}},
                                    "transform": {"type": ["string", "null"]},
                                    "units": {"type": ["string", "null"]},
                                    "ref_notes": {"type": ["string", "null"]},
                                },
                            },
                        },
                        "uses_fasting_subsample": {"type": "boolean"},
                        "design_vars": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "strata": {"type": "string"},
                                "weight": {"type": "string"},
                            },
                        },
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "step": {"type": "string"},
                                    "description": {"type": "string"},
                                    "outputs": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                        },
                        "causal_claims": {"type": "array", "items": {"type": "string"}},
                        "rationale": {"type": ["string", "null"]},
                        "guardrail_notes": {"type": ["string", "null"]},
                    },
                }
            },
        }
        return json.dumps(schema)

    def _build_registry_context(self, registry_path: Path | None) -> str:
        """Build concise JSON registry context for the LLM.

        Returns a JSON string with variable entries containing only:
        name, source_variable, source_module, status, nhanes_cycles.
        """
        if not registry_path:
            return "[]"

        try:
            registry = load_variable_registry(registry_path)
            variables_data = []
            for v in registry:
                var_obj = {
                    "name": v.name,
                    "source_variable": v.source_variable,
                    "source_module": v.source_module,
                    "status": v.status.value,
                    "nhanes_cycles": v.nhanes_cycles,
                }
                variables_data.append(var_obj)
            return json.dumps(variables_data)
        except Exception as e:
            raise PlannerError(
                "registry_load_error",
                f"Failed to load registry: {e}",
                {"path": str(registry_path)},
            )

    def _build_routing_context(self, routing_context: dict[str, Any] | None) -> str:
        """Build routing context string for the LLM.

        Returns a JSON string with routing decision information.
        """
        if not routing_context:
            return "{}"

        try:
            return json.dumps({
                "database": routing_context.get("database", ""),
                "feasible": routing_context.get("feasible", True),
                "rationale": routing_context.get("rationale", ""),
                "caveats": routing_context.get("caveats", []),
            })
        except Exception as e:
            raise PlannerError(
                "routing_context_error",
                f"Failed to serialize routing context: {e}",
            )

    def _build_argv(
        self,
        question: str,
        registry_context: str,
        routing_context: str = "{}",
    ) -> list[str]:
        """Build subprocess argv for Claude Code call.

        Uses verified safe CLI flags with shell=False.
        """
        prompt = self._load_prompt()

        # Prepare the full prompt with question, registry context, and routing context
        # Use str.replace to safely substitute only the exact tokens we need,
        # preserving all other braces (including JSON examples in the prompt)
        full_prompt = (
            prompt.replace("{question}", question)
                  .replace("{registry_summary}", registry_context)
                  .replace("{routing_context}", routing_context)
        )

        # Build JSON schema for structured output
        json_schema = self._build_json_schema()

        # Build Claude Code argv with verified safe flags
        argv = [
            "claude",
            "-p",
            "--safe-mode",
            "--model", self.model,
            "--effort", "low",
            "--permission-mode", "dontAsk",
            "--output-format", "json",
            "--json-schema", json_schema,
        ]

        if self.max_budget_usd is not None:
            argv.extend(["--max-budget-usd", str(self.max_budget_usd)])

        # Add prompt as final argument
        argv.append(full_prompt)

        return argv

    def _call_claude(self, question: str, registry_context: str, routing_context: str) -> tuple[dict[str, Any], dict[str, Any], CallTelemetry]:
        """Execute Claude Code subprocess and capture JSON output.

        Returns:
            Tuple of (envelope dict, execution_metadata dict, CallTelemetry)

        Raises:
            PlannerError: For subprocess failures or non-JSON output

        Note: telemetry captures only scalar usage/cost/timing fields from the
        envelope. No stdout, prompts, auth material, or other secrets are
        retained.
        """
        argv = self._build_argv(question, registry_context, routing_context)
        start_time = time.time()

        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                check=False,
                shell=False,
            )

            duration = time.time() - start_time

            # Check for subprocess errors
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                raise PlannerError(
                    "claude_subprocess_error",
                    f"Claude Code subprocess failed with exit code {result.returncode}",
                    {
                        "exit_code": result.returncode,
                        "stderr": result.stderr[-1000:] if result.stderr else None,
                        "stdout": result.stdout[:500] if result.stdout else None,
                        "duration_seconds": duration,
                    },
                )

            stdout = result.stdout or ""
            if not stdout.strip():
                raise PlannerError(
                    "claude_empty_output",
                    "Claude Code returned an empty stdout payload",
                    {"stderr": (result.stderr or "")[:500], "duration_seconds": duration},
                )

            # Parse JSON envelope output
            try:
                envelope = json.loads(stdout)
            except json.JSONDecodeError as e:
                raise PlannerError(
                    "claude_json_parse_error",
                    f"Failed to parse Claude output as JSON: {e}",
                    {
                        "stdout": stdout[:500],
                        "parse_error": str(e),
                        "duration_seconds": duration,
                    },
                )

            # Build execution metadata (without secrets)
            execution_metadata = {
                "duration_seconds": duration,
                "model": self.model,
                "timeout": self.timeout,
                "max_budget_usd": self.max_budget_usd,
            }

            # Parse scalar telemetry from the envelope (None for missing
            # fields; never coerced to zero). No secrets retained.
            telemetry = parse_envelope_telemetry(envelope)

            return envelope, execution_metadata, telemetry

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            raise PlannerError(
                "claude_timeout",
                f"Claude Code subprocess timed out after {self.timeout}s",
                {"timeout": self.timeout, "duration_seconds": duration},
            )
        except FileNotFoundError:
            raise PlannerError(
                "claude_not_found",
                "Claude Code CLI not found on PATH",
                {"argv": argv[:4]},  # First few args only (no secrets)
            )

    def generate_plan(
        self,
        question: str,
        registry_path: Path | None = None,
        routing_context: dict[str, Any] | None = None,
    ) -> AnalysisPlan:
        """Generate a plan via Claude Code subprocess.

        Args:
            question: Clinical question text
            registry_path: Optional path to variable registry for context
            routing_context: Optional routing information from deterministic router

        Returns:
            Validated AnalysisPlan object

        Raises:
            PlannerError: For any subprocess or validation failure
        """
        # Build registry context
        registry_context = self._build_registry_context(registry_path)

        # Build routing context
        routing_context_str = self._build_routing_context(routing_context)

        # A subprocess call is about to be attempted. Mark attempted so that
        # even if parsing or plan validation fails afterwards, this still counts
        # as one model call. Reset to None only happens here at entry, after
        # context building (which can raise without invoking the subprocess).
        self.last_call_telemetry = CallTelemetry(model_call_attempted=True)

        # Call Claude
        envelope, execution_metadata, telemetry = self._call_claude(question, registry_context, routing_context_str)

        # Refresh telemetry with parsed usage (attempted stays True). This is
        # set before plan validation so failures below still preserve telemetry.
        self.last_call_telemetry = telemetry

        # Validate envelope structure
        if not isinstance(envelope, dict):
            raise PlannerError(
                "claude_invalid_envelope_type",
                f"Claude output envelope must be a dict, got {type(envelope).__name__}",
                {"envelope_type": str(type(envelope).__name__), **execution_metadata},
            )

        # Extract structured_output from envelope first (real CLI behavior)
        structured_output = envelope.get("structured_output")
        if structured_output is not None:
            # Real CLI puts validated content in structured_output
            plan_data = structured_output.get("plan") if isinstance(structured_output, dict) else None
            if plan_data is None:
                raise PlannerError(
                    "claude_missing_plan_in_structured_output",
                    "Claude structured_output missing 'plan' key",
                    {"structured_output_keys": sorted(structured_output.keys()) if isinstance(structured_output, dict) else type(structured_output).__name__, **execution_metadata},
                )
        else:
            # Fallback to result field if structured_output missing
            result = envelope.get("result")
            if result is not None:
                if isinstance(result, str):
                    # Result might be JSON string
                    try:
                        result_obj = json.loads(result)
                        plan_data = result_obj.get("plan") if isinstance(result_obj, dict) else None
                    except json.JSONDecodeError:
                        raise PlannerError(
                            "claude_result_invalid_json",
                            "Claude result field is not valid JSON",
                            {"result_preview": result[:200], **execution_metadata},
                        )
                else:
                    plan_data = result.get("plan") if isinstance(result, dict) else None

                if plan_data is None:
                    raise PlannerError(
                        "claude_missing_plan_in_result",
                        "Claude result missing 'plan' key",
                        {"result_keys": sorted(result.keys()) if isinstance(result, dict) else type(result).__name__, **execution_metadata},
                    )
            else:
                # Direct envelope plan (legacy)
                plan_data = envelope.get("plan")
                if plan_data is None:
                    raise PlannerError(
                        "claude_missing_plan",
                        "Claude output missing 'plan' key in envelope, structured_output, or result",
                        {"envelope_keys": sorted(envelope.keys()), **execution_metadata},
                    )

        if not isinstance(plan_data, dict):
            raise PlannerError(
                "claude_invalid_plan_type",
                f"Plan must be a dict, got {type(plan_data).__name__}",
                {**execution_metadata},
            )

        # Validate as AnalysisPlan (never silently repair/fallback)
        try:
            return AnalysisPlan.model_validate(plan_data)
        except ValidationError as e:
            raise PlannerError(
                "claude_validation_error",
                f"Claude output does not validate as AnalysisPlan: {e}",
                {"validation_errors": e.errors(), **execution_metadata},
            )
