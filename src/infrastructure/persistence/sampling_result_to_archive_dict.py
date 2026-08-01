from datetime import timedelta
from typing import Any, Dict

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.sampling_result import SamplingResult
from src.infrastructure.persistence.archive_schema_version import (
    ARCHIVE_SCHEMA_VERSION,
    RETRY_SCHEMA_VERSION,
)
from src.infrastructure.persistence.measurement_result_to_archive_dict import (
    measurement_result_to_archive_dict,
)


def sampling_result_to_archive_dict(
    result: SamplingResult,
    schema_version: int = ARCHIVE_SCHEMA_VERSION,
) -> Dict[str, Any]:
    """Encode one sampling result using the requested archive schema."""
    includes_retries = schema_version >= RETRY_SCHEMA_VERSION
    successful_samples = sum(
        sample.result.status is MeasurementStatus.SUCCESS
        for sample in result.samples
    )
    missed_samples = sum(
        any(
            error.code is MeasurementErrorCode.SAMPLING_SLOT_MISSED
            for error in sample.result.errors
        )
        for sample in result.samples
    )
    serialized_samples = []
    for sample in result.samples:
        retry_fields = (
            {"request_attempts": sample.request_attempts}
            if includes_retries
            else {}
        )
        scheduled_at_utc = (
            result.sampling_started_at_utc
            + timedelta(seconds=sample.scheduled_elapsed_seconds)
        )
        started_at_utc = (
            result.sampling_started_at_utc
            + timedelta(seconds=sample.started_elapsed_seconds)
            if sample.started_elapsed_seconds is not None
            else None
        )
        serialized_samples.append(
            {
                "sample_index": sample.sample_index,
                "scheduled_elapsed_seconds": (
                    sample.scheduled_elapsed_seconds
                ),
                "scheduled_at_utc": (
                    scheduled_at_utc.isoformat().replace("+00:00", "Z")
                ),
                "started_elapsed_seconds": (
                    sample.started_elapsed_seconds
                ),
                "started_at_utc": (
                    started_at_utc.isoformat().replace("+00:00", "Z")
                    if started_at_utc is not None
                    else None
                ),
                "completed_elapsed_seconds": (
                    sample.completed_elapsed_seconds
                ),
                "timing_error_seconds": (
                    sample.started_elapsed_seconds
                    - sample.scheduled_elapsed_seconds
                    if sample.started_elapsed_seconds is not None
                    else None
                ),
                "result": measurement_result_to_archive_dict(
                    sample.result
                ),
                **retry_fields,
            }
        )

    retry_document = (
        {
            "retry": {
                "max_attempts": result.retry_policy.max_attempts,
                "retry_delay_seconds": (
                    result.retry_policy.retry_delay_seconds
                ),
            }
        }
        if includes_retries
        else {}
    )
    return {
        "ammeter_type": result.ammeter_type,
        "status": result.status.value,
        "timestamp_utc": (
            result.timestamp_utc.isoformat().replace("+00:00", "Z")
        ),
        "elapsed_seconds": result.elapsed_seconds,
        "sampling_started_at_utc": (
            result.sampling_started_at_utc.isoformat().replace(
                "+00:00",
                "Z",
            )
            if result.sampling_started_at_utc is not None
            else None
        ),
        "sampling_elapsed_seconds": result.sampling_elapsed_seconds,
        "unit": result.unit,
        "settings": {
            "measurements_count": result.settings.measurements_count,
            "total_duration_seconds": (
                result.settings.total_duration_seconds
            ),
            "sampling_frequency_hz": (
                result.settings.sampling_frequency_hz
            ),
        },
        "summary": {
            "successful_samples": successful_samples,
            "failed_samples": (
                len(result.samples)
                - successful_samples
                - missed_samples
            ),
            "missed_samples": missed_samples,
        },
        **retry_document,
        "samples": serialized_samples,
        "errors": [
            {
                "code": error.code.value,
                "message": error.message,
            }
            for error in result.errors
        ],
    }
