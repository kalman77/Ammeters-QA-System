from src.domain.models.historical_comparison import HistoricalComparison
from src.presentation.console.format_historical_comparison_table import (
    format_historical_comparison_table,
)


def print_historical_comparison(
    comparison: HistoricalComparison,
) -> None:
    """Print one historical comparison as an aligned console table."""
    print(format_historical_comparison_table(comparison))
