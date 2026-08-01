import threading
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from src.application.errors.emulator_start_error import EmulatorStartError
from src.application.errors.emulator_stop_error import EmulatorStopError
from src.application.errors.invalid_ammeter_type_error import (
    InvalidAmmeterTypeError,
)
from src.application.errors.measurement_request_error import (
    MeasurementRequestError,
)
from src.application.errors.unsupported_ammeter_error import (
    UnsupportedAmmeterError,
)
from src.application.use_cases.run_single_ammeter_test import (
    run_single_ammeter_test,
)
from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.ammeter_settings import AmmeterSettings
from src.domain.models.network_settings import NetworkSettings
from src.domain.models.runtime_settings import RuntimeSettings


class SequenceClock:
    def __init__(self, *values):
        self._values = iter(values)
        self.call_count = 0

    def __call__(self):
        self.call_count += 1
        return next(self._values)


class MeasureAmmeterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = NetworkSettings(
            host="127.0.0.9",
            connect_timeout_seconds=1.5,
            read_timeout_seconds=2.5,
            startup_timeout_seconds=3.5,
            shutdown_timeout_seconds=4.5,
        )
        self.settings = (
            AmmeterSettings(
                name="greenlee",
                port=5000,
                command=b"GREENLEE_COMMAND",
            ),
            AmmeterSettings(
                name="entes",
                port=5001,
                command=b"ENTES_COMMAND",
            ),
            AmmeterSettings(
                name="circutor",
                port=5002,
                command=b"CIRCUTOR_COMMAND",
            ),
        )
        self.runtime_settings = RuntimeSettings(
            network=self.network,
            ammeters=self.settings,
        )

    def _successful_dependencies(self, current=1.25):
        observed = {}

        def start_emulators(runtime_settings, stop_event):
            selected = runtime_settings.ammeters[0]
            running = SimpleNamespace(
                settings=selected,
                emulator=SimpleNamespace(port=selected.port + 100),
            )
            observed["selected_runtime"] = runtime_settings
            observed["stop_event"] = stop_event
            observed["running"] = [running]
            return observed["running"]

        start = Mock(side_effect=start_emulators)
        stop = Mock()
        request = Mock(return_value=current)
        monotonic = SequenceClock(10.0, 10.5, 10.75, 11.0)
        measurement_time = datetime(
            2026,
            8,
            1,
            9,
            30,
            0,
            tzinfo=timezone.utc,
        )
        result_time = datetime(
            2026,
            8,
            1,
            9,
            30,
            1,
            tzinfo=timezone.utc,
        )
        utc = SequenceClock(measurement_time, result_time)
        return observed, start, stop, request, monotonic, utc, result_time

    def test_each_supported_type_uses_only_its_selected_configuration(self) -> None:
        cases = (
            (" GREENLEE ", self.settings[0]),
            ("Entes", self.settings[1]),
            ("circutor", self.settings[2]),
        )

        for selector, expected_settings in cases:
            with self.subTest(selector=selector):
                (
                    observed,
                    start,
                    stop,
                    request,
                    monotonic,
                    utc,
                    result_time,
                ) = self._successful_dependencies(current=12)

                result = run_single_ammeter_test(
                    self.runtime_settings,
                    selector,
                    start_emulators=start,
                    stop_emulators=stop,
                    request_current=request,
                    monotonic_clock=monotonic,
                    utc_clock=utc,
                )

                selected_runtime = observed["selected_runtime"]
                self.assertEqual(
                    selected_runtime.ammeters,
                    (expected_settings,),
                )
                self.assertIs(selected_runtime.network, self.network)
                self.assertIsInstance(
                    observed["stop_event"],
                    threading.Event,
                )
                request.assert_called_once_with(
                    expected_settings.port + 100,
                    expected_settings.command,
                    host=self.network.host,
                    connect_timeout_seconds=(
                        self.network.connect_timeout_seconds
                    ),
                    read_timeout_seconds=(
                        self.network.read_timeout_seconds
                    ),
                )
                stop.assert_called_once_with(
                    observed["running"],
                    observed["stop_event"],
                    self.network.shutdown_timeout_seconds,
                )
                self.assertEqual(
                    result.ammeter_type,
                    expected_settings.name,
                )
                self.assertIs(result.status, MeasurementStatus.SUCCESS)
                self.assertEqual(result.current, 12.0)
                self.assertEqual(result.unit, "A")
                self.assertEqual(result.request_latency_seconds, 0.25)
                self.assertEqual(result.elapsed_seconds, 1.0)
                self.assertEqual(result.timestamp_utc, result_time)
                self.assertEqual(result.errors, ())
                self.assertEqual(monotonic.call_count, 4)
                self.assertEqual(utc.call_count, 2)

    def test_measurement_request_error_returns_failure_and_stops(self) -> None:
        observed, start, stop, request, _, _, _ = (
            self._successful_dependencies()
        )
        request.side_effect = MeasurementRequestError(
            "connection refused"
        )
        monotonic = SequenceClock(10.0, 10.25, 11.0)
        result_time = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
        utc = SequenceClock(result_time)

        result = run_single_ammeter_test(
            self.runtime_settings,
            "greenlee",
            start_emulators=start,
            stop_emulators=stop,
            request_current=request,
            monotonic_clock=monotonic,
            utc_clock=utc,
        )

        self.assertIs(result.status, MeasurementStatus.FAILED)
        self.assertIsNone(result.current)
        self.assertIsNone(result.request_latency_seconds)
        self.assertEqual(len(result.errors), 1)
        self.assertIs(
            result.errors[0].code,
            MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
        )
        self.assertIn("connection refused", result.errors[0].message)
        stop.assert_called_once_with(
            observed["running"],
            observed["stop_event"],
            self.network.shutdown_timeout_seconds,
        )

    def test_invalid_adapter_values_return_structured_failures(self) -> None:
        invalid_values = (True, "1.25", float("nan"), float("inf"))

        for invalid_value in invalid_values:
            with self.subTest(value=invalid_value):
                observed, start, stop, request, _, _, _ = (
                    self._successful_dependencies()
                )
                request.return_value = invalid_value
                monotonic = SequenceClock(10.0, 10.25, 11.0)
                utc = SequenceClock(
                    datetime(
                        2026,
                        8,
                        1,
                        10,
                        0,
                        tzinfo=timezone.utc,
                    )
                )

                result = run_single_ammeter_test(
                    self.runtime_settings,
                    "entes",
                    start_emulators=start,
                    stop_emulators=stop,
                    request_current=request,
                    monotonic_clock=monotonic,
                    utc_clock=utc,
                )

                self.assertIs(result.status, MeasurementStatus.FAILED)
                self.assertIs(
                    result.errors[0].code,
                    MeasurementErrorCode.INVALID_MEASUREMENT,
                )
                stop.assert_called_once_with(
                    observed["running"],
                    observed["stop_event"],
                    self.network.shutdown_timeout_seconds,
                )

    def test_start_failure_returns_structured_failure_without_stopping(self) -> None:
        start = Mock(
            side_effect=EmulatorStartError("listener did not become ready")
        )
        stop = Mock()
        request = Mock()
        monotonic = SequenceClock(10.0, 11.0)
        result_time = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
        utc = SequenceClock(result_time)

        result = run_single_ammeter_test(
            self.runtime_settings,
            "circutor",
            start_emulators=start,
            stop_emulators=stop,
            request_current=request,
            monotonic_clock=monotonic,
            utc_clock=utc,
        )

        self.assertIs(result.status, MeasurementStatus.FAILED)
        self.assertEqual(
            result.errors[0].code,
            MeasurementErrorCode.EMULATOR_START_FAILED,
        )
        self.assertIn(
            "listener did not become ready",
            result.errors[0].message,
        )
        request.assert_not_called()
        stop.assert_not_called()

    def test_empty_starter_result_returns_structured_start_failure(self) -> None:
        start = Mock(return_value=[])
        stop = Mock()
        request = Mock()
        monotonic = SequenceClock(10.0, 11.0)
        result_time = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
        utc = SequenceClock(result_time)

        result = run_single_ammeter_test(
            self.runtime_settings,
            "greenlee",
            start_emulators=start,
            stop_emulators=stop,
            request_current=request,
            monotonic_clock=monotonic,
            utc_clock=utc,
        )

        self.assertIs(result.status, MeasurementStatus.FAILED)
        self.assertEqual(
            result.errors[0].code,
            MeasurementErrorCode.EMULATOR_START_FAILED,
        )
        self.assertIn("requested 'greenlee' emulator", result.errors[0].message)
        request.assert_not_called()
        stop.assert_not_called()

    def test_stop_failure_after_measurement_returns_partial_result(self) -> None:
        observed, start, stop, request, monotonic, utc, _ = (
            self._successful_dependencies(current=-0.5)
        )
        stop.side_effect = EmulatorStopError("thread remained alive")

        result = run_single_ammeter_test(
            self.runtime_settings,
            "greenlee",
            start_emulators=start,
            stop_emulators=stop,
            request_current=request,
            monotonic_clock=monotonic,
            utc_clock=utc,
        )

        self.assertIs(result.status, MeasurementStatus.PARTIAL)
        self.assertEqual(result.current, -0.5)
        self.assertEqual(result.request_latency_seconds, 0.25)
        self.assertEqual(len(result.errors), 1)
        self.assertIs(
            result.errors[0].code,
            MeasurementErrorCode.EMULATOR_STOP_FAILED,
        )
        stop.assert_called_once_with(
            observed["running"],
            observed["stop_event"],
            self.network.shutdown_timeout_seconds,
        )

    def test_request_and_stop_failures_are_both_reported_in_order(self) -> None:
        observed, start, stop, request, _, _, _ = (
            self._successful_dependencies()
        )
        request.side_effect = MeasurementRequestError("request failed")
        stop.side_effect = EmulatorStopError("stop failed")
        monotonic = SequenceClock(10.0, 10.25, 11.0)
        utc = SequenceClock(
            datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
        )

        result = run_single_ammeter_test(
            self.runtime_settings,
            "entes",
            start_emulators=start,
            stop_emulators=stop,
            request_current=request,
            monotonic_clock=monotonic,
            utc_clock=utc,
        )

        self.assertIs(result.status, MeasurementStatus.FAILED)
        self.assertEqual(
            tuple(error.code for error in result.errors),
            (
                MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
                MeasurementErrorCode.EMULATOR_STOP_FAILED,
            ),
        )
        stop.assert_called_once_with(
            observed["running"],
            observed["stop_event"],
            self.network.shutdown_timeout_seconds,
        )

    def test_invalid_or_unsupported_selector_has_no_runtime_side_effects(
        self,
    ) -> None:
        start = Mock()
        stop = Mock()
        request = Mock()
        monotonic = Mock()
        utc = Mock()

        for invalid_selector in (None, 42, "", " \t "):
            with self.subTest(invalid_selector=invalid_selector):
                with self.assertRaises(InvalidAmmeterTypeError):
                    run_single_ammeter_test(
                        self.runtime_settings,
                        invalid_selector,
                        start_emulators=start,
                        stop_emulators=stop,
                        request_current=request,
                        monotonic_clock=monotonic,
                        utc_clock=utc,
                    )

        with self.assertRaises(UnsupportedAmmeterError):
            run_single_ammeter_test(
                self.runtime_settings,
                "unknown",
                start_emulators=start,
                stop_emulators=stop,
                request_current=request,
                monotonic_clock=monotonic,
                utc_clock=utc,
            )

        start.assert_not_called()
        stop.assert_not_called()
        request.assert_not_called()
        monotonic.assert_not_called()
        utc.assert_not_called()

    def test_control_flow_exception_is_re_raised_after_cleanup(self) -> None:
        observed, start, stop, request, _, _, _ = (
            self._successful_dependencies()
        )
        interrupt = KeyboardInterrupt()
        request.side_effect = interrupt
        monotonic = SequenceClock(10.0, 10.25)
        utc = Mock()

        with self.assertRaises(KeyboardInterrupt) as raised:
            run_single_ammeter_test(
                self.runtime_settings,
                "greenlee",
                start_emulators=start,
                stop_emulators=stop,
                request_current=request,
                monotonic_clock=monotonic,
                utc_clock=utc,
            )

        self.assertIs(raised.exception, interrupt)
        stop.assert_called_once_with(
            observed["running"],
            observed["stop_event"],
            self.network.shutdown_timeout_seconds,
        )
        utc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
