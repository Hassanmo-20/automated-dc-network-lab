"""Abstract base class for node transports."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional
from netauto.utils.command_runner import CommandResult


class Transport(ABC):
    """Abstract interface for communicating with lab network nodes."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the underlying execution runtime is reachable."""
        pass

    @abstractmethod
    def list_nodes(self) -> List[str]:
        """Return a list of discovered node names."""
        pass

    @abstractmethod
    def is_node_ready(self, node: str) -> bool:
        """Check if a specific node is online and accepting commands."""
        pass

    @abstractmethod
    def execute_command(self, node: str, command: str, timeout: int = 30) -> CommandResult:
        """Execute a shell command inside the specified node."""
        pass

    @abstractmethod
    def execute_vtysh(self, node: str, command: str, timeout: int = 30) -> CommandResult:
        """Execute an FRR vtysh command inside a router node."""
        pass

    @abstractmethod
    def copy_file(self, node: str, source_path: Path, dest_path: str) -> CommandResult:
        """Copy a file from host to the specified container."""
        pass
