"""NeuroSurgEpiAgent - reproducible neurosurgical epidemiology planning for public databases.

The LLM is a planner/explainer only. Variable names, survey-design rules, and
statistical validity are enforced deterministically by typed schemas, a
versioned YAML registry, and guardrails. Nothing in this package invents
variable codes, citations, or results.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
