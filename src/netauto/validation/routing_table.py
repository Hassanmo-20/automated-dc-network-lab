"""Routing table inspection and validation."""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from netauto.transport.base import Transport
from netauto.utils.logging import setup_logger

logger = setup_logger("netauto.validation.routing_table")


@dataclass
class RouteEntry:
    """Represents an installed route in the routing table."""
    prefix: str
    protocol: str  # "bgp", "ospf", "connected", "kernel", etc.
    next_hops: List[str]
    metric: int = 0
    raw: Dict = field(default_factory=dict)


@dataclass
class RouterRoutingHealth:
    """Evaluation of a router's routing table."""
    router_name: str
    routes: Dict[str, RouteEntry]
    expected_prefixes: List[str]
    missing_prefixes: List[str]
    status: str  # "PASS", "FAIL", "DEGRADED"
    details: str


class RoutingTableInspector:
    """Inspects FRR and Linux routing tables."""

    def __init__(self, transport: Transport):
        self.transport = transport

    def inspect_router(self, router_name: str, expected_prefixes: List[str]) -> RouterRoutingHealth:
        """Inspect installed routes on a given router.

        Args:
            router_name: Name of the router.
            expected_prefixes: Prefixes that must be present in the routing table.

        Returns:
            RouterRoutingHealth evaluation.
        """
        routes: Dict[str, RouteEntry] = {}

        # 1. Query FRR routing table via vtysh
        cmd_res = self.transport.execute_vtysh(router_name, "show ip route json")
        if cmd_res.success and cmd_res.stdout:
            try:
                routes = self._parse_frr_json(cmd_res.stdout)
            except Exception as exc:
                logger.warning("Failed to parse FRR routing JSON on %s: %s", router_name, exc)

        # 2. Text fallback if JSON parsing failed
        if not routes:
            text_res = self.transport.execute_vtysh(router_name, "show ip route")
            if text_res.success and text_res.stdout:
                routes = self._parse_frr_text(text_res.stdout)

        missing = [pfx for pfx in expected_prefixes if pfx not in routes]
        if missing:
            status = "FAIL" if len(missing) == len(expected_prefixes) else "DEGRADED"
            details = f"Missing {len(missing)} expected route(s): {', '.join(missing)}"
        else:
            status = "PASS"
            details = f"All {len(expected_prefixes)} expected routes installed."

        return RouterRoutingHealth(
            router_name=router_name,
            routes=routes,
            expected_prefixes=expected_prefixes,
            missing_prefixes=missing,
            status=status,
            details=details,
        )

    def _parse_frr_json(self, json_str: str) -> Dict[str, RouteEntry]:
        """Parse 'show ip route json' output."""
        data = json.loads(json_str)
        routes: Dict[str, RouteEntry] = {}

        for prefix, route_list in data.items():
            if not isinstance(route_list, list):
                route_list = [route_list]

            for item in route_list:
                if not isinstance(item, dict):
                    continue
                protocol = item.get("protocol", "unknown").lower()
                metric = item.get("metric", 0)
                next_hops: List[str] = []
                nh_list = item.get("nexthops", [])
                for nh in nh_list:
                    if isinstance(nh, dict):
                        ip = nh.get("ip") or nh.get("interfaceName") or ""
                        if ip:
                            next_hops.append(ip)

                routes[prefix] = RouteEntry(
                    prefix=prefix,
                    protocol=protocol,
                    next_hops=next_hops,
                    metric=metric,
                    raw=item,
                )

        return routes

    def _parse_frr_text(self, text: str) -> Dict[str, RouteEntry]:
        """Parse textual 'show ip route' output."""
        routes: Dict[str, RouteEntry] = {}
        lines = text.strip().splitlines()

        for line in lines:
            line = line.strip()
            # B>* 172.16.12.0/24 [20/0] via 10.0.0.4, eth1, weight 1, 00:03:15
            # O   10.255.0.2/32 [110/10] via 10.0.0.2, eth2, 00:05:12
            if not line or line.startswith("Codes:") or line.startswith("Gateway"):
                continue

            parts = line.split()
            if len(parts) >= 2:
                code = parts[0]
                proto = "unknown"
                if "B" in code:
                    proto = "bgp"
                elif "O" in code:
                    proto = "ospf"
                elif "C" in code:
                    proto = "connected"

                # Find prefix token
                prefix = ""
                for part in parts[1:]:
                    if "/" in part:
                        prefix = part
                        break

                if prefix:
                    next_hops = []
                    if "via" in parts:
                        via_idx = parts.index("via")
                        if via_idx + 1 < len(parts):
                            next_hops.append(parts[via_idx + 1].rstrip(","))

                    routes[prefix] = RouteEntry(
                        prefix=prefix,
                        protocol=proto,
                        next_hops=next_hops,
                        metric=0,
                        raw={"line": line},
                    )

        return routes
