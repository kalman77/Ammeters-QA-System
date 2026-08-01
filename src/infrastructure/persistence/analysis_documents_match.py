import math
from collections.abc import Mapping

from src.infrastructure.persistence.json_values_are_identical import (
    json_values_are_identical,
)


def analysis_documents_match(
    recalculated: object,
    stored: object,
) -> bool:
    """Compare analysis documents with an eight-ULP statistics tolerance."""
    if not isinstance(recalculated, Mapping) or not isinstance(
        stored,
        Mapping,
    ):
        return False

    recalculated_fields = dict(recalculated)
    stored_fields = dict(stored)
    recalculated_statistics = recalculated_fields.pop(
        "statistics",
        object(),
    )
    stored_statistics = stored_fields.pop("statistics", object())
    if not json_values_are_identical(
        recalculated_fields,
        stored_fields,
    ):
        return False
    if recalculated_statistics is None or stored_statistics is None:
        return (
            recalculated_statistics is None
            and stored_statistics is None
        )
    if not isinstance(recalculated_statistics, Mapping) or not isinstance(
        stored_statistics,
        Mapping,
    ):
        return False

    recalculated_metrics = dict(recalculated_statistics)
    stored_metrics = dict(stored_statistics)
    metric_names = (
        "mean_current",
        "median_current",
        "standard_deviation_current",
        "minimum_current",
        "maximum_current",
    )
    for metric_name in metric_names:
        if (
            metric_name not in recalculated_metrics
            or metric_name not in stored_metrics
        ):
            return False
        recalculated_value = recalculated_metrics.pop(metric_name)
        stored_value = stored_metrics.pop(metric_name)
        if (
            type(recalculated_value) is not float
            or type(stored_value) is not float
            or not math.isfinite(stored_value)
        ):
            return False
        tolerance = 8 * max(
            math.ulp(recalculated_value),
            math.ulp(stored_value),
        )
        if abs(recalculated_value - stored_value) > tolerance:
            return False

    return json_values_are_identical(
        recalculated_metrics,
        stored_metrics,
    )
