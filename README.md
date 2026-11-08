# Data Center Network Lab (Spine-Leaf Clos Fabric)

A working 2-tier Clos (Spine-Leaf) data center network running on **Containerlab** and **FRRouting (FRR)**. It implements an **OSPFv2 underlay**, an **eBGP overlay/service layer**, active-active **BGP ECMP**, and a custom Python CLI (`netauto`) that manages the entire lifecycle: inventory validation, Jinja2 config rendering, deployment, live routing table inspection, fault detection, and reporting.

---

## Topology

```
                       +-------------------+       +-------------------+
                       |      spine1       |       |      spine2       |
                       |     AS 65000      |       |     AS 65000      |
                       |    10.255.0.1     |       |    10.255.0.2     |
                       +-------------------+       +-------------------+
                         /   |       |   \           /   |       |   \
            10.0.0.0/31 /    |       |    \         /    |       |    \ 10.0.0.14/31
                       / 10.0.0.4/31 |     \       / 10.0.0.6/31 |     \
                      /      |  10.0.0.8/31 \     /      |  10.0.0.10/31\
                     /       |       |       \   /       |       |       \
               +-------+ +-------+ +-------+ +-------+
               | leaf1 | | leaf2 | | leaf3 | | leaf4 |
               |AS65101| |AS65102| |AS65103| |AS65104|
               |10.255.| |10.255.| |10.255.| |10.255.|
               |  1.1  | |  1.2  | |  1.3  | |  1.4  |
               +-------+ +-------+ +-------+ +-------+
                   |         |         |         |
      172.16.11.0/24|172.16.12.0/24|   |172.16.14.0/24
                   |         |         |         |
               +-------+ +-------+ +-------+ +-------+
               | host1 | | host2 | | host3 | | host4 |
               | .10   | | .10   | | .10   | | .10   |
               +-------+ +-------+ +-------+ +-------+
```

Each Leaf connects to both Spines via `/31` point-to-point links. Each Leaf also terminates one `/24` server subnet where an application container resides.

---

## IP Addressing & Autonomous Systems

### Loopback Interfaces (Router IDs)

| Router | Role | Loopback IPv4 | OSPF Router ID | BGP ASN |
|---|---|---|---|---|
| `spine1` | Spine | `10.255.0.1/32` | `10.255.0.1` | `65000` |
| `spine2` | Spine | `10.255.0.2/32` | `10.255.0.2` | `65000` |
| `leaf1` | Leaf | `10.255.1.1/32` | `10.255.1.1` | `65101` |
| `leaf2` | Leaf | `10.255.1.2/32` | `10.255.1.2` | `65102` |
| `leaf3` | Leaf | `10.255.1.3/32` | `10.255.1.3` | `65103` |
| `leaf4` | Leaf | `10.255.1.4/32` | `10.255.1.4` | `65104` |

### Fabric P2P Links (/31 RFC 3021)

| Link | Subnet | Spine Interface & IP | Leaf Interface & IP |
|---|---|---|---|
| `spine1 <-> leaf1` | `10.0.0.0/31` | `spine1:eth1` (`10.0.0.0`) | `leaf1:eth1` (`10.0.0.1`) |
| `spine2 <-> leaf1` | `10.0.0.2/31` | `spine2:eth1` (`10.0.0.2`) | `leaf1:eth2` (`10.0.0.3`) |
| `spine1 <-> leaf2` | `10.0.0.4/31` | `spine1:eth2` (`10.0.0.4`) | `leaf2:eth1` (`10.0.0.5`) |
| `spine2 <-> leaf2` | `10.0.0.6/31` | `spine2:eth2` (`10.0.0.6`) | `leaf2:eth2` (`10.0.0.7`) |
| `spine1 <-> leaf3` | `10.0.0.8/31` | `spine1:eth3` (`10.0.0.8`) | `leaf3:eth1` (`10.0.0.9`) |
| `spine2 <-> leaf3` | `10.0.0.10/31` | `spine2:eth3` (`10.0.0.10`) | `leaf3:eth2` (`10.0.0.11`) |
| `spine1 <-> leaf4` | `10.0.0.12/31` | `spine1:eth4` (`10.0.0.12`) | `leaf4:eth1` (`10.0.0.13`) |
| `spine2 <-> leaf4` | `10.0.0.14/31` | `spine2:eth4` (`10.0.0.14`) | `leaf4:eth2` (`10.0.0.15`) |

