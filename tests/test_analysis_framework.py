import json
import unittest
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from src.application.errors.measurement_request_error import (
    MeasurementRequestError,
)
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.sampling_analysis import SamplingAnalysis
from src.testing.test_framework import AmmeterTestFramework


class AnalysisTimeline:
    def __init__(self) -> None:
        self.current = 100.0
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
        self.current += seconds

    def utc(self) -> datetime:
        return self.started_at_utc + timedelta(
            seconds=self.current - 100.0
        )


class AnalysisFrameworkTests(unittest.TestCase):
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

    def _new_framework(self, readings_by_command):
        timeline = AnalysisTimeline()
        remaining_readings = {
            command: list(readings)
            for command, readings in readings_by_command.items()
        }
        request_counts = defaultdict(int)
        observed = {
            "starts": [],
            "stops": [],
            "requests": [],
        }

        def start_emulators(runtime_settings, stop_event):
            selected = runtime_settings.ammeters[0]
            observed["starts"].append((selected.name, stop_event))
            return [
                SimpleNamespace(
                    settings=selected,
                    emulator=SimpleNamespace(port=43210),
                )
            ]

        def stop_emulators(running, stop_event, timeout_seconds):
            observed["stops"].append(
                (
                    running[0].settings.name,
                    stop_event,
                    timeout_seconds,
                )
            )

        def request_current(port, command, **network):
            observed["requests"].append((port, command, network))
            timeline.current += 0.005
            index = request_counts[command]
            request_counts[command] += 1
            action = remaining_readings[command][index]
            if isinstance(action, BaseException):
                raise action
            return action

        framework = AmmeterTestFramework(
            self.config_path,
            start_emulators=start_emulators,
            stop_emulators=stop_emulators,
            request_current=request_current,
            monotonic_clock=timeline.monotonic,
            utc_clock=timeline.utc,
            sleeper=timeline.sleep,
        )
        return framework, observed

    def test_analyze_applies_overrides_and_returns_typed_statistics(
        self,
    ) -> None:
        framework, observed = self._new_framework(
            {
                b"GREENLEE_COMMAND": [1.0, 2.0, 3.0, 4.0],
            }
        )

        analysis = framework.analyze(
            " GREENLEE ",
            measurements_count=4,
            sampling_frequency_hz=20.0,
        )

        self.assertIsInstance(analysis, SamplingAnalysis)
        self.assertIs(
            analysis.sampling_result.status,
            MeasurementStatus.SUCCESS,
        )
        self.assertEqual(
            analysis.sampling_result.settings.measurements_count,
            4,
        )
        self.assertAlmostEqual(
            analysis.sampling_result.settings.total_duration_seconds,
            0.2,
        )
        self.assertEqual(
            analysis.sampling_result.settings.sampling_frequency_hz,
            20.0,
        )
        self.assertIsNotNone(analysis.statistics)
        self.assertEqual(analysis.statistics.measurements_count, 4)
        self.assertEqual(analysis.statistics.mean_current, 2.5)
        self.assertEqual(analysis.statistics.median_current, 2.5)
        self.assertAlmostEqual(
            analysis.statistics.standard_deviation_current,
            1.118033988749895,
        )
        self.assertEqual(analysis.statistics.minimum_current, 1.0)
        self.assertEqual(analysis.statistics.maximum_current, 4.0)
        self.assertEqual(
            [entry[0] for entry in observed["starts"]],
            ["greenlee"],
        )
        self.assertEqual(
            [entry[0] for entry in observed["stops"]],
            ["greenlee"],
        )
        self.assertIs(
            observed["starts"][0][1],
            observed["stops"][0][1],
        )

    def test_analyze_all_preserves_order_and_isolates_empty_analysis(
        self,
    ) -> None:
        framework, observed = self._new_framework(
            {
                b"GREENLEE_COMMAND": [1.0, 3.0],
                b"ENTES_COMMAND": [
                    MeasurementRequestError("entes request failed"),
                    MeasurementRequestError("entes request failed"),
                ],
                b"CIRCUTOR_COMMAND": [8.0, 12.0],
            }
        )

        analyses = framework.analyze_all(
            measurements_count=2,
            total_duration_seconds=0.2,
        )

        configured_order = ["greenlee", "entes", "circutor"]
        self.assertEqual(list(analyses), configured_order)
        self.assertEqual(
            [entry[0] for entry in observed["starts"]],
            configured_order,
        )
        self.assertEqual(
            [entry[0] for entry in observed["stops"]],
            configured_order,
        )
        self.assertEqual(len(observed["starts"]), 3)
        self.assertEqual(len(observed["stops"]), 3)
        for started, stopped in zip(
            observed["starts"],
            observed["stops"],
        ):
            self.assertEqual(started[0], stopped[0])
            self.assertIs(started[1], stopped[1])

        self.assertIs(
            analyses["greenlee"].sampling_result.status,
            MeasurementStatus.SUCCESS,
        )
        self.assertEqual(
            analyses["greenlee"].statistics.mean_current,
            2.0,
        )
        self.assertIs(
            analyses["entes"].sampling_result.status,
            MeasurementStatus.FAILED,
        )
        self.assertIsNone(analyses["entes"].statistics)
        self.assertIs(
            analyses["circutor"].sampling_result.status,
            MeasurementStatus.SUCCESS,
        )
        self.assertEqual(
            analyses["circutor"].statistics.mean_current,
            10.0,
        )
        for analysis in analyses.values():
            settings = analysis.sampling_result.settings
            self.assertEqual(settings.measurements_count, 2)
            self.assertEqual(settings.total_duration_seconds, 0.2)
            self.assertEqual(settings.sampling_frequency_hz, 10.0)

    def test_serialized_analysis_apis_are_json_safe(self) -> None:
        framework, observed = self._new_framework(
            {
                b"GREENLEE_COMMAND": [2.0, 4.0, 6.0, 8.0],
                b"ENTES_COMMAND": [10.0, 14.0],
                b"CIRCUTOR_COMMAND": [20.0, 24.0],
            }
        )

        one_result = framework.run_analysis(
            "greenlee",
            measurements_count=2,
            sampling_frequency_hz=10.0,
        )
        all_results = framework.run_all_analyses(
            measurements_count=2,
            sampling_frequency_hz=10.0,
        )

        self.assertEqual(one_result["ammeter_type"], "greenlee")
        self.assertEqual(one_result["status"], "success")
        self.assertEqual(one_result["statistics"]["mean_current"], 3.0)
        self.assertEqual(
            one_result["statistics"]["standard_deviation_method"],
            "population",
        )
        self.assertEqual(
            one_result["summary"]["analyzed_samples"],
            2,
        )
        self.assertEqual(
            one_result["sampling_result"]["settings"],
            {
                "measurements_count": 2,
                "total_duration_seconds": 0.2,
                "sampling_frequency_hz": 10.0,
            },
        )
        self.assertEqual(
            list(all_results),
            ["greenlee", "entes", "circutor"],
        )
        self.assertEqual(
            [
                result["statistics"]["mean_current"]
                for result in all_results.values()
            ],
            [7.0, 12.0, 22.0],
        )
        json.dumps(one_result, allow_nan=False)
        json.dumps(all_results, allow_nan=False)
        self.assertEqual(len(observed["starts"]), 4)
        self.assertEqual(len(observed["stops"]), 4)


if __name__ == "__main__":
    unittest.main()
