import os
import unittest
from collections import OrderedDict
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from src.application.errors.result_management_configuration_error import (
    ResultManagementConfigurationError,
)
from src.domain.enums.measurement_status import MeasurementStatus
from src.testing.ammeter_result_manager import AmmeterResultManager
from src.testing.test_framework import AmmeterTestFramework
from tests.result_archive_fixtures import (
    RUN_ID,
    SAMPLING_STARTED_AT,
    SECOND_RUN_ID,
    THIRD_RUN_ID,
    build_archived_test_run,
)


def framework_config(*, archive_directory=None) -> str:
    result_management = (
        ""
        if archive_directory is None
        else (
            "\nresult_management:\n"
            f'  archive_directory: "{archive_directory}"\n'
        )
    )
    return (
        """
testing:
  sampling:
    measurements_count: 2
    total_duration_seconds: 1.0
    sampling_frequency_hz: 2.0
network:
  host: "127.0.0.1"
  connect_timeout_seconds: 1.0
  read_timeout_seconds: 1.0
  startup_timeout_seconds: 1.0
  shutdown_timeout_seconds: 1.0
ammeters:
  greenlee:
    port: 0
    command: "GREENLEE"
  entes:
    port: 0
    command: "ENTES"
  circutor:
    port: 0
    command: "CIRCUTOR"
""".strip()
        + result_management
    )


class AmmeterResultManagerTests(unittest.TestCase):
    def test_archive_and_archive_all_delegate_without_new_measurements(
        self,
    ) -> None:
        greenlee_analysis = build_archived_test_run().analysis
        entes_analysis = build_archived_test_run(
            run_id=SECOND_RUN_ID,
            ammeter_type="entes",
            currents=(10.0, 14.0),
        ).analysis
        generated_ids = iter((RUN_ID, SECOND_RUN_ID, THIRD_RUN_ID))
        archived_times = iter(
            (
                SAMPLING_STARTED_AT,
                SAMPLING_STARTED_AT + timedelta(seconds=1),
                SAMPLING_STARTED_AT + timedelta(seconds=2),
            )
        )
        saved_runs = []

        def forbidden_read(*args, **kwargs):
            self.fail("archive operations must not read the archive")

        manager = AmmeterResultManager(
            save_archived_run=saved_runs.append,
            load_archived_run=forbidden_read,
            list_archived_runs=forbidden_read,
            generate_run_id=lambda: next(generated_ids),
            utc_clock=lambda: next(archived_times),
        )

        one = manager.archive(
            greenlee_analysis,
            metadata={"operator": "Nir"},
        )
        all_runs = manager.archive_all(
            OrderedDict(
                (
                    ("greenlee", greenlee_analysis),
                    ("entes", entes_analysis),
                )
            ),
            metadata={"batch": "nightly"},
        )

        self.assertIs(one.analysis, greenlee_analysis)
        self.assertEqual(one.run_id, RUN_ID)
        self.assertEqual(
            tuple(entry.key for entry in one.metadata),
            ("operator",),
        )
        self.assertEqual(list(all_runs), ["greenlee", "entes"])
        self.assertIs(
            all_runs["greenlee"].analysis,
            greenlee_analysis,
        )
        self.assertIs(all_runs["entes"].analysis, entes_analysis)
        self.assertEqual(
            [run.run_id for run in saved_runs],
            [RUN_ID, SECOND_RUN_ID, THIRD_RUN_ID],
        )

    def test_get_find_and_compare_are_strictly_read_only(self) -> None:
        baseline = build_archived_test_run(
            archived_at_utc=SAMPLING_STARTED_AT,
        )
        candidate = build_archived_test_run(
            run_id=SECOND_RUN_ID,
            archived_at_utc=SAMPLING_STARTED_AT
            + timedelta(seconds=1),
            currents=(2.0, 6.0),
        )
        stored_by_id = {
            baseline.run_id: baseline,
            candidate.run_id: candidate,
        }
        load_calls = []
        list_calls = []

        def forbidden_write(*args, **kwargs):
            self.fail(
                "read-only result operations must not write, generate IDs, "
                "or read the clock"
            )

        def load_archived_run(run_id):
            load_calls.append(run_id)
            return stored_by_id[run_id]

        def list_archived_runs():
            list_calls.append(True)
            return (baseline, candidate)

        manager = AmmeterResultManager(
            save_archived_run=forbidden_write,
            load_archived_run=load_archived_run,
            list_archived_runs=list_archived_runs,
            generate_run_id=forbidden_write,
            utc_clock=forbidden_write,
        )

        self.assertIs(manager.get(RUN_ID), baseline)
        found = manager.find(
            ammeter_type=" GREENLEE ",
            status=" SUCCESS ",
            has_statistics=True,
            limit=1,
        )
        comparison = manager.compare(
            RUN_ID,
            (run_id for run_id in (SECOND_RUN_ID,)),
        )

        self.assertEqual(found, (candidate,))
        self.assertIs(comparison.baseline, baseline)
        self.assertEqual(comparison.candidates, (candidate,))
        self.assertEqual(
            comparison.statistics_deltas[0].mean_current_delta,
            2.0,
        )
        self.assertEqual(
            load_calls,
            [RUN_ID, RUN_ID, SECOND_RUN_ID],
        )
        self.assertEqual(list_calls, [True])
        self.assertEqual(
            stored_by_id,
            {
                baseline.run_id: baseline,
                candidate.run_id: candidate,
            },
        )


class FrameworkResultManagerCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.config_directory = Path(self._temporary_directory.name) / "cfg"
        self.config_directory.mkdir()
        self.config_path = self.config_directory / "ammeter.yaml"

    def test_result_configuration_is_lazy(self) -> None:
        self.config_path.write_text(
            framework_config(),
            encoding="utf-8",
        )

        framework = AmmeterTestFramework(self.config_path)

        self.assertEqual(
            framework.ammeter_types,
            ("greenlee", "entes", "circutor"),
        )
        with self.assertRaises(ResultManagementConfigurationError):
            _ = framework.results

    def test_results_is_cached_and_resolves_path_relative_to_config(
        self,
    ) -> None:
        relative_archive = Path("history") / "archive"
        expected_archive = (
            self.config_directory / relative_archive
        ).resolve()
        self.config_path.write_text(
            framework_config(
                archive_directory=relative_archive.as_posix()
            ),
            encoding="utf-8",
        )
        framework = AmmeterTestFramework(
            self.config_path,
            utc_clock=lambda: SAMPLING_STARTED_AT,
        )

        first_manager = framework.results

        self.assertIs(first_manager, framework.results)
        self.assertFalse(expected_archive.exists())

        archived_run = first_manager.archive(
            build_archived_test_run().analysis,
            metadata={"source": "framework"},
        )

        self.assertTrue(
            (expected_archive / f"{archived_run.run_id}.json").is_file()
        )
        self.assertEqual(first_manager.get(archived_run.run_id), archived_run)
        self.assertEqual(first_manager.find(), (archived_run,))
        self.assertEqual(
            archived_run.archived_at_utc,
            SAMPLING_STARTED_AT,
        )

    def test_injected_manager_bypasses_archive_configuration(self) -> None:
        self.config_path.write_text(
            framework_config(),
            encoding="utf-8",
        )
        injected_manager = object()

        framework = AmmeterTestFramework(
            self.config_path,
            result_manager=injected_manager,
        )

        self.assertIs(framework.results, injected_manager)
        self.assertIs(framework.results, injected_manager)

    def test_relative_config_path_is_frozen_before_cwd_changes(
        self,
    ) -> None:
        expected_archive = self.config_directory / "history"
        self.config_path.write_text(
            framework_config(archive_directory="history"),
            encoding="utf-8",
        )
        other_directory = Path(
            self._temporary_directory.name
        ) / "other"
        other_directory.mkdir()
        original_directory = Path.cwd()
        try:
            os.chdir(self.config_directory.parent)
            relative_config_path = self.config_path.relative_to(
                self.config_directory.parent
            )
            framework = AmmeterTestFramework(
                relative_config_path,
                utc_clock=lambda: SAMPLING_STARTED_AT,
            )
            os.chdir(other_directory)

            archived_run = framework.results.archive(
                build_archived_test_run().analysis
            )
        finally:
            os.chdir(original_directory)

        self.assertTrue(
            (
                expected_archive
                / f"{archived_run.run_id}.json"
            ).is_file()
        )


if __name__ == "__main__":
    unittest.main()
