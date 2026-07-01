#!/usr/bin/env python
"""Scan tracked files for accidental secrets and local absolute paths.

This is the security scanner invoked by ``.github/workflows/tests.yml``. It is
deliberately a standalone, importable module so its behaviour can be unit-tested.

Design choices that make the scan reliable (no self-trigger):

* The detector matches credential *assignments* (``api_key = "..."``) and
  well-known token *shapes* (GitHub ``ghp_…``, AWS ``AKIA…``, Slack ``xox…``,
  OpenAI ``sk-…``, Google ``AIza…``, PEM private-key headers), **not** bare
  keywords. A policy document, this very script, or a workflow file can mention
  ``api_key`` / ``Bearer`` in prose or rule definitions without tripping the
  scan, because there is no ``= <value>`` following the word.
* Obvious placeholder values (``<user-supplied>``, ``your_key``,
  ``EXAMPLE``, ``redacted``, ``…``, env-var references) are NOT treated as
  secrets, so example/env-template files pass.
* A precise **per-file allowlist of exact repo-relative paths** exempts files
  that legitimately show credential-shaped strings as policy text. There is no
  broad directory ignore (no ``docs/`` or ``.github/`` carve-out).

Absolute local paths (``E:\\Nhance``, ``C:\\Users``) are detected verbatim —
these are the workspace markers that must never leak into a tracked file.

Exit code: 0 if clean, 1 if any finding. The set of files scanned defaults to
``git ls-files`` of the repository root (tracked tree only — never the working
copy, which may contain ``.venv/`` / caches / local data).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# --------------------------------------------------------------------------- #
# Detection rules
# --------------------------------------------------------------------------- #

# Well-known, high-signal token shapes. These are unambiguous real secrets.
_TOKEN_SHAPES: tuple[tuple[str, str], ...] = (
    ("github_token", r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    ("aws_access_key_id", r"\bAKIA[0-9A-Z]{16}\b"),
    ("slack_token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ("openai_api_key", r"\bsk-[A-Za-z0-9]{20,}\b"),
    ("google_api_key", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ("stripe_key", r"\b(?:sk|pk|rk)_(?:live|test)_[0-9A-Za-z]{16,}\b"),
    ("private_key_block", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |)PRIVATE KEY-----"),
    ("bearer_token_value", r"\bBearer\s+[A-Za-z0-9._-]{20,}"),
)

# Credential *assignment*: ``keyword`` immediately followed by ``:``/``=`` and a
# non-placeholder value of decent length. ``api_key`` alone (no assignment) does
# NOT match — that is what prevents self-trigger on prose / rule definitions.
_CREDENTIAL_KEYWORDS = (
    r"api[_-]?key|apikey|secret|password|passwd|passphrase|"
    r"client[_-]?secret|access[_-]?token|auth[_-]?token|private[_-]?key|"
    r"aws[_-]?secret"
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    rf"(?i)(?:{_CREDENTIAL_KEYWORDS})\s*[:=]\s*"
    r"""['"]?([A-Za-z0-9._~+/=-]{12,})['"]?"""
)

# Values that are obviously placeholders, not real secrets.
_PLACEHOLDER_RE = re.compile(
    r"""(?ix)
    ^<
    | ^\$\{                       # ${VAR}
    | <[a-z][a-z0-9_-]*>$         # <user-supplied>
    | your[_-]?
    | example
    | xxxx
    | redacted
    | placeholder
    | change_?me
    | \.\.\.                      # literal ellipsis
    | ^n/?a$ | ^none$ | ^null$
    """,
)

# Absolute local paths that must never appear in a tracked file. Backslashes are
# literal in the file text; we match both ``E:\Nhance`` and ``E:/Nhance``.
_LOCAL_PATH_PATTERNS = (
    re.compile(r"E:[\\/]Nhance"),
    re.compile(r"C:[\\/]Users"),
)


@dataclass(frozen=True)
class Finding:
    path: str
    lineno: int
    rule: str
    snippet: str

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"{self.path}:{self.lineno}: {self.rule}: {self.snippet}"


# --------------------------------------------------------------------------- #
# Exact-file allowlist: files that legitimately contain policy / example text.
# No broad directory ignores — every entry is an explicit repo-relative path.
# --------------------------------------------------------------------------- #
DEFAULT_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Security-tooling source legitimately contains the detector patterns.
        "scripts/scan_tracked_secrets.py",
        "tests/test_secret_scan.py",
        # Policy / governance docs discuss these keywords as prose / examples.
        "docs/DATA_GOVERNANCE.md",
        "docs/DATA_PROVENANCE.md",
        "docs/REPOSITORY_RELEASE_CHECKLIST.md",
        "SECURITY.md",
    }
)


