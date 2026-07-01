#!/usr/bin/env python
"""Metadata-only inspection of a local SEER*Stat export directory.

This script is a thin CLI wrapper around
``neurosurg_epi_agent.adapters.SEERAdapter.inspect``. It writes a JSON
inspection report and refuses to read or write any case row. It is
deliberately separated from the main ``neurosurg-epi`` CLI so that the
public entry point to the SEER adapter is also a one-file script that
reviewers can audit end-to-end.

Usage:

    python scripts/inspect_seer_exports.py \\
        --data-root <local-seer-directory> \\
        --output manifests/seer_inspection.json

The script never reads participant data and never writes a file outside
the path passed in via ``--output``. The local directory referenced by
``--data-root`` is read-only; nothing inside it is modified.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make the in-tree package importable when run as a script.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from neurosurg_epi_agent.adapters import SEERAdapter  # noqa: E402


def parse_data_version_args(items: list[str]) -> dict[str, str]:
    """Parse ``--data-version key=value`` items into a dict."""
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(
                f"--data-version expects key=value, got {item!r}"
            )
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--data-root", required=True,
        help="Local SEER*Stat export directory. Read-only; never modified.",
    )
    p.add_argument(
        "--output", required=True,
        help="Path to write the metadata-only JSON inspection report.",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    p.add_argument(
        "--with-sha256", action="store_true",
        help="Stream a SHA-256 over every file's bytes. Off by default.",
    )
    p.add_argument(
        "--sha256-max-bytes", type=int, default=8 * 1024 * 1024 * 1024,
        help="Hard upper bound on bytes hashed per file. Default 8 GiB.",
    )
    p.add_argument(
        "--data-version", nargs="*", default=[],
        help="Optional key=value pairs: release_submission, product_type, "
             "registry_set, seerstat_version, session_type, export_date, "
             "selection_statements, export_data_dictionary. Missing fields "
             "are recorded as needs_verification rather than guessed.",
    )
    args = p.parse_args()

    out_path = Path(args.output)
    if out_path.exists() and not args.force:
        print(
            f"ERROR: output already exists; refusing to overwrite without "
            f"--force: {out_path}",
            file=sys.stderr,
        )
        return 2
    if not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)

    data_version = parse_data_version_args(args.data_version)
    adapter = SEERAdapter()
    try:
        result = adapter.inspect(
            Path(args.data_root),
            with_sha256=args.with_sha256,
            sha256_max_bytes=args.sha256_max_bytes,
            data_version=data_version or None,
        )
    except Exception as exc:
        print(
            f"ERROR: inspection failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    payload = result.to_dict()
    # Strip any absolute path that may have leaked in via the env vars a
    # caller might have set (defense in depth: the adapter already enforces
    # the token, this is a final scrub).
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    text = text.replace(os.environ.get("NEUROSURG_EPI_SEER_ROOT", ""), "<user-supplied>")
    payload = json.loads(text)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")

    print(f"wrote SEER metadata -> {out_path}")
    print(
        f"database={payload['database']} "
        f"direct_files={len(payload['direct_files'])} "
        f"skipped={len(payload['skipped_roots'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())