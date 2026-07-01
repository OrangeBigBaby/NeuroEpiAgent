"""CDC WONDER CSV adapter — metadata-only inspection of public aggregate exports.

CDC WONDER (Wide-ranging ONline Data for Epidemiologic Research) distributes
*public, aggregated* mortality/natality export CSVs (counts and rates; no
participant-level records). This adapter inspects user-downloaded WONDER export
directories and emits schema + provenance metadata: SHA-256 hashes, row/column
counts, the column list, and the query-parameter block WONDER embeds in every
export (dataset, cause, group-by, standard population, rate basis, query date,
and dataset version).

It follows the same metadata-only contract as the NHANES/CHARLS adapters:
read-only, never persists extracted files, never follows symlinks outside the
requested root, and emits a NEUTRAL ``<user-supplied>`` data_root token so the
metadata output can never leak an absolute/local filesystem path.

Even though WONDER exports do not carry participant-level records, the
aggregate cell values ARE subject to NCHS / CDC WONDER data-use restrictions
(per-query suppression of small counts, instability flags for small
denominators, and the Underlying vs Multiple Cause distinction). The adapter
explicitly propagates WONDER's own ``Notes`` column status (``Suppressed``,
``Unreliable``) verbatim and re-enforces the disclosure rules in code: it
never attempts to recover a suppressed count, never promotes an unstable
rate to a stable rate, and never compares UCD and MCD exports head-to-head
without flagging the case-selection difference.

Parsing uses only the stdlib ``csv`` module — no pandas dependency. WONDER's
export format is shared across its databases (Underlying Cause of Death, Multiple
Cause of Death, etc.): a header row, data rows, a ``"---"`` separator, a
"Query Parameters:" provenance block, and a "Caveats:" footer. The provenance
block lets the adapter record which WONDER database (UCD vs MCD), which ICD-10
cause was selected, and how results were grouped — without reading a single
death count into its output.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
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

_CSV_SUFFIXES = (".csv",)

# Neutral provenance token emitted in place of the caller's real data_root so
# the metadata output can never leak an absolute/local filesystem path.
DATA_ROOT_TOKEN = "<user-supplied>"

# WONDER writes a single-field "---" row between the data table and the
# provenance block, and again between provenance sub-sections.
_SEPARATOR = "---"
# Unquoted footer header that ends the provenance region.
_CAVEATS_HEADER = "Caveats:"

# The cause line key varies by the selection tab used ("ICD-10 113 Cause List",
# "ICD-10 Codes", "ICD-10 130 Cause List (Infants)", ...). We capture any
# provenance key whose key starts with this prefix and normalize it to "cause".
_CAUSE_KEY_PREFIX = "ICD-10"

# Provenance keys we capture from the "Query Parameters" block.
_KNOWN_PROVENANCE_KEYS = (
    "Dataset",
    "Group By",
    "Show Totals",
    "Show Zero Values",
    "Show Suppressed",
    "Standard Population",
    "Calculate Rates Per",
    "Rate Options",
    "Query Date",
    "Suggested Citation",
)

# Matches a "Key: Value" provenance line (key starts uppercase). Non-greedy on
# the key so the first ": " splits label from value (values may contain colons,
# e.g. "Query Date: Jul 1, 2026 11:05:05 AM").
_PROVENANCE_RE = re.compile(r"^([A-Z][A-Za-z0-9 ./()%\-]*?):\s+(.*)$")

# Substring tokens found inside the Notes column that flag a row as carrying
# restricted / disclosed values. WONDER writes these verbatim; the adapter
# passes them through and never tries to recover the underlying cell value.
_SUPPRESSED_TOKENS = ("Suppressed",)
_UNRELIABLE_TOKENS = ("Unreliable",)

# Disclosure threshold used when summarizing Notes over the inspected file.
# WONDER suppresses any cell with Deaths <= 9; rates with Deaths < 20 are
# flagged Unreliable. These are WONDER-defined policy values, reproduced here
# so downstream disclosure checks can be expressed in terms of them.
SUPPRESSED_MAX_DEATHS = 9
UNRELIABLE_MAX_DEATHS = 19

# Filename anomalies that we record in provenance but never silently rewrite.
# The local tree contains ``wonder_neuro_injury_us.csv.csv`` (a duplicated
# ``.csv`` suffix). Renaming would change SHA-256 of the source bytes; the
# adapter only flags it.
_FILENAME_ANOMALY_DOUBLE_CSV = ".csv.csv"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_files(root: Path) -> list[Path]:
    """Return real (non-symlinked) files under ``root`` in deterministic order.

    Symlinked directories are not descended into (``followlinks=False``) and
    symlinked files are excluded so a symlink pointing outside the requested
    root is never read.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames if not (Path(dirpath) / d).is_symlink()
        )
        for fname in sorted(filenames):
            p = Path(dirpath) / fname
            if not p.is_symlink():
                found.append(p)
    return found


