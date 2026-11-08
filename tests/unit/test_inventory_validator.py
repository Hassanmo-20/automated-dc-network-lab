"""Unit tests for inventory validation rules and constraints."""

import pytest
import copy
from netauto.inventory.loader import load_raw_inventory
from netauto.inventory.validator import InventoryValidationError, validate_and_build_inventory


@pytest.fixture
def base_inventory():
    """Load valid base inventory for mutation testing."""
    return load_raw_inventory("inventory/fabric.yml")


def test_valid_inventory_build(base_inventory):
    """Ensure baseline inventory validates cleanly."""
    inv = validate_and_build_inventory(base_inventory)
    assert len(inv.routers) == 6
    assert len(inv.links) == 8
    assert len(inv.servers) == 4
    assert inv.ecmp.maximum_paths == 2


def test_missing_required_section(base_inventory):
    """Ensure missing top-level section fails validation."""
    data = copy.deepcopy(base_inventory)
    del data["routers"]
    with pytest.raises(InventoryValidationError) as exc_info:
        validate_and_build_inventory(data)
    assert "Missing required top-level section: 'routers'" in str(exc_info.value)


def test_duplicate_router_name(base_inventory):
    """Ensure duplicate router names are rejected."""
    data = copy.deepcopy(base_inventory)
    data["routers"].append(copy.deepcopy(data["routers"][0]))
    with pytest.raises(InventoryValidationError) as exc_info:
        validate_and_build_inventory(data)
    assert "Duplicate router name found" in str(exc_info.value)


def test_invalid_asn(base_inventory):
    """Ensure out-of-range ASN is rejected."""
    data = copy.deepcopy(base_inventory)
    data["routers"][0]["asn"] = 0
    with pytest.raises(InventoryValidationError) as exc_info:
        validate_and_build_inventory(data)
    assert "invalid ASN" in str(exc_info.value)


def test_duplicate_ip_address(base_inventory):
    """Ensure duplicate loopback or interface IP is detected."""
    data = copy.deepcopy(base_inventory)
    # Give spine2 same loopback as spine1
    data["routers"][1]["loopback"]["ipv4"] = "10.255.0.1/32"
    with pytest.raises(InventoryValidationError) as exc_info:
        validate_and_build_inventory(data)
    assert "Duplicate IP 10.255.0.1" in str(exc_info.value)


def test_duplicate_interface_on_router(base_inventory):
    """Ensure multiple links using the same interface on a router fail."""
    data = copy.deepcopy(base_inventory)
    # Link 1: spine1:eth1 -> leaf1:eth1
    # Change link 2 from spine2:eth1 to spine1:eth1
    data["links"][1]["source"]["node"] = "spine1"
    data["links"][1]["source"]["interface"] = "eth1"
    with pytest.raises(InventoryValidationError) as exc_info:
        validate_and_build_inventory(data)
    assert "Duplicate interface 'eth1' on router 'spine1'" in str(exc_info.value)


def test_mismatched_p2p_subnet(base_inventory):
    """Ensure P2P endpoints must belong to the same /31 subnet."""
    data = copy.deepcopy(base_inventory)
    data["links"][0]["target"]["ipv4"] = "10.0.0.5/31"
    with pytest.raises(InventoryValidationError) as exc_info:
        validate_and_build_inventory(data)
    assert "belong to different subnets" in str(exc_info.value)


def test_link_nonexistent_node(base_inventory):
    """Ensure links referencing unknown nodes are rejected."""
    data = copy.deepcopy(base_inventory)
    data["links"][0]["source"]["node"] = "phantom_spine"
    with pytest.raises(InventoryValidationError) as exc_info:
        validate_and_build_inventory(data)
    assert "not in defined routers" in str(exc_info.value)


def test_server_gateway_mismatch(base_inventory):
    """Ensure server gateway must match leaf server interface IP."""
    data = copy.deepcopy(base_inventory)
    data["servers"][0]["gateway"] = "172.16.11.254"
    with pytest.raises(InventoryValidationError) as exc_info:
        validate_and_build_inventory(data)
    assert "does not match leaf 'leaf1' interface IP" in str(exc_info.value)
