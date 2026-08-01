from typing import Any, Dict

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.sampling_analysis import SamplingAnalysis
from src.presentation.serialization.sampling_result_to_dict import (
    sampling_result_to_dict,
)


def sampling_analysis_to_dict(
    analysis: SamplingAnalysis,
) -> Dict[str, Any]:
    """Serialize an analysis and retain its complete sampling provenance."""
    sampling_result = analysis.sampling_result
    analyzed_samples = sum(
        sample.result.status is MeasurementStatus.SUCCESS
        for sample in sampling_result.samples
    )
    retried_samples = sum(
        sample.request_attempts > 1 for sample in sampling_result.samples
    )
    missed_samples = sum(
        any(
            error.code is MeasurementErrorCode.SAMPLING_SLOT_MISSED
            for error in sample.result.errors
        )
        for sample in sampling_result.samples
    )
    failed_samples = (
        len(sampling_result.samples)
        - analyzed_samples
        - missed_samples
    )
    if analysis.statistics is None:
        serialized_statistics = None
    else:
        serialized_statistics = {
            "measurements_count": (
                analysis.statistics.measurements_count
            ),
            "mean_current": analysis.statistics.mean_current,
            "median_current": analysis.statistics.median_current,
            "standard_deviation_current": (
                analysis.statistics.standard_deviation_current
            ),
            "standard_deviation_method": "population",
            "minimum_current": analysis.statistics.minimum_current,
            "maximum_current": analysis.statistics.maximum_current,
            "unit": analysis.statistics.unit,
        }

    return {
        "ammeter_type": sampling_result.ammeter_type,
        "status": sampling_result.status.value,
        "timestamp_utc": (
            sampling_result.timestamp_utc.isoformat().replace(
                "+00:00",
                "Z",
            )
        ),
        "unit": sampling_result.unit,
        "summary": {
            "planned_samples": (
                sampling_result.settings.measurements_count
            ),
            "recorded_samples": len(sampling_result.samples),
            "analyzed_samples": analyzed_samples,
            "excluded_samples": (
                len(sampling_result.samples) - analyzed_samples
            ),
            "failed_samples": failed_samples,
            "missed_samples": missed_samples,
            "retried_samples": retried_samples,
        },
        "statistics": serialized_statistics,
        "sampling_result": sampling_result_to_dict(sampling_result),
    }
