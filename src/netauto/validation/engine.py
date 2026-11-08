"""Central validation engine orchestrating all network health checks."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from netauto.inventory.models import FabricInventory
from netauto.protocols.bgp import BgpInspector, RouterBgpHealth
from netauto.protocols.ospf import OspfInspector, RouterOspfHealth
from netauto.transport.base import Transport
from netauto.validation.connectivity import ConnectivityMatrixResult, ConnectivityTester
from netauto.validation.ecmp import EcmpValidator, LeafEcmpHealth
from netauto.validation.routing_table import (
    RouteEntry,
    RouterRoutingHealth,
    RoutingTableInspector,
)


@dataclass
class FailureDetail:
    """Diagnostic detail for a specific detected failure."""
    device: str
    protocol: str
    expected_state: str
    actual_state: str
    explanation: str
    suggested_commands: List[str]


@dataclass
class ContainerHealthSummary:
    """Summary of container runtime availability."""
    total_expected: int
    running_count: int
    running_nodes: List[str]
    missing_nodes: List[str]
    status: str  # "PASS", "FAIL"


@dataclass
class ValidationReportData:
    """Complete validation dataset for reports and dashboards."""
    timestamp: str
    overall_status: str  # "PASS", "FAIL", "DEGRADED"
    container_health: ContainerHealthSummary
    ospf_health: Dict[str, RouterOspfHealth]
    bgp_health: Dict[str, RouterBgpHealth]
    routing_health: Dict[str, RouterRoutingHealth]
    ecmp_health: Dict[str, LeafEcmpHealth]
    connectivity: ConnectivityMatrixResult
    failures: List[FailureDetail] = field(default_factory=list)


class ValidationEngine:
    """Orchestrates comprehensive validation across all fabric layers."""

    def __init__(self, transport: Transport, inventory: FabricInventory):
        self.transport = transport
        self.inventory = inventory
        self.ospf_inspector = OspfInspector(transport)
        self.bgp_inspector = BgpInspector(transport)
        self.routing_inspector = RoutingTableInspector(transport)
        self.ecmp_validator = EcmpValidator(transport)
        self.connectivity_tester = ConnectivityTester(transport)

    def run_all_checks(self) -> ValidationReportData:
        """Run all validation phases and return consolidated results."""
        timestamp = datetime.now(timezone.utc).isoformat()
        failures: List[FailureDetail] = []

        # 1. Container Health Check
        expected_nodes = [r.name for r in self.inventory.routers] + [s.name for s in self.inventory.servers]
        running_nodes: List[str] = []
        missing_nodes: List[str] = []

        for node in expected_nodes:
            if self.transport.is_node_ready(node):
                running_nodes.append(node)
            else:
                missing_nodes.append(node)
                failures.append(
                    FailureDetail(
                        device=node,
                        protocol="Infrastructure/Docker",
                        expected_state="Container Running",
                        actual_state="Container Missing or Stopped",
                        explanation=f"Container for node '{node}' is not active.",
                        suggested_commands=[f"docker ps -a --filter name={node}", f"docker logs {node}"],
                    )
                )

        container_status = "PASS" if len(missing_nodes) == 0 else "FAIL"
        container_health = ContainerHealthSummary(
            total_expected=len(expected_nodes),
            running_count=len(running_nodes),
            running_nodes=running_nodes,
            missing_nodes=missing_nodes,
            status=container_status,
        )

        # 2. OSPF Validation
        ospf_health: Dict[str, RouterOspfHealth] = {}
        for router in self.inventory.routers:
            expected_ospf = 4 if router.role == "spine" else 2
            h = self.ospf_inspector.inspect_router(router.name, expected_ospf)
            ospf_health[router.name] = h
            if h.status != "PASS":
                failures.append(
                    FailureDetail(
                        device=router.name,
                        protocol="OSPFv2",
                        expected_state=f"{expected_ospf} neighbors FULL",
                        actual_state=h.details,
                        explanation=f"OSPF adjacency incomplete on {router.name}. Fabric underlay link issue or MTU mismatch.",
                        suggested_commands=[
                            f"docker exec clab-dc-fabric-lab-{router.name} vtysh -c 'show ip ospf neighbor'",
                            f"docker exec clab-dc-fabric-lab-{router.name} vtysh -c 'show ip ospf interface'",
                        ],
                    )
                )

        # 3. BGP Validation
        bgp_health: Dict[str, RouterBgpHealth] = {}
        for router in self.inventory.routers:
            expected_bgp = 4 if router.role == "spine" else 2
            b = self.bgp_inspector.inspect_router(router.name, expected_bgp)
            bgp_health[router.name] = b
            if b.status != "PASS":
                failures.append(
                    FailureDetail(
                        device=router.name,
                        protocol="eBGP",
                        expected_state=f"{expected_bgp} peers Established",
                        actual_state=b.details,
                        explanation=f"BGP session failure on {router.name}. Check ASN configuration, peering IP, or firewall.",
                        suggested_commands=[
                            f"docker exec clab-dc-fabric-lab-{router.name} vtysh -c 'show bgp ipv4 unicast summary'",
                            f"docker exec clab-dc-fabric-lab-{router.name} vtysh -c 'show bgp neighbor'",
                        ],
                    )
                )

        # 4. Routing Table Validation
        all_server_subnets = [
            r.server_subnet for r in self.inventory.routers if r.role == "leaf" and r.server_subnet
        ]
        routing_health: Dict[str, RouterRoutingHealth] = {}
        for router in self.inventory.routers:
            expected_pfxs = (
                all_server_subnets
                if router.role == "spine"
                else [p for p in all_server_subnets if p != router.server_subnet]
            )
            r_health = self.routing_inspector.inspect_router(router.name, expected_pfxs)
            routing_health[router.name] = r_health
            if r_health.status != "PASS":
                failures.append(
                    FailureDetail(
                        device=router.name,
                        protocol="Routing Table",
                        expected_state=f"Prefixes installed: {expected_pfxs}",
                        actual_state=r_health.details,
                        explanation="BGP route propagation failed or route-map filtered the server prefixes.",
                        suggested_commands=[
                            f"docker exec clab-dc-fabric-lab-{router.name} vtysh -c 'show ip route'",
                            f"docker exec clab-dc-fabric-lab-{router.name} vtysh -c 'show bgp ipv4 unicast'",
                        ],
                    )
                )

        # 5. ECMP Validation (on Leafs)
        ecmp_health: Dict[str, LeafEcmpHealth] = {}
        for router in self.inventory.routers:
            if router.role != "leaf":
                continue
            remotes = [p for p in all_server_subnets if p != router.server_subnet]
            e_health = self.ecmp_validator.validate_leaf(
                router.name, remotes, expected_paths=self.inventory.ecmp.maximum_paths
            )
            ecmp_health[router.name] = e_health
            if e_health.status != "PASS":
                failures.append(
                    FailureDetail(
                        device=router.name,
                        protocol="BGP ECMP",
                        expected_state=f"2 equal-cost paths for each of {remotes}",
                        actual_state=e_health.details,
                        explanation="ECMP path diversity degraded. One Spine link may be down or maximum-paths not configured.",
                        suggested_commands=[
                            f"docker exec clab-dc-fabric-lab-{router.name} vtysh -c 'show ip route {remotes[0] if remotes else ''}'",
                            f"docker exec clab-dc-fabric-lab-{router.name} vtysh -c 'show bgp ipv4 unicast {remotes[0] if remotes else ''}'",
                            f"docker exec clab-dc-fabric-lab-{router.name} ip -4 route show",
                        ],
                    )
                )

        # 6. End-to-End Server Connectivity
        servers_info = [{"name": s.name, "ipv4": s.ipv4} for s in self.inventory.servers]
        conn_res = self.connectivity_tester.test_full_mesh(servers_info, count=3)
        if conn_res.status != "PASS":
            failures.append(
                FailureDetail(
                    device="Servers",
                    protocol="ICMP Connectivity",
                    expected_state="100% reachability across all server pairs",
                    actual_state=conn_res.details,
                    explanation="Host packets dropped across the Clos fabric. Check gateway ARP and leaf forwarding.",
                    suggested_commands=[
                        "docker exec clab-dc-fabric-lab-host1 ping -c 3 172.16.12.10",
                        "docker exec clab-dc-fabric-lab-leaf1 ip route show",
                    ],
                )
            )

        # 7. Calculate Overall Health
        statuses = [
            container_health.status,
            *(h.status for h in ospf_health.values()),
            *(b.status for b in bgp_health.values()),
            *(r.status for r in routing_health.values()),
            *(e.status for e in ecmp_health.values()),
            conn_res.status,
        ]

        if any(s == "FAIL" for s in statuses):
            overall = "FAIL"
        elif any(s == "DEGRADED" for s in statuses):
            overall = "DEGRADED"
        else:
            overall = "PASS"

        return ValidationReportData(
            timestamp=timestamp,
            overall_status=overall,
            container_health=container_health,
            ospf_health=ospf_health,
            bgp_health=bgp_health,
            routing_health=routing_health,
            ecmp_health=ecmp_health,
            connectivity=conn_res,
            failures=failures,
        )
