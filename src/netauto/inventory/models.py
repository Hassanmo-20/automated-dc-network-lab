"""Data models representing the fabric inventory."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class LoopbackConfig:
    ipv4: str


@dataclass
class OspfNodeConfig:
    enabled: bool = True
    router_id: str = ""


@dataclass
class ServerInterfaceConfig:
    name: str
    ipv4: str


@dataclass
class FabricInterface:
    name: str
    ipv4: str
    peer_node: str
    peer_interface: str


@dataclass
class BgpNeighbor:
    peer_ip: str
    remote_as: int
    peer_name: str


@dataclass
class ConnectedServer:
    name: str
    interface: str
    ipv4: str
    gateway: str


@dataclass
class Router:
    name: str
    role: str  # "spine" or "leaf"
    asn: int
    loopback: LoopbackConfig
    ospf: OspfNodeConfig
    server_subnet: Optional[str] = None
    server_interface: Optional[ServerInterfaceConfig] = None
    fabric_interfaces: List[FabricInterface] = field(default_factory=list)
    bgp_neighbors: List[BgpNeighbor] = field(default_factory=list)
    connected_server: Optional[ConnectedServer] = None


@dataclass
class Endpoint:
    node: str
    interface: str
    ipv4: str


@dataclass
class FabricLink:
    source: Endpoint
    target: Endpoint


@dataclass
class ServerNode:
    name: str
    connected_to: str
    leaf_interface: str
    interface: str
    ipv4: str
    gateway: str


@dataclass
class EcmpConfig:
    enabled: bool = True
    maximum_paths: int = 2


@dataclass
class OspfGlobalConfig:
    process_id: int = 1
    area: str = "0.0.0.0"
    reference_bandwidth_mbps: int = 100000


@dataclass
class BgpGlobalConfig:
    multipath_as_path_relax: bool = True


@dataclass
class LabImages:
    frr: str = "quay.io/frrouting/frr:10.2.1"
    host: str = "alpine:3.20"


@dataclass
class LabConfig:
    name: str = "dc-fabric-lab"
    prefix: str = "clab"
    images: LabImages = field(default_factory=LabImages)


@dataclass
class FabricInventory:
    lab: LabConfig
    ecmp: EcmpConfig
    ospf: OspfGlobalConfig
    bgp: BgpGlobalConfig
    routers: List[Router]
    links: List[FabricLink]
    servers: List[ServerNode]
    raw_data: Dict = field(default_factory=dict)
