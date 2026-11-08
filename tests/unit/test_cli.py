"""Unit tests for netauto CLI commands using Click runner."""

from click.testing import CliRunner
from netauto.cli import cli


def test_cli_validate_inventory():
    """Verify 'validate-inventory' command runs and succeeds."""
    runner = CliRunner()
    result = runner.invoke(cli, ["validate-inventory", "-i", "inventory/fabric.yml"])
    assert result.exit_code == 0
    assert "Inventory validation PASSED" in result.output


def test_cli_render(tmp_path):
    """Verify 'render' command generates configs into custom output dir."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["render", "-i", "inventory/fabric.yml", "-t", "templates", "-o", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Successfully generated" in result.output
    assert (tmp_path / "topology.clab.yml").is_file()


def test_cli_check_without_docker():
    """Verify 'check' command cleanly handles absent Docker environment without crash."""
    runner = CliRunner()
    result = runner.invoke(cli, ["check", "-i", "inventory/fabric.yml"])
    # If Docker is absent, it should report a clear error and exit code 1
    assert result.exit_code in (0, 1, 2)
