"""Validation package for netauto."""

from netauto.validation.connectivity import ConnectivityMatrixResult, ConnectivityTester, PingResult
from netauto.validation.ecmp import EcmpPrefixResult, EcmpValidator, LeafEcmpHealth
from netauto.validation.engine import (
    ContainerHealthSummary,
    FailureDetail,
    ValidationEngine,
    ValidationReportData,
)
from netauto.validation.routing_table import (
    RouteEntry,
    RouterRoutingHealth,
    RoutingTableInspector,
)

__all__ = [
    "ConnectivityMatrixResult",
    "ConnectivityTester",
    "PingResult",
    "EcmpPrefixResult",
    "EcmpValidator",
    "LeafEcmpHealth",
    "ContainerHealthSummary",
    "FailureDetail",
    "ValidationEngine",
    "ValidationReportData",
    "RouteEntry",
    "RouterRoutingHealth",
    "RoutingTableInspector",
]
