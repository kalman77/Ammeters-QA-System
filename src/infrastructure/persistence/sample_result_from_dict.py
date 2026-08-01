from collections.abc import Mapping

from src.domain.models.sample_result import SampleResult
from src.infrastructure.persistence.measurement_result_from_dict import (
    measurement_result_from_dict,
)


def sample_result_from_dict(data: object) -> SampleResult:
    """Reconstruct one scheduled sample result from archive data."""
    if not isinstance(data, Mapping):
        raise ValueError("sample result must be a mapping")
    return SampleResult(
        sample_index=data["sample_index"],
        scheduled_elapsed_seconds=data["scheduled_elapsed_seconds"],
        started_elapsed_seconds=data["started_elapsed_seconds"],
        completed_elapsed_seconds=data["completed_elapsed_seconds"],
        result=measurement_result_from_dict(data["result"]),
    )