### Server Subnets

| Host | Leaf Gateway | Subnet | Host IP |
|---|---|---|---|
| `host1` | `leaf1:eth3` (`172.16.11.1`) | `172.16.11.0/24` | `172.16.11.10` |
| `host2` | `leaf2:eth3` (`172.16.12.1`) | `172.16.12.0/24` | `172.16.12.10` |
| `host3` | `leaf3:eth3` (`172.16.13.1`) | `172.16.13.0/24` | `172.16.13.10` |
| `host4` | `leaf4:eth3` (`172.16.14.1`) | `172.16.14.0/24` | `172.16.14.10` |

---

## Design Choices

1. **Why Spines share ASN 65000**:
   In BGP, path selection prioritizes shortest `AS_PATH`. If Spines used different AS numbers, any difference in path length would break multipath. With both Spines on `65000`, the route from `leaf1` to `172.16.12.0/24` has the exact same AS path length (`65000 65102`) whether learned through `spine1` or `spine2`. Combined with `maximum-paths 2` and `bgp bestpath as-path multipath-relax`, FRR installs both next-hops into the Linux kernel routing table.
   As a bonus, BGP loop prevention automatically blocks any accidental spine-to-spine transit if someone connects them.

2. **RFC 3021 /31 Subnets**:
   Traditional `/30` subnets waste two addresses per link on network and broadcast IDs (4 IPs allocated for 2 hosts). Using `/31` cuts underlay IP consumption in half and eliminates broadcast traffic on fabric links.

3. **OSPF Underlay + eBGP Overlay Boundary**:
   OSPF runs in Area 0 on fabric P2P links and loopbacks only. Interfaces are set to `ip ospf network point-to-point` so routers skip DR/BDR elections and converge instantly. Server subnets are intentionally kept out of OSPF and advertised only via eBGP, preserving a clean boundary between physical fabric routing and customer/workload subnets.

4. **Strict Route Filtering**:
   - Leafs advertise only their local server subnet to Spines via prefix-list (`PL-LOCAL-SERVER`).
   - Spines accept only valid `/24` server subnets (`172.16.0.0/16 ge 24 le 24`) and re-advertise them down to all Leafs.
   - No route redistribution between OSPF and BGP is permitted.

---

## Quickstart

