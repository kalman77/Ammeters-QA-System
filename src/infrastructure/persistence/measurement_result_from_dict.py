from collections.abc import Mapping

from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_result import MeasurementResult
from src.infrastructure.persistence.measurement_error_from_dict import (
    measurement_error_from_dict,
)
from src.infrastructure.persistence.parse_utc_timestamp import (
    parse_utc_timestamp,
)


def measurement_result_from_dict(data: object) -> MeasurementResult:
    """Reconstruct one typed measurement result from archive data."""
    if not isinstance(data, Mapping):
        raise ValueError("measurement result must be a mapping")
    errors = data["errors"]
    if not isinstance(errors, list):
        raise ValueError("measurement result errors must be a list")
    return MeasurementResult(
        ammeter_type=data["ammeter_type"],
        status=MeasurementStatus(data["status"]),
        timestamp_utc=parse_utc_timestamp(
            data["timestamp_utc"],
            "measurement timestamp_utc",
        ),
        elapsed_seconds=data["elapsed_seconds"],
        current=data["current"],
        unit=data["unit"],
        request_latency_seconds=data["request_latency_seconds"],
        errors=tuple(
            measurement_error_from_dict(error) for error in errors
        ),
    )
