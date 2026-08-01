import math
from dataclasses import dataclass


MAX_MEASUREMENTS_COUNT = 100_000
MAX_TOTAL_DURATION_SECONDS = 86_400.0
MAX_SAMPLING_FREQUENCY_HZ = 10_000.0


@dataclass(frozen=True)
class SamplingSettings:
    """Resolved and internally consistent sampling-window settings."""

    measurements_count: int
    total_duration_seconds: float
    sampling_frequency_hz: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.measurements_count, bool)
            or not isinstance(self.measurements_count, int)
            or self.measurements_count < 1
            or self.measurements_count > MAX_MEASUREMENTS_COUNT
        ):
            raise ValueError(
                "measurements_count must be a positive integer no greater "
                f"than {MAX_MEASUREMENTS_COUNT}"
            )

        for field_name, value, maximum in (
            (
                "total_duration_seconds",
                self.total_duration_seconds,
                MAX_TOTAL_DURATION_SECONDS,
            ),
            (
                "sampling_frequency_hz",
                self.sampling_frequency_hz,
                MAX_SAMPLING_FREQUENCY_HZ,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
                or value > maximum
            ):
                raise ValueError(
                    f"{field_name} must be positive and no greater "
                    f"than {maximum:g}"
                )

        try:
            expected_count = (
                float(self.total_duration_seconds)
                * float(self.sampling_frequency_hz)
            )
            normalized_count = float(self.measurements_count)
        except (OverflowError, ValueError) as exc:
            raise ValueError(
                "sampling settings must use finite representable values"
            ) from exc
        if not math.isfinite(expected_count):
            raise ValueError(
                "sampling settings must use finite representable values"
            )
        if not math.isclose(
            normalized_count,
            expected_count,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                "sampling settings must satisfy measurements_count = "
                "total_duration_seconds * sampling_frequency_hz"
            )
