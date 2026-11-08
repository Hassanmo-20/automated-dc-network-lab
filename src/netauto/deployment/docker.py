"""Docker image and container management utilities."""

from pathlib import Path
from typing import Optional
from netauto.utils.command_runner import CommandResult, run_command
from netauto.utils.logging import setup_logger

logger = setup_logger("netauto.deployment.docker")


class DockerManager:
    """Manages Docker daemon interactions and image builds."""

    @staticmethod
    def is_docker_available() -> bool:
        """Check if Docker CLI is present and the Docker daemon is responding."""
        res = run_command(["docker", "info"], timeout=5)
        return res.success

    @staticmethod
    def build_host_image(
        dockerfile_dir: Path = Path("docker/host"),
        image_tag: str = "dc-lab-host:latest",
    ) -> CommandResult:
        """Build the custom server testing image."""
        if not dockerfile_dir.is_dir():
            raise FileNotFoundError(f"Dockerfile directory not found: {dockerfile_dir.resolve()}")

        logger.info("Building custom server image '%s' from %s...", image_tag, dockerfile_dir)
        cmd = ["docker", "build", "-t", image_tag, str(dockerfile_dir)]
        return run_command(cmd, timeout=300)
