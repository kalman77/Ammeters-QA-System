from typing import Tuple

from src.application.errors.result_storage_error import ResultStorageError
from src.application.ports.archived_run_lister import ArchivedRunLister
from src.domain.models.archived_run_query import ArchivedRunQuery
from src.domain.models.archived_test_run import ArchivedTestRun


def find_archived_test_runs(
    query: ArchivedRunQuery,
    *,
    list_archived_runs: ArchivedRunLister,
) -> Tuple[ArchivedTestRun, ...]:
    """Filter complete archives and return deterministic newest-first data."""
    if not isinstance(query, ArchivedRunQuery):
        raise ValueError("query must be ArchivedRunQuery")
    archived_runs = list_archived_runs()
    if not isinstance(archived_runs, tuple) or not all(
        isinstance(run, ArchivedTestRun) for run in archived_runs
    ):
        raise ResultStorageError(
            "Archive lister must return a tuple of ArchivedTestRun"
        )

    ordered_runs = sorted(archived_runs, key=lambda run: run.run_id)
    ordered_runs.sort(
        key=lambda run: run.archived_at_utc,
        reverse=True,
    )
    required_metadata = {
        entry.key: entry.value for entry in query.metadata
    }
    matching_runs = []
    for run in ordered_runs:
        sampling_result = run.analysis.sampling_result
        if (
            query.ammeter_type is not None
            and sampling_result.ammeter_type != query.ammeter_type
        ):
            continue
        if (
            query.status is not None
            and sampling_result.status is not query.status
        ):
            continue
        if (
            query.archived_from_utc is not None
            and run.archived_at_utc < query.archived_from_utc
        ):
            continue
        if (
            query.archived_until_utc is not None
            and run.archived_at_utc >= query.archived_until_utc
        ):
            continue
        if (
            query.has_statistics is not None
            and (run.analysis.statistics is not None)
            is not query.has_statistics
        ):
            continue
        stored_metadata = {
            entry.key: entry.value for entry in run.metadata
        }
        if any(
            key not in stored_metadata
            or type(stored_metadata[key]) is not type(value)
            or stored_metadata[key] != value
            for key, value in required_metadata.items()
        ):
            continue
        matching_runs.append(run)
        if query.limit is not None and len(matching_runs) >= query.limit:
            break
    return tuple(matching_runs)
