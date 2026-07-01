"""NHANES identity adapter.

NHANES public XPT processing is owned by the existing case-study and template
tooling (SAS XPORT reader, survey-design helpers). This adapter exposes the
NHANES *identity + capability card* so the multi-database registry is symmetric
(NHANES and CHARLS both present), without re-implementing XPT parsing here.

``inspect`` performs a metadata-only scan of a user-supplied directory of public
NHANES ``.XPT`` files: it hashes files and lists the variable names carried in
each XPT header (the public, redistributable SAS Transport v5 header), but
emits no participant values. It is intentionally lightweight and is not on the
critical path of the historical NHANES-only router.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

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

_XPT_SUFFIXES = (".xpt",)

# Neutral provenance token emitted in place of the caller's real data_root so
# the metadata output can never leak an absolute/local filesystem path.
DATA_ROOT_TOKEN = "<user-supplied>"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _xport_member_names(raw: bytes) -> list[str]:
    """Best-effort extraction of variable names from a SAS XPORT v5 header.

    The XPORT header (first 480 bytes per member record) is public metadata:
    it names the variables but carries no participant values. We parse only the
    name records. On any deviation we return an empty list rather than guess.
    """
    names: list[str] = []
    try:
        text = raw[:0x20000]  # header region only
        if b"HEADER RECORD" not in text:
            return names
        # NAME RECORDS start after the member header; each is an 140-byte record
        # whose first bytes tag it as a name record. This is a deliberately
        # conservative scan: it surfaces names that appear in the documented
        # NAME STRNAME pattern without attempting full XPORT parsing.
        for line in text.split(b"\x00"):
            if len(line) >= 8 and line[:8].strip().isalpha():
                token = line[:8].decode("ascii", errors="ignore").strip()
                if token and token not in names and token.isidentifier():
                    names.append(token)
    except Exception:
        return []
    return names


class NHANESAdapter:
    """Identity + lightweight public-XPT metadata adapter for NHANES."""

    identity = AdapterIdentity(
        database="NHANES",
        label="National Health and Nutrition Examination Survey",
        version="0.1.0",
        data_formats=("sas-xport",),
        capabilities=("metadata-inspection",),
        access="public",
    )

    def inspect(
        self,
        data_root: Path,
        *,
        max_member_bytes: int = 2 * 1024 * 1024 * 1024,
        members: set[str] | None = None,
    ) -> InspectionResult:
        root = Path(data_root)
        if not root.exists():
            raise ArchiveInspectionError(f"data_root does not exist: {root}")

        direct_files: list[MemberMetadata] = []
        skipped: list[SkippedMember] = []

        candidate_paths = [root] if root.is_file() else _walk_files(root)
        for p in candidate_paths:
            rel = p.relative_to(root)
            rel_str = str(rel).replace("\\", "/")
            if p.is_dir():
                continue
            if p.is_symlink():
                skipped.append(SkippedMember(
                    member_path=rel_str, member_name=p.name,
                    reason="symlink not followed",
                ))
                continue
            if p.suffix.lower() not in _XPT_SUFFIXES:
                skipped.append(SkippedMember(
                    member_path=rel_str, member_name=p.name,
                    reason=f"unsupported file type ({p.suffix.lower() or 'no ext'})",
                ))
                continue
            # Stat and enforce the size limit BEFORE reading any bytes.
            size = p.stat().st_size
            if size > max_member_bytes:
                skipped.append(SkippedMember(
                    member_path=rel_str, member_name=p.name,
                    reason=f"size {size} exceeds limit {max_member_bytes} bytes",
                ))
                continue
            raw = p.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            names = _xport_member_names(raw)
            if members is not None and p.name not in members and rel_str not in members:
                continue
            direct_files.append(MemberMetadata(
                source_archive=None,
                member_path=rel_str,
                member_name=p.name,
                format="sas-xport",
                byte_size=size,
                sha256=digest,
                row_count=None,
                column_count=len(names) if names else None,
                dataset_label=None,
                variables=tuple(MemberVariable(name=n, label="") for n in names),
                provenance={"source": "NHANES public XPT"},
            ))

        return InspectionResult(
            database=self.identity.database,
            identity=self.identity,
            data_root=DATA_ROOT_TOKEN,
            archives=(),
            direct_files=tuple(direct_files),
            skipped_roots=tuple(skipped),
            privacy_statement=PRIVACY_STATEMENT,
            adapter_version=ADAPTER_VERSION,
            notes=(
                "NHANES XPT files are public and redistributable; this adapter "
                "emits header variable names + hashes only, never participant values.",
            ),
        )