### Prerequisites
- Linux (Ubuntu 22.04/24.04 or WSL2 on Windows 11)
- Python 3.11+
- Docker
- [Containerlab](https://containerlab.dev/install/)

```bash
# Clone the repository
git clone https://github.com/example/automated-dc-network-lab.git
cd automated-dc-network-lab

# Install python dependencies
pip install -r requirements.txt
pip install -e .
```

### 1. Validate the Inventory
Checks `inventory/fabric.yml` for duplicate IPs, missing neighbors, invalid `/31` pairs, ASN ranges, and gateway mismatches:
```bash
python -m netauto validate-inventory
```

### 2. Render Configurations
Generates Containerlab topology and per-router FRR configs (`frr.conf`, `daemons`, `vtysh.conf`) under `build/`:
```bash
python -m netauto render
```

### 3. Deploy the Fabric
Deploys the 6 FRR routers and 4 Linux hosts, then polls until all nodes and vtysh instances respond:
```bash
python -m netauto up
```

### 4. Run Automated Health Checks
Inspects OSPF neighbor states, BGP peering, routing tables, ECMP next-hops, and runs an inter-server ping matrix:
```bash
python -m netauto check
```

Example terminal output:
```text
==========================================
 Fabric Validation Status: PASS
==========================================

  - Containers: 10/10 online (PASS)
  - OSPF: 6/6 routers healthy
  - BGP: 6/6 routers healthy
  - ECMP: 4/4 leafs healthy
  - Connectivity: 12/12 tests passed (PASS)

[OK] Generated reports:
    - JSON: reports/latest.json
    - Markdown: reports/latest.md
```

### 5. Tear Down
Destroys the lab and cleans up bridge interfaces:
```bash
python -m netauto down
```

---

## The `netauto` CLI

| Command | Purpose |
|---|---|
| `python -m netauto validate-inventory` | Validates YAML inventory rules and constraints |
| `python -m netauto render` | Renders Jinja2 templates into `build/` |
| `python -m netauto up` | Deploys Containerlab topology and verifies node readiness |
| `python -m netauto apply` | Dynamically reloads running FRR routers (`vtysh -f`) with updated configs |
| `python -m netauto check` | Audits OSPF, BGP, ECMP, kernel routes, and host reachability |
| `python -m netauto report` | Generates detailed Markdown and JSON reports |
| `python -m netauto down` | Destroys the deployment and cleans up container resources |

---

## Verifying ECMP in Action

Log in to `leaf1` and check the kernel routing table for remote server subnets:
```bash
docker exec -it clab-dc-fabric-lab-leaf1 ip -4 route show 172.16.12.0/24
```
Output shows two equal-cost next-hops installed via both Spines:
```text
172.16.12.0/24 proto bgp metric 20
    nexthop via 10.0.0.0 dev eth1 weight 1
    nexthop via 10.0.0.2 dev eth2 weight 1
```

Now check FRR's BGP table:
```bash
docker exec -it clab-dc-fabric-lab-leaf1 vtysh -c "show bgp ipv4 unicast 172.16.12.0/24"
```
Both paths are marked with `*>` (multipath installed).

---

## Failure Injection Scenarios

Comprehensive walk-throughs and rollback commands are documented in [docs/failure-scenarios.md](docs/failure-scenarios.md).

### Scenario: Silent ECMP Redundancy Loss
Shut down the BGP peer on `leaf1` toward `spine2`:
```bash
docker exec clab-dc-fabric-lab-leaf1 vtysh -c "configure terminal" -c "router bgp 65101" -c "neighbor 10.0.0.2 shutdown"
```

1. **What happens**: The path via `10.0.0.2` drops out of the kernel FIB. Traffic fails over to `spine1` (`10.0.0.0`).
2. **The Catch**: Standard connectivity tests (`ping 172.16.12.10` from `host1`) **still succeed**, masking the outage.
3. **Detection**: Run `python -m netauto check`. The validator inspects the actual forwarding table and flags ECMP as `DEGRADED`:
   ```text
   [WARN] Detected issue:
       - [BGP ECMP] leaf1: DEGRADED: Only 1 path installed (10.0.0.0); redundancy lost!
   ```
4. **Recovery**:
   ```bash
   docker exec clab-dc-fabric-lab-leaf1 vtysh -c "configure terminal" -c "router bgp 65101" -c "no neighbor 10.0.0.2 shutdown"
   ```

Other failure scenarios documented:
- OSPF neighbor drop via link flap
- BGP session failure via bad remote-as
- OSPF stuck in `ExStart` due to MTU mismatch on P2P links

---

## Testing

The project includes an offline unit test suite and integration tests:

```bash
# Run 29 unit tests (runs offline without Docker in ~0.4s)
pytest -v tests/unit

# Run live integration tests (against deployed Containerlab nodes)
pytest -v -m integration
```

---

## Repository Structure

```
automated-dc-network-lab/
├── inventory/
│   └── fabric.yml              # Central inventory (nodes, links, subnets, ASNs)
├── templates/
│   ├── frr.conf.j2             # Jinja2 template for FRR routing daemons
│   ├── topology.clab.yml.j2    # Jinja2 template for Containerlab topology
│   ├── daemons.j2              # Enabled daemons (zebra, bgpd, ospfd)
│   ├── vtysh.conf.j2           # Integrated vtysh config
│   └── host-startup.sh.j2      # Host network startup script
├── src/
│   └── netauto/
│       ├── cli.py              # CLI commands (validate, render, up, check, etc.)
│       ├── inventory/          # Loader, models, validation rules
│       ├── rendering/          # Jinja2 config generation
│       ├── deployment/         # Containerlab & Docker lifecycle
│       ├── transport/          # Subprocess & mock execution
│       ├── protocols/          # OSPF and BGP parsers (JSON & text fallbacks)
│       ├── validation/         # Health checks, ECMP validator, ping tester
│       ├── reporting/          # Markdown and JSON report generators
│       └── utils/              # Command runner and logging
├── tests/
│   ├── unit/                   # 29 offline tests
│   ├── integration/            # Live container integration tests
│   └── fixtures/               # Realistic FRR command outputs
├── docs/                       # Architecture, addressing, and troubleshooting docs
├── scripts/                    # Shell helper scripts
└── pyproject.toml
```

---

## License

[MIT](LICENSE)
