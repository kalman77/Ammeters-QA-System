from src.application.errors.invalid_run_id_error import InvalidRunIdError
from src.application.errors.result_storage_error import ResultStorageError
from src.application.ports.archived_run_loader import ArchivedRunLoader
from src.domain.models.archived_test_run import ArchivedTestRun
from src.domain.services.normalize_run_id import normalize_run_id


def retrieve_archived_test_run(
    run_id: object,
    *,
    load_archived_run: ArchivedRunLoader,
) -> ArchivedTestRun:
    """Validate an ID and retrieve exactly one typed archived run."""
    try:
        normalized_run_id = normalize_run_id(run_id)
    except ValueError as exc:
        raise InvalidRunIdError(str(exc)) from exc

    archived_run = load_archived_run(normalized_run_id)
    if (
        not isinstance(archived_run, ArchivedTestRun)
        or archived_run.run_id != normalized_run_id
    ):
        raise ResultStorageError(
            "Archive loader returned a mismatched archived test run"
        )
    return archived_run
