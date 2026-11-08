# Data Center Network Health Report

## Overall Status

Status: 🟢 **PASS**

## Infrastructure

| Component | Expected | Actual | Status |
|---|---:|---:|---|
| Containers | 10 | 10 | PASS |
| OSPF neighbors | 6 | 0 | FAIL |
| BGP sessions | 6 | 0 | FAIL |
| ECMP paths | 1 | 1 | PASS |

## OSPF Details

| Router | Role | Router ID | Full / Expected | Status | Details |
|---|---|---|---:|---|---|
| spine1 | Spine | 10.255.0.1 | 0/4 | PASS | All 4 FULL |
| leaf1 | Leaf | 10.255.1.1 | 0/2 | PASS | All 2 FULL |

## BGP Details

| Router | Role | ASN | Established / Expected | Status | Details |
|---|---|---|---:|---|---|
| spine1 | Spine | 65000 | 0/4 | PASS | All 4 Established |
| leaf1 | Leaf | 65101 | 0/2 | PASS | All 2 Established |

## Routing Table Details

| Router | Expected Prefixes | Installed | Status | Details |
|---|---|---:|---|---|
| leaf1 | 1 | 0 | PASS | All routes installed |

## ECMP Details

| Leaf Router | Destination Prefix | Expected Paths | Installed Next Hops | Status |
|---|---|---:|---|---|
| leaf1 | 172.16.12.0/24 | 2 | 10.0.0.0, 10.0.0.2 | PASS |

## Connectivity Tests

Status: PASS (1/1 passed)

| Source | Destination | Target IP | Packets (Tx/Rx) | Loss % | Avg RTT | Status |
|---|---|---|---:|---:|---:|---|
| host1 | host2 | 172.16.12.10 | 3/3 | 0.0% | 0.45 ms | PASS |

## Failures

No failures detected. Fabric is operating at 100% health.

## Timestamp

Report generated at: `2026-11-07T21:00:00Z` (UTC)
