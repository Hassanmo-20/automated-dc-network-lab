# Engineering Design Decisions & Interview Deep-Dive

This document details the architectural reasoning and technical tradeoffs behind the design choices implemented in this lab. It is tailored for technical interviews at companies like Meta, Google, and Amazon for Production Engineering, Network Engineering, and Infrastructure roles.

---

## 1. Why Spine-Leaf (Clos) Architecture?

### Context & Problem
In legacy 3-tier networks (Access, Aggregation, Core), links between switches were Layer 2 trunks protected by Spanning Tree Protocol (STP). STP avoids loops by blocking redundant links, resulting in 50% or more of bandwidth remaining completely idle. East-West traffic (server-to-server) had to travel up to the aggregation/core layer, creating major bottlenecks and variable latency.

### Decision
Implement a 2-Tier Clos topology where every Leaf connects to every Spine, with no horizontal (Leaf-Leaf or Spine-Spine) links.
- **Predictable Latency**: Any server communicates with any other server across exactly 3 switch hops (`Leaf1 -> Spine -> Leaf2`).
- **Full Bandwidth Utilization**: Every physical link is actively forwarding traffic via Equal-Cost Multi-Pathing (ECMP).
- **Scale-Out Economics**: To add compute, add Leafs. To add bisectional bandwidth, add Spines.

---

## 2. Why RFC 3021 /31 Subnets for Point-to-Point Links?

### Context & Problem
A standard IPv4 subnet requires a network address and a broadcast address. For a point-to-point link between two routers, a `/30` subnet was historically used, which consumes 4 IP addresses to support only 2 usable devices (50% address waste).

### Decision
Use `/31` subnets per RFC 3021.
- In a `/31` subnet, the two addresses (e.g. `10.0.0.0` and `10.0.0.1`) are both usable host addresses.
- Saves 50% of underlay address space.
- Eliminates directed broadcast packets, reducing CPU overhead and potential DDoS attack surfaces.

---

## 3. Why Loopbacks as Router IDs?

### Context & Problem
If a routing protocol selects a Router ID from an active physical interface (e.g., `eth1`), and that interface flaps or goes down, the Router ID may change or become unreachable, forcing neighbor reconvergence or tearing down BGP sessions.

### Decision
Dedicate a virtual `lo` loopback interface with a `/32` address to every router (e.g., `10.255.0.1/32` for `spine1`).
- Loopback interfaces never go down unless the switch itself crashes.
- Provides a stable, permanent identifier for OSPF Router ID, BGP Router ID, and out-of-band management.

---

## 4. Why OSPF for the Underlay?

### Decision
OSPFv2 is used strictly within the network fabric to establish reachability for loopbacks and physical links.
- **Fast Convergence**: Link-state updates (LSAs) flood rapidly using Dijkstra's algorithm.
- **Point-to-Point Mode**: Configuring `ip ospf network point-to-point` skips DR/BDR election, eliminating 40 seconds of startup delay.
- **Protocol Decoupling**: Having OSPF as an independent underlay allows engineers to diagnose physical connectivity and fabric health independently from customer/application routing.

---

## 5. Why eBGP Between Leafs and Spines?

### Decision
eBGP (External BGP) is used between each Leaf and both Spines.
- **Policy Control**: BGP provides rich attribute manipulation (AS_PATH, Community, Local Preference, Prefix Lists, Route Maps) that IGPs like OSPF lack.
- **Fault Domain Isolation**: BGP does not flood link-state across the whole network. If an access link flaps on `leaf1`, only `leaf1` sends a BGP update/withdrawal. The other leafs do not recompute a full Dijkstra tree.
- **Hyperscale Proven**: As documented in RFC 7938, hyperscale networks (Meta, Google, Microsoft) use BGP exclusively across their data center fabrics.

---

## 6. Why Assign the Same ASN (65000) to Both Spines?

### Context & Problem
In eBGP, if two paths have different AS_PATH lengths, BGP strictly prefers the shorter path. Furthermore, if they have different AS numbers, standard BGP multipath may consider them non-equivalent.

### Decision
Both `spine1` and `spine2` belong to ASN `65000`.
- **Identical AS_PATH**: When `leaf1` learns about `leaf2`'s subnet `172.16.12.0/24`:
  - Via `spine1`: AS_PATH is `[65000, 65102]`
  - Via `spine2`: AS_PATH is `[65000, 65102]`
- Because the AS_PATH, Local Preference, Origin, and MED match identically, BGP enters multipath evaluation and installs **two equal-cost paths** into the forwarding table.
- **Loop Prevention**: If an accidental link were created between `spine1` and `spine2`, BGP's loop prevention rule (discard updates containing local ASN in `AS_PATH`) immediately drops the update, preventing routing loops between Spines.

---

## 7. How Does BGP Choose the Best Path?

The BGP best-path decision algorithm evaluates paths in this strict order:
1. Highest **Weight** (Cisco/vendor proprietary, local to switch).
2. Highest **Local Preference** (default 100).
3. Locally originated routes (via `network` or `redistribute`).
4. Shortest **AS_PATH**.
5. Lowest **Origin** code (IGP < EGP < Incomplete).
6. Lowest **MED** (Multi-Exit Discriminator).
7. eBGP over iBGP.
8. Lowest IGP metric to next hop.
9. **Multipath evaluation**: If `maximum-paths` is configured and steps 1–8 are tied, install up to $N$ multipath next hops!
10. Lowest BGP Router ID.

---

## 8. What Happens When One Spine Fails?

1. **Failure Event**: `spine1` loses power or crashes.
2. **Detection**: BGP keepalive timeout expires (or interface link goes down immediately).
3. **Withdrawal**: `leaf1` removes `10.0.0.0` from its multipath group.
4. **Sub-Second Convergence**: The Linux kernel seamlessly routes 100% of traffic via `spine2` (`10.0.0.2`).
5. **Impact**: Zero packet loss after convergence. Bisectional bandwidth is reduced from 200 Gbps to 100 Gbps, but all 4 server subnets remain completely reachable.
6. **Automation Detection**: `python -m netauto check` flags ECMP as `DEGRADED`, alerting the operations team before a second failure can take down the network.

---

## 9. Why YAML as the Single Source of Truth?

- Avoids configuration drift across 6 different switches.
- Machine-readable, human-friendly, and version-controlled via Git.
- Enables automated pre-flight validation (duplicate IP checks, subnet validation, ASN range verification) before a single configuration line is touched.

---

## 10. Why Jinja2 Templating?

- Decouples business logic and network definitions from vendor-specific syntax.
- Reusable: Adding 10 more Leafs requires adding entries to `inventory/fabric.yml`, not handwriting 10 new 100-line router configuration files.

---

## 11. Why Docker CLI Subprocess Over Netmiko/SSH Initially?

- **Zero-Dependency Bootstrap**: In containerized environments, SSH servers inside network nodes add unnecessary memory footprint, keys, and startup delays.
- **Fail-Safe Reliability**: `docker exec` works directly through the container runtime socket. It does not depend on network reachability or credentials.
- **Clean Interface Abstraction**: Our `Transport` class abstracts this completely, allowing a `NetmikoSSHTransport` to be dropped in seamlessly in the future without modifying any validation or protocol code.
