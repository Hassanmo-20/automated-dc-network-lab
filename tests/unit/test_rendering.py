"""Unit tests for Jinja2 template rendering."""

from pathlib import Path
import pytest
from netauto.inventory.loader import load_raw_inventory
from netauto.inventory.validator import validate_and_build_inventory
from netauto.rendering.renderer import ConfigRenderer


@pytest.fixture
def inventory():
    raw_data = load_raw_inventory("inventory/fabric.yml")
    return validate_and_build_inventory(raw_data)


def test_render_all(tmp_path, inventory):
    """Verify all expected files are generated in output directory."""
    renderer = ConfigRenderer(templates_dir="templates", output_dir=tmp_path)
    files = renderer.render_all(inventory)

    assert len(files) == 23  # topology + 6*(frr.conf+daemons+vtysh.conf) + 4*host_startup

    topo_file = tmp_path / "topology.clab.yml"
    assert topo_file.is_file()
    topo_content = topo_file.read_text(encoding="utf-8")
    assert "dc-fabric-lab" in topo_content
    assert "spine1:" in topo_content
    assert "leaf1:" in topo_content
    assert "host1:" in topo_content

    # Inspect spine1 frr.conf
    spine1_conf = tmp_path / "configs" / "spine1" / "frr.conf"
    assert spine1_conf.is_file()
    spine_content = spine1_conf.read_text(encoding="utf-8")
    assert "router bgp 65000" in spine_content
    assert "router ospf" in spine_content
    assert "ospf router-id 10.255.0.1" in spine_content
    assert "maximum-paths 2" in spine_content
    assert "neighbor 10.0.0.1 remote-as 65101" in spine_content

    # Inspect leaf1 frr.conf
    leaf1_conf = tmp_path / "configs" / "leaf1" / "frr.conf"
    assert leaf1_conf.is_file()
    leaf_content = leaf1_conf.read_text(encoding="utf-8")
    assert "router bgp 65101" in leaf_content
    assert "network 172.16.11.0/24" in leaf_content
    assert "maximum-paths 2" in leaf_content
    assert "neighbor 10.0.0.0 remote-as 65000" in leaf_content
    assert "neighbor 10.0.0.2 remote-as 65000" in leaf_content
    assert "ip prefix-list PL-LOCAL-SERVER" in leaf_content

    # Inspect host1 startup script
    host1_script = tmp_path / "configs" / "host1" / "startup.sh"
    assert host1_script.is_file()
    host_content = host1_script.read_text(encoding="utf-8")
    assert "172.16.11.10/24" in host_content
    assert "172.16.11.1" in host_content
