"""Cross-layer version consistency.

The software package release version has ONE source of truth: the literal
``__version__`` in ``src/neurosurg_epi_agent/__init__.py``. ``pyproject.toml``
reads it dynamically (``setuptools dynamic`` + ``attr``), and ``CITATION.cff``
mirrors it for citation. These tests pin that chain so a bump in one place
cannot silently desync the others.

They deliberately do NOT require the adapter protocol version
(``adapters.base.ADAPTER_VERSION``) or the per-adapter implementation versions
(``<Adapter>.identity.version``) to equal the package release version — those
are distinct version axes (see the versioning-policy docstring in
``__init__.py``).
"""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import neurosurg_epi_agent

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RELEASE = "0.3.1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestSingleSourceOfTruth:
    def test_module_version_is_the_expected_release(self):
        assert neurosurg_epi_agent.__version__ == EXPECTED_RELEASE

    def test_pyproject_reads_version_dynamically_from_module(self):
        text = _read(ROOT / "pyproject.toml")
        # No hand-written literal version under [project] — it is dynamic.
        project_block = re.split(r"\n\[", text)[0]
        assert re.search(r'^version\s*=', project_block, re.MULTILINE) is None, (
            "pyproject [project] must not set a literal `version`; it must be "
            "dynamic so __init__.py stays the single source of truth."
        )
        assert 'dynamic = ["version"]' in text
        # The dynamic version must be resolved from the module literal.
        assert 'attr = "neurosurg_epi_agent.__version__"' in text, (
            "pyproject must read the version from "
            "neurosurg_epi_agent.__version__ via setuptools attr."
        )

    def test_citation_matches_module_version(self):
        text = _read(ROOT / "CITATION.cff")
        m = re.search(r'^version:\s*"([^"]+)"', text, re.MULTILINE)
        assert m, "CITATION.cff must declare a quoted version"
        assert m.group(1) == neurosurg_epi_agent.__version__
        assert m.group(1) == EXPECTED_RELEASE

    def test_distribution_metadata_matches_when_installed(self):
        # When the package is installed (the normal case in CI / `pip install -e`),
        # the distribution metadata must agree with the module literal. If the
        # distribution is not present (bare source checkout), skip rather than
        # fail — the pyproject/citation checks above already cover source-level
        # consistency.
        try:
            dist_version = importlib.metadata.version("neurosurg-epi-agent")
        except importlib.metadata.PackageNotFoundError:
            import pytest

            pytest.skip("neurosurg-epi-agent distribution not installed in this env")
        assert dist_version == neurosurg_epi_agent.__version__, (
            "stale install: run `pip install -e .` to rebuild distribution "
            "metadata from the current __version__"
        )

    def test_expected_release_constant_is_a_valid_tag(self):
        # Guard against typos in the EXPECTED_RELEASE target itself.
        assert re.fullmatch(r"\d+\.\d+\.\d+", EXPECTED_RELEASE)