def _looks_binary(raw: bytes) -> bool:
    return b"\x00" in raw[:4096]


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _scan_text(text: str) -> list[tuple[int, str, str]]:
    """Return ``(1-based lineno, rule, snippet)`` findings within ``text``."""
    out: list[tuple[int, str, str]] = []
    lines = text.splitlines()

    for i, line in enumerate(lines, start=1):
        # Token-shape rules (unambiguous).
        for name, pat in _TOKEN_SHAPES:
            m = re.search(pat, line)
            if m:
                out.append((i, name, _snippet(line, m.start())))
        # Credential-assignment rule (with placeholder exclusion).
        for m in _CREDENTIAL_ASSIGNMENT.finditer(line):
            value = m.group(1)
            if _PLACEHOLDER_RE.search(value):
                continue
            out.append((i, "credential_assignment", _snippet(line, m.start())))
        # Local absolute paths.
        for pat in _LOCAL_PATH_PATTERNS:
            m = pat.search(line)
            if m:
                out.append((i, "local_absolute_path", _snippet(line, m.start())))
    return out


def _snippet(line: str, start: int, width: int = 60) -> str:
    s = line.strip()
    if len(s) <= width:
        return s
    # Centre the snippet on the match for readability.
    lo = max(0, start - width // 4)
    return (s[lo : lo + width]).strip()


def scan_file(path: Path) -> list[Finding]:
    """Scan a single file on disk. Returns findings (empty = clean)."""
    try:
        raw = path.read_bytes()
    except OSError:
        # Unreadable file is not a secret finding; CI size-check guards bloat.
        return []
    if _looks_binary(raw):
        return []
    text = _decode(raw)
    return [
        Finding(path=str(path), lineno=lineno, rule=rule, snippet=snippet)
        for lineno, rule, snippet in _scan_text(text)
    ]


def scan_paths(
    paths: Iterable[str | Path],
    *,
    allowlist: Iterable[str] = DEFAULT_ALLOWLIST,
    root: Path | None = None,
) -> list[Finding]:
    """Scan an iterable of paths, suppressing allowlisted repo-relative ones.

    ``allowlist`` is a set of repo-relative POSIX paths. For each input path the
    repo-relative form is computed (relative to ``root`` when given, else the
    path itself, POSIX-normalized) and matched exactly against the allowlist.
    The ``Finding.path`` carried in results is the repo-relative POSIX form so
    output is stable across platforms.
    """
    allow = {p.replace("\\", "/") for p in allowlist}
    root_resolved = root.resolve() if root is not None else None
    findings: list[Finding] = []
    for p in paths:
        abs_path = Path(p)
        if not abs_path.is_absolute() and root_resolved is not None:
            abs_path = root_resolved / abs_path
        rel_posix = _rel_posix(abs_path, root_resolved)
        if _is_allowlisted(rel_posix, allow):
            continue
        for lineno, rule, snippet in _scan_file_raw(abs_path):
            findings.append(
                Finding(path=rel_posix, lineno=lineno, rule=rule, snippet=snippet)
            )
    return findings


def _rel_posix(abs_path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return abs_path.resolve().relative_to(root).as_posix()
        except ValueError:
            pass
    return abs_path.as_posix()


def _scan_file_raw(path: Path) -> list[tuple[int, str, str]]:
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if _looks_binary(raw):
        return []
    return _scan_text(_decode(raw))


def _is_allowlisted(rel_path_posix: str, allow: set[str]) -> bool:
    if rel_path_posix in allow:
        return True
    # Also allow a leading "./" form.
    if rel_path_posix.startswith("./") and rel_path_posix[2:] in allow:
        return True
    return False


def git_tracked_files(repo_root: Path) -> list[str]:
    """Return tracked file paths (POSIX, repo-relative) via ``git ls-files``."""
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError(f"git ls-files failed in {repo_root}: {exc}") from exc
    return [line for line in out.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--root",
        default=".",
        help="Repository root used to resolve tracked files (default: cwd).",
    )
    p.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Explicit files to scan instead of `git ls-files` (used by tests).",
    )
    p.add_argument(
        "--allowlist",
        nargs="*",
        default=list(DEFAULT_ALLOWLIST),
        help="Exact repo-relative paths to exempt (in addition to the defaults).",
    )
    args = p.parse_args(argv)

    repo_root = Path(args.root).resolve()
    allow = set(args.allowlist) | set(DEFAULT_ALLOWLIST)

    if args.paths is not None:
        raw_paths = args.paths
    else:
        raw_paths = git_tracked_files(repo_root)

    findings = scan_paths(raw_paths, allowlist=allow, root=repo_root)
    if findings:
        print("ERROR: forbidden tokens / absolute paths found:")
        for f in findings:
            print(f"  {f}")
        return 1
    print("secret scan: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
