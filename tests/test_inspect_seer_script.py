"""Subprocess tests for scripts/inspect_seer_exports.py — synthetic data only.

The SEER inspection entry point must run as a real script (not just via the
package API) and must never corrupt its JSON output or leak an absolute path.
These tests drive it end-to-end as a subprocess over a fully synthetic CSV
directory; the real SEER*Stat exports are never touched.

Covers the original bug: ``text.replace(os.environ.get(ROOT, ""), token)``
corrupted the JSON when the env var was unset (``""`` replace inserts the token
between every character), raising ``JSONDecodeError``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inspect_seer_exports.py"

# Minimal SEER-shaped synthetic header (quoted, comma-safe). No data rows.
_SYNTHETIC_HEADER = '"Year of diagnosis","Sex","Primary Site"'
_SYNTHETIC_ROW = '"2018","Female","C71.0"'


def _make_seer_dir(tmp_path: Path, *, filename: str = "export_C69-C72.csv",
                   rows: int = 0) -> Path:
    d = tmp_path / "seer_root"
    d.mkdir()
    lines = [_SYNTHETIC_HEADER] + [_SYNTHETIC_ROW] * rows
    (d / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


def _run(data_root: Path, output: Path, *, env_root: str | None,
         extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "NEUROSURG_EPI_SEER_ROOT"}
    if env_root is not None:
        env["NEUROSURG_EPI_SEER_ROOT"] = env_root
    return subprocess.run(
        [sys.executable, str(SCRIPT),
         "--data-root", str(data_root),
         "--output", str(output),
         *(extra_args or [])],
        capture_output=True, text=True, env=env,
    )


class TestEnvVarHandling:
    def test_env_unset_succeeds_and_emits_valid_json(self, tmp_path):
        # The original bug: unset env -> "" replace -> JSONDecodeError.
        data_root = _make_seer_dir(tmp_path)
        out = tmp_path / "out.json"
        proc = _run(data_root, out, env_root=None)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        payload = json.loads(out.read_text(encoding="utf-8"))  # must reparse
        assert payload["data_root"] == "<user-supplied>"
        assert len(payload["direct_files"]) == 1

    def test_env_empty_string_succeeds(self, tmp_path):
        # Empty-string env var must behave like unset (no "" replace).
        data_root = _make_seer_dir(tmp_path)
        out = tmp_path / "out.json"
        proc = _run(data_root, out, env_root="")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        json.loads(out.read_text(encoding="utf-8"))  # reparses cleanly

    def test_env_set_to_data_root_scrubs_absolute_path(self, tmp_path):
        data_root = _make_seer_dir(tmp_path)
        out = tmp_path / "out.json"
        proc = _run(data_root, out, env_root=str(data_root))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        text = out.read_text(encoding="utf-8")
        # The literal absolute path must not appear anywhere in the output.
        assert str(data_root) not in text
        assert str(data_root).replace("\\", "/") not in text
        assert "<user-supplied>" in text
        # JSON is still valid after the scrub.
        json.loads(text)

    def test_chinese_filename_preserved(self, tmp_path):
        data_root = _make_seer_dir(
            tmp_path, filename="export_C15-C26消化器官恶性肿瘤.csv"
        )
        out = tmp_path / "out.json"
        proc = _run(data_root, out, env_root=None)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["direct_files"][0]["member_name"].endswith(
            "消化器官恶性肿瘤.csv"
        )


class TestOutputHandling:
    def test_existing_output_refused_without_force(self, tmp_path):
        data_root = _make_seer_dir(tmp_path)
        out = tmp_path / "out.json"
        out.write_text("{}", encoding="utf-8")  # pre-existing
        proc = _run(data_root, out, env_root=None)
        assert proc.returncode == 2  # refused
        # Original content untouched.
        assert out.read_text(encoding="utf-8") == "{}"

    def test_existing_output_overwritten_with_force(self, tmp_path):
        data_root = _make_seer_dir(tmp_path)
        out = tmp_path / "out.json"
        out.write_text("{}", encoding="utf-8")
        proc = _run(data_root, out, env_root=None, extra_args=["--force"])
        assert proc.returncode == 0, proc.stdout + proc.stderr
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["database"] == "SEER"

    def test_output_is_reparseable_and_has_no_absolute_paths(self, tmp_path):
        data_root = _make_seer_dir(tmp_path, rows=3)
        out = tmp_path / "deep" / "out.json"
        proc = _run(data_root, out, env_root=None)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        # (6) reparseable
        payload = json.loads(out.read_text(encoding="utf-8"))
        # (7) no absolute path, and no synthetic data-row value leaked.
        text = out.read_text(encoding="utf-8")
        assert str(data_root) not in text
        assert "C71.0" not in text  # a planted data-row value
        assert "Female" not in text
        # Member path is relative, not absolute.
        assert payload["direct_files"][0]["member_path"] == "export_C69-C72.csv"
