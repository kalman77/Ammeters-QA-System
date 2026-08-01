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
from src.infrastructure.persistence.archive_schema_version import (
    ARCHIVE_SCHEMA_VERSION,
)


def sampling_analysis_from_dict(
    data: object,
    schema_version: int = ARCHIVE_SCHEMA_VERSION,
) -> SamplingAnalysis:
    """Reconstruct an analysis and reject contradictory derived fields."""
    if not isinstance(data, Mapping):
        raise ValueError("sampling analysis must be a mapping")
    analysis = SamplingAnalysis(
        sampling_result=sampling_result_from_dict(
            data["sampling_result"],
            schema_version,
        )
    )
    if not analysis_documents_match(
        sampling_analysis_to_archive_dict(analysis, schema_version),
        dict(data),
    ):
        raise ValueError(
            "stored sampling analysis contradicts its sampling result"
        )
    return analysis
