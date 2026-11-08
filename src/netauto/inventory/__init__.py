"""Inventory package for netauto."""

from netauto.inventory.loader import InventoryLoadError, load_raw_inventory
from netauto.inventory.models import (
    FabricInventory,
    Router,
    FabricLink,
    ServerNode,
    LoopbackConfig,
    OspfNodeConfig,
    FabricInterface,
    BgpNeighbor,
)
from netauto.inventory.validator import InventoryValidationError, validate_and_build_inventory

__all__ = [
    "InventoryLoadError",
    "InventoryValidationError",
    "load_raw_inventory",
    "validate_and_build_inventory",
    "FabricInventory",
    "Router",
    "FabricLink",
    "ServerNode",
    "LoopbackConfig",
    "OspfNodeConfig",
    "FabricInterface",
    "BgpNeighbor",
]
