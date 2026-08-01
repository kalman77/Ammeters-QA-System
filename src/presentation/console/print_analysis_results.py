from typing import Iterable

from src.domain.models.sampling_analysis import SamplingAnalysis
from src.presentation.console.format_analysis_results_table import (
    format_analysis_results_table,
)


def print_analysis_results(
    analyses: Iterable[SamplingAnalysis],
) -> None:
    """Print the aligned Phase 4 statistical-analysis table."""
    print(format_analysis_results_table(analyses))
