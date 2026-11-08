"""BGP protocol state inspection and parsing."""

import json
from dataclasses import dataclass
from typing import Dict, List, Optional
from netauto.transport.base import Transport
from netauto.utils.logging import setup_logger

logger = setup_logger("netauto.protocols.bgp")


@dataclass
class BgpPeerState:
    """Status of an individual BGP peer session."""
    peer_ip: str
    remote_as: int
    state: str
    is_established: bool
    prefixes_received: int
    prefixes_sent: int
    raw: Dict


@dataclass
class RouterBgpHealth:
    """Aggregated BGP health for a specific router."""
    router_name: str
    local_as: int
    peers: List[BgpPeerState]
    expected_peer_count: int
    all_established: bool
    status: str  # "PASS", "FAIL", "DEGRADED"
    details: str


class BgpInspector:
    """Inspects and parses BGP state via FRR vtysh."""

    def __init__(self, transport: Transport):
        self.transport = transport

    def inspect_router(self, router_name: str, expected_peer_count: int) -> RouterBgpHealth:
        """Inspect BGP peer sessions on a given router.

        Args:
            router_name: Name of the router (e.g., 'spine1', 'leaf1').
            expected_peer_count: Expected number of Established sessions.

        Returns:
            RouterBgpHealth with structured evaluation.
        """
        # 1. Try JSON command first
        cmd_result = self.transport.execute_vtysh(router_name, "show bgp ipv4 unicast summary json")
        peers: List[BgpPeerState] = []
        local_as = 0

        if cmd_result.success and cmd_result.stdout:
            try:
                peers, local_as = self._parse_json(cmd_result.stdout)
            except Exception as exc:
                logger.warning(
                    "Failed to parse BGP JSON for %s (%s). Falling back to text parser.",
                    router_name, exc
                )
                peers = []

        # 2. Text fallback if JSON parsing failed or was empty
        if not peers:
            text_result = self.transport.execute_vtysh(router_name, "show bgp ipv4 unicast summary")
            if text_result.success and text_result.stdout:
                peers, local_as = self._parse_text(text_result.stdout)

        # 3. Evaluate health
        established_peers = [p for p in peers if p.is_established]
        all_established = (
            len(established_peers) == expected_peer_count and len(peers) == expected_peer_count
        )

        if len(peers) == 0 and expected_peer_count > 0:
            status = "FAIL"
            details = f"No BGP peers found (expected {expected_peer_count})"
        elif len(established_peers) == expected_peer_count:
            status = "PASS"
            details = f"All {expected_peer_count} BGP sessions Established"
        else:
            status = "FAIL" if len(established_peers) == 0 else "DEGRADED"
            details = (
                f"{len(established_peers)}/{expected_peer_count} peers Established. "
                f"Total peers observed: {len(peers)}"
            )

        return RouterBgpHealth(
            router_name=router_name,
            local_as=local_as,
            peers=peers,
            expected_peer_count=expected_peer_count,
            all_established=all_established,
            status=status,
            details=details,
        )

    def _parse_json(self, json_str: str) -> (List[BgpPeerState], int):
        """Parse 'show bgp ipv4 unicast summary json' output."""
        data = json.loads(json_str)
        peers: List[BgpPeerState] = []
        local_as = data.get("as", 0)

        # FRR JSON can place peers either in data['peers'] or data['ipv4Unicast']['peers']
        peers_dict = data.get("peers")
        if not peers_dict and "ipv4Unicast" in data:
            peers_dict = data["ipv4Unicast"].get("peers", {})

        if isinstance(peers_dict, dict):
            for peer_ip, p_info in peers_dict.items():
                if not isinstance(p_info, dict):
                    continue
                remote_as = int(p_info.get("remoteAs", 0))
                state_str = str(p_info.get("state", ""))
                is_est = state_str.lower() == "established"

                pfx_rcd = int(p_info.get("pfxRcd", 0) or 0)
                pfx_snt = int(p_info.get("pfxSnt", 0) or 0)

                peers.append(
                    BgpPeerState(
                        peer_ip=peer_ip,
                        remote_as=remote_as,
                        state=state_str,
                        is_established=is_est,
                        prefixes_received=pfx_rcd,
                        prefixes_sent=pfx_snt,
                        raw=p_info,
                    )
                )

        return peers, local_as

    def _parse_text(self, text: str) -> (List[BgpPeerState], int):
        """Parse tabular 'show bgp ipv4 unicast summary' text output."""
        peers: List[BgpPeerState] = []
        local_as = 0
        lines = text.strip().splitlines()

        in_table = False
        for line in lines:
            line = line.strip()
            if "local AS number" in line:
                parts = line.split()
                try:
                    local_as = int(parts[-1])
                except (ValueError, IndexError):
                    pass
                continue

            if line.startswith("Neighbor") and "AS" in line:
                in_table = True
                continue

            if in_table and line:
                parts = line.split()
                # e.g.: 10.0.0.1 4 65101 23 24 0 0 0 00:01:23 1 3
                if len(parts) >= 10:
                    peer_ip = parts[0]
                    try:
                        remote_as = int(parts[2])
                    except ValueError:
                        remote_as = 0
                    state_or_pfx = parts[9]
                    # If state_or_pfx is a number, it indicates number of prefixes received in Established state!
                    if state_or_pfx.isdigit():
                        state_str = "Established"
                        is_est = True
                        pfx_rcd = int(state_or_pfx)
                    else:
                        state_str = state_or_pfx
                        is_est = state_str.lower() == "established"
                        pfx_rcd = 0

                    pfx_snt = 0
                    if len(parts) >= 11 and parts[10].isdigit():
                        pfx_snt = int(parts[10])

                    peers.append(
                        BgpPeerState(
                            peer_ip=peer_ip,
                            remote_as=remote_as,
                            state=state_str,
                            is_established=is_est,
                            prefixes_received=pfx_rcd,
                            prefixes_sent=pfx_snt,
                            raw={"line": line},
                        )
                    )

        return peers, local_as
