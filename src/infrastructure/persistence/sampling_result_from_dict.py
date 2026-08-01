from collections.abc import Mapping

from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import (
    MAX_MEASUREMENTS_COUNT,
    SamplingSettings,
)
from src.infrastructure.persistence.measurement_error_from_dict import (
    measurement_error_from_dict,
)
from src.infrastructure.persistence.parse_utc_timestamp import (
    parse_utc_timestamp,
)
from src.infrastructure.persistence.sample_result_from_dict import (
    sample_result_from_dict,
)


def sampling_result_from_dict(data: object) -> SamplingResult:
    """Reconstruct one aggregate sampling result from archive data."""
    if not isinstance(data, Mapping):
        raise ValueError("sampling result must be a mapping")
    settings = data["settings"]
    samples = data["samples"]
    errors = data["errors"]
    if not isinstance(settings, Mapping):
        raise ValueError("sampling settings must be a mapping")
    if not isinstance(samples, list):
        raise ValueError("sampling samples must be a list")
    if len(samples) > MAX_MEASUREMENTS_COUNT:
        raise ValueError(
            "sampling samples exceed the supported collection limit"
        )
    if not isinstance(errors, list):
        raise ValueError("sampling errors must be a list")

    sampling_started_at = data["sampling_started_at_utc"]
    return SamplingResult(
        ammeter_type=data["ammeter_type"],
        status=MeasurementStatus(data["status"]),
        timestamp_utc=parse_utc_timestamp(
            data["timestamp_utc"],
            "sampling timestamp_utc",
        ),
        elapsed_seconds=data["elapsed_seconds"],
        sampling_started_at_utc=(
            parse_utc_timestamp(
                sampling_started_at,
                "sampling_started_at_utc",
            )
            if sampling_started_at is not None
            else None
        ),
        sampling_elapsed_seconds=data["sampling_elapsed_seconds"],
        settings=SamplingSettings(
            measurements_count=settings["measurements_count"],
            total_duration_seconds=settings["total_duration_seconds"],
            sampling_frequency_hz=settings["sampling_frequency_hz"],
        ),
        samples=tuple(
            sample_result_from_dict(sample) for sample in samples
        ),
        errors=tuple(
            measurement_error_from_dict(error) for error in errors
        ),
        unit=data["unit"],
    )
