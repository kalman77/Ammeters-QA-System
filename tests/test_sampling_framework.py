import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from src.application.errors.sampling_configuration_error import (
    SamplingConfigurationError,
)
from src.application.errors.measurement_request_error import (
    MeasurementRequestError,
)
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.sampling_result import SamplingResult
from src.testing.test_framework import AmmeterTestFramework


class SamplingTimeline:
    def __init__(self) -> None:
        self.current = 100.0
        self.sleeps = []
        self.started_at_utc = datetime(
            2026,
            8,
            1,
            12,
            0,
            tzinfo=timezone.utc,
        )

    def monotonic(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds

    def utc(self) -> datetime:
        return self.started_at_utc + timedelta(
            seconds=self.current - 100.0
        )


class SamplingFrameworkTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.config_path = Path(self._directory.name) / "config.yaml"
        self.config_path.write_text(
            """
testing:
  sampling:
    measurements_count: 2
    total_duration_seconds: 1.0
    sampling_frequency_hz: 2.0
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

    def _new_framework(self, failed_commands=()):
        timeline = SamplingTimeline()
        observed = {
            "starts": [],
            "stops": [],
            "requests": [],
        }

        def start_emulators(runtime_settings, stop_event):
            selected = runtime_settings.ammeters[0]
            observed["starts"].append((runtime_settings, stop_event))
            return [
                SimpleNamespace(
                    settings=selected,
                    emulator=SimpleNamespace(port=43210),
                )
            ]

        def stop_emulators(running, stop_event, timeout_seconds):
            observed["stops"].append(
                (running, stop_event, timeout_seconds)
            )

        def request_current(port, command, **network):
            observed["requests"].append((port, command, network))
            timeline.current += 0.01
            if command in failed_commands:
                raise MeasurementRequestError(
                    f"request failed for {command!r}"
                )
            return float(len(observed["requests"]))

        framework = AmmeterTestFramework(
            self.config_path,
            start_emulators=start_emulators,
            stop_emulators=stop_emulators,
            request_current=request_current,
            monotonic_clock=timeline.monotonic,
            utc_clock=timeline.utc,
            sleeper=timeline.sleep,
        )
        return framework, timeline, observed

    def test_sample_uses_lazy_config_and_one_emulator_session(self) -> None:
        framework, timeline, observed = self._new_framework()

        result = framework.sample(" GREENLEE ")

        self.assertIsInstance(result, SamplingResult)
        self.assertIs(result.status, MeasurementStatus.SUCCESS)
        self.assertEqual(result.ammeter_type, "greenlee")
        self.assertEqual(
            [sample.result.current for sample in result.samples],
            [1.0, 2.0],
        )
        self.assertEqual(
            [
                sample.scheduled_elapsed_seconds
                for sample in result.samples
            ],
            [0.0, 0.5],
        )
        self.assertAlmostEqual(result.sampling_elapsed_seconds, 1.0)
        self.assertEqual(len(observed["starts"]), 1)
        self.assertEqual(len(observed["stops"]), 1)
        self.assertEqual(len(observed["requests"]), 2)
        self.assertTrue(all(delay >= 0 for delay in timeline.sleeps))
        self.assertEqual(
            framework.sampling_settings.measurements_count,
            2,
        )

    def test_shipped_config_exposes_the_default_sampling_window(self) -> None:
        framework = AmmeterTestFramework()

        self.assertEqual(framework.sampling_settings.measurements_count, 5)
        self.assertEqual(
            framework.sampling_settings.total_duration_seconds,
            1.0,
        )
        self.assertEqual(
            framework.sampling_settings.sampling_frequency_hz,
            5.0,
        )

    def test_explicit_values_replace_the_configured_schedule(self) -> None:
        framework, _, observed = self._new_framework()

        result = framework.sample(
            "entes",
            measurements_count=3,
            total_duration_seconds=0.3,
        )

        self.assertEqual(result.settings.measurements_count, 3)
        self.assertAlmostEqual(result.settings.sampling_frequency_hz, 10.0)
        self.assertEqual(len(observed["requests"]), 3)

    def test_incomplete_explicit_values_fail_before_startup(self) -> None:
        framework, timeline, observed = self._new_framework()

        with self.assertRaises(SamplingConfigurationError):
            framework.sample(
                "greenlee",
                measurements_count=3,
            )

        self.assertEqual(observed["starts"], [])
        self.assertEqual(observed["requests"], [])
        self.assertEqual(timeline.sleeps, [])

    def test_serialized_and_all_meter_sampling_apis(self) -> None:
        framework, _, observed = self._new_framework()

        serialized = framework.run_sampling_test("circutor")
        all_results = framework.run_all_sampling_tests(
            measurements_count=1,
            sampling_frequency_hz=20.0,
        )

        self.assertEqual(serialized["status"], "success")
        self.assertEqual(serialized["summary"]["successful_samples"], 2)
        self.assertEqual(len(serialized["samples"]), 2)
        self.assertEqual(
            list(all_results),
            ["greenlee", "entes", "circutor"],
        )
        self.assertTrue(
            all(result["status"] == "success" for result in all_results.values())
        )
        json.dumps(serialized)
        json.dumps(all_results)
        self.assertEqual(len(observed["starts"]), 4)
        self.assertEqual(len(observed["stops"]), 4)

    def test_missing_sampling_config_does_not_break_phase_two_api(self) -> None:
        config_without_sampling = Path(
            self._directory.name
        ) / "without-sampling.yaml"
        configured_text = self.config_path.read_text(encoding="utf-8")
        config_without_sampling.write_text(
            "network:" + configured_text.split("network:", maxsplit=1)[1],
            encoding="utf-8",
        )
        timeline = SamplingTimeline()

        def start_emulators(runtime_settings, stop_event):
            selected = runtime_settings.ammeters[0]
            return [
                SimpleNamespace(
                    settings=selected,
                    emulator=SimpleNamespace(port=43210),
                )
            ]

        framework = AmmeterTestFramework(
            config_without_sampling,
            start_emulators=start_emulators,
            stop_emulators=lambda *args: None,
            request_current=lambda *args, **kwargs: 1.25,
            monotonic_clock=timeline.monotonic,
            utc_clock=timeline.utc,
            sleeper=timeline.sleep,
        )

        self.assertEqual(framework.measure("greenlee").current, 1.25)
        with self.assertRaises(SamplingConfigurationError):
            framework.sample("greenlee")

    def test_sample_all_continues_after_one_ammeter_fails(self) -> None:
        framework, _, observed = self._new_framework(
            failed_commands=(b"ENTES_COMMAND",)
        )

        results = framework.sample_all(
            measurements_count=1,
            sampling_frequency_hz=20.0,
        )

        self.assertEqual(
            {
                name: result.status
                for name, result in results.items()
            },
            {
                "greenlee": MeasurementStatus.SUCCESS,
                "entes": MeasurementStatus.FAILED,
                "circutor": MeasurementStatus.SUCCESS,
            },
        )
        self.assertEqual(len(observed["starts"]), 3)
        self.assertEqual(len(observed["stops"]), 3)
        self.assertEqual(len(observed["requests"]), 3)


if __name__ == "__main__":
    unittest.main()
