# IP Addressing Plan

This document specifies the complete IPv4 addressing architecture for the Spine-Leaf fabric.

---

## 1. Loopback Addresses (Underlay Router IDs)

All routers configure a dedicated `/32` loopback (`lo`) interface.
Loopback addresses serve as stable, protocol-independent Router IDs for OSPF and BGP.

| Device | Role | Loopback IPv4 | OSPF Router ID | BGP Router ID | Purpose |
|---|---|---|---|---|---|
| `spine1` | Spine | `10.255.0.1/32` | `10.255.0.1` | `10.255.0.1` | Management & Underlay Identifier |
| `spine2` | Spine | `10.255.0.2/32` | `10.255.0.2` | `10.255.0.2` | Management & Underlay Identifier |
| `leaf1` | Leaf | `10.255.1.1/32` | `10.255.1.1` | `10.255.1.1` | Management & Underlay Identifier |
| `leaf2` | Leaf | `10.255.1.2/32` | `10.255.1.2` | `10.255.1.2` | Management & Underlay Identifier |
| `leaf3` | Leaf | `10.255.1.3/32` | `10.255.1.3` | `10.255.1.3` | Management & Underlay Identifier |
| `leaf4` | Leaf | `10.255.1.4/32` | `10.255.1.4` | `10.255.1.4` | Management & Underlay Identifier |

> [!NOTE]
> Loopback interfaces are marked as `passive-interface lo` in OSPF to ensure their /32 prefixes are advertised across the fabric without transmitting OSPF Hellos.

---

## 2. Fabric Point-to-Point Links (/31 Subnets)

All inter-switch links utilize `/31` subnets conforming to **RFC 3021** (*Using 31-Bit Prefixes on IPv4 Point-to-Point Links*).

### Why /31 instead of /30?
In traditional IPv4 networking, a `/30` subnet consumes 4 IP addresses:
- 1 Network address (e.g. `10.0.0.0`)
- 2 Usable host addresses (`10.0.0.1`, `10.0.0.2`)
- 1 Broadcast address (e.g. `10.0.0.3`)

RFC 3021 defines point-to-point links using `/31` (2 addresses total). Neither address is reserved for broadcast or network identifiers. This halves IPv4 address consumption and prevents directed broadcast attacks on fabric links.

| Link | Subnet | Spine Node & Port | Spine IP | Leaf Node & Port | Leaf IP |
|---|---|---|---|---|---|
| `spine1 - leaf1` | `10.0.0.0/31` | `spine1:eth1` | `10.0.0.0` | `leaf1:eth1` | `10.0.0.1` |
| `spine2 - leaf1` | `10.0.0.2/31` | `spine2:eth1` | `10.0.0.2` | `leaf1:eth2` | `10.0.0.3` |
| `spine1 - leaf2` | `10.0.0.4/31` | `spine1:eth2` | `10.0.0.4` | `leaf2:eth1` | `10.0.0.5` |
| `spine2 - leaf2` | `10.0.0.6/31` | `spine2:eth2` | `10.0.0.6` | `leaf2:eth2` | `10.0.0.7` |
| `spine1 - leaf3` | `10.0.0.8/31` | `spine1:eth3` | `10.0.0.8` | `leaf3:eth1` | `10.0.0.9` |
| `spine2 - leaf3` | `10.0.0.10/31` | `spine2:eth3` | `10.0.0.10` | `leaf3:eth2` | `10.0.0.11` |
| `spine1 - leaf4` | `10.0.0.12/31` | `spine1:eth4` | `10.0.0.12` | `leaf4:eth1` | `10.0.0.13` |
| `spine2 - leaf4` | `10.0.0.14/31` | `spine2:eth4` | `10.0.0.14` | `leaf4:eth2` | `10.0.0.15` |

---

## 3. Server Subnets & Gateways

Each Leaf switch connects to an isolated server subnet. Servers configure their default route pointing to their connected Leaf's server interface IP.

| Leaf Switch | Server Subnet | Leaf Interface & IP | Connected Server | Server IP | Default Gateway |
|---|---|---|---|---|---|
| `leaf1` | `172.16.11.0/24` | `eth3` (`172.16.11.1/24`) | `host1` | `172.16.11.10/24` | `172.16.11.1` |
| `leaf2` | `172.16.12.0/24` | `eth3` (`172.16.12.1/24`) | `host2` | `172.16.12.10/24` | `172.16.12.1` |
| `leaf3` | `172.16.13.0/24` | `eth3` (`172.16.13.1/24`) | `host3` | `172.16.13.10/24` | `172.16.13.1` |
| `leaf4` | `172.16.14.0/24` | `eth3` (`172.16.14.1/24`) | `host4` | `172.16.14.10/24` | `172.16.14.1` |

> [!IMPORTANT]
> Server interfaces and subnets are strictly excluded from OSPF. They are advertised exclusively via eBGP, establishing an architectural boundary between the physical underlay infrastructure and tenant workload prefixes.
