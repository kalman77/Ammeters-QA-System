import io
import json
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from src.domain.enums.measurement_status import MeasurementStatus
from src.presentation.serialization.historical_comparison_to_dict import (
    historical_comparison_to_dict,
)
from src.testing.test_framework import AmmeterTestFramework


class PhaseFiveIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.config_path = Path(self._directory.name) / "config.yaml"
        self.archive_directory = (
            Path(self._directory.name) / "history"
        )
        self.config_path.write_text(
            """
testing:
  sampling:
    measurements_count: 2
    total_duration_seconds: 0.1
    sampling_frequency_hz: 20.0
network:
  host: "127.0.0.1"
  connect_timeout_seconds: 1.0
  read_timeout_seconds: 1.0
  startup_timeout_seconds: 2.0
  shutdown_timeout_seconds: 2.0
ammeters:
  greenlee:
    port: 0
    command: "ARCHIVE_GREENLEE"
  entes:
    port: 0
    command: "ARCHIVE_ENTES"
  circutor:
    port: 0
    command: "ARCHIVE_CIRCUTOR"
result_management:
  archive_directory: "history"
""".strip(),
            encoding="utf-8",
        )

    def _ammeter_thread_ids(self) -> set:
        return {
            id(thread)
            for thread in threading.enumerate()
            if thread.name.startswith("ammeter-")
        }

    def test_real_analyses_survive_restart_and_compare_without_io(
        self,
    ) -> None:
        baseline_thread_ids = self._ammeter_thread_ids()
        framework = AmmeterTestFramework(self.config_path)
        output = io.StringIO()

        with (
            patch.object(
                GreenleeAmmeter,
                "measure_current",
                side_effect=(1.0, 3.0, 2.0, 6.0),
            ) as measure_current,
            redirect_stdout(output),
        ):
            baseline = framework.results.archive(
                framework.analyze("greenlee"),
                metadata={"label": "baseline"},
            )
            candidate = framework.results.archive(
                framework.analyze("greenlee"),
                metadata={"label": "candidate"},
            )

        restarted_framework = AmmeterTestFramework(self.config_path)
        restored_baseline = restarted_framework.results.get(
            baseline.run_id
        )
        restored_candidate = restarted_framework.results.get(
            candidate.run_id
        )
        comparison = restarted_framework.results.compare(
            baseline.run_id,
            (candidate.run_id,),
        )

        self.assertEqual(restored_baseline, baseline)
        self.assertEqual(restored_candidate, candidate)
        self.assertIs(
            restored_baseline.analysis.sampling_result.status,
            MeasurementStatus.SUCCESS,
        )
        self.assertEqual(
            comparison.statistics_deltas[0].mean_current_delta,
            2.0,
        )
        self.assertTrue(comparison.same_ammeter_types[0])
        self.assertTrue(comparison.same_sampling_settings[0])
        self.assertEqual(measure_current.call_count, 4)
        self.assertEqual(
            output.getvalue().count(
                "GreenleeAmmeter is running on port"
            ),
            2,
        )
        self.assertEqual(output.getvalue().count("Connected by"), 4)
        self.assertEqual(
            len(tuple(self.archive_directory.glob("*.json"))),
            2,
        )
        self.assertEqual(
            self._ammeter_thread_ids(),
            baseline_thread_ids,
        )
        json.dumps(
            historical_comparison_to_dict(comparison),
            allow_nan=False,
        )


if __name__ == "__main__":
    unittest.main()
