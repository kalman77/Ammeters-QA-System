from typing import Any, Dict

from src.domain.models.archived_test_run import ArchivedTestRun
from src.infrastructure.persistence.archive_schema_version import (
    ARCHIVE_SCHEMA_VERSION,
)
from src.infrastructure.persistence.sampling_analysis_to_archive_dict import (
    sampling_analysis_to_archive_dict,
)


def archived_test_run_to_archive_dict(
    archived_run: ArchivedTestRun,
    schema_version: int = ARCHIVE_SCHEMA_VERSION,
) -> Dict[str, Any]:
    """Encode one complete run using the requested archive schema."""
    if not isinstance(archived_run, ArchivedTestRun):
        raise ValueError("archived_run must be ArchivedTestRun")
    return {
        "schema_version": schema_version,
        "run_id": archived_run.run_id,
        "archived_at_utc": (
            archived_run.archived_at_utc.isoformat().replace(
                "+00:00",
                "Z",
            )
        ),
        "metadata": {
            entry.key: entry.value for entry in archived_run.metadata
        },
        "analysis": sampling_analysis_to_archive_dict(
            archived_run.analysis,
            schema_version,
        ),
    }
