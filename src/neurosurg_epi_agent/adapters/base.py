"""Database adapter protocol, registry, and metadata dataclasses.

An *adapter* is the thin, security-hardened boundary between NeuroSurgEpiAgent
and a single external database's local files. The MVP only requires adapters to
expose *identity* (who they are, what formats/capabilities they support) and a
*metadata-only inspection* method. They do NOT execute epidemiologic models,
read participant values into outputs, or persist extracted raw files.

The dataclasses here are deliberately framework-light (plain ``dataclasses``,
not pydantic) so the adapter layer can evolve without coupling to the engine's
typed-schema boundary in :mod:`neurosurg_epi_agent.schemas`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

# Adapter PROTOCOL / schema version — the shape of ``InspectionResult``,
# ``MemberMetadata``, etc. Bump only when that contract changes in a breaking
# way. This is a DISTINCT version axis from the software package release
# version (``neurosurg_epi_agent.__version__``): a release may ship without a
# protocol bump, and a protocol bump need not coincide with a release. Do not
# collapse the two.
ADAPTER_VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #

class AdapterError(RuntimeError):
    """Base class for adapter-layer failures."""


class UnsupportedFormatError(AdapterError):
    """Raised when a file/archive is not a format the adapter handles."""


class ArchiveInspectionError(AdapterError):
    """Base class for problems inspecting an archive (ZIP) or its members."""


class MalformedArchiveError(ArchiveInspectionError):
    """Raised when an archive is structurally invalid or unreadable."""


class PathTraversalError(ArchiveInspectionError):
    """Raised when an archive member name escapes the safe root (traversal)."""


class EncryptedMemberError(ArchiveInspectionError):
    """Raised when an archive member is encrypted and cannot be inspected."""


class MemberSizeExceededError(ArchiveInspectionError):
    """Raised when a member exceeds the configured byte-size guard."""


class DuplicateMemberError(ArchiveInspectionError):
    """Raised when two members resolve to the same safe name (ambiguous)."""


class MissingDependencyError(AdapterError):
    """Raised when an optional dependency (e.g. pandas) is required but absent."""


# --------------------------------------------------------------------------- #
# Metadata dataclasses (metadata-only; never carry participant values)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class AdapterIdentity:
    """Static identity + capability card advertised by an adapter."""

    database: str
    label: str
    version: str
    data_formats: tuple[str, ...]
    capabilities: tuple[str, ...]
    access: str  # "local-authorized" | "public" | "account-required" | ...

    def to_dict(self) -> dict:
        return {
            "database": self.database,
            "label": self.label,
            "version": self.version,
            "data_formats": list(self.data_formats),
            "capabilities": list(self.capabilities),
            "access": self.access,
        }


@dataclass(frozen=True)
class MemberVariable:
    """A single variable's name + human label. Values are NEVER carried."""

    name: str
    label: str


