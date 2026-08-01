from collections.abc import Mapping

from src.infrastructure.persistence.json_values_are_identical import (
    json_values_are_identical,
)
from src.infrastructure.persistence.analysis_documents_match import (
    analysis_documents_match,
)


def archive_documents_match(
    recalculated: object,
    stored: object,
) -> bool:
    """Compare archive envelopes while tolerating derived float rounding."""
    if not isinstance(recalculated, Mapping) or not isinstance(
        stored,
        Mapping,
    ):
        return False

    recalculated_fields = dict(recalculated)
    stored_fields = dict(stored)
    recalculated_analysis = recalculated_fields.pop(
        "analysis",
        object(),
    )
    stored_analysis = stored_fields.pop("analysis", object())
    return (
        json_values_are_identical(
            recalculated_fields,
            stored_fields,
        )
        and analysis_documents_match(
            recalculated_analysis,
            stored_analysis,
        )
    )
