import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentStatistics:
    """Summary using population deviation for successful current readings."""

    measurements_count: int
    mean_current: float
    median_current: float
    standard_deviation_current: float
    minimum_current: float
    maximum_current: float
    unit: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.measurements_count, bool)
            or not isinstance(self.measurements_count, int)
            or self.measurements_count < 1
        ):
            raise ValueError(
                "measurements_count must be a positive integer"
            )

        for field_name, value in (
            ("mean_current", self.mean_current),
            ("median_current", self.median_current),
            (
                "standard_deviation_current",
                self.standard_deviation_current,
            ),
            ("minimum_current", self.minimum_current),
            ("maximum_current", self.maximum_current),
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

        if self.standard_deviation_current < 0:
            raise ValueError(
                "standard_deviation_current cannot be negative"
            )
        if self.minimum_current > self.maximum_current:
            raise ValueError(
                "minimum_current cannot exceed maximum_current"
            )
        if not (
            self.minimum_current
            <= self.mean_current
            <= self.maximum_current
        ):
            raise ValueError(
                "mean_current must be within the observed range"
            )
        if not (
            self.minimum_current
            <= self.median_current
            <= self.maximum_current
        ):
            raise ValueError(
                "median_current must be within the observed range"
            )
        if self.measurements_count == 1 and (
            self.mean_current != self.median_current
            or self.mean_current != self.minimum_current
            or self.mean_current != self.maximum_current
            or self.standard_deviation_current != 0
        ):
            raise ValueError(
                "one measurement requires identical central/range values "
                "and zero standard deviation"
            )
        if self.unit != "A":
            raise ValueError("current statistics must use unit 'A'")
