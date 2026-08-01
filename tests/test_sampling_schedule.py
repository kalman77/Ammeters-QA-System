import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.application.use_cases.run_ammeter_sampling_test import (
    run_ammeter_sampling_test,
)
from src.application.use_cases.wait_until_deadline import (
    wait_until_deadline,
)
from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.ammeter_settings import AmmeterSettings
from src.domain.models.network_settings import NetworkSettings
from src.domain.models.runtime_settings import RuntimeSettings
from src.domain.models.sampling_settings import SamplingSettings


class FakeTimeline:
    def __init__(self, now: float = 0.0):
        self.now = now
        self.sleeps = []
        self.utc_origin = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise AssertionError("the scheduler must not sleep negatively")
        self.sleeps.append(seconds)
        self.now += seconds

    def utc(self) -> datetime:
        return self.utc_origin + timedelta(seconds=self.now)

    def advance(self, seconds: float) -> None:
        self.now += seconds


def runtime_settings() -> RuntimeSettings:
    return RuntimeSettings(
        network=NetworkSettings(
            host="127.0.0.1",
            connect_timeout_seconds=1.0,
            read_timeout_seconds=2.0,
            startup_timeout_seconds=3.0,
            shutdown_timeout_seconds=4.0,
        ),
        ammeters=(
            AmmeterSettings(
                name="greenlee",
                port=0,
                command=b"GREENLEE_COMMAND",
            ),
            AmmeterSettings(
                name="entes",
                port=0,
                command=b"ENTES_COMMAND",
            ),
        ),
    )