@dataclass(frozen=True)
class MemberMetadata:
    """Metadata for one inspected data member (a .dta file or archive member)."""

    member_path: str           # safe relative path (within archive, or rel to root)
    member_name: str           # basename
    format: str                # e.g. "stata-dta"
    byte_size: int
    sha256: str
    row_count: int | None = None
    column_count: int | None = None
    dataset_label: str | None = None
    variables: tuple[MemberVariable, ...] = ()
    provenance: dict[str, str] = field(default_factory=dict)
    source_archive: str | None = None  # relative archive path if read from a ZIP

    def to_dict(self) -> dict:
        return {
            "source_archive": self.source_archive,
            "member_path": self.member_path,
            "member_name": self.member_name,
            "format": self.format,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "dataset_label": self.dataset_label,
            "variables": [{"name": v.name, "label": v.label} for v in self.variables],
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class SkippedMember:
    """A member that was deliberately not inspected, with the reason."""

    member_path: str
    member_name: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "member_path": self.member_path,
            "member_name": self.member_name,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ArchiveMetadata:
    """Metadata for one source archive (ZIP) and the members it contained."""

    archive_path: str          # safe relative path (relative to the supplied root)
    sha256: str
    byte_size: int
    members: tuple[MemberMetadata, ...] = ()
    skipped: tuple[SkippedMember, ...] = ()

    def to_dict(self) -> dict:
        return {
            "archive_path": self.archive_path,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "members": [m.to_dict() for m in self.members],
            "skipped": [s.to_dict() for s in self.skipped],
        }


# Standard privacy statement emitted by every inspection. It is intentionally
# explicit so downstream tooling and reviewers cannot mistake the output for a
# data extract.
PRIVACY_STATEMENT = (
    "Metadata-only output. This file contains aggregate schema information only: "
    "relative archive/member paths, byte sizes, SHA-256 hashes, row/column counts, "
    "dataset labels, variable names and variable labels, and dataset/wave provenance. "
    "It does NOT contain, and the adapter never emits, participant identifiers, "
    "household identifiers, sample rows, value frequencies, value labels, or any "
    "participant-level records. No raw bytes or extracted files are persisted by the "
    "adapter; members are read into transient memory only."
)


@dataclass(frozen=True)
class InspectionResult:
    """Top-level, metadata-only result returned by ``DatabaseAdapter.inspect``."""

    database: str
    identity: AdapterIdentity
    data_root: str              # neutral provenance token (never the raw path)
    archives: tuple[ArchiveMetadata, ...] = ()
    direct_files: tuple[MemberMetadata, ...] = ()
    skipped_roots: tuple[SkippedMember, ...] = ()
    privacy_statement: str = PRIVACY_STATEMENT
    adapter_version: str = ""
    notes: tuple[str, ...] = ()
    # Adapter-level provenance (e.g. SEER data-version fields). Distinct from
    # per-member provenance carried in ``MemberMetadata.provenance``.
    provenance: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "database": self.database,
            "identity": self.identity.to_dict(),
            "data_root": self.data_root,
            "privacy_statement": self.privacy_statement,
            "adapter_version": self.adapter_version,
            "notes": list(self.notes),
            "archives": [a.to_dict() for a in self.archives],
            "direct_files": [m.to_dict() for m in self.direct_files],
            "skipped_roots": [s.to_dict() for s in self.skipped_roots],
            "provenance": dict(self.provenance),
        }


# --------------------------------------------------------------------------- #
# Protocol + registry
# --------------------------------------------------------------------------- #

@runtime_checkable
class DatabaseAdapter(Protocol):
    """The contract every adapter satisfies.

    ``inspect`` returns metadata only and must:

    * require a user-supplied ``data_root`` (never a hard-coded licensed path);
    * emit a NEUTRAL ``data_root`` token in the result (e.g. ``"<user-supplied>"``),
      never the absolute/local path the caller actually passed;
    * refuse to follow symlinks outside the requested root;
    * defend against ZIP path traversal, encrypted members, malformed archives,
      unsupported files, and unbounded reads;
    * hash source archives and inspected members with SHA-256;
    * never persist extracted raw files (members are read transiently).
    """

    identity: AdapterIdentity

    def inspect(
        self,
        data_root: Path,
        *,
        max_member_bytes: int = 2 * 1024 * 1024 * 1024,
        members: set[str] | None = None,
    ) -> InspectionResult:
        """Inspect ``data_root`` and return metadata only."""
        ...


class AdapterRegistry:
    """Maps database name -> adapter instance."""

    def __init__(self) -> None:
        self._adapters: dict[str, DatabaseAdapter] = {}

    def register(self, adapter: DatabaseAdapter) -> None:
        name = adapter.identity.database
        if name in self._adapters:
            raise AdapterError(f"adapter already registered for database {name!r}")
        self._adapters[name] = adapter

    def get(self, name: str) -> DatabaseAdapter:
        if name not in self._adapters:
            raise AdapterError(
                f"no adapter registered for database {name!r}; "
                f"known: {sorted(self._adapters)}"
            )
        return self._adapters[name]

    def names(self) -> list[str]:
        return sorted(self._adapters)

    def __contains__(self, name: object) -> bool:
        return name in self._adapters
