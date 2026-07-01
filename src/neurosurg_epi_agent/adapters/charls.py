"""CHARLS database adapter — metadata-only inspection of local Stata archives.

CHARLS (China Health and Retirement Longitudinal Study) distributes
participant-level data under a registration/data-use agreement. This adapter
inspects *authorized local* archives only and emits schema metadata — never
participant values. It is deliberately read-only and never persists extracted
files: ZIP members and direct ``.dta`` files are read into transient memory,
hashed, and their variable dictionaries + row/column counts extracted.

Security posture (see ``acceptance`` / tests):

* user-supplied ``data_root`` is required (no hard-coded licensed path);
* symlinked directories/files inside the root are not followed;
* ZIP member names are sanitized and rejected on path traversal
  (``..`` components, absolute paths, Windows drive letters);
* duplicate member names raise (ambiguous);
* encrypted members raise (cannot be inspected);
* members exceeding ``max_member_bytes`` are skipped (unbounded-read guard);
* malformed archives raise; individual member parse failures are skipped;
* archives and inspected members are SHA-256 hashed;
* pandas (used only for Stata ``.dta`` metadata) is imported lazily so the
  core package keeps its light dependency footprint.

Reading Stata ``.dta`` requires pandas. Install via the ``multidb`` (or
``case-study``) extra: ``pip install neurosurg-epi-agent[multidb]``.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .base import (
    ADAPTER_VERSION,
    AdapterIdentity,
    ArchiveInspectionError,
    ArchiveMetadata,
    DuplicateMemberError,
    EncryptedMemberError,
    InspectionResult,
    MalformedArchiveError,
    MemberMetadata,
    MemberSizeExceededError,
    MemberVariable,
    MissingDependencyError,
    PathTraversalError,
    PRIVACY_STATEMENT,
    SkippedMember,
    UnsupportedFormatError,
)

# Reasonable default: 2 GiB uncompressed per member. Overridable via the CLI.
DEFAULT_MAX_MEMBER_BYTES = 2 * 1024 * 1024 * 1024

# Neutral provenance token emitted in place of the caller's real data_root so
# the metadata output can never leak an absolute/local filesystem path.
DATA_ROOT_TOKEN = "<user-supplied>"

_DTA_SUFFIXES = (".dta",)
_ZIP_SUFFIXES = (".zip",)

# Matches a Windows drive prefix, e.g. "C:" or "c:\\".
_DRIVE_RE = re.compile(r"^[A-Za-z]:")

# Stata "version" byte used by pandas to read 118/119 files; we do not pin it.


def _require_pandas():
    """Import pandas lazily; raise a typed error if it is unavailable."""
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only without pandas
        raise MissingDependencyError(
            "CHARLS metadata inspection requires pandas. Install it with "
            "`pip install neurosurg-epi-agent[multidb]` (or `pip install pandas`)."
        ) from exc
    return pd


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_capped(stream, max_bytes: int, *, chunk_size: int = 1024 * 1024) -> bytes | None:
    """Read at most ``max_bytes + 1`` bytes; return ``None`` when over limit."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(min(chunk_size, max_bytes - total + 1))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            return None


def safe_member_path(member_name: str) -> str:
    """Return a sanitized, forward-slash relative member path.

    Raises :class:`PathTraversalError` if the name escapes its container
    (``..`` component, absolute POSIX path, or a Windows drive letter).

    Backslashes are normalized to forward slashes so Windows-style traversal
    (``..\\..\\evil``) is caught by the same component check.
    """
    if not member_name or not isinstance(member_name, str):
        raise PathTraversalError(f"empty/non-string member name: {member_name!r}")
    name = member_name.replace("\\", "/")
    if name.startswith("/"):
        raise PathTraversalError(f"absolute member path rejected: {member_name!r}")
    if _DRIVE_RE.match(member_name):
        raise PathTraversalError(f"drive-letter member path rejected: {member_name!r}")
    parts = name.split("/")
    if any(part == ".." for part in parts):
        raise PathTraversalError(f"traversal member path rejected: {member_name!r}")
    # Drop empty components (e.g. trailing or double slashes) but keep order.
    parts = [p for p in parts if p != ""]
    if not parts:
        raise PathTraversalError(f"empty member path after normalization: {member_name!r}")
    return "/".join(parts)