class SamplingScheduleTests(unittest.TestCase):
    def test_deadline_wait_retries_early_wake_and_rejects_expired_slot(
        self,
    ) -> None:
        timeline = FakeTimeline()
        sleep_calls = 0

        def wake_early_once(seconds):
            nonlocal sleep_calls
            sleep_calls += 1
            timeline.advance(seconds / 2 if sleep_calls == 1 else seconds)

        started_at = wait_until_deadline(
            1.0,
            2.0,
            monotonic_clock=timeline.monotonic,
            sleeper=wake_early_once,
        )

        self.assertEqual(started_at, 1.0)
        self.assertEqual(sleep_calls, 2)

        timeline.now = 0.0
        expired = wait_until_deadline(
            1.0,
            2.0,
            monotonic_clock=timeline.monotonic,
            sleeper=lambda seconds: timeline.advance(seconds + 1.0),
        )
        self.assertIsNone(expired)

        timeline.now = 2.0
        self.assertIsNone(
            wait_until_deadline(
                1.0,
                2.0,
                monotonic_clock=timeline.monotonic,
                sleeper=timeline.sleep,
            )
        )

    def test_deadlines_are_anchored_and_fast_run_waits_for_full_window(
        self,
    ) -> None:
        timeline = FakeTimeline(now=100.0)
        settings = SamplingSettings(
            measurements_count=4,
            total_duration_seconds=2.0,
            sampling_frequency_hz=2.0,
        )
        starts = []
        stops = []
        requests = []

        def start_emulators(selected_runtime, stop_event):
            starts.append((selected_runtime, stop_event))
            timeline.advance(0.2)
            selected = selected_runtime.ammeters[0]
            return [
                SimpleNamespace(
                    settings=selected,
                    emulator=SimpleNamespace(port=43210),
                )
            ]

        def stop_emulators(running, stop_event, timeout_seconds):
            stops.append((running, stop_event, timeout_seconds))
            timeline.advance(0.1)

        def request_current(port, command, **network):
            requests.append((timeline.now, port, command, network))
            timeline.advance(0.1)
            return 12.5

        result = run_ammeter_sampling_test(
            runtime_settings(),
            settings,
            " GREENLEE ",
            start_emulators=start_emulators,
            stop_emulators=stop_emulators,
            request_current=request_current,
            monotonic_clock=timeline.monotonic,
            utc_clock=timeline.utc,
            sleeper=timeline.sleep,
        )

        self.assertIs(result.status, MeasurementStatus.SUCCESS)
        self.assertEqual(result.ammeter_type, "greenlee")
        self.assertEqual(len(result.samples), 4)
        self.assertEqual(
            [sample.scheduled_elapsed_seconds for sample in result.samples],
            [0.0, 0.5, 1.0, 1.5],
        )
        for actual, expected in zip(
            [
                sample.started_elapsed_seconds
                for sample in result.samples
            ],
            [0.0, 0.5, 1.0, 1.5],
        ):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(
            [
                sample.completed_elapsed_seconds
                for sample in result.samples
            ],
            [0.1, 0.6, 1.1, 1.6],
        ):
            self.assertAlmostEqual(actual, expected)

        request_offsets = [
            request[0] - 100.2
            for request in requests
        ]
        for actual, expected in zip(
            request_offsets,
            [0.0, 0.5, 1.0, 1.5],
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(
            [(request[1], request[2]) for request in requests],
            [(43210, b"GREENLEE_COMMAND")] * 4,
        )
        self.assertEqual(
            requests[0][3],
            {
                "host": "127.0.0.1",
                "connect_timeout_seconds": 1.0,
                "read_timeout_seconds": 2.0,
            },
        )

        self.assertEqual(len(timeline.sleeps), 4)
        for duration in timeline.sleeps:
            self.assertAlmostEqual(duration, 0.4)
        self.assertAlmostEqual(result.sampling_elapsed_seconds, 2.0)
        self.assertAlmostEqual(result.elapsed_seconds, 2.3)

        self.assertEqual(len(starts), 1)
        self.assertEqual(
            [meter.name for meter in starts[0][0].ammeters],
            ["greenlee"],
        )
        self.assertEqual(len(stops), 1)
        self.assertEqual(len(stops[0][0]), 1)
        self.assertIs(stops[0][1], starts[0][1])
        self.assertEqual(stops[0][2], 4.0)

    def test_slow_request_skips_expired_slots_without_catch_up_burst(
        self,
    ) -> None:
        timeline = FakeTimeline()
        settings = SamplingSettings(
            measurements_count=5,
            total_duration_seconds=5.0,
            sampling_frequency_hz=1.0,
        )
        request_durations = iter((3.2, 0.1, 0.1))
        request_times = []
        lifecycle = {"starts": 0, "stops": 0}

        def start_emulators(selected_runtime, stop_event):
            lifecycle["starts"] += 1
            selected = selected_runtime.ammeters[0]
            return [
                SimpleNamespace(
                    settings=selected,
                    emulator=SimpleNamespace(port=43210),
                )
            ]

        def stop_emulators(running, stop_event, timeout_seconds):
            lifecycle["stops"] += 1

        def request_current(port, command, **network):
            request_times.append(timeline.now)
            timeline.advance(next(request_durations))
            return 4.0

        result = run_ammeter_sampling_test(
            runtime_settings(),
            settings,
            "greenlee",
            start_emulators=start_emulators,
            stop_emulators=stop_emulators,
            request_current=request_current,
            monotonic_clock=timeline.monotonic,
            utc_clock=timeline.utc,
            sleeper=timeline.sleep,
        )

        self.assertIs(result.status, MeasurementStatus.PARTIAL)
        self.assertEqual(len(result.samples), 5)
        self.assertEqual(
            [
                sample.result.status
                for sample in result.samples
            ],
            [
                MeasurementStatus.SUCCESS,
                MeasurementStatus.FAILED,
                MeasurementStatus.FAILED,
                MeasurementStatus.SUCCESS,
                MeasurementStatus.SUCCESS,
            ],
        )
        self.assertEqual(
            [
                sample.started_elapsed_seconds
                for sample in result.samples
            ],
            [0.0, None, None, 3.2, 4.0],
        )
        for missed_index in (1, 2):
            self.assertEqual(
                [
                    error.code
                    for error in result.samples[
                        missed_index
                    ].result.errors
                ],
                [MeasurementErrorCode.SAMPLING_SLOT_MISSED],
            )

        self.assertEqual(len(request_times), 3)
        for actual, expected in zip(request_times, [0.0, 3.2, 4.0]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(len(timeline.sleeps), 2)
        self.assertAlmostEqual(timeline.sleeps[0], 0.7)
        self.assertAlmostEqual(timeline.sleeps[1], 0.9)
        self.assertAlmostEqual(result.sampling_elapsed_seconds, 5.0)
        self.assertEqual(lifecycle, {"starts": 1, "stops": 1})

    def test_final_in_flight_request_may_complete_after_window(self) -> None:
        timeline = FakeTimeline()
        settings = SamplingSettings(
            measurements_count=2,
            total_duration_seconds=1.0,
            sampling_frequency_hz=2.0,
        )
        request_count = 0

        def start_emulators(selected_runtime, stop_event):
            selected = selected_runtime.ammeters[0]
            return [
                SimpleNamespace(
                    settings=selected,
                    emulator=SimpleNamespace(port=43210),
                )
            ]

        def request_current(port, command, **network):
            nonlocal request_count
            request_count += 1
            timeline.advance(0.1 if request_count == 1 else 0.75)
            return float(request_count)

        result = run_ammeter_sampling_test(
            runtime_settings(),
            settings,
            "greenlee",
            start_emulators=start_emulators,
            stop_emulators=lambda *args: None,
            request_current=request_current,
            monotonic_clock=timeline.monotonic,
            utc_clock=timeline.utc,
            sleeper=timeline.sleep,
        )

        self.assertIs(result.status, MeasurementStatus.SUCCESS)
        self.assertEqual(request_count, 2)
        self.assertEqual(
            result.samples[1].started_elapsed_seconds,
            0.5,
        )
        self.assertAlmostEqual(
            result.samples[1].completed_elapsed_seconds,
            1.25,
        )
        self.assertAlmostEqual(result.sampling_elapsed_seconds, 1.25)

    def test_final_window_wait_retries_an_early_waking_sleeper(self) -> None:
        timeline = FakeTimeline()
        settings = SamplingSettings(
            measurements_count=1,
            total_duration_seconds=1.0,
            sampling_frequency_hz=1.0,
        )
        sleep_calls = 0

        def start_emulators(selected_runtime, stop_event):
            selected = selected_runtime.ammeters[0]
            return [
                SimpleNamespace(
                    settings=selected,
                    emulator=SimpleNamespace(port=43210),
                )
            ]

        def request_current(port, command, **network):
            timeline.advance(0.1)
            return 3.5

        def wake_early_once(seconds):
            nonlocal sleep_calls
            sleep_calls += 1
            timeline.advance(seconds / 2 if sleep_calls == 1 else seconds)

        result = run_ammeter_sampling_test(
            runtime_settings(),
            settings,
            "greenlee",
            start_emulators=start_emulators,
            stop_emulators=lambda *args: None,
            request_current=request_current,
            monotonic_clock=timeline.monotonic,
            utc_clock=timeline.utc,
            sleeper=wake_early_once,
        )

        self.assertIs(result.status, MeasurementStatus.SUCCESS)
        self.assertEqual(sleep_calls, 2)
        self.assertAlmostEqual(result.sampling_elapsed_seconds, 1.0)


if __name__ == "__main__":
    unittest.main()
