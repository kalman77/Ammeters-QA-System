import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentStatisticsDelta:
    """Candidate-minus-baseline differences for Phase 4 statistics."""

    measurements_count_delta: int
    mean_current_delta: float
    median_current_delta: float
    standard_deviation_current_delta: float
    minimum_current_delta: float
    maximum_current_delta: float
    unit: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.measurements_count_delta, bool)
            or not isinstance(self.measurements_count_delta, int)
        ):
            raise ValueError("measurements_count_delta must be an integer")
        for field_name, value in (
            ("mean_current_delta", self.mean_current_delta),
            ("median_current_delta", self.median_current_delta),
            (
                "standard_deviation_current_delta",
                self.standard_deviation_current_delta,
            ),
            ("minimum_current_delta", self.minimum_current_delta),
            ("maximum_current_delta", self.maximum_current_delta),
        ):
            if isinstance(value, bool) or not isinstance(
                value,
                (int, float),
            ):
                raise ValueError(f"{field_name} must be a finite number")
            try:
                finite_value = math.isfinite(value)
            except OverflowError as exc:
                raise ValueError(
                    f"{field_name} must be a finite number"
                ) from exc
            if not finite_value:
                raise ValueError(f"{field_name} must be a finite number")
        if self.unit != "A":
            raise ValueError("current-statistics deltas must use unit 'A'")
