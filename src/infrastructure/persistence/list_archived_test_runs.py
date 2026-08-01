import stat
from pathlib import Path
from typing import Tuple, Union

from src.application.errors.result_storage_error import ResultStorageError
from src.domain.models.archived_test_run import ArchivedTestRun
from src.domain.services.normalize_run_id import normalize_run_id
from src.infrastructure.persistence.load_archived_test_run import (
    load_archived_test_run,
)


def list_archived_test_runs(
    archive_directory: Union[str, Path],
) -> Tuple[ArchivedTestRun, ...]:
    """Load every canonical archive in deterministic newest-first order."""
    try:
        archive_path = Path(archive_directory)
    except (TypeError, ValueError) as exc:
        raise ResultStorageError(
            "Result archive path must be a filesystem path"
        ) from exc
    try:
        archive_status = archive_path.stat()
    except FileNotFoundError:
        return ()
    except (OSError, ValueError) as exc:
        raise ResultStorageError(
            f"Unable to access result archive {archive_path}: {exc}"
        ) from exc
    if not stat.S_ISDIR(archive_status.st_mode):
        raise ResultStorageError(
            f"Result archive path is not a directory: {archive_path}"
        )

    try:
        entries = tuple(archive_path.iterdir())
    except (OSError, ValueError) as exc:
        raise ResultStorageError(
            f"Unable to list result archive {archive_path}: {exc}"
        ) from exc

    archived_runs = []
    for entry in entries:
        if (
            entry.name.startswith(".")
            or entry.suffix != ".json"
        ):
            continue
        try:
            normalized_run_id = normalize_run_id(entry.stem)
        except ValueError:
            continue
        archived_runs.append(
            load_archived_test_run(
                archive_path,
                normalized_run_id,
            )
        )

    archived_runs.sort(key=lambda run: run.run_id)
    archived_runs.sort(
        key=lambda run: run.archived_at_utc,
        reverse=True,
    )
    return tuple(archived_runs)
