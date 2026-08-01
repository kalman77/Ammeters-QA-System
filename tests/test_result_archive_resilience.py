import importlib
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from src.application.errors.archived_run_already_exists_error import (
    ArchivedRunAlreadyExistsError,
)
from src.application.errors.archived_run_not_found_error import (
    ArchivedRunNotFoundError,
)
from src.application.errors.corrupt_archived_run_error import (
    CorruptArchivedRunError,
)
from src.application.errors.invalid_historical_comparison_error import (
    InvalidHistoricalComparisonError,
)
from src.application.errors.result_storage_error import ResultStorageError
from src.application.use_cases.archive_sampling_analyses import (
    archive_sampling_analyses,
)
from src.application.use_cases.find_archived_test_runs import (
    find_archived_test_runs,
)
from src.application.use_cases.resolve_archived_run_query import (
    resolve_archived_run_query,
)
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
from src.testing.ammeter_result_manager import AmmeterResultManager
from tests.result_archive_fixtures import (
    RUN_ID,
    SECOND_RUN_ID,
    build_archived_test_run,
)


SAVE_MODULE = importlib.import_module(
    "src.infrastructure.persistence.save_archived_test_run"
)
LOAD_MODULE = importlib.import_module(
    "src.infrastructure.persistence.load_archived_test_run"
)
LIST_MODULE = importlib.import_module(
    "src.infrastructure.persistence.list_archived_test_runs"
)
PUBLISH_MODULE = importlib.import_module(
    "src.infrastructure.persistence.publish_archive_without_overwrite"
)


class AtomicArchivePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.archive_directory = Path(self._temporary_directory.name)
        self.archived_run = build_archived_test_run()

    def test_non_cooperating_race_cannot_overwrite_destination(
        self,
    ) -> None:
        target_path = self.archive_directory / f"{RUN_ID}.json"
        competing_bytes = b'{"owned_by": "another writer"}\n'
        real_link = os.link

        def publish_after_competitor(source, target):
            Path(target).write_bytes(competing_bytes)
            return real_link(source, target)

        with patch.object(
            SAVE_MODULE.os,
            "link",
            side_effect=publish_after_competitor,
        ):
            with self.assertRaises(ArchivedRunAlreadyExistsError):
                save_archived_test_run(
                    self.archive_directory,
                    self.archived_run,
                )

        self.assertEqual(target_path.read_bytes(), competing_bytes)
        self.assertEqual(
            tuple(
                path
                for path in self.archive_directory.iterdir()
                if path.name.startswith(".")
            ),
            (),
        )

    def test_publish_failure_leaves_no_partial_or_temporary_file(
        self,
    ) -> None:
        with patch.object(
            SAVE_MODULE.os,
            "link",
            side_effect=OSError("publish failed"),
        ):
            with self.assertRaises(ResultStorageError):
                save_archived_test_run(
                    self.archive_directory,
                    self.archived_run,
                )

        self.assertEqual(tuple(self.archive_directory.iterdir()), ())

    def test_encoding_and_fsync_failures_leave_no_visible_record(
        self,
    ) -> None:
        for dependency, failure in (
            (
                "json.dump",
                patch.object(
                    SAVE_MODULE.json,
                    "dump",
                    side_effect=ValueError("encoding failed"),
                ),
            ),
            (
                "os.fsync",
                patch.object(
                    SAVE_MODULE.os,
                    "fsync",
                    side_effect=OSError("fsync failed"),
                ),
            ),
        ):
            with self.subTest(dependency=dependency), failure:
                with self.assertRaises(ResultStorageError):
                    save_archived_test_run(
                        self.archive_directory,
                        self.archived_run,
                    )
                self.assertEqual(
                    tuple(self.archive_directory.iterdir()),
                    (),
                )

    def test_reader_sees_not_found_before_atomic_publication(
        self,
    ) -> None:
        publish = SAVE_MODULE.publish_archive_without_overwrite
        observed_before_publish = []

        def inspect_then_publish(temporary_path, target_path):
            try:
                load_archived_test_run(
                    self.archive_directory,
                    RUN_ID,
                )
            except ArchivedRunNotFoundError:
                observed_before_publish.append(
                    ArchivedRunNotFoundError
                )
            publish(temporary_path, target_path)

        with patch.object(
            SAVE_MODULE,
            "publish_archive_without_overwrite",
            side_effect=inspect_then_publish,
        ):
            save_archived_test_run(
                self.archive_directory,
                self.archived_run,
            )

        self.assertEqual(
            observed_before_publish,
            [ArchivedRunNotFoundError],
        )
        self.assertEqual(
            load_archived_test_run(self.archive_directory, RUN_ID),
            self.archived_run,
        )

    def test_temporary_cleanup_failure_does_not_hide_commit(
        self,
    ) -> None:
        real_unlink = Path.unlink
        failed_once = False

        def fail_first_temporary_unlink(path, *args, **kwargs):
            nonlocal failed_once
            if path.suffix == ".tmp" and not failed_once:
                failed_once = True
                raise OSError("temporary cleanup failed")
            return real_unlink(path, *args, **kwargs)

        with patch.object(
            SAVE_MODULE.Path,
            "unlink",
            autospec=True,
            side_effect=fail_first_temporary_unlink,
        ):
            save_archived_test_run(
                self.archive_directory,
                self.archived_run,
            )

        self.assertTrue(failed_once)
        self.assertEqual(
            load_archived_test_run(self.archive_directory, RUN_ID),
            self.archived_run,
        )
        self.assertEqual(
            tuple(
                path
                for path in self.archive_directory.iterdir()
                if path.name.startswith(".")
            ),
            (),
        )

    def test_same_id_concurrency_publishes_exactly_one_record(
        self,
    ) -> None:
        start_barrier = Barrier(2)

        def save_concurrently():
            start_barrier.wait()
            try:
                save_archived_test_run(
                    self.archive_directory,
                    self.archived_run,
                )
            except ArchivedRunAlreadyExistsError:
                return "duplicate"
            return "saved"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = tuple(
                executor.map(
                    lambda _: save_concurrently(),
                    range(2),
                )
            )

        self.assertCountEqual(outcomes, ("saved", "duplicate"))
        self.assertEqual(
            load_archived_test_run(self.archive_directory, RUN_ID),
            self.archived_run,
        )
        self.assertEqual(
            tuple(
                path
                for path in self.archive_directory.iterdir()
                if path.name.startswith(".")
            ),
            (),
        )

    def test_windows_publication_uses_no_replace_rename_path(
        self,
    ) -> None:
        temporary_path = self.archive_directory / ".temporary"
        target_path = self.archive_directory / f"{RUN_ID}.json"

        with (
            patch.object(PUBLISH_MODULE.os, "name", "nt"),
            patch.object(PUBLISH_MODULE.os, "rename") as rename,
            patch.object(PUBLISH_MODULE.os, "link") as link,
        ):
            PUBLISH_MODULE.publish_archive_without_overwrite(
                temporary_path,
                target_path,
            )

        rename.assert_called_once_with(temporary_path, target_path)
        link.assert_not_called()

    def test_file_size_limit_is_enforced_before_publish_and_read(
        self,
    ) -> None:
        with patch.object(
            SAVE_MODULE,
            "MAX_ARCHIVE_FILE_BYTES",
            10,
        ):
            with self.assertRaises(ResultStorageError):
                save_archived_test_run(
                    self.archive_directory,
                    self.archived_run,
                )
        self.assertEqual(tuple(self.archive_directory.iterdir()), ())

        target_path = self.archive_directory / f"{RUN_ID}.json"
        target_path.write_text("x" * 11, encoding="utf-8")
        with patch.object(
            LOAD_MODULE,
            "MAX_ARCHIVE_FILE_BYTES",
            10,
        ):
            with self.assertRaises(CorruptArchivedRunError):
                load_archived_test_run(
                    self.archive_directory,
                    RUN_ID,
                )


class DefensiveArchiveLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.archive_directory = Path(self._temporary_directory.name)

    def test_duplicate_json_object_keys_are_corruption(self) -> None:
        document = archived_test_run_to_dict(build_archived_test_run())
        encoded = json.dumps(document)
        encoded = encoded.replace(
            '"schema_version": 1',
            '"schema_version": 999, "schema_version": 1',
            1,
        )
        (self.archive_directory / f"{RUN_ID}.json").write_text(
            encoded,
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            CorruptArchivedRunError,
            "duplicate JSON object key",
        ):
            load_archived_test_run(self.archive_directory, RUN_ID)

    def test_non_standard_non_finite_json_is_corruption(self) -> None:
        document = archived_test_run_to_dict(build_archived_test_run())
        encoded = json.dumps(document).replace(
            '"current": 1.0',
            '"current": NaN',
            1,
        )
        (self.archive_directory / f"{RUN_ID}.json").write_text(
            encoded,
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            CorruptArchivedRunError,
            "non-finite JSON constant",
        ):
            load_archived_test_run(self.archive_directory, RUN_ID)

    def test_deeply_nested_json_is_typed_corruption(self) -> None:
        nested_document = "[" * 2_000 + "]" * 2_000
        (self.archive_directory / f"{RUN_ID}.json").write_text(
            nested_document,
            encoding="utf-8",
        )

        with self.assertRaises(CorruptArchivedRunError):
            load_archived_test_run(self.archive_directory, RUN_ID)

    def test_symlink_archive_is_rejected_without_following_it(self) -> None:
        outside_path = (
            Path(self._temporary_directory.name).parent
            / f"outside-{RUN_ID}.json"
        )
        self.addCleanup(outside_path.unlink, missing_ok=True)
        outside_path.write_text(
            json.dumps(
                archived_test_run_to_dict(build_archived_test_run())
            ),
            encoding="utf-8",
        )
        target_path = self.archive_directory / f"{RUN_ID}.json"
        try:
            target_path.symlink_to(outside_path)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symbolic links unavailable: {exc}")

        with self.assertRaises(CorruptArchivedRunError):
            load_archived_test_run(self.archive_directory, RUN_ID)

    def test_swap_to_symlink_during_open_is_rejected(self) -> None:
        target_path = self.archive_directory / f"{RUN_ID}.json"
        outside_path = self.archive_directory / "outside.json"
        valid_document = json.dumps(
            archived_test_run_to_dict(build_archived_test_run())
        )
        target_path.write_text(valid_document, encoding="utf-8")
        outside_path.write_text(valid_document, encoding="utf-8")
        probe_path = self.archive_directory / "probe"
        try:
            probe_path.symlink_to(outside_path)
            probe_path.unlink()
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symbolic links unavailable: {exc}")

        real_open = os.open
        swapped = False

        def swap_before_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if Path(path) == target_path and not swapped:
                swapped = True
                target_path.unlink()
                target_path.symlink_to(outside_path)
            return real_open(path, flags, *args, **kwargs)

        with patch.object(
            LOAD_MODULE.os,
            "open",
            side_effect=swap_before_open,
        ):
            with self.assertRaises(CorruptArchivedRunError):
                load_archived_test_run(
                    self.archive_directory,
                    RUN_ID,
                )

    def test_permission_errors_are_storage_failures_not_empty_history(
        self,
    ) -> None:
        with patch.object(
            LOAD_MODULE.Path,
            "stat",
            side_effect=PermissionError("denied"),
        ):
            with self.assertRaises(ResultStorageError):
                load_archived_test_run(
                    self.archive_directory,
                    RUN_ID,
                )
        with patch.object(
            LIST_MODULE.Path,
            "stat",
            side_effect=PermissionError("denied"),
        ):
            with self.assertRaises(ResultStorageError):
                list_archived_test_runs(self.archive_directory)


