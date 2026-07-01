"""Versioned YAML registry loader + cross-check validation.

Registries are plain YAML on disk so they are auditable and diff-able. The
loader is the only place variable mappings enter the engine, so it validates
hard: required schema version, no duplicate stems, status fields present.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .schemas import DatabaseConfig, VariableMapping, VariableStatus

REGISTRY_VERSION = "1"
SUPPORTED_VARIABLE_REGISTRY_VERSIONS = {"1"}


class RegistryError(ValueError):
    """Raised when a registry file is structurally invalid."""


def _load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise RegistryError(f"registry file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise RegistryError(f"registry root must be a mapping, got {type(data).__name__}: {p}")
    return data


def _check_version(data: dict[str, Any], path: Path, kind: str) -> None:
    version = str(data.get("registry_version", ""))
    if version not in SUPPORTED_VARIABLE_REGISTRY_VERSIONS:
        raise RegistryError(
            f"unsupported {kind} registry_version {version!r}; "
            f"supported: {sorted(SUPPORTED_VARIABLE_REGISTRY_VERSIONS)} ({path})"
        )


def load_databases(path: str | Path) -> dict[str, DatabaseConfig]:
    """Load the full databases capability file -> {name: DatabaseConfig}."""
    data = _load_yaml(path)
    _check_version(data, Path(path), "database")
    block = data.get("databases")
    if not isinstance(block, dict):
        raise RegistryError(f"'databases' must be a mapping in {path}")
    return {name: DatabaseConfig.model_validate(cfg) for name, cfg in block.items()}


def load_database_registry(path: str | Path, name: str = "NHANES") -> DatabaseConfig:
    dbs = load_databases(path)
    if name not in dbs:
        raise RegistryError(f"database {name!r} not present in {path}")
    return dbs[name]


def load_variable_registry(path: str | Path) -> list[VariableMapping]:
    """Load and validate a variable-mapping file.

    Cross-checks:
      * registry_version present and supported
      * no duplicate `name` or `source_variable`
      * every mapping carries an explicit `status`
      * ILLUSTRATIVE/NEEDS_REVIEW are surfaced, never silently treated as VERIFIED
    """
    data = _load_yaml(path)
    _check_version(data, Path(path), "variable")
    version = str(data.get("registry_version", ""))
    if version not in SUPPORTED_VARIABLE_REGISTRY_VERSIONS:  # pragma: no cover - defensive
        raise RegistryError(f"unsupported variable registry_version {version!r} ({path})")
    variables = data.get("variables")
    if not isinstance(variables, list):
        raise RegistryError(f"'variables' must be a list in {path}")

    seen_names: dict[str, int] = {}
    seen_sources: dict[str, int] = {}
    out: list[VariableMapping] = []
    for i, item in enumerate(variables):
        if not isinstance(item, dict):
            raise RegistryError(f"variable entry #{i} is not a mapping in {path}")
        if "status" not in item:
            raise RegistryError(
                f"variable entry #{i} ({item.get('name', '?')}) is missing explicit 'status' "
                f"in {path}"
            )
        vm = VariableMapping.model_validate(item)
        if vm.name in seen_names:
            raise RegistryError(
                f"duplicate variable name {vm.name!r} (entries #{seen_names[vm.name]} and #{i})"
            )
        if vm.source_variable in seen_sources:
            raise RegistryError(
                f"duplicate source_variable {vm.source_variable!r} "
                f"(entries #{seen_sources[vm.source_variable]} and #{i})"
            )
        seen_names[vm.name] = i
        seen_sources[vm.source_variable] = i
        out.append(vm)
    return out


def variables_by_name(variables: list[VariableMapping]) -> dict[str, VariableMapping]:
    return {v.name: v for v in variables}


def unverified(variables: list[VariableMapping]) -> list[VariableMapping]:
    """Return anything that is not independently confirmed against a codebook."""
    return [v for v in variables if v.status is not VariableStatus.VERIFIED]
