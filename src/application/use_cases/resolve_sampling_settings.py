import math
from typing import Optional

from src.application.errors.sampling_configuration_error import (
    SamplingConfigurationError,
)
from src.domain.models.sampling_settings import (
    MAX_MEASUREMENTS_COUNT,
    MAX_SAMPLING_FREQUENCY_HZ,
    MAX_TOTAL_DURATION_SECONDS,
    SamplingSettings,
)


def resolve_sampling_settings(
    measurements_count: Optional[object],
    total_duration_seconds: Optional[object],
    sampling_frequency_hz: Optional[object],
) -> SamplingSettings:
    """Validate two or three sampling values and derive a complete plan."""
    provided_count = sum(
        value is not None
        for value in (
            measurements_count,
            total_duration_seconds,
            sampling_frequency_hz,
        )
    )
    if provided_count < 2:
        raise SamplingConfigurationError(
            "Configure at least two of measurements_count, "
            "total_duration_seconds, and sampling_frequency_hz"
        )

    if measurements_count is not None and (
        isinstance(measurements_count, bool)
        or not isinstance(measurements_count, int)
        or measurements_count < 1
        or measurements_count > MAX_MEASUREMENTS_COUNT
    ):
        raise SamplingConfigurationError(
            "measurements_count must be a positive integer no greater "
            f"than {MAX_MEASUREMENTS_COUNT}"
        )
    for field_name, value, maximum in (
        (
            "total_duration_seconds",
            total_duration_seconds,
            MAX_TOTAL_DURATION_SECONDS,
        ),
        (
            "sampling_frequency_hz",
            sampling_frequency_hz,
            MAX_SAMPLING_FREQUENCY_HZ,
        ),
    ):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            or value > maximum
        ):
            raise SamplingConfigurationError(
                f"{field_name} must be positive and no greater "
                f"than {maximum:g}"
            )

    resolved_count = measurements_count
    resolved_duration = total_duration_seconds
    resolved_frequency = sampling_frequency_hz

    try:
        if resolved_count is None:
            derived_count = (
                float(resolved_duration) * float(resolved_frequency)
            )
            if not math.isfinite(derived_count):
                raise SamplingConfigurationError(
                    "Sampling values must produce a finite measurement count"
                )
            nearest_count = round(derived_count)
            if nearest_count < 1 or not math.isclose(
                derived_count,
                float(nearest_count),
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise SamplingConfigurationError(
                    "total_duration_seconds * sampling_frequency_hz "
                    "must produce a whole number of measurements"
                )
            resolved_count = int(nearest_count)
        elif resolved_duration is None:
            resolved_duration = (
                float(resolved_count) / float(resolved_frequency)
            )
        elif resolved_frequency is None:
            resolved_frequency = (
                float(resolved_count) / float(resolved_duration)
            )
        elif not math.isclose(
            float(resolved_count),
            float(resolved_duration) * float(resolved_frequency),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise SamplingConfigurationError(
                "Sampling values must satisfy measurements_count = "
                "total_duration_seconds * sampling_frequency_hz"
            )
    except SamplingConfigurationError:
        raise
    except (OverflowError, ValueError) as exc:
        raise SamplingConfigurationError(
            "Sampling values must be finite and representable"
        ) from exc

    try:
        return SamplingSettings(
            measurements_count=int(resolved_count),
            total_duration_seconds=float(resolved_duration),
            sampling_frequency_hz=float(resolved_frequency),
        )
    except (OverflowError, ValueError) as exc:
        raise SamplingConfigurationError(str(exc)) from exc
