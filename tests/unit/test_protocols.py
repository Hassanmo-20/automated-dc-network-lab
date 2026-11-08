"""Unit tests for OSPF and BGP parser and inspector logic."""

from pathlib import Path
from netauto.protocols.bgp import BgpInspector
from netauto.protocols.ospf import OspfInspector
from netauto.transport.mock_transport import MockTransport
from netauto.utils.command_runner import CommandResult


def test_ospf_spine_parsing():
    """Verify OSPF parser correctly parses 4 FULL neighbors on Spine."""
    transport = MockTransport()
    json_path = Path("tests/fixtures/ospf_spine_show_neighbor.json")
    json_text = json_path.read_text(encoding="utf-8")

    transport.register_vtysh_response(
        "spine1", "show ip ospf neighbor json",
        CommandResult(command=[], exit_code=0, stdout=json_text, stderr="")
    )

    inspector = OspfInspector(transport)
    health = inspector.inspect_router("spine1", expected_neighbor_count=4)

    assert health.status == "PASS"
    assert health.all_full is True
    assert len(health.neighbors) == 4
    assert all(n.is_full for n in health.neighbors)


def test_ospf_leaf_degraded_parsing():
    """Verify OSPF parser flags 1/2 neighbors as DEGRADED."""
    transport = MockTransport()
    json_path = Path("tests/fixtures/ospf_degraded_show_neighbor.json")
    json_text = json_path.read_text(encoding="utf-8")

    transport.register_vtysh_response(
        "leaf1", "show ip ospf neighbor json",
        CommandResult(command=[], exit_code=0, stdout=json_text, stderr="")
    )

    inspector = OspfInspector(transport)
    health = inspector.inspect_router("leaf1", expected_neighbor_count=2)

    assert health.status == "DEGRADED"
    assert health.all_full is False
    assert len([n for n in health.neighbors if n.is_full]) == 1


def test_bgp_spine_summary_parsing():
    """Verify BGP parser correctly identifies 4 Established peers on Spine."""
    transport = MockTransport()
    json_path = Path("tests/fixtures/bgp_spine_summary.json")
    json_text = json_path.read_text(encoding="utf-8")

    transport.register_vtysh_response(
        "spine1", "show bgp ipv4 unicast summary json",
        CommandResult(command=[], exit_code=0, stdout=json_text, stderr="")
    )

    inspector = BgpInspector(transport)
    health = inspector.inspect_router("spine1", expected_peer_count=4)

    assert health.status == "PASS"
    assert health.all_established is True
    assert len(health.peers) == 4
    assert health.local_as == 65000


def test_bgp_leaf_failed_peer():
    """Verify BGP parser flags non-established peer as DEGRADED or FAIL."""
    transport = MockTransport()
    json_path = Path("tests/fixtures/bgp_failed_summary.json")
    json_text = json_path.read_text(encoding="utf-8")

    transport.register_vtysh_response(
        "leaf1", "show bgp ipv4 unicast summary json",
        CommandResult(command=[], exit_code=0, stdout=json_text, stderr="")
    )

    inspector = BgpInspector(transport)
    health = inspector.inspect_router("leaf1", expected_peer_count=2)

    assert health.status == "DEGRADED"
    assert health.all_established is False
    assert len([p for p in health.peers if p.is_established]) == 1
