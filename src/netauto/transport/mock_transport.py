"""Mock transport for testing validation logic without Docker."""

from pathlib import Path
from typing import Callable, Dict, List, Optional
from netauto.transport.base import Transport
from netauto.utils.command_runner import CommandResult


class MockTransport(Transport):
    """Simulated transport providing canned responses for offline testing."""

    def __init__(self, available: bool = True):
        self._available = available
        self.node_responses: Dict[str, Dict[str, CommandResult]] = {}
        self.vtysh_responses: Dict[str, Dict[str, CommandResult]] = {}
        self.online_nodes: List[str] = []

    def set_available(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def register_command_response(self, node: str, cmd: str, result: CommandResult) -> None:
        if node not in self.node_responses:
            self.node_responses[node] = {}
        self.node_responses[node][cmd] = result

    def register_vtysh_response(self, node: str, cmd: str, result: CommandResult) -> None:
        if node not in self.vtysh_responses:
            self.vtysh_responses[node] = {}
        self.vtysh_responses[node][cmd] = result

    def list_nodes(self) -> List[str]:
        return self.online_nodes

    def is_node_ready(self, node: str) -> bool:
        return node in self.online_nodes

    def execute_command(self, node: str, command: str, timeout: int = 30) -> CommandResult:
        if node in self.node_responses and command in self.node_responses[node]:
            return self.node_responses[node][command]
        return CommandResult(command=[command], exit_code=0, stdout="", stderr="")

    def execute_vtysh(self, node: str, command: str, timeout: int = 30) -> CommandResult:
        if node in self.vtysh_responses and command in self.vtysh_responses[node]:
            return self.vtysh_responses[node][command]
        return CommandResult(command=["vtysh", "-c", command], exit_code=0, stdout="{}", stderr="")

    def copy_file(self, node: str, source_path: Path, dest_path: str) -> CommandResult:
        return CommandResult(command=["mock_cp"], exit_code=0, stdout="copied", stderr="")
