import json
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from src.application.errors.archived_run_already_exists_error import (
    ArchivedRunAlreadyExistsError,
)
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
from src.domain.models.run_metadata_entry import RunMetadataEntry
from src.infrastructure.persistence.list_archived_test_runs import (
    list_archived_test_runs,
)
from src.infrastructure.persistence.load_archived_test_run import (
    load_archived_test_run,
)
from src.infrastructure.persistence.save_archived_test_run import (
    save_archived_test_run,
)
from src.presentation.serialization.archived_test_run_to_dict import (
    archived_test_run_to_dict,
)
from tests.result_archive_fixtures import (
    RUN_ID,
    SAMPLING_STARTED_AT,
    SECOND_RUN_ID,
    THIRD_RUN_ID,
    build_archived_test_run,
)


class ResultArchivePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.archive_directory = (
            Path(self._temporary_directory.name) / "nested" / "archive"
        )

    def _document_path(self, run_id: str) -> Path:
        return self.archive_directory / f"{run_id}.json"

    def _write_document(self, run_id: str, document: object) -> None:
        self.archive_directory.mkdir(parents=True, exist_ok=True)
        self._document_path(run_id).write_text(
            json.dumps(document, allow_nan=False),
            encoding="utf-8",
        )

    def test_save_creates_archive_and_loads_complete_typed_result(
        self,
    ) -> None:
        archived_run = build_archived_test_run()

        save_archived_test_run(self.archive_directory, archived_run)

        self.assertTrue(self._document_path(RUN_ID).is_file())
        stored_document = json.loads(
            self._document_path(RUN_ID).read_text(encoding="utf-8")
        )
        self.assertEqual(
            stored_document,
            archived_test_run_to_dict(archived_run),
        )
        self.assertEqual(
            load_archived_test_run(self.archive_directory, RUN_ID),
            archived_run,
        )
        self.assertEqual(
            list_archived_test_runs(self.archive_directory),
            (archived_run,),
        )
        self.assertEqual(
            [
                path.name
                for path in self.archive_directory.iterdir()
                if path.name.startswith(".")
            ],
            [],
        )

    def test_duplicate_save_is_append_only_and_does_not_clobber(
        self,
    ) -> None:
        original = build_archived_test_run()
        replacement = build_archived_test_run(
            metadata=(
                RunMetadataEntry(key="operator", value="Someone else"),
            ),
            currents=(100.0, 200.0),
        )
        save_archived_test_run(self.archive_directory, original)
        original_bytes = self._document_path(RUN_ID).read_bytes()

        with self.assertRaises(ArchivedRunAlreadyExistsError):
            save_archived_test_run(
                self.archive_directory,
                replacement,
            )

        self.assertEqual(
            self._document_path(RUN_ID).read_bytes(),
            original_bytes,
        )
        self.assertEqual(
            load_archived_test_run(self.archive_directory, RUN_ID),
            original,
        )

    def test_load_rejects_missing_and_traversal_like_identifiers(
        self,
    ) -> None:
        with self.assertRaises(ArchivedRunNotFoundError):
            load_archived_test_run(
                self.archive_directory,
                SECOND_RUN_ID,
            )

        for invalid_run_id in (
            "../outside",
            f"../{RUN_ID}",
            f"{RUN_ID}/../../outside",
            f"{RUN_ID}.json",
            RUN_ID.upper(),
            "",
            None,
        ):
            with self.subTest(run_id=invalid_run_id):
                with self.assertRaises(InvalidRunIdError):
                    load_archived_test_run(
                        self.archive_directory,
                        invalid_run_id,
                    )

    def test_load_maps_invalid_json_and_non_document_roots_to_corruption(
        self,
    ) -> None:
        self.archive_directory.mkdir(parents=True)
        self._document_path(RUN_ID).write_text(
            "{not valid json",
            encoding="utf-8",
        )
        with self.assertRaises(CorruptArchivedRunError):
            load_archived_test_run(self.archive_directory, RUN_ID)

        self._write_document(RUN_ID, [])
        with self.assertRaises(CorruptArchivedRunError):
            load_archived_test_run(self.archive_directory, RUN_ID)

    def test_load_preserves_unsupported_schema_as_a_typed_error(
        self,
    ) -> None:
        document = archived_test_run_to_dict(build_archived_test_run())
        document["schema_version"] = 999
        self._write_document(RUN_ID, document)

        with self.assertRaises(UnsupportedArchiveSchemaError):
            load_archived_test_run(self.archive_directory, RUN_ID)

    def test_load_and_list_reject_file_payload_id_mismatch(self) -> None:
        mismatched_document = archived_test_run_to_dict(
            build_archived_test_run(run_id=SECOND_RUN_ID)
        )
        self._write_document(RUN_ID, mismatched_document)

        with self.assertRaises(CorruptArchivedRunError):
            load_archived_test_run(self.archive_directory, RUN_ID)
        with self.assertRaises(CorruptArchivedRunError):
            list_archived_test_runs(self.archive_directory)

    def test_list_ignores_hidden_transient_and_unrelated_files(
        self,
    ) -> None:
        archived_run = build_archived_test_run()
        save_archived_test_run(self.archive_directory, archived_run)
        ignored_files = {
            ".temporary.json": "{broken",
            f".{SECOND_RUN_ID}.lock": "",
            f".{SECOND_RUN_ID}.tmp": "{broken",
            "notes.txt": "not an archive",
            "not-a-run-id.json": "{broken",
            f"{SECOND_RUN_ID}.json.backup": "{broken",
        }
        for file_name, contents in ignored_files.items():
            (self.archive_directory / file_name).write_text(
                contents,
                encoding="utf-8",
            )
        (self.archive_directory / "unrelated-directory").mkdir()

        self.assertEqual(
            list_archived_test_runs(self.archive_directory),
            (archived_run,),
        )

    def test_list_is_newest_first_with_run_id_tiebreak(self) -> None:
        runs = (
            build_archived_test_run(
                run_id=THIRD_RUN_ID,
                archived_at_utc=SAMPLING_STARTED_AT
                + timedelta(seconds=4.0),
            ),
            build_archived_test_run(
                run_id=RUN_ID,
                archived_at_utc=SAMPLING_STARTED_AT
                + timedelta(seconds=2.0),
            ),
            build_archived_test_run(
                run_id=SECOND_RUN_ID,
                archived_at_utc=SAMPLING_STARTED_AT
                + timedelta(seconds=4.0),
            ),
        )
        for archived_run in runs:
            save_archived_test_run(
                self.archive_directory,
                archived_run,
            )

        listed_runs = list_archived_test_runs(self.archive_directory)

        self.assertEqual(
            tuple(run.run_id for run in listed_runs),
            (SECOND_RUN_ID, THIRD_RUN_ID, RUN_ID),
        )

    def test_filesystem_target_failures_are_typed(self) -> None:
        blocking_file = Path(self._temporary_directory.name) / "not-a-dir"
        blocking_file.write_text("content", encoding="utf-8")

        with self.assertRaises(ResultStorageError):
            save_archived_test_run(
                blocking_file,
                build_archived_test_run(),
            )
        with self.assertRaises(ResultStorageError):
            load_archived_test_run(blocking_file, RUN_ID)
        with self.assertRaises(ResultStorageError):
            list_archived_test_runs(blocking_file)


if __name__ == "__main__":
    unittest.main()