@dataclass(frozen=True)
class _WaveHint:
    wave: str | None = None
    year: str | None = None
    product: str | None = None  # "raw" | "harmonized"
    version: str | None = None


def infer_wave_provenance(rel_path: str, dataset_label: str | None) -> dict[str, str]:
    """Best-effort, conservative wave/product provenance from path + label.

    Only infers tokens that appear literally; never invents a wave or version.
    """
    blob = (rel_path + " " + (dataset_label or "")).lower()
    out: dict[str, str] = {}
    m = re.search(r"wave\s*([0-9])", blob)
    if m:
        out["wave"] = m.group(1)
    m = re.search(r"(20[0-9]{2})", blob)
    if m:
        out["year"] = m.group(1)
    if "harmonized" in blob:
        out["product"] = "harmonized"
        mv = re.search(r"ver\.?\s*([a-z])", blob) or re.search(r"version\s*([a-z])", blob)
        if mv:
            out["version"] = mv.group(1).upper()
    elif re.search(r"\bcharls\b", blob) and out.get("wave"):
        out["product"] = "raw"
    return out


class CHARLSAdapter:
    """Metadata-only adapter for local CHARLS ZIP/Stata archives."""

    identity = AdapterIdentity(
        database="CHARLS",
        label="China Health and Retirement Longitudinal Study",
        version="0.1.0",
        data_formats=("stata-dta", "zip"),
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
        max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
        members: set[str] | None = None,
    ) -> InspectionResult:
        """Inspect ``data_root`` and return metadata only.

        Args:
            data_root: User-supplied directory (or single file) to inspect.
            max_member_bytes: Skip members whose declared uncompressed size
                exceeds this (unbounded-read guard).
            members: Optional set of basenames/member-paths to restrict to.
        """
        root = Path(data_root)
        if not root.exists():
            raise ArchiveInspectionError(f"data_root does not exist: {root}")
        if max_member_bytes <= 0:
            raise ValueError("max_member_bytes must be positive")

        archives: list[ArchiveMetadata] = []
        direct_files: list[MemberMetadata] = []
        skipped_roots: list[SkippedMember] = []

        if root.is_file():
            self._inspect_single_file(
                root, root.parent, max_member_bytes, members,
                archives, direct_files, skipped_roots,
            )
        else:
            self._walk_root(
                root, max_member_bytes, members,
                archives, direct_files, skipped_roots,
            )

        return InspectionResult(
            database=self.identity.database,
            identity=self.identity,
            data_root=DATA_ROOT_TOKEN,
            archives=tuple(archives),
            direct_files=tuple(direct_files),
            skipped_roots=tuple(skipped_roots),
            privacy_statement=PRIVACY_STATEMENT,
            adapter_version=ADAPTER_VERSION,
            notes=self._inspection_notes(),
        )

    # ------------------------------------------------------------------ #
    # walking
    # ------------------------------------------------------------------ #

    def _walk_root(
        self, root: Path, max_member_bytes: int, members_filter: set[str] | None,
        archives: list, direct_files: list, skipped_roots: list,
    ) -> None:
        # followlinks=False is the default; we additionally skip symlinked
        # entries so a symlink pointing outside the requested root is never
        # traversed.
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Drop symlinked subdirectories in-place so os.walk does not descend.
            dirnames[:] = sorted(
                d for d in dirnames if not (Path(dirpath) / d).is_symlink()
            )
            for fname in sorted(filenames):
                fpath = Path(dirpath) / fname
                if fpath.is_symlink():
                    skipped_roots.append(SkippedMember(
                        member_path=str(fpath.relative_to(root)).replace("\\", "/"),
                        member_name=fname, reason="symlink not followed",
                    ))
                    continue
                self._inspect_single_file(
                    fpath, root, max_member_bytes, members_filter,
                    archives, direct_files, skipped_roots,
                )

    def _inspect_single_file(
        self, fpath: Path, root: Path, max_member_bytes: int,
        members_filter: set[str] | None,
        archives: list, direct_files: list, skipped_roots: list,
    ) -> None:
        suffix = fpath.suffix.lower()
        try:
            rel = fpath.relative_to(root)
        except ValueError:
            rel = fpath
        rel_str = str(rel).replace("\\", "/")

        if suffix in _ZIP_SUFFIXES:
            archives.append(
                self._inspect_zip(fpath, rel_str, max_member_bytes, members_filter)
            )
        elif suffix in _DTA_SUFFIXES:
            # Stat and enforce the size limit BEFORE reading any bytes, so an
            # oversized direct file is never fully loaded into memory.
            file_size = fpath.stat().st_size
            if file_size > max_member_bytes:
                skipped_roots.append(SkippedMember(
                    member_path=rel_str, member_name=fpath.name,
                    reason=(
                        f"file size {file_size} exceeds limit {max_member_bytes} "
                        "bytes; skipped before reading"
                    ),
                ))
            else:
                mm = self._extract_dta_metadata(
                    raw=fpath.read_bytes(),
                    rel_path=rel_str,
                    member_name=fpath.name,
                    source_archive=None,
                    max_member_bytes=max_member_bytes,
                    members_filter=members_filter,
                    skip_on_parse=True,
                    skipped_sink=skipped_roots,
                )
                if mm is not None:
                    direct_files.append(mm)
        else:
            skipped_roots.append(SkippedMember(
                member_path=rel_str, member_name=fpath.name,
                reason=f"unsupported file type ({suffix or 'no ext'})",
            ))

    # ------------------------------------------------------------------ #
    # ZIP inspection
    # ------------------------------------------------------------------ #

    def _inspect_zip(
        self, zip_path: Path, rel_path: str, max_member_bytes: int,
        members_filter: set[str] | None,
    ) -> ArchiveMetadata:
        archive_hash = sha256_file(zip_path)
        archive_size = zip_path.stat().st_size
        try:
            zf = zipfile.ZipFile(zip_path)
        except zipfile.BadZipFile as exc:
            raise MalformedArchiveError(
                f"malformed archive (not a valid ZIP): {rel_path} ({exc})"
            ) from exc

        members: list[MemberMetadata] = []
        skipped: list[SkippedMember] = []
        seen_safe_names: dict[str, int] = {}
        with zf:
            try:
                infos = zf.infolist()
            except zipfile.BadZipFile as exc:
                raise MalformedArchiveError(
                    f"malformed archive (unreadable central directory): {rel_path} ({exc})"
                ) from exc
            for zi in infos:
                if zi.is_dir():
                    continue
                try:
                    safe = safe_member_path(zi.filename)
                except PathTraversalError:
                    raise  # security: always propagate traversal
                # duplicate-member ambiguity (fail-closed)
                if safe in seen_safe_names:
                    raise DuplicateMemberError(
                        f"duplicate member name {safe!r} in archive {rel_path}; "
                        "refusing to silently hash an ambiguous member"
                    )
                seen_safe_names[safe] = 1

                base = safe.rsplit("/", 1)[-1]
                if members_filter is not None and not self._matches_filter(
                    safe, base, members_filter
                ):
                    continue
                if not safe.lower().endswith(_DTA_SUFFIXES):
                    skipped.append(SkippedMember(
                        member_path=safe, member_name=base,
                        reason="non-.dta member skipped",
                    ))
                    continue
                if zi.flag_bits & 0x1:
                    raise EncryptedMemberError(
                        f"encrypted member not inspectable: {rel_path}::{safe}"
                    )
                # Enforce the DECLARED uncompressed size before decompression.
                if zi.file_size > max_member_bytes:
                    skipped.append(SkippedMember(
                        member_path=safe, member_name=base,
                        reason=(
                            f"member uncompressed size {zi.file_size} exceeds "
                            f"limit {max_member_bytes} bytes; skipped"
                        ),
                    ))
                    continue
                try:
                    with zf.open(zi) as member_stream:
                        raw = _read_capped(member_stream, max_member_bytes)
                except (zipfile.BadZipFile, RuntimeError) as exc:
                    # RuntimeError covers encrypted/compression-mismatch members
                    # that slipped past the flag check; treat as malformed.
                    raise MalformedArchiveError(
                        f"malformed archive (unreadable member {safe!r} in "
                        f"{rel_path}): {exc}"
                    ) from exc
                if raw is None:
                    skipped.append(SkippedMember(
                        member_path=safe,
                        member_name=base,
                        reason=(
                            f"actual decompressed bytes exceed limit "
                            f"{max_member_bytes}; skipped"
                        ),
                    ))
                    continue
                mm = self._extract_dta_metadata(
                    raw=raw, rel_path=safe, member_name=base,
                    source_archive=rel_path, max_member_bytes=max_member_bytes,
                    members_filter=None, skip_on_parse=True,
                    skipped_sink=skipped,
                )
                if mm is not None:
                    members.append(mm)
        return ArchiveMetadata(
            archive_path=rel_path, sha256=archive_hash, byte_size=archive_size,
            members=tuple(members), skipped=tuple(skipped),
        )

    # ------------------------------------------------------------------ #
    # .dta metadata extraction
    # ------------------------------------------------------------------ #

    def _extract_dta_metadata(
        self, raw: bytes, rel_path: str, member_name: str,
        source_archive: str | None, max_member_bytes: int,
        members_filter: set[str] | None, skip_on_parse: bool,
        skipped_sink: list | None,
    ) -> MemberMetadata | None:
        # Enforce ACTUAL decompressed/read bytes (guards against a member whose
        # declared size was missing/understated). The declared-size guard for
        # archive members and the stat guard for direct files already ran above.
        if len(raw) > max_member_bytes:
            if skipped_sink is not None:
                skipped_sink.append(SkippedMember(
                    member_path=rel_path, member_name=member_name,
                    reason=(
                        f"actual bytes {len(raw)} exceed limit {max_member_bytes} "
                        "after read; skipped"
                    ),
                ))
                return None
            raise MemberSizeExceededError(
                f"member {rel_path} actual size {len(raw)} exceeds limit "
                f"{max_member_bytes}"
            )
        base = member_name
        if members_filter is not None and not self._matches_filter(
            rel_path, base, members_filter
        ):
            return None
        digest = sha256_bytes(raw)
        try:
            pd = _require_pandas()
            from pandas.io.stata import StataReader

            labels: dict[str, str] = {}
            dataset_label: str | None = None
            with StataReader(io.BytesIO(raw)) as reader:
                labels = reader.variable_labels()
                dataset_label = getattr(reader, "data_label", None)
            row_count = self._count_rows(pd, raw)
        except MissingDependencyError:
            raise
        except Exception as exc:
            if skip_on_parse and skipped_sink is not None:
                skipped_sink.append(SkippedMember(
                    member_path=rel_path, member_name=member_name,
                    reason=f"Stata parse failed: {type(exc).__name__}: {exc}",
                ))
                return None
            raise ArchiveInspectionError(
                f"failed to parse Stata member {rel_path}: {exc}"
            ) from exc

        variables = tuple(MemberVariable(name=n, label=(lab or "")) for n, lab in labels.items())
        prov = infer_wave_provenance(
            rel_path + " " + (source_archive or ""), dataset_label
        )
        if dataset_label:
            prov.setdefault("dataset_label", str(dataset_label))
        return MemberMetadata(
            source_archive=source_archive,
            member_path=rel_path,
            member_name=member_name,
            format="stata-dta",
            byte_size=len(raw),
            sha256=digest,
            row_count=row_count,
            column_count=len(labels),
            dataset_label=dataset_label,
            variables=variables,
            provenance=prov,
        )

    def _count_rows(self, pd, raw: bytes) -> int:
        """Stream-count rows without retaining participant values.

        ``read_stata(chunksize=...)`` yields chunk DataFrames transiently; we
        keep only their lengths. Row count is metadata, not a participant value.
        """
        total = 0
        for chunk in pd.read_stata(
            io.BytesIO(raw), chunksize=20000, convert_categoricals=False
        ):
            total += len(chunk)
            del chunk
        return total

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _matches_filter(safe_path: str, base: str, members_filter: set[str]) -> bool:
        if base in members_filter or safe_path in members_filter:
            return True
        return any(safe_path == m or base == m for m in members_filter)

    def _inspection_notes(self) -> tuple[str, ...]:
        return (
            "Adapter reads member bytes into transient memory only; no extracted "
            "files are written to disk.",
            "Variable dictionaries carry names + labels only. Value labels, value "
            "frequencies, and any participant/household identifier VALUES are never emitted.",
            "Wave/product provenance is inferred conservatively from path and dataset "
            "label tokens; confirm against the official CHARLS codebook before analysis.",
            "Row counts are obtained by streaming over the file in memory; no rows are retained.",
        )


def register(registry) -> None:
    """Register the CHARLS adapter on an AdapterRegistry."""
    from .base import AdapterRegistry  # local import to avoid cycles
    if not isinstance(registry, AdapterRegistry):
        raise TypeError("register() expects an AdapterRegistry")
    registry.register(CHARLSAdapter())
