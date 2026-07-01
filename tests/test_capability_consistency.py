"""Cross-layer capability consistency.

The capability model documented in README.md / docs/ROADMAP.md /
config/databases.yaml must agree with what the code actually does. These tests
pin that agreement so a future edit to one layer cannot silently desync
another.

The model (see docs/ROADMAP.md and the README capability matrix):

| Capability                | NHANES | CDC WONDER | SEER | CHARLS |
| Deterministic routing     | supported | n/a       | planned/infeasible | planned/infeasible |
| Planning adapter          | supported | supported | planned/not supported | planned/not supported |
| Metadata inspection       | supported | supported | supported | supported |
| Clinical analysis         | light case study | not in repo | not implemented | not in repo |

The router only knows NHANES / CHARLS / GBD / SEER (CDC WONDER is a public
aggregate, not a routing target).
"""

from __future__ import annotations

import yaml

from neurosurg_epi_agent.adapters import default_registry
from neurosurg_epi_agent.adapters.seer import SEERAdapter
from neurosurg_epi_agent.router import route
from neurosurg_epi_agent.schemas import DatabaseStatus

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestRouterCapabilityModel:
    def test_nhanes_is_the_only_supported_routing_target(self):
        # NHANES questions that pass capability checks route feasibly.
        d = route("What is the NHANES prevalence of stroke?")
        assert d.database == "NHANES"
        assert d.status is DatabaseStatus.SUPPORTED

    def test_seer_explicit_is_planned_and_infeasible(self):
        d = route("Use SEER registry data for glioblastoma survival.")
        assert d.database == "SEER"
        assert d.status is DatabaseStatus.PLANNED
        assert d.feasible is False

    def test_charls_and_gbd_are_also_planned(self):
        assert route("Use GBD for regional tumor burden.").status is DatabaseStatus.PLANNED
        # CHARLS routes via the concussion/cognitive specialized intent.
        assert route("CHARLS cognitive trajectory in older adults.").status is DatabaseStatus.PLANNED


class TestAdapterCapabilityCards:
    def test_every_registered_adapter_advertises_metadata_inspection(self):
        reg = default_registry()
        for name in reg.names():
            caps = reg.get(name).identity.capabilities
            assert "metadata-inspection" in caps, f"{name} missing metadata-inspection"

    def test_no_adapter_advertises_clinical_analysis(self):
        # Clinical-analysis execution is not implemented for ANY database in
        # this release; it must not appear in any adapter's capability tuple.
        reg = default_registry()
        for name in reg.names():
            caps = reg.get(name).identity.capabilities
            assert not any("clinical" in c.lower() for c in caps), (
                f"{name} must not advertise a clinical capability"
            )

    def test_seer_identity_is_metadata_only(self):
        caps = SEERAdapter().identity.capabilities
        assert caps == ("metadata-inspection",)


class TestConfigCapabilityModel:
    def test_databases_yaml_status_matches_router_for_shared_databases(self):
        """`status` in config/databases.yaml must agree with router status for
        the databases the router knows about (NHANES supported; SEER/CHARLS/GBD
        planned). CDC WONDER is not a router target."""
        with (ROOT / "config" / "databases.yaml").open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        statuses = {name: entry["status"] for name, entry in cfg["databases"].items()}
        assert statuses["NHANES"] == "supported"
        # SEER/CHARLS/GBD are planned routing targets.
        for db in ("SEER", "CHARLS", "GBD"):
            assert statuses[db] == "planned", f"{db} should be planned in config"

    def test_databases_yaml_documents_seer_metadata_inspection(self):
        # config notes must reflect that SEER metadata inspection is implemented
        # even though routing/planning stay planned.
        text = (ROOT / "config" / "databases.yaml").read_text(encoding="utf-8")
        assert "metadata_inspection: implemented" in text or "metadata-only" in text.lower()
