import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.application.errors.emulator_start_error import EmulatorStartError
from src.application.errors.emulator_stop_error import EmulatorStopError
from src.application.errors.measurement_request_error import (
    MeasurementRequestError,
)
from src.application.use_cases.run_ammeter_sampling_test import (
    run_ammeter_sampling_test,
)
from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.ammeter_settings import AmmeterSettings
from src.domain.models.network_settings import NetworkSettings
from src.domain.models.runtime_settings import RuntimeSettings
from src.domain.models.sampling_settings import SamplingSettings


class FakeTimeline:
    def __init__(self):
        self.now = 0.0
        self.utc_origin = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def utc(self) -> datetime:
        return self.utc_origin + timedelta(seconds=self.now)


class SamplingHarness:
    def __init__(
        self,
        actions,
        *,
        start_error=None,
        stop_error=None,
        starter_shape="normal",
    ):
        self.timeline = FakeTimeline()
        self.actions = list(actions)
        self.start_error = start_error
        self.stop_error = stop_error
        self.starter_shape = starter_shape
        self.starts = []
        self.stops = []
        self.requests = []
        self.runtime_settings = RuntimeSettings(
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

    def start_emulators(self, selected_runtime, stop_event):
        self.starts.append((selected_runtime, stop_event))
        if self.start_error is not None:
            raise self.start_error

        selected = selected_runtime.ammeters[0]
        running = SimpleNamespace(
            settings=selected,
            emulator=SimpleNamespace(port=43210),
        )
        if self.starter_shape == "empty":
            return []
        if self.starter_shape == "duplicate":
            return [running, running]
        if self.starter_shape == "wrong":
            wrong = SimpleNamespace(
                settings=AmmeterSettings(
                    name="entes",
                    port=0,
                    command=b"ENTES_COMMAND",
                ),
                emulator=SimpleNamespace(port=43211),
            )
            return [wrong]
        return [running]

    def stop_emulators(
        self,
        running,
        stop_event,
        timeout_seconds,
    ):
        self.stops.append((running, stop_event, timeout_seconds))
        if self.stop_error is not None:
            raise self.stop_error

    def request_current(self, port, command, **network):
        self.requests.append((self.timeline.now, port, command, network))
        self.timeline.now += 0.1
        action = self.actions.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action

    def run(self, measurements_count=None):
        count = (
            len(self.actions)
            if measurements_count is None
            else measurements_count
        )
        settings = SamplingSettings(
            measurements_count=count,
            total_duration_seconds=float(count),
            sampling_frequency_hz=1.0,
        )
        return run_ammeter_sampling_test(
            self.runtime_settings,
            settings,
            "greenlee",
            start_emulators=self.start_emulators,
            stop_emulators=self.stop_emulators,
            request_current=self.request_current,
            monotonic_clock=self.timeline.monotonic,
            utc_clock=self.timeline.utc,
            sleeper=self.timeline.sleep,
        )


class SamplingFailureTests(unittest.TestCase):
    def test_mixed_request_and_validation_failures_return_partial_result(
        self,
    ) -> None:
        harness = SamplingHarness(
            [
                1.25,
                MeasurementRequestError("connection lost"),
                float("nan"),
            ]
        )

        result = harness.run()

        self.assertIs(result.status, MeasurementStatus.PARTIAL)
        self.assertEqual(
            [sample.result.status for sample in result.samples],
            [
                MeasurementStatus.SUCCESS,
                MeasurementStatus.FAILED,
                MeasurementStatus.FAILED,
            ],
        )
        self.assertEqual(
            result.samples[0].result.current,
            1.25,
        )
        self.assertEqual(
            [
                result.samples[index].result.errors[0].code
                for index in (1, 2)
            ],
            [
                MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
                MeasurementErrorCode.INVALID_MEASUREMENT,
            ],
        )
        self.assertEqual(result.errors, ())
        self.assertEqual(len(harness.starts), 1)
        self.assertEqual(len(harness.stops), 1)
        self.assertEqual(len(harness.requests), 3)

    def test_all_failed_measurements_return_failed_sampling_result(
        self,
    ) -> None:
        harness = SamplingHarness(
            [
                MeasurementRequestError("first request failed"),
                MeasurementRequestError("second request failed"),
            ]
        )

        result = harness.run()

        self.assertIs(result.status, MeasurementStatus.FAILED)
        self.assertEqual(len(result.samples), 2)
        self.assertTrue(
            all(
                sample.result.status is MeasurementStatus.FAILED
                for sample in result.samples
            )
        )
        self.assertTrue(
            all(
                sample.result.errors[0].code
                is MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED
                for sample in result.samples
            )
        )
        self.assertEqual(len(harness.starts), 1)
        self.assertEqual(len(harness.stops), 1)

    def test_start_failure_returns_no_samples_and_does_not_stop(
        self,
    ) -> None:
        harness = SamplingHarness(
            [],
            start_error=EmulatorStartError("unable to listen"),
        )

        result = harness.run(measurements_count=2)

        self.assertIs(result.status, MeasurementStatus.FAILED)
        self.assertEqual(result.samples, ())
        self.assertIsNone(result.sampling_started_at_utc)
        self.assertIsNone(result.sampling_elapsed_seconds)
        self.assertEqual(
            [error.code for error in result.errors],
            [MeasurementErrorCode.EMULATOR_START_FAILED],
        )
        self.assertEqual(len(harness.starts), 1)
        self.assertEqual(harness.stops, [])
        self.assertEqual(harness.requests, [])

    def test_stop_failure_preserves_samples_and_returns_partial_result(
        self,
    ) -> None:
        harness = SamplingHarness(
            [8.5],
            stop_error=EmulatorStopError("thread did not stop"),
        )

        result = harness.run()

        self.assertIs(result.status, MeasurementStatus.PARTIAL)
        self.assertEqual(len(result.samples), 1)
        self.assertIs(
            result.samples[0].result.status,
            MeasurementStatus.SUCCESS,
        )
        self.assertEqual(result.samples[0].result.current, 8.5)
        self.assertEqual(
            [error.code for error in result.errors],
            [MeasurementErrorCode.EMULATOR_STOP_FAILED],
        )
        self.assertEqual(len(harness.starts), 1)
        self.assertEqual(len(harness.stops), 1)

    def test_request_and_stop_failures_are_both_preserved(self) -> None:
        harness = SamplingHarness(
            [MeasurementRequestError("request failed")],
            stop_error=EmulatorStopError("stop failed"),
        )

        result = harness.run()

        self.assertIs(result.status, MeasurementStatus.FAILED)
        self.assertEqual(
            result.samples[0].result.errors[0].code,
            MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
        )
        self.assertEqual(
            [error.code for error in result.errors],
            [MeasurementErrorCode.EMULATOR_STOP_FAILED],
        )

    def test_malformed_starter_results_become_start_failures(self) -> None:
        expectations = {
            "empty": 0,
            "duplicate": 1,
            "wrong": 1,
        }
        for starter_shape, expected_stop_calls in expectations.items():
            with self.subTest(starter_shape=starter_shape):
                harness = SamplingHarness(
                    [],
                    starter_shape=starter_shape,
                )

                result = harness.run(measurements_count=2)

                self.assertIs(result.status, MeasurementStatus.FAILED)
                self.assertEqual(result.samples, ())
                self.assertEqual(
                    [error.code for error in result.errors],
                    [MeasurementErrorCode.EMULATOR_START_FAILED],
                )
                self.assertEqual(len(harness.starts), 1)
                self.assertEqual(
                    len(harness.stops),
                    expected_stop_calls,
                )
                self.assertEqual(harness.requests, [])

    def test_control_flow_exceptions_are_re_raised_after_cleanup(self) -> None:
        for control_error in (
            KeyboardInterrupt("cancelled"),
            SystemExit(7),
        ):
            with self.subTest(error_type=type(control_error).__name__):
                harness = SamplingHarness([control_error])

                with self.assertRaises(type(control_error)) as raised:
                    harness.run()

                self.assertIs(raised.exception, control_error)
                self.assertEqual(len(harness.starts), 1)
                self.assertEqual(len(harness.stops), 1)
                self.assertIs(
                    harness.stops[0][1],
                    harness.starts[0][1],
                )
                self.assertEqual(len(harness.requests), 1)

    def test_unexpected_exceptions_are_re_raised_after_cleanup(self) -> None:
        unexpected_error = LookupError("programming failure")
        harness = SamplingHarness([unexpected_error])

        with self.assertRaises(LookupError) as raised:
            harness.run()

        self.assertIs(raised.exception, unexpected_error)
        self.assertEqual(len(harness.starts), 1)
        self.assertEqual(len(harness.stops), 1)

    def test_sleeper_exceptions_are_re_raised_after_cleanup(self) -> None:
        for sleep_error in (
            KeyboardInterrupt("cancelled while waiting"),
            LookupError("clock adapter failed"),
        ):
            with self.subTest(error_type=type(sleep_error).__name__):
                harness = SamplingHarness([1.0])

                def failing_sleep(seconds, error=sleep_error):
                    raise error

                harness.timeline.sleep = failing_sleep

                with self.assertRaises(type(sleep_error)) as raised:
                    harness.run()

                self.assertIs(raised.exception, sleep_error)
                self.assertEqual(len(harness.starts), 1)
                self.assertEqual(len(harness.stops), 1)
                self.assertEqual(len(harness.requests), 1)

    def test_inter_slot_sleeper_failure_stops_before_next_request(
        self,
    ) -> None:
        sleep_error = RuntimeError("unable to wait")
        harness = SamplingHarness([1.0, 2.0])

        def failing_sleep(seconds):
            raise sleep_error

        harness.timeline.sleep = failing_sleep

        with self.assertRaises(RuntimeError) as raised:
            harness.run()

        self.assertIs(raised.exception, sleep_error)
        self.assertEqual(len(harness.starts), 1)
        self.assertEqual(len(harness.stops), 1)
        self.assertEqual(len(harness.requests), 1)


if __name__ == "__main__":
    unittest.main()
