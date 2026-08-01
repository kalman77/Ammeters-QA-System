import errno
import json
import os
import stat
from pathlib import Path
from typing import Union

from src.application.errors.archived_run_not_found_error import (
    ArchivedRunNotFoundError,
)
from src.application.errors.corrupt_archived_run_error import (
    CorruptArchivedRunError,
)
from src.application.errors.invalid_run_id_error import InvalidRunIdError
from src.application.errors.result_storage_error import ResultStorageError
from src.application.errors.unsupported_archive_schema_error import (
    UnsupportedArchiveSchemaError,
)
from src.domain.models.archived_test_run import ArchivedTestRun
from src.domain.services.normalize_run_id import normalize_run_id
from src.infrastructure.persistence.archive_limits import (
    MAX_ARCHIVE_FILE_BYTES,
)
from src.infrastructure.persistence.archived_test_run_from_dict import (
    archived_test_run_from_dict,
)
from src.infrastructure.persistence.reject_duplicate_json_object_keys import (
    reject_duplicate_json_object_keys,
)
from src.infrastructure.persistence.reject_non_finite_json_constant import (
    reject_non_finite_json_constant,
)


def load_archived_test_run(
    archive_directory: Union[str, Path],
    run_id: object,
) -> ArchivedTestRun:
    """Load one validated archive without trusting caller-provided paths."""
    try:
        normalized_run_id = normalize_run_id(run_id)
    except ValueError as exc:
        raise InvalidRunIdError(str(exc)) from exc

    try:
        archive_path = Path(archive_directory)
    except (TypeError, ValueError) as exc:
        raise ResultStorageError(
            "Result archive path must be a filesystem path"
        ) from exc
    target_path = archive_path / f"{normalized_run_id}.json"
    try:
        archive_status = archive_path.stat()
    except FileNotFoundError as exc:
        raise ArchivedRunNotFoundError(
            f"Archived run {normalized_run_id} was not found"
        ) from exc
    except (OSError, ValueError) as exc:
        raise ResultStorageError(
            f"Unable to access result archive {archive_path}: {exc}"
        ) from exc
    if not stat.S_ISDIR(archive_status.st_mode):
        raise ResultStorageError(
            f"Result archive path is not a directory: {archive_path}"
        )

    try:
        target_status = target_path.lstat()
    except FileNotFoundError as exc:
        raise ArchivedRunNotFoundError(
            f"Archived run {normalized_run_id} was not found"
        ) from exc
    except (OSError, ValueError) as exc:
        raise ResultStorageError(
            f"Unable to access archived run {normalized_run_id}: {exc}"
        ) from exc
    if not stat.S_ISREG(target_status.st_mode):
        raise CorruptArchivedRunError(
            f"Archived run {normalized_run_id} is not a regular file"
        )

    descriptor = None
    try:
        open_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        open_flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(target_path, open_flags)
        opened_status = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_status.st_mode)
            or opened_status.st_dev != target_status.st_dev
            or opened_status.st_ino != target_status.st_ino
        ):
            raise CorruptArchivedRunError(
                f"Archived run {normalized_run_id} changed while opening"
            )
        if opened_status.st_size > MAX_ARCHIVE_FILE_BYTES:
            raise CorruptArchivedRunError(
                f"Archived run {normalized_run_id} exceeds the "
                f"{MAX_ARCHIVE_FILE_BYTES}-byte storage limit"
            )
        with os.fdopen(descriptor, "rb") as archive_file:
            descriptor = None
            encoded_document = archive_file.read(
                MAX_ARCHIVE_FILE_BYTES + 1
            )
        if len(encoded_document) > MAX_ARCHIVE_FILE_BYTES:
            raise CorruptArchivedRunError(
                f"Archived run {normalized_run_id} exceeds the "
                f"{MAX_ARCHIVE_FILE_BYTES}-byte storage limit"
            )
        document = json.loads(
            encoded_document.decode("utf-8"),
            object_pairs_hook=reject_duplicate_json_object_keys,
            parse_constant=reject_non_finite_json_constant,
        )
        archived_run = archived_test_run_from_dict(document)
    except FileNotFoundError as exc:
        raise ArchivedRunNotFoundError(
            f"Archived run {normalized_run_id} was not found"
        ) from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise CorruptArchivedRunError(
                f"Archived run {normalized_run_id} is not a regular file"
            ) from exc
        raise ResultStorageError(
            f"Unable to read archived run {normalized_run_id}: {exc}"
        ) from exc
    except UnsupportedArchiveSchemaError:
        raise
    except CorruptArchivedRunError:
        raise
    except (
        OverflowError,
        RecursionError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise CorruptArchivedRunError(
            f"Archived run {normalized_run_id} is corrupt: {exc}"
        ) from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass

    if archived_run.run_id != normalized_run_id:
        raise CorruptArchivedRunError(
            f"Archived run {normalized_run_id} contains run ID "
            f"{archived_run.run_id}"
        )
    return archived_run
