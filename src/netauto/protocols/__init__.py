"""Protocol inspection package for netauto."""

from netauto.protocols.ospf import OspfInspector, OspfNeighborState, RouterOspfHealth
from netauto.protocols.bgp import BgpInspector, BgpPeerState, RouterBgpHealth

__all__ = [
    "OspfInspector",
    "OspfNeighborState",
    "RouterOspfHealth",
    "BgpInspector",
    "BgpPeerState",
    "RouterBgpHealth",
]