class ResultManagementPolicyEdgeTests(unittest.TestCase):
    def test_archive_all_validates_every_analysis_before_first_save(
        self,
    ) -> None:
        valid_analysis = build_archived_test_run().analysis
        saved_runs = []

        with self.assertRaises(ValueError):
            archive_sampling_analyses(
                {
                    "greenlee": valid_analysis,
                    "entes": valid_analysis,
                },
                None,
                save_archived_run=saved_runs.append,
                generate_run_id=lambda: RUN_ID,
                utc_clock=lambda: (
                    build_archived_test_run().archived_at_utc
                ),
            )

        self.assertEqual(saved_runs, [])

    def test_metadata_filter_distinguishes_boolean_and_integer(
        self,
    ) -> None:
        archived_run = build_archived_test_run(
            metadata=(),
        )
        integer_run = build_archived_test_run(
            run_id=SECOND_RUN_ID,
            metadata=(),
        )
        archived_run = type(archived_run)(
            run_id=archived_run.run_id,
            archived_at_utc=archived_run.archived_at_utc,
            analysis=archived_run.analysis,
            metadata=resolve_archived_run_query(
                metadata={"value": True}
            ).metadata,
        )
        integer_run = type(integer_run)(
            run_id=integer_run.run_id,
            archived_at_utc=integer_run.archived_at_utc,
            analysis=integer_run.analysis,
            metadata=resolve_archived_run_query(
                metadata={"value": 1}
            ).metadata,
        )
        query = resolve_archived_run_query(metadata={"value": True})

        self.assertEqual(
            find_archived_test_runs(
                query,
                list_archived_runs=lambda: (
                    integer_run,
                    archived_run,
                ),
            ),
            (archived_run,),
        )

    def test_empty_comparison_is_rejected_before_archive_reads(
        self,
    ) -> None:
        read_calls = []
        manager = AmmeterResultManager(
            save_archived_run=lambda run: None,
            load_archived_run=lambda run_id: read_calls.append(run_id),
            list_archived_runs=lambda: (),
            generate_run_id=lambda: RUN_ID,
            utc_clock=lambda: build_archived_test_run().archived_at_utc,
        )

        with self.assertRaises(InvalidHistoricalComparisonError):
            manager.compare(RUN_ID, ())

        self.assertEqual(read_calls, [])

    def test_archive_all_retains_only_records_before_storage_failure(
        self,
    ) -> None:
        analyses = {
            "greenlee": build_archived_test_run(
                ammeter_type="greenlee"
            ).analysis,
            "entes": build_archived_test_run(
                ammeter_type="entes"
            ).analysis,
            "circutor": build_archived_test_run(
                ammeter_type="circutor"
            ).analysis,
        }
        generated_ids = iter((RUN_ID, SECOND_RUN_ID))
        saved_runs = []

        def fail_second_save(archived_run):
            if saved_runs:
                raise ResultStorageError("second save failed")
            saved_runs.append(archived_run)

        with self.assertRaisesRegex(
            ResultStorageError,
            "second save failed",
        ):
            archive_sampling_analyses(
                analyses,
                None,
                save_archived_run=fail_second_save,
                generate_run_id=lambda: next(generated_ids),
                utc_clock=lambda: (
                    build_archived_test_run().archived_at_utc
                ),
            )

        self.assertEqual(len(saved_runs), 1)
        self.assertEqual(
            saved_runs[0].analysis.sampling_result.ammeter_type,
            "greenlee",
        )


if __name__ == "__main__":
    unittest.main()
