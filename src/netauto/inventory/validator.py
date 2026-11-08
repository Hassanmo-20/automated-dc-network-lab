"""Comprehensive inventory validation and model instantiation."""

import ipaddress
from typing import Any, Dict, List, Set, Tuple

from netauto.inventory.models import (
    BgpGlobalConfig,
    BgpNeighbor,
    ConnectedServer,
    EcmpConfig,
    Endpoint,
    FabricInterface,
    FabricInventory,
    FabricLink,
    LabConfig,
    LabImages,
    LoopbackConfig,
    OspfGlobalConfig,
    OspfNodeConfig,
    Router,
    ServerInterfaceConfig,
    ServerNode,
)


class InventoryValidationError(Exception):
    """Raised when the inventory fails validation checks."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        message = f"Inventory validation failed with {len(errors)} error(s):\n" + "\n".join(
            f"  - {err}" for err in errors
        )
        super().__init__(message)


def validate_and_build_inventory(raw_data: Dict[str, Any]) -> FabricInventory:
    """Validate raw inventory dictionary and construct typed domain models.

    Args:
        raw_data: Parsed dictionary from inventory/fabric.yml.

    Returns:
        FabricInventory domain model.

    Raises:
        InventoryValidationError: If any validation rule is violated.
    """
    errors: List[str] = []

    # 1. Required Top-Level Sections
    required_sections = ["lab", "routers", "links", "servers"]
    for sec in required_sections:
        if sec not in raw_data:
            errors.append(f"Missing required top-level section: '{sec}'")

    if errors:
        raise InventoryValidationError(errors)

    # 2. Lab Config
    lab_raw = raw_data.get("lab", {})
    images_raw = lab_raw.get("images", {})
    lab = LabConfig(
        name=lab_raw.get("name", "dc-fabric-lab"),
        prefix=lab_raw.get("prefix", "clab"),
        images=LabImages(
            frr=images_raw.get("frr", "quay.io/frrouting/frr:10.2.1"),
            host=images_raw.get("host", "alpine:3.20"),
        ),
    )

    # 3. Global Configs
    ecmp_raw = raw_data.get("ecmp", {})
    ecmp = EcmpConfig(
        enabled=ecmp_raw.get("enabled", True),
        maximum_paths=int(ecmp_raw.get("maximum_paths", 2)),
    )
    if ecmp.maximum_paths < 1 or ecmp.maximum_paths > 64:
        errors.append(f"Invalid maximum_paths {ecmp.maximum_paths}. Expected 1-64.")

    ospf_raw = raw_data.get("ospf", {})
    ospf = OspfGlobalConfig(
        process_id=int(ospf_raw.get("process_id", 1)),
        area=ospf_raw.get("area", "0.0.0.0"),
        reference_bandwidth_mbps=int(ospf_raw.get("reference_bandwidth_mbps", 100000)),
    )

    bgp_raw = raw_data.get("bgp", {})
    bgp = BgpGlobalConfig(
        multipath_as_path_relax=bool(bgp_raw.get("multipath_as_path_relax", True))
    )

    # 4. Routers Validation
    routers_dict: Dict[str, Router] = {}
    router_names: Set[str] = set()
    used_ips: Dict[str, str] = {}  # ip_address -> "context"
    router_asns: Dict[str, int] = {}

    routers_list = raw_data.get("routers", [])
    if not isinstance(routers_list, list) or len(routers_list) == 0:
        errors.append("The 'routers' list must contain at least one router.")

    for r_entry in routers_list:
        r_name = r_entry.get("name")
        if not r_name or not isinstance(r_name, str):
            errors.append(f"Router definition missing valid 'name': {r_entry}")
            continue

        if r_name in router_names:
            errors.append(f"Duplicate router name found: '{r_name}'")
        router_names.add(r_name)

        role = r_entry.get("role", "").lower()
        if role not in ("spine", "leaf"):
            errors.append(f"Router '{r_name}' has invalid role '{role}'. Must be 'spine' or 'leaf'.")

        asn = r_entry.get("asn")
        if not isinstance(asn, int) or asn < 1 or asn > 4294967295:
            errors.append(f"Router '{r_name}' has invalid ASN: {asn}. Must be between 1 and 4294967295.")
        else:
            router_asns[r_name] = asn

        # Loopback
        lb_raw = r_entry.get("loopback", {})
        lb_ip = lb_raw.get("ipv4")
        if not lb_ip:
            errors.append(f"Router '{r_name}' missing loopback.ipv4")
        else:
            try:
                ip_interface = ipaddress.IPv4Interface(lb_ip)
                if ip_interface.network.prefixlen != 32:
                    errors.append(f"Router '{r_name}' loopback must be a /32, got {lb_ip}")
                ip_str = str(ip_interface.ip)
                if ip_str in used_ips:
                    errors.append(f"Duplicate IP {ip_str} on router '{r_name}' loopback (already used by {used_ips[ip_str]})")
                else:
                    used_ips[ip_str] = f"router '{r_name}' loopback"
            except ValueError as ve:
                errors.append(f"Router '{r_name}' invalid loopback IP '{lb_ip}': {ve}")

        # OSPF Node Config
        ospf_node_raw = r_entry.get("ospf", {})
        ospf_node = OspfNodeConfig(
            enabled=bool(ospf_node_raw.get("enabled", True)),
            router_id=ospf_node_raw.get("router_id", lb_ip.split("/")[0] if lb_ip else ""),
        )

        # Server Subnet & Interface for Leafs
        server_subnet = r_entry.get("server_subnet")
        server_iface_raw = r_entry.get("server_interface")
        server_iface: Optional[ServerInterfaceConfig] = None

        if role == "leaf":
            if not server_subnet:
                errors.append(f"Leaf router '{r_name}' missing required 'server_subnet'")
            else:
                try:
                    subnet_net = ipaddress.IPv4Network(server_subnet, strict=True)
                except ValueError as ve:
                    errors.append(f"Leaf router '{r_name}' invalid server_subnet '{server_subnet}': {ve}")

            if not server_iface_raw:
                errors.append(f"Leaf router '{r_name}' missing required 'server_interface'")
            else:
                s_iface_name = server_iface_raw.get("name")
                s_iface_ip = server_iface_raw.get("ipv4")
                if not s_iface_name or not s_iface_ip:
                    errors.append(f"Leaf router '{r_name}' server_interface missing 'name' or 'ipv4'")
                else:
                    try:
                        s_ip_if = ipaddress.IPv4Interface(s_iface_ip)
                        ip_str = str(s_ip_if.ip)
                        if ip_str in used_ips:
                            errors.append(f"Duplicate IP {ip_str} on '{r_name}' server_interface (already used by {used_ips[ip_str]})")
                        else:
                            used_ips[ip_str] = f"leaf '{r_name}' server interface"
                        server_iface = ServerInterfaceConfig(name=s_iface_name, ipv4=s_iface_ip)
                    except ValueError as ve:
                        errors.append(f"Leaf router '{r_name}' server_interface invalid IP '{s_iface_ip}': {ve}")

        routers_dict[r_name] = Router(
            name=r_name,
            role=role,
            asn=asn if isinstance(asn, int) else 0,
            loopback=LoopbackConfig(ipv4=lb_ip or ""),
            ospf=ospf_node,
            server_subnet=server_subnet,
            server_interface=server_iface,
        )

    # 5. Links Validation
    links_list = raw_data.get("links", [])
    if not isinstance(links_list, list) or len(links_list) == 0:
        errors.append("The 'links' list must contain at least one link.")

    links: List[FabricLink] = []
    node_interfaces: Dict[str, Set[str]] = {r: set() for r in router_names}

    for idx, l_entry in enumerate(links_list):
        src_raw = l_entry.get("source", {})
        tgt_raw = l_entry.get("target", {})

        src_node = src_raw.get("node")
        src_iface = src_raw.get("interface")
        src_ip = src_raw.get("ipv4")

        tgt_node = tgt_raw.get("node")
        tgt_iface = tgt_raw.get("interface")
        tgt_ip = tgt_raw.get("ipv4")

        # Validate nodes exist
        if src_node not in router_names:
            errors.append(f"Link {idx}: Source node '{src_node}' is not in defined routers.")
        if tgt_node not in router_names:
            errors.append(f"Link {idx}: Target node '{tgt_node}' is not in defined routers.")

        if src_node and src_node in node_interfaces:
            if src_iface in node_interfaces[src_node]:
                errors.append(f"Duplicate interface '{src_iface}' on router '{src_node}'")
            node_interfaces[src_node].add(src_iface)

        if tgt_node and tgt_node in node_interfaces:
            if tgt_iface in node_interfaces[tgt_node]:
                errors.append(f"Duplicate interface '{tgt_iface}' on router '{tgt_node}'")
            node_interfaces[tgt_node].add(tgt_iface)

        # Validate Point-to-Point /31 Addressing
        if src_ip and tgt_ip:
            try:
                src_net = ipaddress.IPv4Interface(src_ip)
                tgt_net = ipaddress.IPv4Interface(tgt_ip)

                if src_net.network.prefixlen != 31:
                    errors.append(f"Link {idx} ({src_node}-{tgt_node}): Source subnet prefixlen must be /31, got {src_ip}")
                if tgt_net.network.prefixlen != 31:
                    errors.append(f"Link {idx} ({src_node}-{tgt_node}): Target subnet prefixlen must be /31, got {tgt_ip}")

                if src_net.network != tgt_net.network:
                    errors.append(f"Link {idx} ({src_node}-{tgt_node}): Endpoints belong to different subnets: {src_ip} vs {tgt_ip}")

                if src_net.ip == tgt_net.ip:
                    errors.append(f"Link {idx} ({src_node}-{tgt_node}): Both endpoints have identical IP {src_net.ip}")

                # Duplicate IP check
                src_ip_str = str(src_net.ip)
                tgt_ip_str = str(tgt_net.ip)

                if src_ip_str in used_ips:
                    errors.append(f"Duplicate IP {src_ip_str} on {src_node}:{src_iface} (already used by {used_ips[src_ip_str]})")
                else:
                    used_ips[src_ip_str] = f"{src_node}:{src_iface}"

                if tgt_ip_str in used_ips:
                    errors.append(f"Duplicate IP {tgt_ip_str} on {tgt_node}:{tgt_iface} (already used by {used_ips[tgt_ip_str]})")
                else:
                    used_ips[tgt_ip_str] = f"{tgt_node}:{tgt_iface}"

                # Assign interfaces & neighbors to router domain models
                if src_node in routers_dict and tgt_node in routers_dict:
                    src_router = routers_dict[src_node]
                    tgt_router = routers_dict[tgt_node]

                    src_router.fabric_interfaces.append(
                        FabricInterface(
                            name=src_iface,
                            ipv4=src_ip,
                            peer_node=tgt_node,
                            peer_interface=tgt_iface,
                        )
                    )
                    tgt_router.fabric_interfaces.append(
                        FabricInterface(
                            name=tgt_iface,
                            ipv4=tgt_ip,
                            peer_node=src_node,
                            peer_interface=src_iface,
                        )
                    )

                    # BGP Neighbor relationship
                    src_router.bgp_neighbors.append(
                        BgpNeighbor(
                            peer_ip=tgt_ip_str,
                            remote_as=tgt_router.asn,
                            peer_name=tgt_node,
                        )
                    )
                    tgt_router.bgp_neighbors.append(
                        BgpNeighbor(
                            peer_ip=src_ip_str,
                            remote_as=src_router.asn,
                            peer_name=src_node,
                        )
                    )

            except ValueError as ve:
                errors.append(f"Link {idx} invalid IP addressing: {ve}")

        links.append(
            FabricLink(
                source=Endpoint(node=src_node or "", interface=src_iface or "", ipv4=src_ip or ""),
                target=Endpoint(node=tgt_node or "", interface=tgt_iface or "", ipv4=tgt_ip or ""),
            )
        )

    # 6. Servers Validation
    servers_list = raw_data.get("servers", [])
    servers: List[ServerNode] = []
    server_names: Set[str] = set()

    for s_entry in servers_list:
        s_name = s_entry.get("name")
        if not s_name:
            errors.append(f"Server missing 'name': {s_entry}")
            continue

        if s_name in server_names:
            errors.append(f"Duplicate server name '{s_name}'")
        server_names.add(s_name)

        conn_leaf = s_entry.get("connected_to")
        if conn_leaf not in router_names:
            errors.append(f"Server '{s_name}' connects to nonexistent router '{conn_leaf}'")
            continue

        leaf_router = routers_dict[conn_leaf]
        if leaf_router.role != "leaf":
            errors.append(f"Server '{s_name}' connects to router '{conn_leaf}', which is not a leaf.")

        s_iface = s_entry.get("interface", "eth1")
        leaf_iface = s_entry.get("leaf_interface", "eth3")
        s_ip = s_entry.get("ipv4")
        gateway = s_entry.get("gateway")

        if not s_ip or not gateway:
            errors.append(f"Server '{s_name}' missing 'ipv4' or 'gateway'")
            continue

        try:
            s_ip_if = ipaddress.IPv4Interface(s_ip)
            gw_ip = ipaddress.IPv4Address(gateway)

            # Check duplicate IP
            s_ip_str = str(s_ip_if.ip)
            if s_ip_str in used_ips:
                errors.append(f"Duplicate IP {s_ip_str} on server '{s_name}' (already used by {used_ips[s_ip_str]})")
            else:
                used_ips[s_ip_str] = f"server '{s_name}'"

            # Check server IP within subnet
            if leaf_router.server_subnet:
                leaf_subnet = ipaddress.IPv4Network(leaf_router.server_subnet)
                if s_ip_if.ip not in leaf_subnet:
                    errors.append(f"Server '{s_name}' IP {s_ip} does not belong to Leaf '{conn_leaf}' server subnet {leaf_subnet}")
                if gw_ip not in leaf_subnet:
                    errors.append(f"Server '{s_name}' gateway {gateway} does not belong to Leaf '{conn_leaf}' server subnet {leaf_subnet}")

            # Check gateway matches leaf server interface IP
            if leaf_router.server_interface:
                leaf_gw = ipaddress.IPv4Interface(leaf_router.server_interface.ipv4).ip
                if gw_ip != leaf_gw:
                    errors.append(
                        f"Server '{s_name}' gateway {gateway} does not match leaf '{conn_leaf}' interface IP {leaf_gw}"
                    )

            if s_ip_if.ip == gw_ip:
                errors.append(f"Server '{s_name}' has the same IP as its gateway ({gateway})")

            # Link connected_server to leaf model
            leaf_router.connected_server = ConnectedServer(
                name=s_name,
                interface=s_iface,
                ipv4=s_ip,
                gateway=gateway,
            )

            servers.append(
                ServerNode(
                    name=s_name,
                    connected_to=conn_leaf,
                    leaf_interface=leaf_iface,
                    interface=s_iface,
                    ipv4=s_ip,
                    gateway=gateway,
                )
            )

        except ValueError as ve:
            errors.append(f"Server '{s_name}' addressing validation error: {ve}")

    if errors:
        raise InventoryValidationError(errors)

    return FabricInventory(
        lab=lab,
        ecmp=ecmp,
        ospf=ospf,
        bgp=bgp,
        routers=list(routers_dict.values()),
        links=links,
        servers=servers,
        raw_data=raw_data,
    )
