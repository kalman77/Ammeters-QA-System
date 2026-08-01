from typing import Any, Mapping, Optional

from src.application.use_cases.resolve_sampling_settings import (
    resolve_sampling_settings,
)
from src.domain.models.sampling_settings import SamplingSettings
from src.infrastructure.config.read_sampling_settings import (
    read_sampling_settings,
)


def resolve_framework_sampling_settings(
    config: Mapping[str, Any],
    measurements_count: Optional[object],
    total_duration_seconds: Optional[object],
    sampling_frequency_hz: Optional[object],
) -> SamplingSettings:
    """Use explicit sampling values or lazily read the configured values."""
    explicit_values = (
        measurements_count,
        total_duration_seconds,
        sampling_frequency_hz,
    )
    if any(value is not None for value in explicit_values):
        return resolve_sampling_settings(*explicit_values)
    return read_sampling_settings(config)
