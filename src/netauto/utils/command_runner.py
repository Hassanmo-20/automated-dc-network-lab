"""Safe command execution utilities for netauto."""

import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CommandResult:
    """Result of an executed shell/subprocess command."""
    command: List[str]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.exit_code == 0


def run_command(
    cmd: List[str],
    timeout: int = 30,
    check: bool = False,
    input_text: Optional[str] = None,
) -> CommandResult:
    """Execute a command securely using subprocess without shell=True.

    Args:
        cmd: Command arguments list.
        timeout: Execution timeout in seconds.
        check: If True, raise RuntimeError on non-zero exit code.
        input_text: Optional string to send to stdin.

    Returns:
        CommandResult containing return code, stdout, and stderr.
    """
    try:
        process = subprocess.run(
            cmd,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            shell=False,
        )
        result = CommandResult(
            command=cmd,
            exit_code=process.returncode,
            stdout=process.stdout.strip(),
            stderr=process.stderr.strip(),
        )
    except FileNotFoundError as exc:
        result = CommandResult(
            command=cmd,
            exit_code=127,
            stdout="",
            stderr=f"Executable not found: {cmd[0]} ({exc})",
        )
    except subprocess.TimeoutExpired:
        result = CommandResult(
            command=cmd,
            exit_code=124,
            stdout="",
            stderr=f"Command timed out after {timeout} seconds: {' '.join(cmd)}",
        )
    except Exception as exc:  # pylint: disable=broad-except
        result = CommandResult(
            command=cmd,
            exit_code=1,
            stdout="",
            stderr=f"Unexpected error executing {' '.join(cmd)}: {str(exc)}",
        )

    if check and not result.success:
        raise RuntimeError(
            f"Command failed (exit {result.exit_code}): {' '.join(cmd)}\nSTDERR: {result.stderr}"
        )

    return result
