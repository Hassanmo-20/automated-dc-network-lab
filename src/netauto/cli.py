"""Command Line Interface (CLI) for netauto network automation framework."""

import sys
from pathlib import Path
import click

from netauto.deployment.containerlab import ContainerlabManager
from netauto.deployment.docker import DockerManager
from netauto.inventory.loader import InventoryLoadError, load_raw_inventory
from netauto.inventory.validator import InventoryValidationError, validate_and_build_inventory
from netauto.rendering.renderer import ConfigRenderer, TemplateRenderError
from netauto.reporting.json_report import JsonReportGenerator
from netauto.reporting.markdown_report import MarkdownReportGenerator
from netauto.transport.docker_exec import DockerExecTransport
from netauto.transport.mock_transport import MockTransport
from netauto.utils.logging import setup_logger
from netauto.validation.engine import ValidationEngine, ValidationReportData

logger = setup_logger("netauto.cli")


@click.group()
def cli():
    """Automated Data Center Network Lab: Spine-Leaf Fabric Automation CLI."""
    pass


@cli.command("validate-inventory")
@click.option(
    "--inventory-file",
    "-i",
    default="inventory/fabric.yml",
    help="Path to the fabric inventory YAML file.",
    type=click.Path(exists=False),
)
def validate_inventory_cmd(inventory_file: str):
    """Validate YAML inventory schema, IP addressing, ASNs, and topology rules."""
    click.echo(f"[*] Validating inventory: {inventory_file}")
    try:
        raw_data = load_raw_inventory(inventory_file)
        inv = validate_and_build_inventory(raw_data)
        click.secho(
            f"[OK] Inventory validation PASSED!\n"
            f"    - Lab: {inv.lab.name}\n"
            f"    - Routers: {len(inv.routers)} ({sum(1 for r in inv.routers if r.role == 'spine')} spines, {sum(1 for r in inv.routers if r.role == 'leaf')} leafs)\n"
            f"    - Fabric Links: {len(inv.links)}\n"
            f"    - Servers: {len(inv.servers)}\n"
            f"    - ECMP Max Paths: {inv.ecmp.maximum_paths}",
            fg="green",
        )
    except (InventoryLoadError, InventoryValidationError) as exc:
        click.secho(f"[FAIL] Validation Error:\n{exc}", fg="red", err=True)
        sys.exit(1)
    except Exception as exc:
        click.secho(f"[FAIL] Unexpected error during validation: {exc}", fg="red", err=True)
        sys.exit(1)


@cli.command("render")
@click.option(
    "--inventory-file",
    "-i",
    default="inventory/fabric.yml",
    help="Path to inventory file.",
)
@click.option(
    "--templates-dir",
    "-t",
    default="templates",
    help="Path to Jinja2 templates.",
)
@click.option(
    "--output-dir",
    "-o",
    default="build",
    help="Path to output build directory.",
)
def render_cmd(inventory_file: str, templates_dir: str, output_dir: str):
    """Render Jinja2 templates into router configs and Containerlab topology."""
    click.echo(f"[*] Rendering configuration templates from {templates_dir}...")
    try:
        raw_data = load_raw_inventory(inventory_file)
        inv = validate_and_build_inventory(raw_data)

        renderer = ConfigRenderer(templates_dir=templates_dir, output_dir=output_dir)
        files = renderer.render_all(inv)

        click.secho(f"[OK] Successfully generated {len(files)} files under {output_dir}/:", fg="green")
        for f in files:
            click.echo(f"    - {f}")
    except Exception as exc:
        click.secho(f"[FAIL] Rendering failed: {exc}", fg="red", err=True)
        sys.exit(1)