def _decode(raw: bytes) -> str:
    """Decode WONDER CSV bytes. WONDER exports are ASCII/latin-1; try UTF-8
    (with optional BOM) first, then cp1252/latin-1 which never fail."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _is_wonder_export(rows: list[list[str]]) -> bool:
    """A WONDER export has a ``---`` separator row and a ``Dataset:`` row."""
    singles = [r[0].strip() for r in rows if len(r) == 1]
    has_sep = any(s == _SEPARATOR for s in singles)
    has_dataset = any(s.startswith("Dataset:") for s in singles)
    return has_sep and has_dataset


def _extract_provenance(rows: list[list[str]]) -> dict[str, str]:
    """Pull whitelisted "Key: Value" lines from the post-data provenance region.

    The region starts at the first ``---`` separator (after the data table) and
    ends at the ``Caveats:`` footer. ``---`` separators inside the region and
    non-whitelisted lines (e.g. "Help: See ...") are ignored.
    """
    prov: dict[str, str] = {}
    in_region = False
    for r in rows:
        field = r[0].strip() if len(r) == 1 else ""
        if not in_region:
            if field == _SEPARATOR:
                in_region = True
            continue
        if field == _CAVEATS_HEADER:
            break
        if field == _SEPARATOR or not field:
            continue
        m = _PROVENANCE_RE.match(field)
        if not m:
            continue
        key, value = m.group(1).strip(), m.group(2).strip()
        if key.startswith(_CAUSE_KEY_PREFIX):
            prov.setdefault("cause", value)
        elif key in _KNOWN_PROVENANCE_KEYS:
            store_key = key.lower().replace(" ", "_")
            prov.setdefault(store_key, value)
    return prov


def _extract_icd10_definition(prov: dict[str, str]) -> str:
    """Return the ICD-10 selection basis as WONDER recorded it.

    WONDER places the cause selection in ``provenance['cause']`` (the value
    after the ICD-10 list key). The list name itself — "ICD-10 113 Cause List",
    "ICD-10 Codes", etc. — defines which grouping of codes was selected.
    """
    return prov.get("cause", "")


def _extract_dataset_version(prov: dict[str, str]) -> str:
    """Return the WONDER dataset label (e.g. ``Underlying Cause of Death,
    2018-2024, Single Race``).

    The label is WONDER's own version identifier for the query result.
    """
    return prov.get("dataset", "")


def _scan_data_rows(
    columns: list[str],
    data_rows: list[list[str]],
) -> dict[str, object]:
    """Walk every data row once and summarize the WONDER-defined Notes statuses.

    The aggregate counts of suppressed / unreliable / unstable rows are the
    only numeric summary the adapter emits. No cell values are captured.
    """
    cols_lower = {c.lower(): c for c in columns}
    notes_col = cols_lower.get("notes")
    deaths_col = cols_lower.get("deaths")
    notes_idx = columns.index(notes_col) if notes_col in columns else -1
    deaths_idx = columns.index(deaths_col) if deaths_col in columns else -1

    suppressed = 0
    unreliable = 0
    deaths_lt_20 = 0
    notes_seen: dict[str, int] = {}

    for r in data_rows:
        if notes_idx >= 0 and notes_idx < len(r):
            note = r[notes_idx].strip()
        else:
            note = ""
        if not note:
            continue
        # Count distinct Notes phrasings without carrying the cell value into
        # the metadata output: only count + bucket.
        notes_seen[note] = notes_seen.get(note, 0) + 1
        # WONDER capitalizes the keywords; compare case-insensitively so
        # "suppressed" or "Suppressed" both count.
        low = note.lower()
        if any(tok.lower() in low for tok in _SUPPRESSED_TOKENS):
            suppressed += 1
        if any(tok.lower() in low for tok in _UNRELIABLE_TOKENS):
            unreliable += 1
        if deaths_idx >= 0 and deaths_idx < len(r):
            try:
                d = int(r[deaths_idx].strip() or "0")
            except ValueError:
                d = 0
            if d < UNRELIABLE_MAX_DEATHS + 1:  # Deaths < 20
                deaths_lt_20 += 1

    # `notes_seen` is a hashable count map of distinct WONDER-written phrases.
    # We sort keys deterministically; values are integer counts only.
    sorted_notes = {k: notes_seen[k] for k in sorted(notes_seen)}
    return {
        "suppressed_row_count": suppressed,
        "unreliable_row_count": unreliable,
        "deaths_lt_20_row_count": deaths_lt_20,
        "notes_phrases_seen": sorted_notes,
    }


def _enrich(
    columns: list[str],
    data_rows: list[list[str]],
    prov: dict[str, str],
    member_name: str,
) -> dict[str, str]:
    """Derive database family, year range, ICD-10 definition, dataset version,
    measures-present, and disclosure-relevant counts from parsed bits."""
    out: dict[str, str] = {}
    ds = _extract_dataset_version(prov)
    if ds:
        out["dataset_version"] = ds
    if "Multiple Cause" in ds:
        out["database_family"] = "MCD"
    elif "Underlying Cause" in ds:
        out["database_family"] = "UCD"
    icd = _extract_icd10_definition(prov)
    if icd:
        out["icd10_definition"] = icd
    if "Group By" in prov or "group_by" in prov:
        out["group_by"] = prov.get("Group By", prov.get("group_by", ""))
    if "Standard Population" in prov or "standard_population" in prov:
        out["standard_population"] = prov.get(
            "Standard Population", prov.get("standard_population", "")
        )
    if "Calculate Rates Per" in prov or "calculate_rates_per" in prov:
        out["rate_basis"] = prov.get(
            "Calculate Rates Per", prov.get("calculate_rates_per", "")
        )
    if "Query Date" in prov or "query_date" in prov:
        out["query_date"] = prov.get("Query Date", prov.get("query_date", ""))
    if "Year" in columns:
        yi = columns.index("Year")
        years = [r[yi].strip() for r in data_rows if yi < len(r) and r[yi].strip()]
        if years:
            out["years"] = f"{min(years)}-{max(years)}"
    cols_lower = {c.lower(): c for c in columns}
    measures = [
        cols_lower[m]
        for m in ("deaths", "population", "crude rate", "age adjusted rate")
        if m in cols_lower
    ]
    if measures:
        out["measures"] = ", ".join(measures)
    # Filename anomalies (e.g. double ``.csv`` suffix) — flagged, never
    # auto-corrected (would change SHA-256 of the source).
    if member_name.lower().endswith(_FILENAME_ANOMALY_DOUBLE_CSV):
        out["filename_note"] = (
            "Filename ends with '.csv.csv' (likely download artifact); "
            "renaming would change SHA-256 of source bytes — preserved as-is."
        )
    return out


def parse_wonder_csv(raw: bytes, member_name: str = "") -> dict:
    """Parse a WONDER export into metadata (no cell values retained).

    Returns a dict with: ``columns`` (list[str]), ``row_count`` (int, data rows
    only — excludes header, separator, provenance, caveats), ``provenance``
    (dict[str,str]), ``disclosure_summary`` (dict with row counts of
    suppressed / unreliable / Deaths<20 rows and the distinct WONDER-written
    Notes phrases encountered; only counts and bucketed phrases, never cell
    values), and ``recognized`` (bool — False for a .csv lacking the WONDER
    ``---``/``Dataset:`` markers).
    """
    text = _decode(raw)
    rows = [r for r in csv.reader(io.StringIO(text)) if r != []]
    recognized = _is_wonder_export(rows)
    if not rows:
        return {
            "columns": [],
            "row_count": 0,
            "provenance": {},
            "disclosure_summary": {
                "suppressed_row_count": 0,
                "unreliable_row_count": 0,
                "deaths_lt_20_row_count": 0,
                "notes_phrases_seen": {},
            },
            "recognized": recognized,
        }

    columns = [c.strip() for c in rows[0]]
    # Data rows run from row 1 until the first "---" separator.
    data_rows: list[list[str]] = []
    for r in rows[1:]:
        if len(r) >= 1 and r[0].strip() == _SEPARATOR:
            break
        data_rows.append(r)

    prov = _extract_provenance(rows)
    prov.update(_enrich(columns, data_rows, prov, member_name))
    disclosure = _scan_data_rows(columns, data_rows)
    return {
        "columns": columns,
        "row_count": len(data_rows),
        "provenance": prov,
        "disclosure_summary": disclosure,
        "recognized": recognized,
    }


class CDCWonderAdapter:
    """Metadata-only adapter for local CDC WONDER export CSVs."""

    identity = AdapterIdentity(
        database="CDC_WONDER",
        label="CDC WONDER public aggregate mortality/natality exports",
        version="0.3.0",
        data_formats=("csv",),
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
        """Inspect ``data_root`` and return metadata only.

        Args:
            data_root: User-supplied directory (or single file) of WONDER CSVs.
            max_member_bytes: Skip CSVs larger than this before reading.
            members: Optional set of basenames/relative paths to restrict to.
        """
        root = Path(data_root)
        if not root.exists():
            raise ArchiveInspectionError(f"data_root does not exist: {root}")

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
            # Stat and enforce the size limit BEFORE reading any bytes.
            size = p.stat().st_size
            if size > max_member_bytes:
                skipped.append(SkippedMember(
                    member_path=rel_str, member_name=p.name,
                    reason=f"size {size} exceeds limit {max_member_bytes} bytes",
                ))
                continue
            if members is not None and p.name not in members and rel_str not in members:
                continue

            raw = p.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            parsed = parse_wonder_csv(raw, member_name=p.name)
            columns = parsed["columns"]
            prov = dict(parsed["provenance"])
            prov["source"] = "CDC WONDER public aggregate CSV"
            prov["recognized"] = "true" if parsed["recognized"] else "false"
            prov["disclosure_policy"] = (
                "WONDER suppresses Deaths<=9 (Suppressed) and flags rates with "
                "Deaths<20 as Unreliable. These statuses are propagated verbatim "
                "and never recovered or normalized away."
            )
            # Flatten the disclosure summary into provenance so it ships with the
            # member metadata (which is the only public surface). Only counts
            # and bucketed Notes phrases — no cell values.
            disclosure = parsed["disclosure_summary"]
            prov["suppressed_row_count"] = str(disclosure["suppressed_row_count"])
            prov["unreliable_row_count"] = str(disclosure["unreliable_row_count"])
            prov["deaths_lt_20_row_count"] = str(disclosure["deaths_lt_20_row_count"])
            # Carry the distinct WONDER Notes phrases as a JSON-style list so
            # downstream disclosure checks can match them exactly without
            # rebuilding them from scratch.
            prov["notes_phrases"] = ",".join(sorted(disclosure["notes_phrases_seen"]))

            direct_files.append(MemberMetadata(
                source_archive=None,
                member_path=rel_str,
                member_name=p.name,
                format="wonder-csv",
                byte_size=size,
                sha256=digest,
                row_count=parsed["row_count"],
                column_count=len(columns) if columns else None,
                dataset_label=prov.get("dataset_version") or prov.get("dataset"),
                variables=tuple(MemberVariable(name=c, label="") for c in columns),
                provenance=prov,
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
                "CDC WONDER exports are public aggregated counts/rates (no "
                "participant-level records). This adapter emits schema + the "
                "embedded Query Parameters provenance (dataset, ICD-10 "
                "selection, group-by, standard population, rate basis, query "
                "date) and row/column counts. Aggregate cell values are not "
                "retained in this inventory.",
                "Disclosure guardrails: the adapter never attempts to "
                "recover a Suppressed count, never normalizes an Unreliable "
                "rate to a stable one, and never compares Underlying-Cause "
                "(UCD) and Multiple-Cause (MCD) exports head-to-head without "
                "flagging the case-selection difference. WONDER's ``Notes`` "
                "column status (Suppressed / Unreliable / unstable) is "
                "propagated verbatim.",
                "Parsing is stdlib csv only (no pandas). "
                "``provenance['recognized']`` flags any .csv lacking the "
                "WONDER '---'/Dataset: markers.",
                "``provenance['database_family']`` distinguishes UCD "
                "(Underlying Cause) from MCD (Multiple Cause) exports. "
                "``provenance['icd10_definition']``, ``provenance['group_by']``, "
                "``provenance['standard_population']``, ``provenance['rate_basis']``, "
                "``provenance['query_date']``, and ``provenance['dataset_version']`` "
                "are captured individually so any public aggregate derived "
                "downstream can cite them.",
                "``member_metadata['provenance']['filename_note']`` records "
                "filename anomalies (e.g. '.csv.csv') without rewriting the "
                "source file. SHA-256 is computed on the bytes as-stored on "
                "the user's machine; renaming would change the hash.",
            ),
        )


def register(registry) -> None:
    """Register the CDC WONDER adapter on an AdapterRegistry."""
    from .base import AdapterRegistry  # local import to avoid cycles
    if not isinstance(registry, AdapterRegistry):
        raise TypeError("register() expects an AdapterRegistry")
    registry.register(CDCWonderAdapter())