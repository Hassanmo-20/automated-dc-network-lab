"""Integration tests against actual live Containerlab and FRRouting nodes.

These tests are marked with @pytest.mark.integration and require:
1. Docker daemon running
2. Containerlab installed and topology deployed (via 'python -m netauto up')
"""

import pytest
from netauto.deployment.docker import DockerManager
from netauto.inventory.loader import load_raw_inventory
from netauto.inventory.validator import validate_and_build_inventory
from netauto.protocols.bgp import BgpInspector
from netauto.protocols.ospf import OspfInspector
from netauto.transport.docker_exec import DockerExecTransport
from netauto.validation.connectivity import ConnectivityTester
from netauto.validation.ecmp import EcmpValidator


pytestmark = pytest.mark.integration


def is_live_environment_ready() -> bool:
    """Check if Docker is running and at least one lab container is discovered."""
    if not DockerManager.is_docker_available():
        return False
    transport = DockerExecTransport()
    return len(transport.list_nodes()) >= 10


@pytest.fixture(scope="module")
def fabric():
    """Load validated inventory and Docker transport for live tests."""
    if not is_live_environment_ready():
        pytest.skip(
            "Live lab environment is not running. Deploy with 'python -m netauto up' to run integration tests."
        )
    raw = load_raw_inventory("inventory/fabric.yml")
    inv = validate_and_build_inventory(raw)
    transport = DockerExecTransport(lab_name=inv.lab.name, prefix=inv.lab.prefix)
    return inv, transport


def test_integration_containers_running(fabric):
    """Verify all 10 nodes (6 routers + 4 hosts) are online in Docker."""
    inv, transport = fabric
    expected_nodes = [r.name for r in inv.routers] + [s.name for s in inv.servers]
    for node in expected_nodes:
        assert transport.is_node_ready(node), f"Container for node '{node}' is not running."


def test_integration_ospf_adjacencies_full(fabric):
    """Verify OSPF reaches FULL on all routers against live vtysh."""
    inv, transport = fabric
    inspector = OspfInspector(transport)

    for router in inv.routers:
        expected_neighbors = 4 if router.role == "spine" else 2
        health = inspector.inspect_router(router.name, expected_neighbor_count=expected_neighbors)
        assert health.status == "PASS", (
            f"OSPF failure on {router.name}: {health.details} (expected {expected_neighbors} FULL)"
        )


def test_integration_bgp_sessions_established(fabric):
    """Verify BGP sessions reach Established on all routers against live vtysh."""
    inv, transport = fabric
    inspector = BgpInspector(transport)

    for router in inv.routers:
        expected_peers = 4 if router.role == "spine" else 2
        health = inspector.inspect_router(router.name, expected_peer_count=expected_peers)
        assert health.status == "PASS", (
            f"BGP failure on {router.name}: {health.details} (expected {expected_peers} Established)"
        )


def test_integration_ecmp_installed_on_leafs(fabric):
    """Verify two equal-cost next hops are installed for all remote subnets on all Leafs."""
    inv, transport = fabric
    validator = EcmpValidator(transport)

    all_server_subnets = [r.server_subnet for r in inv.routers if r.role == "leaf" and r.server_subnet]

    for router in inv.routers:
        if router.role != "leaf":
            continue
        remotes = [p for p in all_server_subnets if p != router.server_subnet]
        health = validator.validate_leaf(router.name, remotes, expected_paths=2)
        assert health.status == "PASS", f"ECMP failure on {router.name}: {health.details}"


def test_integration_server_connectivity(fabric):
    """Verify end-to-end ping connectivity between all servers through the Clos fabric."""
    inv, transport = fabric
    tester = ConnectivityTester(transport)
    servers_info = [{"name": s.name, "ipv4": s.ipv4} for s in inv.servers]

    result = tester.test_full_mesh(servers_info, count=3)
    assert result.status == "PASS", f"Inter-server ping failed: {result.details}"
