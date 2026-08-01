from typing import Any, Dict

from src.domain.models.historical_comparison import HistoricalComparison
from src.presentation.serialization.archived_test_run_to_dict import (
    archived_test_run_to_dict,
)


def historical_comparison_to_dict(
    comparison: HistoricalComparison,
) -> Dict[str, Any]:
    """Serialize baseline, candidates, and candidate-minus-baseline deltas."""
    if not isinstance(comparison, HistoricalComparison):
        raise ValueError("comparison must be HistoricalComparison")

    serialized_candidates = []
    for index, candidate in enumerate(comparison.candidates):
        delta = comparison.statistics_deltas[index]
        if delta is None:
            serialized_delta = None
        else:
            serialized_delta = {
                "measurements_count_delta": (
                    delta.measurements_count_delta
                ),
                "mean_current_delta": delta.mean_current_delta,
                "median_current_delta": delta.median_current_delta,
                "standard_deviation_current_delta": (
                    delta.standard_deviation_current_delta
                ),
                "minimum_current_delta": delta.minimum_current_delta,
                "maximum_current_delta": delta.maximum_current_delta,
                "unit": delta.unit,
            }
        serialized_candidates.append(
            {
                "archived_run": archived_test_run_to_dict(candidate),
                "statistics_delta": serialized_delta,
                "same_ammeter_type": (
                    comparison.same_ammeter_types[index]
                ),
                "same_sampling_settings": (
                    comparison.same_sampling_settings[index]
                ),
            }
        )

    return {
        "baseline": archived_test_run_to_dict(comparison.baseline),
        "delta_direction": "candidate_minus_baseline",
        "candidates": serialized_candidates,
    }
