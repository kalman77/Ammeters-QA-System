from typing import Iterable

from src.domain.models.measurement_result import MeasurementResult
from src.presentation.console.format_measurement_results_table import (
    format_measurement_results_table,
)


def print_measurement_results(
    results: Iterable[MeasurementResult],
) -> None:
    """Print typed measurement results to standard output."""
    print(format_measurement_results_table(results))
