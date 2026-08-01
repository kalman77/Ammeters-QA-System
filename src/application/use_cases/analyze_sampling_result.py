from src.domain.models.sampling_analysis import SamplingAnalysis
from src.domain.models.sampling_result import SamplingResult


def analyze_sampling_result(
    sampling_result: SamplingResult,
) -> SamplingAnalysis:
    """Calculate current statistics from successful sampling slots only."""
    if not isinstance(sampling_result, SamplingResult):
        raise ValueError("sampling_result must be SamplingResult")

    return SamplingAnalysis(
        sampling_result=sampling_result,
    )
