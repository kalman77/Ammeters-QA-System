import math
from statistics import mean, pstdev
from typing import Iterable, Optional

from src.domain.models.current_statistics import CurrentStatistics


def calculate_current_statistics(
    currents: Iterable[object],
) -> Optional[CurrentStatistics]:
    """Calculate finite population statistics, or None for no readings."""
    try:
        values = tuple(currents)
    except TypeError as exc:
        raise ValueError("currents must be an iterable of finite numbers") from exc

    for current in values:
        if isinstance(current, bool) or not isinstance(
            current,
            (int, float),
        ):
            raise ValueError("currents must contain only finite numbers")
        try:
            finite_current = math.isfinite(current)
        except OverflowError as exc:
            raise ValueError(
                "currents must contain only finite numbers"
            ) from exc
        if not finite_current:
            raise ValueError("currents must contain only finite numbers")
    if not values:
        return None

    ordered_values = sorted(values)
    middle_index = len(ordered_values) // 2
    if len(ordered_values) % 2:
        median_current = float(ordered_values[middle_index])
    else:
        median_current = float(
            mean(
                (
                    ordered_values[middle_index - 1],
                    ordered_values[middle_index],
                )
            )
        )

    return CurrentStatistics(
        measurements_count=len(values),
        mean_current=float(mean(values)),
        median_current=median_current,
        standard_deviation_current=float(pstdev(values)),
        minimum_current=float(ordered_values[0]),
        maximum_current=float(ordered_values[-1]),
        unit="A",
    )
