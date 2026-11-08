# Failure Scenarios and Chaos Engineering

This document details deliberate network failure injections, symptoms, automated detection, root cause analysis, and recovery procedures.

---

## Scenario 1: OSPF Neighbor Failure (Link Flap / Interface Shutdown)

### 1. Initial Healthy State
- `spine1` has 4 OSPF neighbors in `FULL` state.
- `leaf1` has 2 OSPF neighbors in `FULL` state.

### 2. Failure Injection
Shut down the interface connecting `leaf1` to `spine1`:
```bash
docker exec clab-dc-fabric-lab-leaf1 vtysh -c "configure terminal" -c "interface eth1" -c "shutdown"
```

### 3. Observed Symptoms
- OSPF Dead Timer expires on `spine1:eth1`.
- `show ip ospf neighbor` on `spine1` drops from 4 to 3 neighbors.
- Underlay connectivity between `10.0.0.0` and `10.0.0.1` is lost.

### 4. Automated Detection
Run `python -m netauto check`:
- **OSPF Status**: `DEGRADED` on `spine1` (3/4 neighbors Full) and `leaf1` (1/2 neighbors Full).
- **Diagnostics Output**:
  ```text
  [!] Detected issue:
      - [OSPFv2] spine1: 3/4 neighbors FULL. Total neighbors observed: 3
  ```

### 5. Recovery Procedure & Rollback
Re-enable the interface:
```bash
docker exec clab-dc-fabric-lab-leaf1 vtysh -c "configure terminal" -c "interface eth1" -c "no shutdown"
```

### 6. Validation After Recovery
```bash
python -m netauto check
# All OSPF neighbors return to FULL.
```

---

## Scenario 2: BGP Session Failure (ASN Mismatch)

### 1. Initial Healthy State
- `leaf2` has 2 BGP peers (`10.0.0.4` and `10.0.0.6`) in `Established` state.

### 2. Failure Injection
Configure an incorrect remote ASN for `spine1` on `leaf2`:
```bash
docker exec clab-dc-fabric-lab-leaf2 vtysh -c "configure terminal" -c "router bgp 65102" -c "neighbor 10.0.0.4 remote-as 65999"
```

### 3. Observed Symptoms
- BGP session to `10.0.0.4` drops immediately.
- BGP state transitions to `Active` or `Connect`.
- FRR logs show: `NOTIFICATION: sent to neighbor 10.0.0.4 2/2 (OPEN Message Error/Bad Peer AS)`.

### 4. Automated Detection
Run `python -m netauto check`:
- **BGP Status**: `DEGRADED` on `leaf2` (1/2 peers Established).
- **Failure Report**:
  ```text
  Failure: leaf2 (eBGP)
  Expected State: 2 peers Established
  Actual State: 1/2 peers Established. Total peers observed: 2
  Explanation: BGP session failure on leaf2. Check ASN configuration, peering IP, or firewall.
  ```

### 5. Recovery Procedure & Rollback
Restore the correct remote ASN (`65000`):
```bash
docker exec clab-dc-fabric-lab-leaf2 vtysh -c "configure terminal" -c "router bgp 65102" -c "neighbor 10.0.0.4 remote-as 65000"
```

### 6. Validation After Recovery
Verify session returns to `Established` via `python -m netauto check`.

---

## Scenario 3: ECMP Redundancy Loss (Silent Degradation)

### 1. Initial Healthy State
- On `leaf1`, routes to `172.16.12.0/24`, `172.16.13.0/24`, and `172.16.14.0/24` each have **two** equal-cost next hops (`10.0.0.0` and `10.0.0.2`).
- Server `host1` pings `host2` successfully.

### 2. Failure Injection
Disable the BGP session between `leaf1` and `spine2`:
```bash
docker exec clab-dc-fabric-lab-leaf1 vtysh -c "configure terminal" -c "router bgp 65101" -c "neighbor 10.0.0.2 shutdown"
```

### 3. Observed Symptoms
- BGP withdraws the path via `10.0.0.2`.
- Linux kernel routing table on `leaf1` collapses from 2 next-hops to 1 next-hop:
  ```text
  172.16.12.0/24 proto bgp metric 20
      nexthop via 10.0.0.0 dev eth1 weight 1
  ```
- **Crucial Production Insight**: Ping tests between `host1` and `host2` **still succeed** because traffic fails over to `spine1`. Ordinary connectivity monitoring would report green!

### 4. Automated Detection
Run `python -m netauto check`:
- **Overall Status**: `DEGRADED`
- **ECMP Validation**:
  ```text
  [!] Detected issue:
      - [BGP ECMP] leaf1: DEGRADED: Only 1 path installed (10.0.0.0); redundancy lost!
  ```
The automation tool successfully catches silent redundancy loss before a secondary outage causes a complete black hole.

### 5. Recovery Procedure & Rollback
```bash
docker exec clab-dc-fabric-lab-leaf1 vtysh -c "configure terminal" -c "router bgp 65101" -c "no neighbor 10.0.0.2 shutdown"
```

### 6. Validation After Recovery
`python -m netauto check` confirms 2 next-hops restored.

---

## Scenario 4: MTU Mismatch on Fabric Link

### 1. Initial Healthy State
- All links configured with standard MTU 1500 bytes.
- OSPF adjacency between `spine1` and `leaf3` is `FULL`.

### 2. Failure Injection
Change the MTU on `leaf3:eth1` from 1500 to 1400:
```bash
docker exec clab-dc-fabric-lab-leaf3 ip link set dev eth1 mtu 1400
docker exec clab-dc-fabric-lab-leaf3 vtysh -c "clear ip ospf process"
```

### 3. Observed Symptoms & RFC Behavior
- RFC 2328 specifies that routers exchange MTU in Database Description (DBD) packets.
- When `spine1` (MTU 1500) receives a DBD from `leaf3` (MTU 1400), it drops the DBD or rejects the neighbor because the neighbor cannot receive packets larger than 1400 bytes without IP fragmentation.
- The adjacency gets stuck in `ExStart` or `Exchange` state.

### 4. Diagnostics Commands
```bash
docker exec clab-dc-fabric-lab-spine1 vtysh -c "show ip ospf neighbor"
# Neighbor 10.255.1.3 state will show "ExStart/DROther" or "Exchange/DROther" instead of "Full".
```

### 5. Recovery Procedure & Rollback
Restore MTU 1500 on `leaf3:eth1`:
```bash
docker exec clab-dc-fabric-lab-leaf3 ip link set dev eth1 mtu 1500
```
Adjacency transitions immediately: `ExStart -> Exchange -> Loading -> Full`.
