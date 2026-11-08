# Data Center Fabric Architecture

## 1. Overview

This project implements an automated, production-grade 2-tier Spine-Leaf (Clos) Data Center fabric simulated using [Containerlab](https://containerlab.dev/) and [FRRouting (FRR)](https://frrouting.org/).

The architecture connects 2 Spine switches, 4 Leaf switches, and 4 Linux application server containers into a non-blocking, multi-path forwarding fabric.

```mermaid
flowchart TD
    subgraph SPINES ["Spine Layer (AS 65000)"]
        SPINE1["spine1\nRouter ID: 10.255.0.1\nASN: 65000"]
        SPINE2["spine2\nRouter ID: 10.255.0.2\nASN: 65000"]
    end

    subgraph LEAFS ["Leaf Layer (AS 65101 - 65104)"]
        LEAF1["leaf1\nRouter ID: 10.255.1.1\nASN: 65101"]
        LEAF2["leaf2\nRouter ID: 10.255.1.2\nASN: 65102"]
        LEAF3["leaf3\nRouter ID: 10.255.1.3\nASN: 65103"]
        LEAF4["leaf4\nRouter ID: 10.255.1.4\nASN: 65104"]
    end

    subgraph HOSTS ["Application Server Layer"]
        HOST1["host1\n172.16.11.10/24\nGW: 172.16.11.1"]
        HOST2["host2\n172.16.12.10/24\nGW: 172.16.12.1"]
        HOST3["host3\n172.16.13.10/24\nGW: 172.16.13.1"]
        HOST4["host4\n172.16.14.10/24\nGW: 172.16.14.1"]
    end

    %% Spine1 Links
    SPINE1 ---|10.0.0.0/31| LEAF1
    SPINE1 ---|10.0.0.4/31| LEAF2
    SPINE1 ---|10.0.0.8/31| LEAF3
    SPINE1 ---|10.0.0.12/31| LEAF4

    %% Spine2 Links
    SPINE2 ---|10.0.0.2/31| LEAF1
    SPINE2 ---|10.0.0.6/31| LEAF2
    SPINE2 ---|10.0.0.10/31| LEAF3
    SPINE2 ---|10.0.0.14/31| LEAF4

    %% Server Links
    LEAF1 ---|172.16.11.0/24| HOST1
    LEAF2 ---|172.16.12.0/24| HOST2
    LEAF3 ---|172.16.13.0/24| HOST3
    LEAF4 ---|172.16.14.0/24| HOST4
```

---

## 2. Architectural Principles

### 2.1 Why Clos / Spine-Leaf?
Traditional three-tier data center architectures (Core-Aggregation-Access) relied heavily on Spanning Tree Protocol (STP) to eliminate switching loops. STP prevents loops by blocking redundant links, effectively wasting 50% or more of available bisectional bandwidth.

In contrast, a 2-Tier Spine-Leaf Clos architecture:
1. **Eliminates STP**: Every link is an active Layer 3 routed interface.
2. **Deterministic Latency**: Exactly 2 hops between any pair of servers connected to different Leafs (`Host -> Leaf -> Spine -> Leaf -> Host`).
3. **Equal-Cost Multi-Pathing (ECMP)**: Traffic across multiple Spine switches is load-balanced based on L3/L4 packet hashing.
4. **Horizontal Scalability (Scale-Out)**: Throughput can be scaled out by adding more Spine switches; capacity can be scaled out by adding more Leaf switches.

### 2.2 Clos Rules
1. **No Spine-to-Spine Links**: Spines do not connect directly to one another. Traffic between Spines is never routed east-west.
2. **No Leaf-to-Leaf Links**: Leafs do not peer directly with each other in this tier. All inter-leaf traffic traverses the Spine tier.
3. **Every Leaf Connects to Every Spine**: Guarantees maximum path redundancy and fault isolation. If any single Spine fails, bandwidth drops by 50%, but zero destination subnets lose connectivity.

---

## 3. Node Inventory

| Node Name | Node Role | Base Image | Purpose |
|---|---|---|---|
| `spine1` | Spine Switch | `quay.io/frrouting/frr:10.2.1` | Core transit router for spine-leaf fabric |
| `spine2` | Spine Switch | `quay.io/frrouting/frr:10.2.1` | Core transit router for redundant pathing |
| `leaf1` | Leaf Switch | `quay.io/frrouting/frr:10.2.1` | Top-of-Rack (ToR) switch for Host 1 subnet |
| `leaf2` | Leaf Switch | `quay.io/frrouting/frr:10.2.1` | Top-of-Rack (ToR) switch for Host 2 subnet |
| `leaf3` | Leaf Switch | `quay.io/frrouting/frr:10.2.1` | Top-of-Rack (ToR) switch for Host 3 subnet |
| `leaf4` | Leaf Switch | `quay.io/frrouting/frr:10.2.1` | Top-of-Rack (ToR) switch for Host 4 subnet |
| `host1` | Server Node | `alpine:3.20` | Workload container in 172.16.11.0/24 |
| `host2` | Server Node | `alpine:3.20` | Workload container in 172.16.12.0/24 |
| `host3` | Server Node | `alpine:3.20` | Workload container in 172.16.13.0/24 |
| `host4` | Server Node | `alpine:3.20` | Workload container in 172.16.14.0/24 |

---

## 4. Fabric Links Summary

- **8 Router-to-Router Point-to-Point Links**:
  - `/31` subnets per RFC 3021.
  - Configured with `ip ospf network point-to-point`.
  - Directly establish single-hop eBGP neighbor relationships.
- **4 Server-to-Leaf Access Links**:
  - `/24` subnets per Leaf.
  - Leaf acts as default gateway (`.1`).
  - No OSPF running on host-facing interfaces (security & stability boundary).
