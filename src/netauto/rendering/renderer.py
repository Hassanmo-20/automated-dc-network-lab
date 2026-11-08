"""Jinja2 rendering engine for network configurations and topology."""

import os
from pathlib import Path
from typing import List, Union
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from netauto.inventory.models import FabricInventory


class TemplateRenderError(Exception):
    """Raised when Jinja2 template rendering fails."""
    pass


class ConfigRenderer:
    """Renders Containerlab topology and FRR configurations from inventory."""

    def __init__(
        self,
        templates_dir: Union[str, Path] = "templates",
        output_dir: Union[str, Path] = "build",
    ):
        self.templates_dir = Path(templates_dir)
        self.output_dir = Path(output_dir)

        if not self.templates_dir.is_dir():
            raise TemplateRenderError(f"Templates directory not found: {self.templates_dir.resolve()}")

        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,
        )

    def render_all(self, inventory: FabricInventory) -> List[Path]:
        """Render all configurations and topology files.

        Args:
            inventory: Validated FabricInventory.

        Returns:
            List of generated file paths.
        """
        generated_files: List[Path] = []
        self.output_dir.mkdir(parents=True, exist_ok=True)
        configs_dir = self.output_dir / "configs"
        configs_dir.mkdir(parents=True, exist_ok=True)

        # 1. Render Containerlab Topology
        clab_path = self.output_dir / "topology.clab.yml"
        self._render_file(
            template_name="topology.clab.yml.j2",
            context={
                "lab": inventory.lab,
                "routers": inventory.routers,
                "servers": inventory.servers,
                "links": inventory.links,
            },
            output_path=clab_path,
        )
        generated_files.append(clab_path)

        # 2. Render FRR router configurations
        for router in inventory.routers:
            r_dir = configs_dir / router.name
            r_dir.mkdir(parents=True, exist_ok=True)

            # frr.conf
            frr_conf_path = r_dir / "frr.conf"
            self._render_file(
                template_name="frr.conf.j2",
                context={
                    "router": router,
                    "ecmp": inventory.ecmp,
                    "ospf": inventory.ospf,
                    "bgp": inventory.bgp,
                },
                output_path=frr_conf_path,
            )
            generated_files.append(frr_conf_path)

            # daemons
            daemons_path = r_dir / "daemons"
            self._render_file(
                template_name="daemons.j2",
                context={"router": router},
                output_path=daemons_path,
            )
            generated_files.append(daemons_path)

            # vtysh.conf
            vtysh_path = r_dir / "vtysh.conf"
            self._render_file(
                template_name="vtysh.conf.j2",
                context={"router": router},
                output_path=vtysh_path,
            )
            generated_files.append(vtysh_path)

        # 3. Render host startup scripts
        for server in inventory.servers:
            s_dir = configs_dir / server.name
            s_dir.mkdir(parents=True, exist_ok=True)
            host_script_path = s_dir / "startup.sh"
            self._render_file(
                template_name="host-startup.sh.j2",
                context={"server": server},
                output_path=host_script_path,
            )
            generated_files.append(host_script_path)

        return generated_files

    def _render_file(self, template_name: str, context: dict, output_path: Path) -> None:
        """Helper to render a template to a destination file."""
        try:
            template = self.env.get_template(template_name)
            content = template.render(context)
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
        except Exception as exc:
            raise TemplateRenderError(
                f"Failed to render template '{template_name}' to {output_path}: {exc}"
            ) from exc
