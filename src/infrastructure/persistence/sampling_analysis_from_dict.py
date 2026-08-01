from collections.abc import Mapping

from src.domain.models.sampling_analysis import SamplingAnalysis
from src.infrastructure.persistence.sampling_result_from_dict import (
    sampling_result_from_dict,
)
from src.infrastructure.persistence.sampling_analysis_to_archive_dict import (
    sampling_analysis_to_archive_dict,
)
from src.infrastructure.persistence.analysis_documents_match import (
    analysis_documents_match,
)


def sampling_analysis_from_dict(data: object) -> SamplingAnalysis:
    """Reconstruct an analysis and reject contradictory derived fields."""
    if not isinstance(data, Mapping):
        raise ValueError("sampling analysis must be a mapping")
    analysis = SamplingAnalysis(
        sampling_result=sampling_result_from_dict(
            data["sampling_result"]
        )
    )
    if not analysis_documents_match(
        sampling_analysis_to_archive_dict(analysis),
        dict(data),
    ):
        raise ValueError(
            "stored sampling analysis contradicts its sampling result"
        )
    return analysis