@cli.command("up")
@click.option(
    "--inventory-file",
    "-i",
    default="inventory/fabric.yml",
    help="Path to inventory file.",
)
@click.option(
    "--skip-build",
    is_flag=True,
    help="Skip building custom server docker image.",
)
def up_cmd(inventory_file: str, skip_build: bool):
    """Deploy the complete Containerlab topology and verify readiness."""
    click.echo("[*] Starting deployment workflow...")

    # 1. Validate & Render
    try:
        raw_data = load_raw_inventory(inventory_file)
        inv = validate_and_build_inventory(raw_data)
        renderer = ConfigRenderer()
        renderer.render_all(inv)
    except Exception as exc:
        click.secho(f"[FAIL] Pre-deployment build failed: {exc}", fg="red", err=True)
        sys.exit(1)

    # 2. Check Docker
    if not DockerManager.is_docker_available():
        click.secho("[FAIL] Docker daemon is not running or accessible. Deployment aborted.", fg="red", err=True)
        sys.exit(1)

    # 3. Check Containerlab
    clab_bin = ContainerlabManager.get_clab_binary()
    if not clab_bin:
        click.secho("[FAIL] Containerlab ('clab') executable not found. Please install Containerlab.", fg="red", err=True)
        sys.exit(1)

    # 4. Deploy
    clab_mgr = ContainerlabManager(Path("build/topology.clab.yml"))
    res = clab_mgr.deploy(reconfigure=True)
    if not res.success:
        click.secho(f"[FAIL] Containerlab deployment failed:\n{res.stderr}", fg="red", err=True)
        sys.exit(1)

    # 5. Wait for readiness
    transport = DockerExecTransport(lab_name=inv.lab.name, prefix=inv.lab.prefix)
    all_nodes = [r.name for r in inv.routers] + [s.name for s in inv.servers]
    ready = clab_mgr.wait_for_readiness(transport, all_nodes, timeout_seconds=90)

    if not ready:
        click.secho("[WARN] Deployment completed, but some nodes are not yet ready or responsive.", fg="yellow")
    else:
        click.secho("[OK] Fabric successfully deployed and all nodes are ready!", fg="green")


@cli.command("apply")
@click.option(
    "--inventory-file",
    "-i",
    default="inventory/fabric.yml",
    help="Path to inventory file.",
)
def apply_cmd(inventory_file: str):
    """Re-render router configurations and dynamically apply them using vtysh reload."""
    click.echo("[*] Applying updated configurations to running routers...")
    try:
        raw_data = load_raw_inventory(inventory_file)
        inv = validate_and_build_inventory(raw_data)
        renderer = ConfigRenderer()
        renderer.render_all(inv)

        transport = DockerExecTransport(lab_name=inv.lab.name, prefix=inv.lab.prefix)
        if not transport.is_available():
            click.secho("[FAIL] Docker is not available to apply configuration.", fg="red", err=True)
            sys.exit(1)

        # Apply to each router
        for router in inv.routers:
            conf_file = Path("build") / "configs" / router.name / "frr.conf"
            click.echo(f"    - Applying configuration to {router.name}...")
            # Copy new conf
            cp_res = transport.copy_file(router.name, conf_file, "/etc/frr/frr.conf")
            if not cp_res.success:
                click.secho(f"      Failed to copy conf to {router.name}: {cp_res.stderr}", fg="yellow")
                continue
            # Reload using vtysh
            reload_cmd = "vtysh -f /etc/frr/frr.conf"
            r_res = transport.execute_command(router.name, reload_cmd)
            if r_res.success:
                click.secho(f"      Successfully reloaded {router.name}.", fg="green")
            else:
                click.secho(f"      Warning reloading {router.name}: {r_res.stderr}", fg="yellow")

        click.secho("[OK] Configuration application completed.", fg="green")
    except Exception as exc:
        click.secho(f"[FAIL] Apply failed: {exc}", fg="red", err=True)
        sys.exit(1)


