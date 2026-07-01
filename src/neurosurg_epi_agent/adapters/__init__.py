"""Database adapter package: protocol/registry + built-in adapters.

An *adapter* is the security-hardened boundary between NeuroSurgEpiAgent and a
single external database's local files. Adapters expose identity + a
metadata-only ``inspect`` method; they never emit participant values and never
persist extracted files.

Importing this package does NOT require the optional ``pandas`` dependency --
CHARLS imports pandas lazily, only when ``inspect`` actually parses a Stata
``.dta`` file. Install it with ``pip install neurosurg-epi-agent[multidb]``.
"""

from __future__ import annotations

from .base import (
    ADAPTER_VERSION,
    AdapterError,
    AdapterIdentity,
    AdapterRegistry,
    ArchiveInspectionError,
    ArchiveMetadata,
    DatabaseAdapter,
    DuplicateMemberError,
    EncryptedMemberError,
    InspectionResult,
    MalformedArchiveError,
    MemberMetadata,
    MemberSizeExceededError,
    MemberVariable,
    MissingDependencyError,
    PRIVACY_STATEMENT,
    PathTraversalError,
    SkippedMember,
    UnsupportedFormatError,
)
from .cdc_wonder import CDCWonderAdapter
from .charls import CHARLSAdapter
from .nhanes import NHANESAdapter
from .seer import SEERAdapter

__all__ = [
    "ADAPTER_VERSION",
    "AdapterError",
    "AdapterIdentity",
    "AdapterRegistry",
    "ArchiveInspectionError",
    "ArchiveMetadata",
    "CDCWonderAdapter",
    "CHARLSAdapter",
    "DatabaseAdapter",
    "DuplicateMemberError",
    "EncryptedMemberError",
    "InspectionResult",
    "MalformedArchiveError",
    "MemberMetadata",
    "MemberSizeExceededError",
    "MemberVariable",
    "MissingDependencyError",
    "NHANESAdapter",
    "PRIVACY_STATEMENT",
    "PathTraversalError",
    "SEERAdapter",
    "SkippedMember",
    "UnsupportedFormatError",
    "default_registry",
    "get_default",
]


def default_registry() -> AdapterRegistry:
    """Return a fresh registry pre-populated with the built-in adapters.

    Returns a new instance each call so callers can mutate it (register
    additional adapters, etc.) without affecting other callers.
    """
    registry = AdapterRegistry()
    registry.register(CDCWonderAdapter())
    registry.register(CHARLSAdapter())
    registry.register(NHANESAdapter())
    registry.register(SEERAdapter())
    return registry


def get_default(database: str) -> DatabaseAdapter:
    """Convenience accessor: build a default registry and look up ``database``."""
    return default_registry().get(database)
