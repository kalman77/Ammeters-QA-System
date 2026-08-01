from pathlib import Path
from typing import Any, Dict, Union

import yaml


def load_yaml_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """Load a YAML document and require a top-level mapping."""
    path = Path(config_path)
    try:
        with path.open("r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
    except (UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"Unable to parse YAML configuration: {path}") from exc

    if not isinstance(config, dict):
        raise ValueError(f"Configuration must contain a mapping: {path}")

    return config
