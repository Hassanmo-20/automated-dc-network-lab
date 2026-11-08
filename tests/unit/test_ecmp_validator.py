"""Unit tests for ECMP multipath validation logic."""

from pathlib import Path
from netauto.transport.mock_transport import MockTransport
from netauto.utils.command_runner import CommandResult
from netauto.validation.ecmp import EcmpValidator


def test_ecmp_two_paths_pass():
    """Verify that 2 next-hops pass ECMP validation."""
    transport = MockTransport()
    json_path = Path("tests/fixtures/frr_leaf_route_ecmp.json")
    json_text = json_path.read_text(encoding="utf-8")

    transport.register_vtysh_response(
        "leaf1", "show ip route 172.16.12.0/24 json",
        CommandResult(command=[], exit_code=0, stdout=json_text, stderr="")
    )

    validator = EcmpValidator(transport)
    health = validator.validate_leaf("leaf1", ["172.16.12.0/24"], expected_paths=2)

    assert health.status == "PASS"
    assert health.all_ecmp_passed is True
    assert health.prefix_results["172.16.12.0/24"].is_ecmp_active is True
    assert len(health.prefix_results["172.16.12.0/24"].installed_next_hops) == 2


def test_ecmp_single_path_fails():
    """Verify that only 1 installed next-hop fails ECMP validation and is flagged as DEGRADED or FAIL."""
    transport = MockTransport()
    json_path = Path("tests/fixtures/frr_leaf_route_single_path.json")
    json_text = json_path.read_text(encoding="utf-8")

    transport.register_vtysh_response(
        "leaf1", "show ip route 172.16.12.0/24 json",
        CommandResult(command=[], exit_code=0, stdout=json_text, stderr="")
    )

    validator = EcmpValidator(transport)
    health = validator.validate_leaf("leaf1", ["172.16.12.0/24"], expected_paths=2)

    assert health.status in ("FAIL", "DEGRADED")
    assert health.all_ecmp_passed is False
    assert health.prefix_results["172.16.12.0/24"].is_ecmp_active is False
    assert len(health.prefix_results["172.16.12.0/24"].installed_next_hops) == 1
