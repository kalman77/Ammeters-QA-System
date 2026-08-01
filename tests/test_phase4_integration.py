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
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.sampling_analysis import SamplingAnalysis
from src.presentation.serialization.sampling_analysis_to_dict import (
    sampling_analysis_to_dict,
)
from src.testing.test_framework import AmmeterTestFramework


class PhaseFourIntegrationTests(unittest.TestCase):
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
    command: "ANALYSIS_GREENLEE"
  entes:
    port: 0
    command: "ANALYSIS_ENTES"
  circutor:
    port: 0
    command: "ANALYSIS_CIRCUTOR"
""".strip(),
            encoding="utf-8",
        )

    def _ammeter_thread_ids(self) -> set:
        return {
            id(thread)
            for thread in threading.enumerate()
            if thread.name.startswith("ammeter-")
        }

    def test_real_tcp_analysis_uses_one_port_zero_emulator_session(
        self,
    ) -> None:
        baseline_thread_ids = self._ammeter_thread_ids()
        framework = AmmeterTestFramework(self.config_path)
        output = io.StringIO()

        with (
            patch.object(
                GreenleeAmmeter,
                "measure_current",
                side_effect=[1.0, 3.0, 5.0],
            ) as greenlee_measure,
            patch.object(
                EntesAmmeter,
                "measure_current",
                return_value=99.0,
            ) as entes_measure,
            redirect_stdout(output),
        ):
            analysis = framework.analyze("greenlee")

        self.assertIsInstance(analysis, SamplingAnalysis)
        self.assertIs(
            analysis.sampling_result.status,
            MeasurementStatus.SUCCESS,
        )
        self.assertEqual(
            [
                sample.result.current
                for sample in analysis.sampling_result.samples
            ],
            [1.0, 3.0, 5.0],
        )
        self.assertIsNotNone(analysis.statistics)
        self.assertEqual(analysis.statistics.measurements_count, 3)
        self.assertEqual(analysis.statistics.mean_current, 3.0)
        self.assertEqual(analysis.statistics.median_current, 3.0)
        self.assertAlmostEqual(
            analysis.statistics.standard_deviation_current,
            1.632993161855452,
        )
        self.assertEqual(analysis.statistics.minimum_current, 1.0)
        self.assertEqual(analysis.statistics.maximum_current, 5.0)
        greenlee_measure.assert_has_calls(
            [unittest.mock.call(), unittest.mock.call(), unittest.mock.call()]
        )
        entes_measure.assert_not_called()
        self.assertEqual(
            output.getvalue().count(
                "GreenleeAmmeter is running on port"
            ),
            1,
        )
        self.assertEqual(output.getvalue().count("Connected by"), 3)
        self.assertEqual(self._ammeter_thread_ids(), baseline_thread_ids)
        json.dumps(
            sampling_analysis_to_dict(analysis),
            allow_nan=False,
        )
        self.assertEqual(
            framework.config["ammeters"]["greenlee"]["port"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
