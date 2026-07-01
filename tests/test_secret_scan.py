"""Tests for the tracked-tree secret / absolute-path scanner.

The scanner (``scripts/scan_tracked_secrets.py``) is the security gate invoked by
``.github/workflows/tests.yml``. It must:

1. Pass on the real tracked tree (no self-trigger, no false positives on the
   repository's own policy / example prose).
2. Reject a forged secret planted in a temp tree.
3. Ignore bare keyword mentions in prose and obvious placeholder values.
4. Honour the exact-path allowlist for legitimate policy docs.

These properties are asserted with fully synthetic temp files — no real
credential is ever materialised, only well-known *shapes* (``ghp_…``, ``AKIA…``)
that are publicly documented token formats.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Make scripts/ importable without an editable install.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import scan_tracked_secrets as sts  # noqa: E402


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


class TestDetectorLogic:
    def test_github_token_shape_caught(self, tmp_path):
        f = _write(tmp_path / "a.txt", "export GH=ghp_" + "a" * 36 + "\n")
        findings = sts.scan_paths([f], allowlist=[], root=None)
        rules = {x.rule for x in findings}
        assert "github_token" in rules

    def test_aws_key_shape_caught(self, tmp_path):
        f = _write(tmp_path / "a.env", "aws=AKIAIOSFODNN7EXAMPLE\n")
        findings = sts.scan_paths([f], allowlist=[], root=None)
        assert "aws_access_key_id" in {x.rule for x in findings}

    def test_local_absolute_path_caught(self, tmp_path):
        # Forward-slash form must also trip the rule.
        f = _write(tmp_path / "a.txt", "see E:/Nhance/SEERdatabase\n")
        findings = sts.scan_paths([f], allowlist=[], root=None)
        assert "local_absolute_path" in {x.rule for x in findings}

    def test_bare_keyword_in_prose_ignored(self, tmp_path):
        # Mentioning the keywords without an assignment is policy prose, not a
        # secret. This is the property that prevents self-trigger.
        f = _write(
            tmp_path / "notes.md",
            "We scan for api_key, password, and Bearer tokens in the tree.\n",
        )
        assert sts.scan_paths([f], allowlist=[], root=None) == []

    def test_placeholder_values_ignored(self, tmp_path):
        f = _write(
            tmp_path / "template.env",
            "API_KEY=<user-supplied>\nSECRET=your_key_here\nTOKEN=xxxxxxxx\n",
        )
        assert sts.scan_paths([f], allowlist=[], root=None) == []

    def test_binary_file_skipped(self, tmp_path):
        f = tmp_path / "blob.bin"
        f.write_bytes(b"\x00\x01ghp_" + b"a" * 40 + b"\x00")
        assert sts.scan_paths([f], allowlist=[], root=None) == []


class TestAllowlist:
    def test_allowlisted_relative_path_suppressed(self, tmp_path):
        # Simulate a repo layout: a policy doc under docs/ that quotes a path.
        repo = tmp_path
        (repo / "docs").mkdir()
        policy = _write(
            repo / "docs" / "POLICY.md",
            "Never commit E:/Nhance/SEERdatabase paths.\n",
        )
        rel = policy.relative_to(repo)
        findings = sts.scan_paths(
            [str(rel)], allowlist=[rel.as_posix()], root=repo
        )
        assert findings == []

    def test_non_allowlisted_path_still_flagged(self, tmp_path):
        repo = tmp_path
        bad = _write(repo / "leak.txt", "E:/Nhance/SEERdatabase\n")
        rel = bad.relative_to(repo)
        findings = sts.scan_paths([str(rel)], allowlist=[], root=repo)
        assert findings and findings[0].rule == "local_absolute_path"


class TestTrackedTreeClean:
    """The scanner must pass on the real repository tracked tree."""

    def test_tracked_tree_is_clean(self):
        if not (ROOT / ".git").exists():
            pytest.skip("not running inside the git repository checkout")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "scan_tracked_secrets.py"),
             "--root", str(ROOT)],
            capture_output=True, text=True,
        )
        # The clean-tree guarantee must hold on every contributor's machine and
        # in CI; a regression here is a release blocker.
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "clean" in proc.stdout
