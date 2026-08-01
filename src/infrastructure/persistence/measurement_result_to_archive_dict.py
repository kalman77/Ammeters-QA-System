from typing import Any, Dict

from src.domain.models.measurement_result import MeasurementResult


def measurement_result_to_archive_dict(
    result: MeasurementResult,
) -> Dict[str, Any]:
    """Encode one measurement using the immutable archive-v1 schema."""
    return {
        "ammeter_type": result.ammeter_type,
        "status": result.status.value,
        "timestamp_utc": (
            result.timestamp_utc.isoformat().replace("+00:00", "Z")
        ),
        "elapsed_seconds": result.elapsed_seconds,
        "current": result.current,
        "unit": result.unit,
        "request_latency_seconds": result.request_latency_seconds,
        "errors": [
            {
                "code": error.code.value,
                "message": error.message,
            }
            for error in result.errors
        ],
    }
