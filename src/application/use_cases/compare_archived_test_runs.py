from typing import Tuple

from src.application.errors.invalid_historical_comparison_error import (
    InvalidHistoricalComparisonError,
)
from src.domain.models.archived_test_run import ArchivedTestRun
from src.domain.models.historical_comparison import HistoricalComparison


def compare_archived_test_runs(
    baseline: ArchivedTestRun,
    candidates: Tuple[ArchivedTestRun, ...],
) -> HistoricalComparison:
    """Create a descriptive candidate-minus-baseline comparison."""
    try:
        return HistoricalComparison(
            baseline=baseline,
            candidates=candidates,
        )
    except ValueError as exc:
        raise InvalidHistoricalComparisonError(str(exc)) from exc
