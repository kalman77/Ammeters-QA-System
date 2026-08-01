from collections.abc import Mapping

from src.application.errors.unsupported_archive_schema_error import (
    UnsupportedArchiveSchemaError,
)
from src.domain.models.archived_test_run import (
    MAX_METADATA_ENTRIES,
    ArchivedTestRun,
)
from src.domain.models.run_metadata_entry import RunMetadataEntry
from src.infrastructure.persistence.archive_schema_version import (
    ARCHIVE_SCHEMA_VERSION,
)
from src.infrastructure.persistence.archive_documents_match import (
    archive_documents_match,
)
from src.infrastructure.persistence.archived_test_run_to_archive_dict import (
    archived_test_run_to_archive_dict,
)
from src.infrastructure.persistence.parse_utc_timestamp import (
    parse_utc_timestamp,
)
from src.infrastructure.persistence.sampling_analysis_from_dict import (
    sampling_analysis_from_dict,
)


def archived_test_run_from_dict(data: object) -> ArchivedTestRun:
    """Decode one archive envelope and verify its canonical representation."""
    if not isinstance(data, Mapping):
        raise ValueError("archived test run must be a mapping")
    if "schema_version" not in data:
        raise ValueError("archive schema_version is required")
    schema_version = data["schema_version"]
    if type(schema_version) is not int:
        raise ValueError("archive schema_version must be an integer")
    if schema_version != ARCHIVE_SCHEMA_VERSION:
        raise UnsupportedArchiveSchemaError(
            "Unsupported archive schema version "
            f"{schema_version!r}; expected "
            f"{ARCHIVE_SCHEMA_VERSION}"
        )
    metadata = data["metadata"]
    if not isinstance(metadata, Mapping):
        raise ValueError("archive metadata must be a mapping")
    if len(metadata) > MAX_METADATA_ENTRIES:
        raise ValueError(
            "archive metadata exceeds the supported entry limit"
        )

    archived_run = ArchivedTestRun(
        run_id=data["run_id"],
        archived_at_utc=parse_utc_timestamp(
            data["archived_at_utc"],
            "archived_at_utc",
        ),
        analysis=sampling_analysis_from_dict(data["analysis"]),
        metadata=tuple(
            RunMetadataEntry(key=key, value=value)
            for key, value in sorted(metadata.items())
        ),
    )
    if not archive_documents_match(
        archived_test_run_to_archive_dict(archived_run),
        dict(data),
    ):
        raise ValueError(
            "archive document is not canonical or contains contradictions"
        )
    return archived_run
