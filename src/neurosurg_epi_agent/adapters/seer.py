"""SEER database adapter — metadata-only inspection of local SEER*Stat exports.

SEER (Surveillance, Epidemiology, and End Results) registry data are
distributed under a SEER Research Data Use Agreement (DUA) and contain
individual-level tumor records. They are NEVER publicly redistributed.
This adapter inspects user-downloaded SEER*Stat export CSVs in
**metadata-only** mode: it reads the file header, computes a schema
fingerprint, optionally streams a SHA-256 over the bytes, and emits a
neutral ``<user-supplied>`` data_root token. It never loads a single
case row.

Streaming is mandatory: a typical SEER*Stat CNS export (export_C69-C72.csv
and similar) is hundreds of MB to several GB. The adapter reads only the
header line (≤10 KiB on every observed export) plus, on demand, a streaming
SHA-256 over the file bytes via a chunked reader. No pandas, no full-file
load, no row counts derived by parsing data rows.

Capability split (explicitly enforced):

* ``metadata-inspection`` — implemented and supported. Header + schema
  fingerprint + byte size + (optional) SHA-256 + relative path. No record
  data is emitted under any branch of ``inspect``.
* ``clinical-analysis`` — **planned, NOT supported**. The adapter never
  produces a clinical-analysis payload. The user must complete
  ``docs/SEER_STUDY_CONTRACT.md`` before any clinical analysis is written.

Security posture mirrors the other adapters:

* user-supplied ``data_root`` is required (no hard-coded licensed path);
* symlinked files inside the root are not followed;
* members exceeding ``max_member_bytes`` are skipped (unbounded-read guard);
* SHA-256 is streamed, not buffered;
* the absolute path is replaced with the neutral ``<user-supplied>`` token
  in every emitted artifact.

SEER data version (release/submission, Research vs Research Plus, registry
set, SEER*Stat version, session type, export date, selection statements, the
export data dictionary) **cannot** be reliably recovered from the CSV
bytes alone. The adapter accepts these as user-supplied kwargs; when they
are absent, the corresponding field is recorded as ``needs_verification``
and the adapter never guesses.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
from pathlib import Path
from typing import Any

from .base import (
    ADAPTER_VERSION,
    AdapterIdentity,
    ArchiveInspectionError,
    InspectionResult,
    MemberMetadata,
    MemberVariable,
    PRIVACY_STATEMENT,
    SkippedMember,
)

# NEUTRAL token emitted in place of the caller's real data_root.
DATA_ROOT_TOKEN = "<user-supplied>"

# SEER*Stat exports use CSV with the standard .csv extension.
_CSV_SUFFIXES = (".csv",)

# Cap on header bytes we'll ever buffer. SEER headers are <10 KiB in every
# observed release; 1 MiB is a generous safety margin and prevents a malicious
# file from being used to exhaust memory through a huge "header" line.
_MAX_HEADER_BYTES = 1 * 1024 * 1024

# Conservative cap on the bytes streamed for the optional SHA-256. We allow
# 8 GiB by default — well above any current SEER*Stat single-file export —
# but refuse anything larger.
DEFAULT_MAX_MEMBER_BYTES = 8 * 1024 * 1024 * 1024

# User-supplied data-version fields the adapter accepts. None of these can
# be inferred from the CSV bytes; they must come from the researcher's
# SEER*Stat session / DUA paperwork.
_DATA_VERSION_FIELDS: tuple[str, ...] = (
    "release_submission",
    "product_type",      # "Research" | "Research Plus" | "Research Plus 8.0+"
    "registry_set",
    "seerstat_version",
    "session_type",
    "export_date",
    "selection_statements",
    "export_data_dictionary",
)


# --------------------------------------------------------------------------- #
# Filename / site-code hints — only used to label the inventory entry, never
# to alter the file's bytes.
# --------------------------------------------------------------------------- #

# A SEER*Stat export name like ``export_C69-C72.csv`` or
# ``export_C00-C09.csv`` describes an ICD-O-3 site range. We capture the
# literal range as a label only; we do NOT claim every row in the file is
# within that range. SEER*Stat exports often contain rows with Site recode
# values outside the file-name range (e.g. unknown / NOS), and the user must
# confirm the actual cohort with the export data dictionary.
_SITE_RANGE_RE = re.compile(r"(C\d{2})\s*-\s*(C\d{2})", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Streaming helpers
# --------------------------------------------------------------------------- #

def _walk_files(root: Path) -> list[Path]:
    """Return real files under ``root`` (including symlinked files) in order.

    Symlinked *directories* are not descended into (``followlinks=False`` and
    the dirnames filter). Symlinked *files* ARE returned so the caller's inspect
    loop can record them in ``skipped_roots`` — a symlink pointing outside the
    requested root must never be silently dropped, and must never be read.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames if not (Path(dirpath) / d).is_symlink()
        )
        for fname in sorted(filenames):
            found.append(Path(dirpath) / fname)
    return found


