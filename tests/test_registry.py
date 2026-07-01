from pathlib import Path

import pytest

from neurosurg_epi_agent.registry import (
    RegistryError,
    load_database_registry,
    load_databases,
    load_variable_registry,
    unverified,
)

CONFIG = Path(__file__).resolve().parents[1] / "config"
DBS = CONFIG / "databases.yaml"
VARS = CONFIG / "variables" / "nhanes_demo.yaml"


def test_load_databases_has_nhanes_supported():
    dbs = load_databases(DBS)
    assert "NHANES" in dbs
    assert dbs["NHANES"].status.value == "supported"
    # planned adapters are present but not supported
    assert dbs["SEER"].status.value == "planned"
    assert dbs["GBD"].status.value == "planned"
    assert dbs["CHARLS"].status.value == "planned"


def test_load_database_registry_named():
    nh = load_database_registry(DBS, name="NHANES")
    assert nh.survey_design is not None
    assert nh.survey_design.id_var == "SDMVPSU"
    assert nh.survey_design.weight_var == "WTMEC2YR"


def test_load_database_registry_unknown_name():
    with pytest.raises(RegistryError):
        load_database_registry(DBS, name="NOPE")


def test_load_variable_registry_all_have_status():
    vs = load_variable_registry(VARS)
    assert len(vs) > 0
    assert all(v.status is not None for v in vs)
    # the demo file intentionally ships verified, illustrative, AND needs-review
    statuses = {v.status.value for v in vs}
    assert {"verified", "illustrative", "needs review"} <= statuses


def test_unverified_excludes_verified_only():
    vs = load_variable_registry(VARS)
    bad = unverified(vs)
    names = {v.name for v in bad}
    assert "age" not in names            # verified
    assert "tbi_history" in names        # needs review
    assert "bmi" in names                # illustrative


def test_duplicate_source_variable_rejected(tmp_path):
    p = tmp_path / "vars.yaml"
    p.write_text(
        'registry_version: "1"\n'
        'variables:\n'
        '  - {name: a, label: A, source_variable: LBXTC, source_module: LAB, status: illustrative}\n'
        '  - {name: b, label: B, source_variable: LBXTC, source_module: LAB, status: illustrative}\n',
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="duplicate source_variable"):
        load_variable_registry(p)


def test_missing_status_rejected(tmp_path):
    p = tmp_path / "vars.yaml"
    p.write_text(
        'registry_version: "1"\n'
        'variables:\n'
        '  - {name: a, label: A, source_variable: LBXTC, source_module: LAB}\n',
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="missing explicit 'status'"):
        load_variable_registry(p)


def test_bad_version_rejected(tmp_path):
    p = tmp_path / "vars.yaml"
    p.write_text(
        'registry_version: "999"\n'
        'variables: []\n',
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="unsupported"):
        load_variable_registry(p)
