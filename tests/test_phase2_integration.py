import io
import threading
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_result import MeasurementResult
from src.testing.test_framework import AmmeterTestFramework


class PhaseTwoIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.config_path = Path(self._directory.name) / "config.yaml"
        self.config_path.write_text(
            """
network:
  host: "127.0.0.1"
  connect_timeout_seconds: 1.0
  read_timeout_seconds: 1.0
  startup_timeout_seconds: 2.0
  shutdown_timeout_seconds: 2.0
ammeters:
  greenlee:
    port: 0
    command: "INTEGRATION_GREENLEE"
  entes:
    port: 0
    command: "INTEGRATION_ENTES"
  circutor:
    port: 0
    command: "INTEGRATION_CIRCUTOR"
""".strip(),
            encoding="utf-8",
        )

    def _ammeter_thread_ids(self) -> set:
        return {
            id(thread)
            for thread in threading.enumerate()
            if thread.name.startswith("ammeter-")
        }

    def test_requested_meter_uses_real_tcp_path_and_only_its_adapter(
        self,
    ) -> None:
        baseline_thread_ids = self._ammeter_thread_ids()
        framework = AmmeterTestFramework(self.config_path)
        output = io.StringIO()

        with (
            patch.object(
                GreenleeAmmeter,
                "measure_current",
                return_value=6.25,
            ) as greenlee_measure,
            patch.object(
                EntesAmmeter,
                "measure_current",
                return_value=7.5,
            ) as entes_measure,
            patch.object(
                CircutorAmmeter,
                "measure_current",
                return_value=8.75,
            ) as circutor_measure,
            redirect_stdout(output),
        ):
            result = framework.measure("greenlee")

        self.assertIsInstance(result, MeasurementResult)
        self.assertIs(result.status, MeasurementStatus.SUCCESS)
        self.assertEqual(result.ammeter_type, "greenlee")
        self.assertEqual(result.current, 6.25)
        self.assertEqual(result.unit, "A")
        self.assertEqual(result.errors, ())
        self.assertIsNotNone(result.request_latency_seconds)
        self.assertGreaterEqual(result.request_latency_seconds, 0.0)
        self.assertEqual(result.timestamp_utc.utcoffset(), timedelta(0))
        greenlee_measure.assert_called_once_with()
        entes_measure.assert_not_called()
        circutor_measure.assert_not_called()
        self.assertIn("GreenleeAmmeter is running on port", output.getvalue())
        self.assertIn("Connected by", output.getvalue())
        self.assertEqual(self._ammeter_thread_ids(), baseline_thread_ids)

    def test_all_real_adapters_repeat_without_leaking_threads(self) -> None:
        expected = {
            "greenlee": 1.25,
            "entes": 2.5,
            "circutor": 3.75,
        }
        baseline_thread_ids = self._ammeter_thread_ids()
        framework = AmmeterTestFramework(self.config_path)

        with (
            patch.object(
                GreenleeAmmeter,
                "measure_current",
                return_value=expected["greenlee"],
            ),
            patch.object(
                EntesAmmeter,
                "measure_current",
                return_value=expected["entes"],
            ),
            patch.object(
                CircutorAmmeter,
                "measure_current",
                return_value=expected["circutor"],
            ),
            redirect_stdout(io.StringIO()),
        ):
            first = framework.measure_all()
            second = framework.measure_all()

        for results in (first, second):
            self.assertEqual(list(results), list(expected))
            self.assertEqual(
                {
                    name: result.current
                    for name, result in results.items()
                },
                expected,
            )
            self.assertTrue(
                all(
                    result.status is MeasurementStatus.SUCCESS
                    and not result.errors
                    for result in results.values()
                )
            )

        self.assertEqual(self._ammeter_thread_ids(), baseline_thread_ids)
        self.assertTrue(
            all(
                meter["port"] == 0
                for meter in framework.config["ammeters"].values()
            )
        )


if __name__ == "__main__":
    unittest.main()