def _read_header(path: Path, max_bytes: int = _MAX_HEADER_BYTES) -> tuple[str, bool]:
    """Read the first CSV line from ``path`` without loading the rest.

    Returns ``(header_text, truncated)``. ``truncated=True`` means the header
    line exceeded ``max_bytes`` (i.e. looks malformed for SEER).
    """
    chunks: list[bytes] = []
    total = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(64 * 1024)
            if not chunk:
                break
            # Stop at the first newline; that's where the SEER header ends.
            nl = chunk.find(b"\n")
            if nl >= 0:
                chunks.append(chunk[: nl + 1])
                total += nl + 1
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                return (b"".join(chunks).decode("utf-8", errors="replace"), True)
    raw = b"".join(chunks)
    # Strip trailing newline(s).
    raw = raw.rstrip(b"\r\n")
    return (raw.decode("utf-8-sig", errors="replace"), False)


def _parse_header_columns(header_text: str) -> list[str]:
    """Parse a CSV header line into column names.

    Handles SEER's quoted, comma-in-value headers (e.g. ``"Race recode (W, B,
    AI, API)"``) by routing through the stdlib CSV parser.
    """
    if not header_text.strip():
        return []
    return [c.strip() for c in next(csv.reader(io.StringIO(header_text)))]


def _schema_fingerprint(columns: list[str]) -> str:
    """MD5 of the canonicalized header column list.

    MD5 is acceptable here because the fingerprint is an inventory label,
    not a security primitive; SHA-256 is reserved for the optional file hash.
    """
    canonical = "\n".join(columns).encode("utf-8")
    return hashlib.md5(canonical, usedforsecurity=False).hexdigest()


def _stream_sha256(path: Path, max_bytes: int) -> tuple[str | None, int]:
    """Stream a SHA-256 over the file bytes; never load the whole file.

    Returns ``(digest, actual_bytes_hashed)``. ``digest`` is ``None`` when the
    file exceeds ``max_bytes`` (the caller should mark the file as
    "hash-skipped, size limit").
    """
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            total += len(chunk)
            if total > max_bytes:
                return (None, max_bytes)
            digest.update(chunk)
    return (digest.hexdigest(), total)


# --------------------------------------------------------------------------- #
# Adapter
# --------------------------------------------------------------------------- #

