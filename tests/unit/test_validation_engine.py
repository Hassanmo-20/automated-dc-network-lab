"""Unit tests for the central ValidationEngine orchestration and state evaluation."""

import json
from pathlib import Path
import pytest
from netauto.inventory.loader import load_raw_inventory
from netauto.inventory.validator import validate_and_build_inventory
from netauto.transport.mock_transport import MockTransport
from netauto.utils.command_runner import CommandResult
from netauto.validation.engine import ValidationEngine


@pytest.fixture
def fabric_inventory():
    raw = load_raw_inventory("inventory/fabric.yml")
    return validate_and_build_inventory(raw)


def test_validation_engine_all_pass(fabric_inventory):
    """Test ValidationEngine returns PASS when all components are healthy."""
    transport = MockTransport(available=True)
    nodes = [r.name for r in fabric_inventory.routers] + [s.name for s in fabric_inventory.servers]
    transport.online_nodes = nodes

    # Register OSPF responses
    spine_ospf = Path("tests/fixtures/ospf_spine_show_neighbor.json").read_text(encoding="utf-8")
    leaf_ospf = Path("tests/fixtures/ospf_leaf_show_neighbor.json").read_text(encoding="utf-8")
    for r in fabric_inventory.routers:
        resp = spine_ospf if r.role == "spine" else leaf_ospf
        transport.register_vtysh_response(r.name, "show ip ospf neighbor json", CommandResult([], 0, resp, ""))

    # Register BGP responses
    spine_bgp = Path("tests/fixtures/bgp_spine_summary.json").read_text(encoding="utf-8")
    leaf_bgp = Path("tests/fixtures/bgp_leaf_summary.json").read_text(encoding="utf-8")
    for r in fabric_inventory.routers:
        resp = spine_bgp if r.role == "spine" else leaf_bgp
        transport.register_vtysh_response(r.name, "show bgp ipv4 unicast summary json", CommandResult([], 0, resp, ""))

    # Register Routing table responses (with full ECMP for all 4 subnets)
    route_json = Path("tests/fixtures/frr_leaf_route_ecmp.json").read_text(encoding="utf-8")
    for r in fabric_inventory.routers:
        transport.register_vtysh_response(r.name, "show ip route json", CommandResult([], 0, route_json, ""))
        for sub in ["172.16.11.0/24", "172.16.12.0/24", "172.16.13.0/24", "172.16.14.0/24"]:
            transport.register_vtysh_response(
                r.name, f"show ip route {sub} json", CommandResult([], 0, route_json, "")
            )

    # Register ping responses
    ping_txt = Path("tests/fixtures/ping_success.txt").read_text(encoding="utf-8")
    for s in fabric_inventory.servers:
        for target in ["172.16.11.10", "172.16.12.10", "172.16.13.10", "172.16.14.10"]:
            transport.register_command_response(
                s.name, f"ping -c 3 -W 5 {target}", CommandResult([], 0, ping_txt, "")
            )

    engine = ValidationEngine(transport, fabric_inventory)
    report = engine.run_all_checks()

    assert report.overall_status == "PASS"
    assert report.container_health.status == "PASS"
    assert len(report.failures) == 0


def test_validation_engine_ecmp_degradation(fabric_inventory):
    """Test that losing multi-path redundancy flags failure and is detected."""
    transport = MockTransport(available=True)
    transport.online_nodes = [r.name for r in fabric_inventory.routers] + [s.name for s in fabric_inventory.servers]

    # Healthy OSPF & BGP
    spine_ospf = Path("tests/fixtures/ospf_spine_show_neighbor.json").read_text(encoding="utf-8")
    leaf_ospf = Path("tests/fixtures/ospf_leaf_show_neighbor.json").read_text(encoding="utf-8")
    for r in fabric_inventory.routers:
        resp = spine_ospf if r.role == "spine" else leaf_ospf
        transport.register_vtysh_response(r.name, "show ip ospf neighbor json", CommandResult([], 0, resp, ""))

    spine_bgp = Path("tests/fixtures/bgp_spine_summary.json").read_text(encoding="utf-8")
    leaf_bgp = Path("tests/fixtures/bgp_leaf_summary.json").read_text(encoding="utf-8")
    for r in fabric_inventory.routers:
        resp = spine_bgp if r.role == "spine" else leaf_bgp
        transport.register_vtysh_response(r.name, "show bgp ipv4 unicast summary json", CommandResult([], 0, resp, ""))

    # Single path installed on leafs
    single_path_json = Path("tests/fixtures/frr_leaf_route_single_path.json").read_text(encoding="utf-8")
    for r in fabric_inventory.routers:
        transport.register_vtysh_response(r.name, "show ip route json", CommandResult([], 0, single_path_json, ""))
        for sub in ["172.16.11.0/24", "172.16.12.0/24", "172.16.13.0/24", "172.16.14.0/24"]:
            transport.register_vtysh_response(
                r.name, f"show ip route {sub} json", CommandResult([], 0, single_path_json, "")
            )

    # Ping passes (failover still works!)
    ping_txt = Path("tests/fixtures/ping_success.txt").read_text(encoding="utf-8")
    for s in fabric_inventory.servers:
        for target in ["172.16.11.10", "172.16.12.10", "172.16.13.10", "172.16.14.10"]:
            transport.register_command_response(
                s.name, f"ping -c 3 -W 5 {target}", CommandResult([], 0, ping_txt, "")
            )

    engine = ValidationEngine(transport, fabric_inventory)
    report = engine.run_all_checks()

    assert report.overall_status in ("FAIL", "DEGRADED")
    assert any("ECMP" in f.protocol for f in report.failures)


def test_validation_engine_missing_container(fabric_inventory):
    """Test that a missing container causes overall FAIL."""
    transport = MockTransport(available=True)
    # spine1 is missing!
    transport.online_nodes = [
        r.name for r in fabric_inventory.routers if r.name != "spine1"
    ] + [s.name for s in fabric_inventory.servers]

    engine = ValidationEngine(transport, fabric_inventory)
    report = engine.run_all_checks()

    assert report.overall_status == "FAIL"
    assert report.container_health.status == "FAIL"
    assert "spine1" in report.container_health.missing_nodes
