"""Inventory loader for reading YAML topology and network configurations."""

from pathlib import Path
from typing import Any, Dict, Union
import yaml


class InventoryLoadError(Exception):
    """Raised when the inventory file cannot be found or parsed."""
    pass


def load_raw_inventory(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Load and parse the YAML inventory file.

    Args:
        file_path: Path to the inventory YAML file.

    Returns:
        Dictionary representation of YAML content.

    Raises:
        InventoryLoadError: If file is missing or YAML is malformed.
    """
    path = Path(file_path)
    if not path.is_file():
        raise InventoryLoadError(f"Inventory file not found: {path.resolve()}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise InventoryLoadError(f"Inventory must be a YAML dictionary, got {type(data).__name__}")
            return data
    except yaml.YAMLError as exc:
        raise InventoryLoadError(f"Error parsing YAML file {path}: {exc}") from exc
    except Exception as exc:
        raise InventoryLoadError(f"Unexpected error loading {path}: {exc}") from exc
