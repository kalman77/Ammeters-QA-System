import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Union

from src.application.errors.archived_run_already_exists_error import (
    ArchivedRunAlreadyExistsError,
)
from src.application.errors.result_storage_error import ResultStorageError
from src.domain.models.archived_test_run import ArchivedTestRun
from src.infrastructure.persistence.archive_limits import (
    MAX_ARCHIVE_FILE_BYTES,
)
from src.infrastructure.persistence.archived_test_run_to_archive_dict import (
    archived_test_run_to_archive_dict,
)
from src.infrastructure.persistence.publish_archive_without_overwrite import (
    publish_archive_without_overwrite,
)


def save_archived_test_run(
    archive_directory: Union[str, Path],
    archived_run: ArchivedTestRun,
) -> None:
    """Atomically publish one append-only JSON archive document."""
    if not isinstance(archived_run, ArchivedTestRun):
        raise ResultStorageError(
            "Only ArchivedTestRun values can be persisted"
        )

    try:
        archive_path = Path(archive_directory)
    except (TypeError, ValueError) as exc:
        raise ResultStorageError(
            "Result archive path must be a filesystem path"
        ) from exc
    target_path = archive_path / f"{archived_run.run_id}.json"
    lock_path = archive_path / f".{archived_run.run_id}.lock"
    temporary_path: Optional[Path] = None
    temporary_descriptor: Optional[int] = None
    lock_acquired = False

    try:
        archive_path.mkdir(parents=True, exist_ok=True)
        try:
            lock_descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as exc:
            raise ArchivedRunAlreadyExistsError(
                f"Archived run {archived_run.run_id} already exists "
                "or is currently being written"
            ) from exc
        else:
            os.close(lock_descriptor)
            lock_acquired = True

        try:
            target_path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ArchivedRunAlreadyExistsError(
                f"Archived run {archived_run.run_id} already exists"
            )

        temporary_descriptor, temporary_name = tempfile.mkstemp(
            dir=archive_path,
            prefix=f".{archived_run.run_id}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(
            temporary_descriptor,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as archive_file:
            temporary_descriptor = None
            json.dump(
                archived_test_run_to_archive_dict(archived_run),
                archive_file,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            archive_file.write("\n")
            archive_file.flush()
            if (
                os.fstat(archive_file.fileno()).st_size
                > MAX_ARCHIVE_FILE_BYTES
            ):
                raise ResultStorageError(
                    f"Archived run {archived_run.run_id} exceeds the "
                    f"{MAX_ARCHIVE_FILE_BYTES}-byte storage limit"
                )
            os.fsync(archive_file.fileno())

        try:
            publish_archive_without_overwrite(
                temporary_path,
                target_path,
            )
        except FileExistsError as exc:
            raise ArchivedRunAlreadyExistsError(
                f"Archived run {archived_run.run_id} already exists"
            ) from exc
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            temporary_path = None
        except OSError:
            pass
        else:
            temporary_path = None
    except ArchivedRunAlreadyExistsError:
        raise
    except ResultStorageError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ResultStorageError(
            f"Unable to save archived run {archived_run.run_id}: {exc}"
        ) from exc
    finally:
        if temporary_descriptor is not None:
            try:
                os.close(temporary_descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
        if lock_acquired:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
