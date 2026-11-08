"""Docker-based command execution transport for Containerlab nodes."""

import json
from pathlib import Path
from typing import Dict, List, Optional

from netauto.transport.base import Transport
from netauto.utils.command_runner import CommandResult, run_command
from netauto.utils.logging import setup_logger

logger = setup_logger("netauto.transport.docker")


class DockerExecTransport(Transport):
    """Executes commands on nodes using the Docker CLI."""

    def __init__(self, lab_name: str = "dc-fabric-lab", prefix: str = "clab"):
        self.lab_name = lab_name
        self.prefix = prefix
        self._container_cache: Dict[str, str] = {}  # node_name -> container_id_or_name

    def is_available(self) -> bool:
        """Check if Docker CLI and daemon are available."""
        result = run_command(["docker", "info"], timeout=5)
        return result.success

    def discover_containers(self) -> Dict[str, str]:
        """Discover Containerlab containers matching the lab prefix.

        Returns:
            Dictionary mapping node names to container names.

        Raises:
            RuntimeError: If duplicate containers match or discovery fails.
        """
        # Search containers by containerlab label
        cmd = [
            "docker", "ps",
            "--filter", f"label=containerlab={self.lab_name}",
            "--format", "{{json .}}"
        ]
        result = run_command(cmd, timeout=10)
        discovered: Dict[str, str] = {}

        if result.success and result.stdout:
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    c_info = json.loads(line)
                    c_name = c_info.get("Names", "")
                    # Containerlab names follow: clab-{lab_name}-{node_name}
                    expected_pfx = f"{self.prefix}-{self.lab_name}-"
                    if c_name.startswith(expected_pfx):
                        node_name = c_name[len(expected_pfx):]
                        if node_name in discovered:
                            raise RuntimeError(
                                f"Ambiguous containers detected for node '{node_name}': "
                                f"'{discovered[node_name]}' and '{c_name}'"
                            )
                        discovered[node_name] = c_name
                except json.JSONDecodeError:
                    continue

        # Fallback to name-based discovery if label returned nothing
        if not discovered:
            cmd = [
                "docker", "ps",
                "--filter", f"name={self.prefix}-{self.lab_name}-",
                "--format", "{{.Names}}"
            ]
            result = run_command(cmd, timeout=10)
            if result.success and result.stdout:
                expected_pfx = f"{self.prefix}-{self.lab_name}-"
                for c_name in result.stdout.splitlines():
                    c_name = c_name.strip()
                    if c_name.startswith(expected_pfx):
                        node_name = c_name[len(expected_pfx):]
                        if node_name in discovered:
                            raise RuntimeError(
                                f"Ambiguous containers detected for node '{node_name}': "
                                f"'{discovered[node_name]}' and '{c_name}'"
                            )
                        discovered[node_name] = c_name

        self._container_cache = discovered
        return discovered

    def resolve_container(self, node: str) -> str:
        """Resolve a logical node name to its container name."""
        if not self._container_cache:
            self.discover_containers()

        if node in self._container_cache:
            return self._container_cache[node]

        # Re-check in case a container was created recently
        self.discover_containers()
        if node in self._container_cache:
            return self._container_cache[node]

        # Default standard containerlab name if discovery didn't find running container
        return f"{self.prefix}-{self.lab_name}-{node}"

    def list_nodes(self) -> List[str]:
        """Return list of running nodes in this lab."""
        self.discover_containers()
        return list(self._container_cache.keys())

    def is_node_ready(self, node: str) -> bool:
        """Check if container is running."""
        c_name = self.resolve_container(node)
        cmd = ["docker", "inspect", "-f", "{{.State.Running}}", c_name]
        res = run_command(cmd, timeout=5)
        return res.success and res.stdout.lower() == "true"

    def execute_command(self, node: str, command: str, timeout: int = 30) -> CommandResult:
        """Execute a shell command inside a node container."""
        c_name = self.resolve_container(node)
        cmd = ["docker", "exec", c_name, "sh", "-c", command]
        return run_command(cmd, timeout=timeout)

    def execute_vtysh(self, node: str, command: str, timeout: int = 30) -> CommandResult:
        """Execute an FRR vtysh command inside a router container."""
        c_name = self.resolve_container(node)
        cmd = ["docker", "exec", c_name, "vtysh", "-c", command]
        return run_command(cmd, timeout=timeout)

    def copy_file(self, node: str, source_path: Path, dest_path: str) -> CommandResult:
        """Copy a file from host to the container."""
        c_name = self.resolve_container(node)
        cmd = ["docker", "cp", str(source_path), f"{c_name}:{dest_path}"]
        return run_command(cmd, timeout=20)
