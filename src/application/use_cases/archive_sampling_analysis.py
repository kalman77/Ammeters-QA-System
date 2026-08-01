from collections.abc import Mapping
from typing import Optional

from src.application.errors.invalid_run_id_error import InvalidRunIdError
from src.application.errors.result_storage_error import ResultStorageError
from src.application.ports.archived_run_saver import ArchivedRunSaver
from src.application.ports.run_id_generator import RunIdGenerator
from src.application.ports.utc_clock import UtcClock
from src.application.use_cases.resolve_run_metadata import (
    resolve_run_metadata,
)
from src.domain.models.archived_test_run import ArchivedTestRun
from src.domain.models.run_metadata_entry import MetadataValue
from src.domain.models.sampling_analysis import SamplingAnalysis
from src.domain.services.normalize_run_id import normalize_run_id


def archive_sampling_analysis(
    analysis: SamplingAnalysis,
    metadata: Optional[Mapping[str, MetadataValue]],
    *,
    save_archived_run: ArchivedRunSaver,
    generate_run_id: RunIdGenerator,
    utc_clock: UtcClock,
) -> ArchivedTestRun:
    """Create and persist one immutable archived sampling analysis."""
    if not isinstance(analysis, SamplingAnalysis):
        raise ValueError("analysis must be SamplingAnalysis")
    resolved_metadata = resolve_run_metadata(metadata)
    generated_run_id = generate_run_id()
    try:
        normalized_run_id = normalize_run_id(generated_run_id)
    except ValueError as exc:
        raise InvalidRunIdError(
            "run ID generator returned a non-canonical UUID"
        ) from exc
    try:
        archived_run = ArchivedTestRun(
            run_id=normalized_run_id,
            archived_at_utc=utc_clock(),
            analysis=analysis,
            metadata=resolved_metadata,
        )
    except ValueError as exc:
        raise ResultStorageError(
            f"Unable to create archived test run: {exc}"
        ) from exc

    save_archived_run(archived_run)
    return archived_run
