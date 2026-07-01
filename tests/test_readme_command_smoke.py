"""Smoke tests for the public CLI commands documented in README.md.

The README is the contract for the public command surface. These tests prove
that every documented subcommand is wired up (parses, exists) and that
``inspect-database`` works end-to-end for the CSV-backed adapters on synthetic
data. They use no network and no real research data.

The route / plan / validate-plan / manifest commands are exercised individually
in ``tests/test_cli.py``; this file covers the command *surface* (nothing
removed/renamed) plus the metadata-inspection commands over synthetic inputs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from neurosurg_epi_agent.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]

# Every subcommand documented in README.md / the CLI docstring.
DOCUMENTED_SUBCOMMANDS = [
    "route",
    "validate-plan",
    "manifest",
    "plan",
    "evaluate",
    "run-pilot",
    "efficiency-summary",
    "inspect-database",
]


class TestSubcommandSurface:
    @pytest.mark.parametrize("subcmd", DOCUMENTED_SUBCOMMANDS)
    def test_subcommand_responds_to_help(self, subcmd):
        # `--help` must exit 0 for every documented subcommand; this catches a
        # command being removed/renamed without a README update.
        proc = subprocess.run(
            [sys.executable, "-m", "neurosurg_epi_agent.cli", subcmd, "--help"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert proc.returncode == 0, f"{subcmd} --help failed:\n{proc.stderr}"
        assert "usage:" in proc.stdout.lower()


class TestInspectDatabaseAllShippedAdapters:
    """The README documents `inspect-database`; exercise it for the CSV-backed
    adapters (CDC WONDER + SEER) over synthetic data. CHARLS/NHANES require
    Stata/XPT fixtures covered by their own adapter tests."""

    def test_inspect_database_cdc_wonder_smoke(self, tmp_path):
        # Minimal WONDER-shaped CSV so the adapter recognizes it.
        csv = tmp_path / "wonder.csv"
        csv.write_text(
            '"Notes","Year","Year Code",Deaths,Population\n'
            ',"2018","2018",200,300000000\n'
            '"---"\n'
            '"Dataset: Underlying Cause of Death, 2018-2024"\n'
            '"Query Parameters:"\n'
            '"Group By: Year"\n'
            "Caveats:\n"
            '"1. synthetic."\n',
            encoding="utf-8",
        )
        out = tmp_path / "out.json"
        rc = cli_main([
            "inspect-database", "--database", "CDC_WONDER",
            "--data-root", str(csv), "--output", str(out),
        ])
        assert rc == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["data_root"] == "<user-supplied>"

    def test_inspect_database_seer_smoke(self, tmp_path):
        csv = tmp_path / "export_C69-C72.csv"
        csv.write_text(
            '"Year of diagnosis","Sex","Primary Site"\n', encoding="utf-8"
        )
        out = tmp_path / "out.json"
        rc = cli_main([
            "inspect-database", "--database", "SEER",
            "--data-root", str(csv), "--output", str(out),
        ])
        assert rc == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["direct_files"][0]["member_path"] == "export_C69-C72.csv"
