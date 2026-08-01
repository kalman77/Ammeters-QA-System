from collections.abc import Mapping

from src.domain.models.sample_result import SampleResult
from src.infrastructure.persistence.archive_schema_version import (
    ARCHIVE_SCHEMA_VERSION,
    RETRY_SCHEMA_VERSION,
)
from src.infrastructure.persistence.measurement_result_from_dict import (
    measurement_result_from_dict,
)


def sample_result_from_dict(
    data: object,
    schema_version: int = ARCHIVE_SCHEMA_VERSION,
) -> SampleResult:
    """Reconstruct one scheduled sample result from archive data."""
    if not isinstance(data, Mapping):
        raise ValueError("sample result must be a mapping")
    if schema_version >= RETRY_SCHEMA_VERSION:
        request_attempts = data["request_attempts"]
    elif "request_attempts" in data:
        raise ValueError(
            "sample attempts are not part of this archive schema"
        )
    else:
        # Version-1 archives predate retries: a started slot issued exactly
        # one request and a missed slot issued none.
        request_attempts = (
            0 if data["started_elapsed_seconds"] is None else 1
        )
    return SampleResult(
        sample_index=data["sample_index"],
        scheduled_elapsed_seconds=data["scheduled_elapsed_seconds"],
        started_elapsed_seconds=data["started_elapsed_seconds"],
        completed_elapsed_seconds=data["completed_elapsed_seconds"],
        request_attempts=request_attempts,
        result=measurement_result_from_dict(data["result"]),
    )
