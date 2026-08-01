from typing import Mapping

from src.presentation.console.format_measurements_table import (
    format_measurements_table,
)


def print_measurements(measurements: Mapping[str, float]) -> None:
    """Print labeled current measurements to standard output."""
    print(format_measurements_table(measurements))
