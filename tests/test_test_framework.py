import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Dict, List, Mapping, Optional, Type

from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from Ammeters.base_ammeter import AmmeterEmulatorBase
from src.application.errors.framework_configuration_error import (
    FrameworkConfigurationError,
)
from src.application.errors.invalid_ammeter_type_error import (
    InvalidAmmeterTypeError,
)
from src.application.errors.unsupported_ammeter_error import (
    UnsupportedAmmeterError,
)
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_result import MeasurementResult
from src.testing.test_framework import AmmeterTestFramework


class IncrementingMonotonicClock:
    def __init__(self, start: float = 100.0, step: float = 1.0):
        self._next = start
        self._step = step

    def __call__(self) -> float:
        current = self._next
        self._next += self._step
        return current


class IncrementingUtcClock:
    def __init__(self):
        self._next = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self._next
        self._next += timedelta(seconds=1)
        return current


class AmmeterTestFrameworkTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.config_path = Path(self._directory.name) / "config.yaml"
        self.config_path.write_text(
            """
network:
  host: "127.0.0.1"
  connect_timeout_seconds: 1.0
  read_timeout_seconds: 2.0
  startup_timeout_seconds: 3.0
  shutdown_timeout_seconds: 4.0
ammeters:
  greenlee:
    port: 0
    command: "GREENLEE_COMMAND"
  entes:
    port: 0
    command: "ENTES_COMMAND"
  circutor:
    port: 0
    command: "CIRCUTOR_COMMAND"
""".strip(),
            encoding="utf-8",
        )

    def _new_framework(
        self,
        currents: Dict[bytes, float],
        observations: Dict[str, List[object]],
        *,
        config_path: Optional[Path] = None,
        emulator_registry: Optional[
            Mapping[str, Type[AmmeterEmulatorBase]]
        ] = None,
    ) -> AmmeterTestFramework:
        def start_emulators(runtime_settings, stop_event):
            selected = runtime_settings.ammeters[0]
            observations.setdefault("started", []).append(
                (runtime_settings, stop_event)
            )
            return [
                SimpleNamespace(
                    settings=selected,
                    emulator=SimpleNamespace(port=43210),
                )
            ]

        def stop_emulators(running, stop_event, timeout_seconds):
            observations.setdefault("stopped", []).append(
                (running, stop_event, timeout_seconds)
            )

        def request_current(port, command, **network):
            observations.setdefault("requests", []).append(
                (port, command, network)
            )
            return currents[command]

        return AmmeterTestFramework(
            config_path or self.config_path,
            emulator_registry=emulator_registry,
            start_emulators=start_emulators,
            stop_emulators=stop_emulators,
            request_current=request_current,
            monotonic_clock=IncrementingMonotonicClock(),
            utc_clock=IncrementingUtcClock(),
        )

    def test_measure_returns_typed_result_and_uses_selected_configuration(
        self,
    ) -> None:
        observations: Dict[str, List[object]] = {}
        framework = self._new_framework(
            {b"GREENLEE_COMMAND": 12.5},
            observations,
        )

        result = framework.measure("  GREENLEE  ")

        self.assertIsInstance(result, MeasurementResult)
        self.assertEqual(result.ammeter_type, "greenlee")
        self.assertIs(result.status, MeasurementStatus.SUCCESS)
        self.assertEqual(result.current, 12.5)
        self.assertEqual(result.unit, "A")
        self.assertEqual(result.request_latency_seconds, 1.0)
        self.assertEqual(result.elapsed_seconds, 3.0)
        self.assertEqual(
            result.timestamp_utc,
            datetime(2026, 8, 1, 12, 0, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(result.errors, ())

        started_settings, started_event = observations["started"][0]
        self.assertEqual(
            [settings.name for settings in started_settings.ammeters],
            ["greenlee"],
        )
        self.assertEqual(
            observations["requests"],
            [
                (
                    43210,
                    b"GREENLEE_COMMAND",
                    {
                        "host": "127.0.0.1",
                        "connect_timeout_seconds": 1.0,
                        "read_timeout_seconds": 2.0,
                    },
                )
            ],
        )
        stopped, stopped_event, timeout = observations["stopped"][0]
        self.assertEqual(len(stopped), 1)
        self.assertIs(stopped_event, started_event)
        self.assertEqual(timeout, 4.0)

    def test_run_test_preserves_json_friendly_dictionary_contract(self) -> None:
        framework = self._new_framework(
            {b"ENTES_COMMAND": -2.25},
            {},
        )

        result = framework.run_test("entes")

        self.assertEqual(
            result,
            {
                "ammeter_type": "entes",
                "status": "success",
                "timestamp_utc": "2026-08-01T12:00:01Z",
                "elapsed_seconds": 3.0,
                "current": -2.25,
                "unit": "A",
                "request_latency_seconds": 1.0,
                "errors": [],
            },
        )

    def test_measure_all_uses_configuration_order_and_same_result_schema(
        self,
    ) -> None:
        observations: Dict[str, List[object]] = {}
        framework = self._new_framework(
            {
                b"GREENLEE_COMMAND": 1.25,
                b"ENTES_COMMAND": 2.5,
                b"CIRCUTOR_COMMAND": 3.75,
            },
            observations,
        )

        results = framework.measure_all()

        self.assertEqual(
            framework.ammeter_types,
            ("greenlee", "entes", "circutor"),
        )
        self.assertEqual(
            list(results),
            ["greenlee", "entes", "circutor"],
        )
        self.assertEqual(
            [result.current for result in results.values()],
            [1.25, 2.5, 3.75],
        )
        self.assertTrue(
            all(
                isinstance(result, MeasurementResult)
                and result.status is MeasurementStatus.SUCCESS
                for result in results.values()
            )
        )
        self.assertEqual(len(observations["started"]), 3)
        self.assertEqual(len(observations["stopped"]), 3)
        self.assertEqual(
            [entry[1] for entry in observations["requests"]],
            [
                b"GREENLEE_COMMAND",
                b"ENTES_COMMAND",
                b"CIRCUTOR_COMMAND",
            ],
        )
        self.assertEqual(
            framework.config["network"]["host"],
            "127.0.0.1",
        )

    def test_run_all_tests_returns_json_serializable_results(self) -> None:
        framework = self._new_framework(
            {
                b"GREENLEE_COMMAND": 1.25,
                b"ENTES_COMMAND": 2.5,
                b"CIRCUTOR_COMMAND": 3.75,
            },
            {},
        )

        results = framework.run_all_tests()

        self.assertEqual(list(results), list(framework.ammeter_types))
        self.assertEqual(
            [result["status"] for result in results.values()],
            ["success", "success", "success"],
        )
        self.assertEqual(
            [result["current"] for result in results.values()],
            [1.25, 2.5, 3.75],
        )
        json.dumps(results)

    def test_custom_registry_extends_the_framework_without_use_case_changes(
        self,
    ) -> None:
        custom_config_path = Path(self._directory.name) / "custom.yaml"
        custom_config_path.write_text(
            """
network:
  host: "127.0.0.1"
  connect_timeout_seconds: 1.0
  read_timeout_seconds: 2.0
  startup_timeout_seconds: 3.0
  shutdown_timeout_seconds: 4.0
ammeters:
  custom:
    port: 0
    command: "CUSTOM_COMMAND"
""".strip(),
            encoding="utf-8",
        )
        observations: Dict[str, List[object]] = {}
        framework = self._new_framework(
            {b"CUSTOM_COMMAND": 9.5},
            observations,
            config_path=custom_config_path,
            emulator_registry={"custom": GreenleeAmmeter},
        )

        result = framework.measure("CUSTOM")

        self.assertEqual(framework.ammeter_types, ("custom",))
        self.assertEqual(result.ammeter_type, "custom")
        self.assertEqual(result.current, 9.5)
        self.assertIs(result.status, MeasurementStatus.SUCCESS)
        self.assertEqual(
            observations["requests"][0][1],
            b"CUSTOM_COMMAND",
        )

    def test_invalid_and_unsupported_selectors_do_not_start_emulators(
        self,
    ) -> None:
        observations: Dict[str, List[object]] = {}
        framework = self._new_framework({}, observations)

        for invalid_selector in (None, 42, "", "   "):
            with self.subTest(selector=invalid_selector):
                with self.assertRaises(InvalidAmmeterTypeError):
                    framework.measure(invalid_selector)

        with self.assertRaises(UnsupportedAmmeterError):
            framework.measure("unknown")

        self.assertNotIn("started", observations)
        self.assertNotIn("requests", observations)
        self.assertNotIn("stopped", observations)

    def test_configuration_failures_use_the_public_framework_error(self) -> None:
        missing_path = Path(self._directory.name) / "missing.yaml"

        with self.assertRaises(FrameworkConfigurationError) as raised:
            AmmeterTestFramework(missing_path)

        self.assertIsInstance(raised.exception.__cause__, OSError)


if __name__ == "__main__":
    unittest.main()