@cli.command("check")
@click.option(
    "--inventory-file",
    "-i",
    default="inventory/fabric.yml",
    help="Path to inventory file.",
)
@click.option(
    "--generate-reports",
    is_flag=True,
    default=True,
    help="Automatically generate Markdown and JSON reports.",
)
def check_cmd(inventory_file: str, generate_reports: bool):
    """Inspect OSPF, BGP, routing tables, ECMP, and server connectivity."""
    click.echo("[*] Performing live network validation...")
    try:
        raw_data = load_raw_inventory(inventory_file)
        inv = validate_and_build_inventory(raw_data)

        transport = DockerExecTransport(lab_name=inv.lab.name, prefix=inv.lab.prefix)
        if not transport.is_available():
            click.secho(
                "[FAIL] Docker daemon is not accessible. Cannot connect to running containers.\n"
                "    If running on Windows, ensure WSL2 and Docker are started.\n"
                "    Use 'python -m netauto validate-inventory' or run unit tests for offline testing.",
                fg="red",
                err=True,
            )
            sys.exit(1)

        engine = ValidationEngine(transport, inv)
        results = engine.run_all_checks()

        # Display Summary
        color = "green" if results.overall_status == "PASS" else "yellow" if results.overall_status == "DEGRADED" else "red"
        click.secho(f"\n==========================================", fg=color)
        click.secho(f" Fabric Validation Status: {results.overall_status}", fg=color, bold=True)
        click.secho(f"==========================================\n", fg=color)

        click.echo(f"  - Containers: {results.container_health.running_count}/{results.container_health.total_expected} online ({results.container_health.status})")
        click.echo(f"  - OSPF: {sum(1 for h in results.ospf_health.values() if h.status == 'PASS')}/{len(results.ospf_health)} routers healthy")
        click.echo(f"  - BGP: {sum(1 for h in results.bgp_health.values() if h.status == 'PASS')}/{len(results.bgp_health)} routers healthy")
        click.echo(f"  - ECMP: {sum(1 for h in results.ecmp_health.values() if h.status == 'PASS')}/{len(results.ecmp_health)} leafs healthy")
        click.echo(f"  - Connectivity: {results.connectivity.passed_tests}/{results.connectivity.total_tests} tests passed ({results.connectivity.status})")

        if results.failures:
            click.secho(f"\n[WARN] Detected {len(results.failures)} issue(s):", fg="yellow")
            for f in results.failures:
                click.echo(f"    - [{f.protocol}] {f.device}: {f.actual_state}")

        if generate_reports:
            json_gen = JsonReportGenerator()
            md_gen = MarkdownReportGenerator()
            j_path = json_gen.generate(results)
            m_path = md_gen.generate(results)
            click.echo(f"\n[OK] Generated reports:")
            click.echo(f"    - JSON: {j_path}")
            click.echo(f"    - Markdown: {m_path}")

        if results.overall_status == "FAIL":
            sys.exit(2)
        elif results.overall_status == "DEGRADED":
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as exc:
        click.secho(f"[FAIL] Validation failed: {exc}", fg="red", err=True)
        sys.exit(1)


@cli.command("report")
@click.option(
    "--inventory-file",
    "-i",
    default="inventory/fabric.yml",
    help="Path to inventory file.",
)
def report_cmd(inventory_file: str):
    """Execute validation and generate Markdown and JSON reports under reports/."""
    # Invokes check_cmd logic
    check_cmd.callback(inventory_file=inventory_file, generate_reports=True)


@cli.command("down")
@click.option(
    "--cleanup",
    is_flag=True,
    default=True,
    help="Remove lab bridge interfaces and temporary directories.",
)
def down_cmd(cleanup: bool):
    """Destroy the Containerlab network lab and clean up lab resources."""
    click.echo("[*] Destroying Containerlab network lab...")
    topo_path = Path("build/topology.clab.yml")
    if not topo_path.is_file():
        click.secho(f"[WARN] Topology file {topo_path} does not exist. Nothing to tear down.", fg="yellow")
        return

    clab_mgr = ContainerlabManager(topo_path)
    try:
        res = clab_mgr.destroy(cleanup=cleanup)
        if res.success:
            click.secho("[OK] Lab successfully destroyed.", fg="green")
        else:
            click.secho(f"[FAIL] Teardown warning/error:\n{res.stderr}", fg="yellow")
    except Exception as exc:
        click.secho(f"[FAIL] Failed to destroy lab: {exc}", fg="red", err=True)
        sys.exit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
