"""Utility package for netauto."""

from netauto.utils.command_runner import CommandResult, run_command
from netauto.utils.logging import setup_logger

__all__ = ["CommandResult", "run_command", "setup_logger"]
