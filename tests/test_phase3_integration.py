import io
import json
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.presentation.serialization.sampling_result_to_dict import (
    sampling_result_to_dict,
)
from src.testing.test_framework import AmmeterTestFramework


class PhaseThreeIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.config_path = Path(self._directory.name) / "config.yaml"
        self.config_path.write_text(
            """
testing:
  sampling:
    measurements_count: 3
    total_duration_seconds: 0.3
    sampling_frequency_hz: 10.0
network:
  host: "127.0.0.1"
  connect_timeout_seconds: 1.0
  read_timeout_seconds: 1.0
  startup_timeout_seconds: 2.0
  shutdown_timeout_seconds: 2.0
ammeters:
  greenlee:
    port: 0
    command: "SAMPLING_GREENLEE"
  entes:
    port: 0
    command: "SAMPLING_ENTES"
  circutor:
    port: 0
    command: "SAMPLING_CIRCUTOR"
""".strip(),
            encoding="utf-8",
        )

    def _ammeter_thread_ids(self) -> set:
        return {
            id(thread)
            for thread in threading.enumerate()
            if thread.name.startswith("ammeter-")
        }

    def test_real_tcp_sampling_reuses_one_selected_emulator(self) -> None:
        baseline_thread_ids = self._ammeter_thread_ids()
        framework = AmmeterTestFramework(self.config_path)
        output = io.StringIO()

        with (
            patch.object(
                GreenleeAmmeter,
                "measure_current",
                side_effect=[1.0, 2.0, 3.0],
            ) as greenlee_measure,
            patch.object(
                EntesAmmeter,
                "measure_current",
                return_value=99.0,
            ) as entes_measure,
            redirect_stdout(output),
        ):
            result = framework.sample("greenlee")

        self.assertIs(result.status, MeasurementStatus.SUCCESS)
        self.assertEqual(
            [sample.result.current for sample in result.samples],
            [1.0, 2.0, 3.0],
        )
        self.assertEqual(
            [
                sample.scheduled_elapsed_seconds
                for sample in result.samples
            ],
            [0.0, 0.1, 0.2],
        )
        self.assertEqual(greenlee_measure.call_count, 3)
        entes_measure.assert_not_called()
        self.assertEqual(
            output.getvalue().count(
                "GreenleeAmmeter is running on port"
            ),
            1,
        )
        self.assertEqual(output.getvalue().count("Connected by"), 3)
        self.assertEqual(self._ammeter_thread_ids(), baseline_thread_ids)
        json.dumps(sampling_result_to_dict(result))

    def test_real_tcp_failure_does_not_cancel_later_slots(self) -> None:
        baseline_thread_ids = self._ammeter_thread_ids()
        framework = AmmeterTestFramework(self.config_path)

        with (
            patch.object(
                GreenleeAmmeter,
                "measure_current",
                side_effect=[1.0, float("nan"), 3.0],
            ),
            redirect_stdout(io.StringIO()),
        ):
            result = framework.sample("greenlee")

        self.assertIs(result.status, MeasurementStatus.PARTIAL)
        self.assertEqual(result.samples[0].result.current, 1.0)
        self.assertIsNone(result.samples[1].result.current)
        self.assertEqual(result.samples[2].result.current, 3.0)
        self.assertIs(
            result.samples[1].result.errors[0].code,
            MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
        )
        self.assertEqual(self._ammeter_thread_ids(), baseline_thread_ids)


if __name__ == "__main__":
    unittest.main()
