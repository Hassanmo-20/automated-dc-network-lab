"""Containerlab lifecycle manager."""

import time
from pathlib import Path
from typing import List, Optional
from netauto.transport.base import Transport
from netauto.utils.command_runner import CommandResult, run_command
from netauto.utils.logging import setup_logger

logger = setup_logger("netauto.deployment.containerlab")


class ContainerlabManager:
    """Manages deployment, destruction, and readiness verification of Containerlab labs."""

    def __init__(self, topo_file: Path = Path("build/topology.clab.yml")):
        self.topo_file = topo_file

    @staticmethod
    def get_clab_binary() -> Optional[str]:
        """Detect whether 'clab' or 'containerlab' is installed."""
        for bin_name in ["clab", "containerlab"]:
            res = run_command([bin_name, "version"], timeout=5)
            if res.success:
                return bin_name
        return None

    def deploy(self, reconfigure: bool = True) -> CommandResult:
        """Deploy the lab topology."""
        clab_bin = self.get_clab_binary()
        if not clab_bin:
            raise RuntimeError("Containerlab executable ('clab' or 'containerlab') is not installed or not in PATH.")

        if not self.topo_file.is_file():
            raise FileNotFoundError(f"Topology file not found: {self.topo_file.resolve()}")

        cmd = [clab_bin, "deploy", "-t", str(self.topo_file)]
        if reconfigure:
            cmd.append("--reconfigure")

        logger.info("Executing Containerlab deployment: %s", " ".join(cmd))
        return run_command(cmd, timeout=300)

    def destroy(self, cleanup: bool = True) -> CommandResult:
        """Destroy the lab topology."""
        clab_bin = self.get_clab_binary()
        if not clab_bin:
            raise RuntimeError("Containerlab executable is not installed or not in PATH.")

        if not self.topo_file.is_file():
            raise FileNotFoundError(f"Topology file not found: {self.topo_file.resolve()}")

        cmd = [clab_bin, "destroy", "-t", str(self.topo_file)]
        if cleanup:
            cmd.append("--cleanup")

        logger.info("Destroying Containerlab deployment: %s", " ".join(cmd))
        return run_command(cmd, timeout=180)

    def wait_for_readiness(
        self,
        transport: Transport,
        nodes: List[str],
        timeout_seconds: int = 60,
        interval_seconds: int = 2,
    ) -> bool:
        """Poll nodes until all are online and responsive or timeout is reached."""
        logger.info("Waiting for %d lab nodes to become ready (timeout %ds)...", len(nodes), timeout_seconds)
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            all_ready = True
            for node in nodes:
                if not transport.is_node_ready(node):
                    all_ready = False
                    break
                # If router node, test vtysh response
                if "spine" in node or "leaf" in node:
                    v_res = transport.execute_vtysh(node, "show version")
                    if not v_res.success:
                        all_ready = False
                        break

            if all_ready:
                logger.info("All lab nodes are ready and accepting commands!")
                return True

            time.sleep(interval_seconds)

        logger.warning("Timed out waiting for nodes to become ready.")
        return False
