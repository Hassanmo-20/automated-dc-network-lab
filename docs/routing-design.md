# Routing Protocol Design

This document describes the dual-layer routing architecture of the Data Center fabric: **OSPFv2 Underlay** and **eBGP Overlay/Service Layer**.

---

## 1. Underlay Routing: OSPFv2

OSPFv2 serves as the link-state interior gateway protocol for the physical fabric switches.

### 1.1 Responsibilities
- Provide IP reachability across all router loopbacks (`10.255.0.0/24`) and point-to-point links (`10.0.0.0/24`).
- Support fast convergence for link state changes.
- Act as an independent protocol layer that can be monitored without depending on BGP.

### 1.2 Configuration Details
- **Process ID**: `1`
- **Area**: `0.0.0.0` (Backbone Area)
- **Interface Network Type**: `ip ospf network point-to-point`
  - On point-to-point links, OSPF bypasses Designated Router (DR) / Backup Designated Router (BDR) election. Adjacencies transition directly from `Init -> 2-Way -> ExStart -> Exchange -> Loading -> Full`.
- **Loopback**: `passive-interface lo`
  - Advertises the router's `/32` loopback without sending unnecessary OSPF Hellos.
- **Reference Bandwidth**: `100000` (100 Gbps reference)
  - Ensures accurate link metrics for 10G/25G/40G/100G interfaces.
- **Boundary Restriction**: Host-facing interfaces (`eth3` on Leafs) are **never** placed into OSPF.

---

## 2. Service & Inter-Leaf Routing: eBGP

BGP is the industry-standard routing protocol for hyperscale Data Center fabrics (RFC 7938: *Use of BGP for Routing in Large-Scale Data Centers*).

### 2.1 Autonomous System Numbers (ASN) Design

| Router Tier | Router | ASN | ASN Type |
|---|---|---|---|
| Spine Tier | `spine1` | `65000` | 2-byte Private ASN |
| Spine Tier | `spine2` | `65000` | 2-byte Private ASN |
| Leaf Tier | `leaf1` | `65101` | 2-byte Private ASN |
| Leaf Tier | `leaf2` | `65102` | 2-byte Private ASN |
| Leaf Tier | `leaf3` | `65103` | 2-byte Private ASN |
| Leaf Tier | `leaf4` | `65104` | 2-byte Private ASN |

### 2.2 Why Both Spines Share ASN 65000
Assigning the same ASN (`65000`) to both Spine switches is a crucial architectural decision:
1. **Loop Prevention Across Spines**: If a link were ever inadvertently added between Spines or misconfigured, BGP's default loop detection would reject routes containing `65000` in their `AS_PATH`.
2. **Equivalent AS_PATH Lengths for ECMP**:
   When `leaf1` learns the route to `leaf2` (`172.16.12.0/24`):
   - Path via `spine1`: `AS_PATH = 65000 65102` (length = 2)
   - Path via `spine2`: `AS_PATH = 65000 65102` (length = 2)
   Because the AS numbers, AS_PATH length, Local Preference, Origin, and MED are identical, BGP multipath installs both paths as equal-cost next hops.

---

## 3. Equal-Cost Multi-Path (ECMP) Mechanics

When `leaf1` forwards a packet destined to `172.16.12.10`:
1. BGP installs both `10.0.0.0` (spine1) and `10.0.0.2` (spine2) into the Linux kernel FIB (`ip -4 route show 172.16.12.0/24`).
2. The Linux kernel uses a 5-tuple hash of the packet header:
   $$\text{Hash} = f(\text{Src IP}, \text{Dst IP}, \text{IP Protocol}, \text{Src Port}, \text{Dst Port})$$
3. Packets belonging to the same flow are directed over the same next-hop to avoid out-of-order packet delivery, while distinct flows are balanced equally across both Spines.

---

## 4. Route Filtering and Safety Policies

Unrestricted route redistribution causes catastrophic routing loops and route table bloat in large fabrics. This lab enforces strict, defense-in-depth route policies using prefix-lists and route-maps:

### 4.1 Leaf Outbound Policy (`RM-SPINE-OUT`)
```text
ip prefix-list PL-LOCAL-SERVER seq 10 permit <LOCAL_SUBNET>
route-map RM-SPINE-OUT permit 10
 match ip address prefix-list PL-LOCAL-SERVER
```
- **Guarantees**: A leaf advertises **only** its directly attached tenant subnet. It never leaks underlay routes or routes learned from another Spine.

### 4.2 Spine Inbound Policy (`RM-LEAF-IN`)
```text
ip prefix-list PL-DC-SERVERS seq 10 permit 172.16.0.0/16 ge 24 le 24
route-map RM-LEAF-IN permit 10
 match ip address prefix-list PL-DC-SERVERS
```
- **Guarantees**: Spines only accept valid `/24` server prefixes within `172.16.0.0/16`. Rogue or overlapping prefixes are dropped on ingress.

### 4.3 Spine Outbound Policy (`RM-LEAF-OUT`)
```text
route-map RM-LEAF-OUT permit 10
 match ip address prefix-list PL-DC-SERVERS
```
- **Guarantees**: Spines propagate only valid tenant prefixes back down to the Leafs.
