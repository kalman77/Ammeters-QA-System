import math
from typing import Optional

from src.domain.models.current_statistics import CurrentStatistics
from src.domain.models.current_statistics_delta import CurrentStatisticsDelta


def calculate_current_statistics_delta(
    baseline: Optional[CurrentStatistics],
    candidate: Optional[CurrentStatistics],
) -> Optional[CurrentStatisticsDelta]:
    """Calculate candidate-minus-baseline deltas when both have data."""
    if baseline is None or candidate is None:
        return None
    if not isinstance(baseline, CurrentStatistics) or not isinstance(
        candidate,
        CurrentStatistics,
    ):
        raise ValueError(
            "baseline and candidate must be CurrentStatistics or None"
        )
    if baseline.unit != candidate.unit:
        raise ValueError("statistics units must match")

    differences = (
        candidate.mean_current - baseline.mean_current,
        candidate.median_current - baseline.median_current,
        (
            candidate.standard_deviation_current
            - baseline.standard_deviation_current
        ),
        candidate.minimum_current - baseline.minimum_current,
        candidate.maximum_current - baseline.maximum_current,
    )
    if not all(math.isfinite(value) for value in differences):
        raise ValueError(
            "statistics differences must be representable finite numbers"
        )
    return CurrentStatisticsDelta(
        measurements_count_delta=(
            candidate.measurements_count - baseline.measurements_count
        ),
        mean_current_delta=differences[0],
        median_current_delta=differences[1],
        standard_deviation_current_delta=differences[2],
        minimum_current_delta=differences[3],
        maximum_current_delta=differences[4],
        unit=baseline.unit,
    )