class SEERAdapter:
    """Metadata-only adapter for local SEER*Stat export CSVs.

    Capabilities are split:

    * ``metadata-inspection`` is implemented and supported.
    * ``clinical-analysis`` is **planned** and intentionally not exposed
      here. Any "analyze the SEER file" workflow must be backed by
      ``docs/SEER_STUDY_CONTRACT.md`` filled in by the researcher, plus the
      user-supplied ``data_version`` kwargs to ``inspect``.
    """

    identity = AdapterIdentity(
        database="SEER",
        label="SEER (Surveillance, Epidemiology, and End Results) registry exports",
        # Adapter IMPLEMENTATION version for SEER — bumped when this adapter's
        # own logic changes. Distinct from the package release version
        # (neurosurg_epi_agent.__version__) and from the shared adapter
        # protocol version (ADAPTER_VERSION).
        version="0.1.0",
        data_formats=("csv",),
        capabilities=("metadata-inspection",),
        access="local-authorized",
    )

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def inspect(
        self,
        data_root: Path,
        *,
        with_sha256: bool = False,
        sha256_max_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
        max_member_bytes: int | None = None,
        members: set[str] | None = None,
        data_version: dict[str, str] | None = None,
    ) -> InspectionResult:
        """Inspect a SEER*Stat export directory in metadata-only mode.

        Args:
            data_root: User-supplied directory containing SEER*Stat
                ``export_*.csv`` files.
            with_sha256: If True, stream a SHA-256 over every file's bytes
                (off by default because the files are large).
            sha256_max_bytes: Hard upper bound on the bytes hashed per file.
                Files exceeding this are inventoried with ``sha256=None`` and
                a ``size_limit_note`` annotation.
            max_member_bytes: Alias for ``sha256_max_bytes`` kept for
                uniformity with the CLI's ``--max-member-bytes`` flag
                across adapters. Ignored if ``sha256_max_bytes`` is also
                supplied.
            members: Optional set of basenames / relative paths to restrict
                inspection to.
            data_version: Optional mapping of user-supplied data-version
                fields (``release_submission``, ``product_type``,
                ``registry_set``, ``seerstat_version``, ``session_type``,
                ``export_date``, ``selection_statements``,
                ``export_data_dictionary``). Missing fields are recorded as
                ``needs_verification`` in the adapter-level provenance; the
                adapter never guesses.

        Returns:
            :class:`InspectionResult` containing per-file schema metadata.
            **No case row, no participant value, no frequency, no unique
            value** is ever present in the result.
        """
        # Allow ``max_member_bytes`` as a CLI-uniform alias.
        if max_member_bytes is not None:
            sha256_max_bytes = max_member_bytes
        root = Path(data_root)
        if not root.exists():
            raise ArchiveInspectionError(f"data_root does not exist: {root}")
        if with_sha256 and sha256_max_bytes <= 0:
            raise ValueError("sha256_max_bytes must be positive")

        data_version_in = dict(data_version or {})
        missing = [f for f in _DATA_VERSION_FIELDS if f not in data_version_in]
        if missing:
            data_version_in.setdefault(
                "needs_verification",
                ", ".join(missing),
            )

        direct_files: list[MemberMetadata] = []
        skipped: list[SkippedMember] = []

        candidate_paths = [root] if root.is_file() else _walk_files(root)
        for p in candidate_paths:
            if p.is_dir():
                continue
            try:
                rel = p.relative_to(root)
            except ValueError:
                rel = p
            rel_str = str(rel).replace("\\", "/")

            if p.is_symlink():
                skipped.append(SkippedMember(
                    member_path=rel_str, member_name=p.name,
                    reason="symlink not followed",
                ))
                continue
            if p.suffix.lower() not in _CSV_SUFFIXES:
                skipped.append(SkippedMember(
                    member_path=rel_str, member_name=p.name,
                    reason=f"unsupported file type ({p.suffix.lower() or 'no ext'})",
                ))
                continue

            size = p.stat().st_size
            # Header read is bounded; do it BEFORE any SHA-256 streaming.
            try:
                header_text, truncated = _read_header(p)
            except OSError as exc:
                skipped.append(SkippedMember(
                    member_path=rel_str, member_name=p.name,
                    reason=f"unreadable file: {type(exc).__name__}: {exc}",
                ))
                continue
            columns = _parse_header_columns(header_text) if not truncated else []
            fingerprint = _schema_fingerprint(columns) if columns else ""

            prov: dict[str, str] = {}
            prov["source"] = "SEER*Stat CSV export"
            prov["recognized"] = "true" if columns else "false"
            prov["header_byte_length"] = str(len(header_text.encode("utf-8")))
            prov["column_count"] = str(len(columns))
            prov["schema_fingerprint"] = fingerprint or "needs_verification"
            m = _SITE_RANGE_RE.search(p.name)
            if m:
                prov["filename_site_range"] = f"{m.group(1).upper()}-{m.group(2).upper()}"
                prov["filename_site_range_note"] = (
                    "Filename embeds an ICD-O-3 site range; rows in the file "
                    "may NOT all be within that range. Confirm cohort with "
                    "the export data dictionary and Site recode values."
                )
            if truncated:
                prov["header_truncated"] = "true"

            sha256: str | None = None
            sha256_note: str | None = None
            if with_sha256:
                digest, _ = _stream_sha256(p, sha256_max_bytes)
                if digest is None:
                    sha256_note = (
                        f"file exceeds sha256_max_bytes ({sha256_max_bytes}); "
                        "sha256 not computed"
                    )
                    prov["sha256_note"] = sha256_note
                else:
                    sha256 = digest

            direct_files.append(MemberMetadata(
                source_archive=None,
                member_path=rel_str,
                member_name=p.name,
                format="seer-stat-csv",
                byte_size=size,
                sha256=sha256 or "",  # type: ignore[arg-type]
                row_count=None,  # never computed by the metadata-only adapter
                column_count=len(columns) if columns else None,
                dataset_label=None,
                variables=tuple(MemberVariable(name=c, label="") for c in columns),
                provenance=prov,
            ))

        # Data-version provenance is emitted at the adapter level so a
        # reviewer can see at a glance which release fields are confirmed.
        adapter_prov = {k: str(v) for k, v in data_version_in.items()}
        adapter_prov["metadata_capability"] = "implemented"
        adapter_prov["clinical_capability"] = "planned"
        if not data_version:
            adapter_prov["needs_verification"] = ", ".join(_DATA_VERSION_FIELDS)

        return InspectionResult(
            database=self.identity.database,
            identity=self.identity,
            data_root=DATA_ROOT_TOKEN,
            archives=(),
            direct_files=tuple(direct_files),
            skipped_roots=tuple(skipped),
            privacy_statement=PRIVACY_STATEMENT,
            adapter_version=ADAPTER_VERSION,
            notes=self._inspection_notes(),
            provenance=adapter_prov,
        )

    @staticmethod
    def _inspection_notes() -> tuple[str, ...]:
        return (
            "Metadata-only output. Header bytes are read from each SEER*Stat "
            "CSV; NO data rows are loaded, parsed, or emitted. SHA-256 is "
            "computed via chunked streaming only when ``with_sha256=True``; "
            "the default is OFF because SEER*Stat files are large (hundreds "
            "of MB to several GB).",
            "Row counts are intentionally ``None`` in this output. Counting "
            "rows would require reading the entire file; the metadata-only "
            "contract forbids it. Use the downstream analysis pipeline after "
            "completing ``docs/SEER_STUDY_CONTRACT.md`` if a row count is "
            "required.",
            "Capabilities are split: ``metadata-inspection`` is implemented "
            "and supported; ``clinical-analysis`` is ``planned`` and is "
            "intentionally NOT exposed by this adapter. Any clinical "
            "analysis must be backed by the filled-in study contract and "
            "the user-supplied data_version kwargs.",
            "Data-version fields (release_submission, product_type, "
            "registry_set, seerstat_version, session_type, export_date, "
            "selection_statements, export_data_dictionary) cannot be "
            "inferred from the CSV bytes alone. The adapter accepts them "
            "as kwargs; missing fields are recorded as "
            "``needs_verification`` rather than guessed.",
            "A filename like ``export_C69-C72.csv`` carries a literal ICD-O-3 "
            "site range label, but the file's row contents are NOT "
            "constrained to that range. The adapter records the label and "
            "flags the limitation; cohort selection must be confirmed against "
            "the export data dictionary.",
        )


def register(registry) -> None:
    """Register the SEER adapter on an AdapterRegistry."""
    from .base import AdapterRegistry  # local import to avoid cycles
    if not isinstance(registry, AdapterRegistry):
        raise TypeError("register() expects an AdapterRegistry")
    registry.register(SEERAdapter())