from typing import Iterable

from src.domain.models.sampling_result import SamplingResult
from src.presentation.console.format_sampling_results_table import (
    format_sampling_results_table,
)


def print_sampling_results(
    results: Iterable[SamplingResult],
) -> None:
    """Print an aligned summary of one or more sampling windows."""
    print(format_sampling_results_table(results))
