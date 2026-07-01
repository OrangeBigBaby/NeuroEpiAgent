"""Default adapter registry tests.

These do NOT require pandas (CHARLS imports pandas lazily, only when an
inspection actually parses a Stata file), so they run in the minimal install.
"""

from __future__ import annotations

import pytest

from neurosurg_epi_agent.adapters import (
    ADAPTER_VERSION,
    AdapterError,
    AdapterRegistry,
    CDCWonderAdapter,
    CHARLSAdapter,
    DatabaseAdapter,
    NHANESAdapter,
    SEERAdapter,
    default_registry,
    get_default,
)


def test_default_registry_contains_all_builtin_adapters():
    registry = default_registry()
    assert registry.names() == ["CDC_WONDER", "CHARLS", "NHANES", "SEER"]
    assert isinstance(registry.get("CDC_WONDER"), CDCWonderAdapter)
    assert isinstance(registry.get("CHARLS"), CHARLSAdapter)
    assert isinstance(registry.get("NHANES"), NHANESAdapter)
    assert isinstance(registry.get("SEER"), SEERAdapter)


def test_default_registry_is_fresh_each_call():
    a = default_registry()
    b = default_registry()
    assert a is not b
    assert a.get("CHARLS") is not b.get("CHARLS")


def test_get_default_lookup():
    assert get_default("NHANES").identity.database == "NHANES"
    assert get_default("CHARLS").identity.database == "CHARLS"
    assert get_default("CDC_WONDER").identity.database == "CDC_WONDER"
    assert get_default("SEER").identity.database == "SEER"


def test_registry_unknown_database_raises():
    registry = default_registry()
    with pytest.raises(AdapterError):
        registry.get("UNKNOWN")


def test_registry_double_register_raises():
    registry = AdapterRegistry()
    registry.register(NHANESAdapter())
    with pytest.raises(AdapterError):
        registry.register(NHANESAdapter())


def test_adapters_satisfy_protocol():
    # runtime_checkable protocol: every adapter exposes `identity` + `inspect`.
    for adapter in (NHANESAdapter(), CHARLSAdapter(), CDCWonderAdapter(), SEERAdapter()):
        assert isinstance(adapter, DatabaseAdapter)


def test_adapter_version_present():
    assert isinstance(ADAPTER_VERSION, str) and ADAPTER_VERSION


def test_identity_cards_are_metadata_only():
    for adapter in (NHANESAdapter(), CHARLSAdapter(), CDCWonderAdapter(), SEERAdapter()):
        ident = adapter.identity
        assert ident.database
        assert ident.label
        assert ident.version
        assert "metadata-inspection" in ident.capabilities
