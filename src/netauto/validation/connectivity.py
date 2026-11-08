"""End-to-End server connectivity verification engine."""

import re
from dataclasses import dataclass, field
from typing import Dict, List
from netauto.transport.base import Transport
from netauto.utils.logging import setup_logger

logger = setup_logger("netauto.validation.connectivity")


@dataclass
class PingResult:
    """Result of a ping test between two server containers."""
    source_host: str
    destination_host: str
    destination_ip: str
    packets_transmitted: int
    packets_received: int
    packet_loss_pct: float
    avg_rtt_ms: Optional[float]
    success: bool
    raw_output: str


@dataclass
class ConnectivityMatrixResult:
    """Aggregate result of connectivity tests across all server pairs."""
    results: List[PingResult] = field(default_factory=list)
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    status: str = "PASS"  # "PASS", "FAIL", "DEGRADED"
    details: str = ""


class ConnectivityTester:
    """Verifies reachability between server containers in the fabric."""

    def __init__(self, transport: Transport):
        self.transport = transport

    def test_pair(
        self,
        src_host: str,
        dst_host: str,
        dst_ip: str,
        count: int = 3,
        timeout: int = 5,
    ) -> PingResult:
        """Execute a ping from src_host to dst_ip."""
        cmd = f"ping -c {count} -W {timeout} {dst_ip}"
        res = self.transport.execute_command(src_host, cmd, timeout=timeout + 2)

        tx = count
        rx = 0
        loss = 100.0
        avg_rtt = None
        success = False

        if res.stdout:
            # Parse packets: e.g. "3 packets transmitted, 3 received, 0% packet loss"
            match_pkts = re.search(r"(\d+)\s+packets\s+transmitted,\s+(\d+)\s+(?:packets\s+)?received", res.stdout)
            if match_pkts:
                tx = int(match_pkts.group(1))
                rx = int(match_pkts.group(2))

            match_loss = re.search(r"(\d+(?:\.\d+)?)%\s+packet\s+loss", res.stdout)
            if match_loss:
                loss = float(match_loss.group(1))

            # Parse rtt: e.g. "rtt min/avg/max/mdev = 0.421/0.654/0.891/0.180 ms"
            match_rtt = re.search(r"=\s*[\d\.]+/([\d\.]+)/[\d\.]+", res.stdout)
            if match_rtt:
                avg_rtt = float(match_rtt.group(1))

            success = (rx > 0) and (loss < 100.0)

        return PingResult(
            source_host=src_host,
            destination_host=dst_host,
            destination_ip=dst_ip,
            packets_transmitted=tx,
            packets_received=rx,
            packet_loss_pct=loss,
            avg_rtt_ms=avg_rtt,
            success=success,
            raw_output=res.stdout or res.stderr,
        )

    def test_full_mesh(
        self,
        servers: List[Dict[str, str]],
        count: int = 3,
    ) -> ConnectivityMatrixResult:
        """Run connectivity tests between all ordered pairs of servers.

        Args:
            servers: List of server dictionaries containing 'name' and 'ipv4' (e.g., '172.16.11.10/24').
            count: Number of ping packets per test.

        Returns:
            ConnectivityMatrixResult
        """
        results: List[PingResult] = []
        passed = 0

        for src in servers:
            src_name = src["name"]
            for dst in servers:
                dst_name = dst["name"]
                if src_name == dst_name:
                    continue

                dst_ip = dst["ipv4"].split("/")[0]
                res = self.test_pair(src_name, dst_name, dst_ip, count=count)
                results.append(res)
                if res.success:
                    passed += 1

        total = len(results)
        failed = total - passed

        if total == 0:
            status = "FAIL"
            details = "No server pairs tested."
        elif passed == total:
            status = "PASS"
            details = f"All {total} inter-server connectivity tests passed with 0% packet loss."
        elif passed == 0:
            status = "FAIL"
            details = f"All {total} connectivity tests failed."
        else:
            status = "DEGRADED"
            details = f"Partial connectivity: {passed}/{total} tests succeeded ({failed} failed)."

        return ConnectivityMatrixResult(
            results=results,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            status=status,
            details=details,
        )
