"""NeuroSurgEpiAgent - reproducible neurosurgical epidemiology planning for public databases.

The LLM is a planner/explainer only. Variable names, survey-design rules, and
statistical validity are enforced deterministically by typed schemas, a
versioned YAML registry, and guardrails. Nothing in this package invents
variable codes, citations, or results.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Versioning policy (single source of truth).
#
# ``__version__`` below is the canonical *software package release version*. It
# is the ONE place the release number is written: ``pyproject.toml`` reads it
# at build time via ``[tool.setuptools.dynamic] version = {attr = ...}``, so the
# distribution metadata always matches this literal without a second hand-edited
# copy. Release docs (``CITATION.cff``, release notes) and the version
# consistency test are kept in sync with this value.
#
# This is intentionally DISTINCT from two other version axes in the codebase:
#
#   * ``adapters.base.ADAPTER_VERSION`` — the adapter *protocol / schema*
#     version (the shape of ``InspectionResult`` etc.). It moves only when the
#     adapter contract changes; it is NOT pinned to the package release.
#   * ``<Adapter>.identity.version`` — each individual adapter's
#     *implementation* version, bumped per adapter when its own logic changes.
#
# Do not collapse these axes onto the package release version for the sake of
# appearances: a protocol bump and a release bump mean different things.
# ---------------------------------------------------------------------------

__version__ = "0.3.1"

__all__ = ["__version__"]
