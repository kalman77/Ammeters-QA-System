from collections.abc import Mapping
from typing import Any

from src.application.errors.sampling_configuration_error import (
    SamplingConfigurationError,
)
from src.application.use_cases.resolve_sampling_settings import (
    resolve_sampling_settings,
)
from src.domain.models.sampling_settings import SamplingSettings


def read_sampling_settings(
    config: Mapping[str, Any],
) -> SamplingSettings:
    """Extract and resolve sampling settings from a raw configuration."""
    testing = config.get("testing")
    if not isinstance(testing, Mapping):
        raise SamplingConfigurationError(
            "Configuration must define a 'testing' mapping for sampling"
        )
    sampling = testing.get("sampling")
    if not isinstance(sampling, Mapping):
        raise SamplingConfigurationError(
            "Configuration must define a 'testing.sampling' mapping"
        )

    return resolve_sampling_settings(
        sampling.get("measurements_count"),
        sampling.get("total_duration_seconds"),
        sampling.get("sampling_frequency_hz"),
    )
