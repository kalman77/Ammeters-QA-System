import sys
from pathlib import Path
from typing import Dict, Union

from src.bootstrap import DEFAULT_CONFIG_PATH, run_application


def main(
    config_path: Union[str, Path] = DEFAULT_CONFIG_PATH,
    *,
    emit: bool = True,
) -> Dict[str, float]:
    """Run the configured ammeter smoke test."""
    return run_application(config_path, emit=emit)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
