"""Equal-Cost Multi-Path (ECMP) validation engine."""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from netauto.transport.base import Transport
from netauto.utils.logging import setup_logger

logger = setup_logger("netauto.validation.ecmp")


@dataclass
class EcmpPrefixResult:
    """ECMP inspection result for a single prefix on a leaf router."""
    prefix: str
    installed_next_hops: List[str]
    expected_paths: int = 2
    is_ecmp_active: bool = False
    bgp_multipath: bool = False
    kernel_multipath: bool = False
    details: str = ""


@dataclass
class LeafEcmpHealth:
    """Aggregated ECMP health for a specific Leaf router."""
    router_name: str
    prefix_results: Dict[str, EcmpPrefixResult]
    all_ecmp_passed: bool
    status: str  # "PASS", "FAIL", "DEGRADED"
    details: str


class EcmpValidator:
    """Validates BGP Control Plane and Linux Forwarding Plane ECMP multipath."""

    def __init__(self, transport: Transport):
        self.transport = transport

    def validate_leaf(
        self,
        leaf_name: str,
        remote_server_subnets: List[str],
        expected_paths: int = 2,
    ) -> LeafEcmpHealth:
        """Validate ECMP for all remote server subnets on a leaf router.

        Args:
            leaf_name: Name of the leaf router (e.g., 'leaf1').
            remote_server_subnets: List of subnets of other leafs (e.g. ['172.16.12.0/24', ...]).
            expected_paths: Expected number of equal-cost paths (default 2).

        Returns:
            LeafEcmpHealth evaluation.
        """
        results: Dict[str, EcmpPrefixResult] = {}
        passed_count = 0

        for prefix in remote_server_subnets:
            res = self._check_prefix_ecmp(leaf_name, prefix, expected_paths)
            results[prefix] = res
            if res.is_ecmp_active:
                passed_count += 1

        total = len(remote_server_subnets)
        all_passed = (passed_count == total) and total > 0

        if all_passed:
            status = "PASS"
            details = f"All {total} remote subnets have {expected_paths} equal-cost next hops installed."
        elif passed_count == 0:
            status = "FAIL"
            details = f"ECMP failed for all remote subnets ({passed_count}/{total} healthy)."
        else:
            status = "DEGRADED"
            details = (
                f"ECMP degraded: only {passed_count}/{total} remote subnets have full "
                f"{expected_paths} multipath redundancy."
            )

        return LeafEcmpHealth(
            router_name=leaf_name,
            prefix_results=results,
            all_ecmp_passed=all_passed,
            status=status,
            details=details,
        )

    def _check_prefix_ecmp(
        self,
        leaf_name: str,
        prefix: str,
        expected_paths: int,
    ) -> EcmpPrefixResult:
        """Check BGP and kernel multipath for a single prefix."""
        # 1. Check FRR routing table for prefix next-hops
        vtysh_cmd = f"show ip route {prefix} json"
        res = self.transport.execute_vtysh(leaf_name, vtysh_cmd)

        next_hops: List[str] = []
        bgp_multipath = False

        if res.success and res.stdout:
            try:
                data = json.loads(res.stdout)
                routes = data.get(prefix, [])
                if isinstance(routes, dict):
                    routes = [routes]

                for r in routes:
                    if isinstance(r, dict):
                        nh_list = r.get("nexthops", [])
                        for nh in nh_list:
                            if isinstance(nh, dict):
                                ip = nh.get("ip")
                                if ip and ip not in next_hops:
                                    next_hops.append(ip)
                        if len(nh_list) >= expected_paths:
                            bgp_multipath = True
            except Exception as exc:
                logger.warning("Error parsing 'show ip route %s json': %s", prefix, exc)

        # 2. Check Linux kernel forwarding table
        kernel_cmd = f"ip -4 route show {prefix}"
        k_res = self.transport.execute_command(leaf_name, kernel_cmd)
        kernel_next_hops: List[str] = []
        kernel_multipath = False

        if k_res.success and k_res.stdout:
            # Parse 'nexthop via X.X.X.X' or multiple lines
            for line in k_res.stdout.splitlines():
                line = line.strip()
                if "nexthop via" in line:
                    parts = line.split()
                    idx = parts.index("via")
                    if idx + 1 < len(parts):
                        nh_ip = parts[idx + 1]
                        if nh_ip not in kernel_next_hops:
                            kernel_next_hops.append(nh_ip)
                elif "via" in line and not line.startswith("nexthop"):
                    parts = line.split()
                    idx = parts.index("via")
                    if idx + 1 < len(parts):
                        nh_ip = parts[idx + 1]
                        if nh_ip not in kernel_next_hops:
                            kernel_next_hops.append(nh_ip)

            kernel_multipath = len(kernel_next_hops) >= expected_paths

        # Merge discovered next hops
        final_next_hops = next_hops or kernel_next_hops
        is_ecmp = (len(final_next_hops) >= expected_paths)

        if is_ecmp:
            details = f"Installed {len(final_next_hops)} paths via: {', '.join(final_next_hops)}"
        elif len(final_next_hops) == 1:
            details = f"DEGRADED: Only 1 path installed ({final_next_hops[0]}); redundancy lost!"
        else:
            details = "FAILED: No path installed for prefix."

        return EcmpPrefixResult(
            prefix=prefix,
            installed_next_hops=final_next_hops,
            expected_paths=expected_paths,
            is_ecmp_active=is_ecmp,
            bgp_multipath=bgp_multipath or is_ecmp,
            kernel_multipath=kernel_multipath or is_ecmp,
            details=details,
        )
