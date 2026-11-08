"""Unit tests for host connectivity parser and tester."""

from pathlib import Path
from netauto.transport.mock_transport import MockTransport
from netauto.utils.command_runner import CommandResult
from netauto.validation.connectivity import ConnectivityTester


def test_connectivity_ping_success():
    """Verify ping parser detects successful transmission, packet loss 0%, and RTT."""
    transport = MockTransport()
    txt = Path("tests/fixtures/ping_success.txt").read_text(encoding="utf-8")

    transport.register_command_response(
        "host1", "ping -c 3 -W 5 172.16.12.10",
        CommandResult(command=[], exit_code=0, stdout=txt, stderr="")
    )

    tester = ConnectivityTester(transport)
    res = tester.test_pair("host1", "host2", "172.16.12.10")

    assert res.success is True
    assert res.packets_transmitted == 3
    assert res.packets_received == 3
    assert res.packet_loss_pct == 0.0
    assert res.avg_rtt_ms == 0.435


def test_connectivity_ping_failure():
    """Verify ping parser detects 100% packet loss and marks success as False."""
    transport = MockTransport()
    txt = Path("tests/fixtures/ping_fail.txt").read_text(encoding="utf-8")

    transport.register_command_response(
        "host1", "ping -c 3 -W 5 172.16.12.10",
        CommandResult(command=[], exit_code=1, stdout=txt, stderr="")
    )

    tester = ConnectivityTester(transport)
    res = tester.test_pair("host1", "host2", "172.16.12.10")

    assert res.success is False
    assert res.packets_transmitted == 3
    assert res.packets_received == 0
    assert res.packet_loss_pct == 100.0
