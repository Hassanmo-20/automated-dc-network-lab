"""OSPF protocol state inspection and parsing."""

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional
from netauto.transport.base import Transport
from netauto.utils.logging import setup_logger

logger = setup_logger("netauto.protocols.ospf")


@dataclass
class OspfNeighborState:
    """Status of an individual OSPF neighbor adjacency."""
    router_id: str
    neighbor_ip: str
    interface: str
    state: str
    is_full: bool
    raw: Dict


@dataclass
class RouterOspfHealth:
    """Aggregated OSPF health for a specific router."""
    router_name: str
    router_id: str
    neighbors: List[OspfNeighborState]
    expected_neighbor_count: int
    all_full: bool
    status: str  # "PASS", "FAIL", "DEGRADED"
    details: str


class OspfInspector:
    """Inspects and parses OSPF state via FRR vtysh."""

    def __init__(self, transport: Transport):
        self.transport = transport

    def inspect_router(self, router_name: str, expected_neighbor_count: int) -> RouterOspfHealth:
        """Inspect OSPF neighbor adjacencies on a given router.

        Args:
            router_name: Name of the router (e.g., 'spine1', 'leaf1').
            expected_neighbor_count: Expected number of FULL neighbors.

        Returns:
            RouterOspfHealth with structured evaluation.
        """
        # 1. Try JSON command first
        cmd_result = self.transport.execute_vtysh(router_name, "show ip ospf neighbor json")
        neighbors: List[OspfNeighborState] = []
        router_id = ""

        if cmd_result.success and cmd_result.stdout:
            try:
                neighbors, router_id = self._parse_json(cmd_result.stdout)
            except Exception as exc:
                logger.warning(
                    "Failed to parse OSPF JSON for %s (%s). Falling back to text parser.",
                    router_name, exc
                )
                neighbors = []

        # 2. Text fallback if JSON parsing returned empty or failed
        if not neighbors:
            text_result = self.transport.execute_vtysh(router_name, "show ip ospf neighbor")
            if text_result.success and text_result.stdout:
                neighbors = self._parse_text(text_result.stdout)

        # 3. Evaluate health
        full_neighbors = [n for n in neighbors if n.is_full]
        all_full = (len(full_neighbors) == expected_neighbor_count) and (len(neighbors) == expected_neighbor_count)

        if len(neighbors) == 0 and expected_neighbor_count > 0:
            status = "FAIL"
            details = f"No OSPF neighbors found (expected {expected_neighbor_count})"
        elif len(full_neighbors) == expected_neighbor_count:
            status = "PASS"
            details = f"All {expected_neighbor_count} OSPF neighbors in FULL state"
        else:
            status = "FAIL" if len(full_neighbors) == 0 else "DEGRADED"
            details = (
                f"{len(full_neighbors)}/{expected_neighbor_count} neighbors FULL. "
                f"Total neighbors observed: {len(neighbors)}"
            )

        return RouterOspfHealth(
            router_name=router_name,
            router_id=router_id,
            neighbors=neighbors,
            expected_neighbor_count=expected_neighbor_count,
            all_full=all_full,
            status=status,
            details=details,
        )

    def _parse_json(self, json_str: str) -> (List[OspfNeighborState], str):
        """Parse 'show ip ospf neighbor json' output."""
        data = json.loads(json_str)
        neighbors: List[OspfNeighborState] = []
        router_id = ""

        # FRR may return dictionary under "neighbors"
        nbrs_dict = data.get("neighbors", data)
        if isinstance(nbrs_dict, dict):
            for key, val in nbrs_dict.items():
                entries = val if isinstance(val, list) else [val]
                for item in entries:
                    if not isinstance(item, dict):
                        continue
                    n_id = item.get("neighborId") or item.get("routerId") or str(key)
                    n_ip = item.get("ipAddress") or item.get("address") or str(key)
                    iface = item.get("ifaceName") or item.get("interface") or ""
                    state_raw = item.get("converged") or item.get("nbrState") or item.get("state") or ""
                    is_full = "full" in state_raw.lower()
                    neighbors.append(
                        OspfNeighborState(
                            router_id=n_id,
                            neighbor_ip=n_ip,
                            interface=iface,
                            state=state_raw,
                            is_full=is_full,
                            raw=item,
                        )
                    )
        elif isinstance(nbrs_dict, list):
            for item in nbrs_dict:
                if not isinstance(item, dict):
                    continue
                n_id = item.get("neighborId") or item.get("routerId") or ""
                n_ip = item.get("ipAddress") or item.get("address") or ""
                iface = item.get("ifaceName") or item.get("interface") or ""
                state_raw = item.get("nbrState") or item.get("state") or ""
                is_full = "full" in state_raw.lower()
                neighbors.append(
                    OspfNeighborState(
                        router_id=n_id,
                        neighbor_ip=n_ip,
                        interface=iface,
                        state=state_raw,
                        is_full=is_full,
                        raw=item,
                    )
                )

        return neighbors, router_id

    def _parse_text(self, text: str) -> List[OspfNeighborState]:
        """Parse tabular 'show ip ospf neighbor' text output."""
        neighbors: List[OspfNeighborState] = []
        lines = text.strip().splitlines()

        for line in lines:
            line = line.strip()
            if not line or line.startswith("Neighbor") or line.startswith("="):
                continue
            # Typical format: 10.255.1.1 1 Full/DROther 33.123s 10.0.0.1 eth1:10.0.0.0
            parts = line.split()
            if len(parts) >= 6:
                n_id = parts[0]
                state_str = parts[2]
                n_ip = parts[4]
                iface = parts[5].split(":")[0]
                neighbors.append(
                    OspfNeighborState(
                        router_id=n_id,
                        neighbor_ip=n_ip,
                        interface=iface,
                        state=state_str,
                        is_full="full" in state_str.lower(),
                        raw={"line": line},
                    )
                )

        return neighbors
