"""Unit tests for inventory loading."""

import pytest
from pathlib import Path
from netauto.inventory.loader import InventoryLoadError, load_raw_inventory


def test_load_valid_inventory():
    """Verify loading existing inventory/fabric.yml succeeds."""
    data = load_raw_inventory("inventory/fabric.yml")
    assert isinstance(data, dict)
    assert "lab" in data
    assert "routers" in data
    assert "links" in data
    assert "servers" in data


def test_load_missing_inventory(tmp_path):
    """Verify missing file raises InventoryLoadError."""
    missing = tmp_path / "nonexistent.yml"
    with pytest.raises(InventoryLoadError) as exc_info:
        load_raw_inventory(missing)
    assert "not found" in str(exc_info.value).lower()


def test_load_malformed_yaml(tmp_path):
    """Verify malformed YAML syntax raises InventoryLoadError."""
    bad_yaml = tmp_path / "bad.yml"
    bad_yaml.write_text("routers:\n  - name: spine1\n    asn: [unclosed list", encoding="utf-8")
    with pytest.raises(InventoryLoadError) as exc_info:
        load_raw_inventory(bad_yaml)
    assert "error parsing yaml" in str(exc_info.value).lower()
