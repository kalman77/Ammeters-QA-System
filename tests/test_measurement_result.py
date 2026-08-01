import math
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement import Measurement
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult


TIMESTAMP_UTC = datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc)


class MeasurementResultTests(unittest.TestCase):
    def _error(self) -> MeasurementError:
        return MeasurementError(
            code=MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
            message="transport unavailable",
        )

    def _success_result(self, **overrides) -> MeasurementResult:
        values = {
            "ammeter_type": "greenlee",
            "status": MeasurementStatus.SUCCESS,
            "timestamp_utc": TIMESTAMP_UTC,
            "elapsed_seconds": 0.75,
            "current": 1.25,
            "unit": "A",
            "request_latency_seconds": 0.25,
            "errors": (),
        }
        values.update(overrides)
        return MeasurementResult(**values)

    def test_measurement_accepts_signed_current_and_is_immutable(self) -> None:
        measurement = Measurement(
            ammeter_type="greenlee",
            current=-1.25,
            unit="A",
            timestamp_utc=TIMESTAMP_UTC,
            request_latency_seconds=0.0,
        )

        self.assertEqual(measurement.current, -1.25)
        self.assertEqual(measurement.unit, "A")
        with self.assertRaises(FrozenInstanceError):
            measurement.current = 2.0

    def test_measurement_rejects_invalid_metadata_types(self) -> None:
        values = {
            "ammeter_type": "greenlee",
            "current": 1.25,
            "unit": "A",
            "timestamp_utc": TIMESTAMP_UTC,
            "request_latency_seconds": 0.1,
        }
        invalid_overrides = (
            {"ammeter_type": "  "},
            {"ammeter_type": None},
            {"timestamp_utc": "2026-08-01T09:30:00Z"},
        )

        for overrides in invalid_overrides:
            with self.subTest(overrides=overrides):
                invalid_values = {**values, **overrides}
                with self.assertRaises(ValueError):
                    Measurement(**invalid_values)

    def test_supports_success_failed_and_partial_result_invariants(self) -> None:
        error = self._error()
        successful = self._success_result()
        failed = self._success_result(
            status=MeasurementStatus.FAILED,
            current=None,
            request_latency_seconds=None,
            errors=(error,),
        )
        partial = self._success_result(
            status=MeasurementStatus.PARTIAL,
            errors=(error,),
        )

        self.assertEqual(successful.errors, ())
        self.assertIsNone(failed.current)
        self.assertEqual(failed.errors, (error,))
        self.assertEqual(partial.current, 1.25)
        self.assertEqual(partial.errors, (error,))
        with self.assertRaises(FrozenInstanceError):
            successful.status = MeasurementStatus.FAILED

    def test_rejects_status_and_payload_combinations_that_disagree(self) -> None:
        error = self._error()
        invalid_overrides = (
            {"current": None, "request_latency_seconds": None},
            {"errors": (error,)},
            {
                "status": MeasurementStatus.FAILED,
                "current": None,
                "request_latency_seconds": None,
                "errors": (),
            },
            {
                "status": MeasurementStatus.FAILED,
                "errors": (error,),
            },
            {
                "status": MeasurementStatus.PARTIAL,
                "errors": (),
            },
            {
                "status": MeasurementStatus.PARTIAL,
                "current": None,
                "request_latency_seconds": None,
                "errors": (error,),
            },
        )

        for overrides in invalid_overrides:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self._success_result(**overrides)

    def test_requires_current_and_request_latency_as_a_pair(self) -> None:
        for current, latency in ((1.25, None), (None, 0.25)):
            with self.subTest(current=current, latency=latency):
                with self.assertRaises(ValueError):
                    self._success_result(
                        current=current,
                        request_latency_seconds=latency,
                    )

    def test_rejects_invalid_numeric_values(self) -> None:
        invalid_elapsed_values = (True, -0.1, math.nan, math.inf)
        for elapsed in invalid_elapsed_values:
            with self.subTest(field="elapsed_seconds", value=elapsed):
                with self.assertRaises(ValueError):
                    self._success_result(elapsed_seconds=elapsed)

        invalid_measurement_values = (True, math.nan, math.inf, "1.25")
        for current in invalid_measurement_values:
            with self.subTest(field="current", value=current):
                with self.assertRaises(ValueError):
                    self._success_result(current=current)

        invalid_latency_values = (True, -0.1, math.nan, math.inf)
        for latency in invalid_latency_values:
            with self.subTest(
                field="request_latency_seconds",
                value=latency,
            ):
                with self.assertRaises(ValueError):
                    self._success_result(
                        request_latency_seconds=latency,
                    )

    def test_rejects_invalid_metadata_and_error_collections(self) -> None:
        invalid_overrides = (
            {"ammeter_type": ""},
            {"ammeter_type": "   "},
            {"ammeter_type": 123},
            {"status": "success"},
            {"timestamp_utc": datetime(2026, 8, 1, 9, 30)},
            {"timestamp_utc": "2026-08-01T09:30:00Z"},
            {"unit": "mA"},
            {"errors": []},
            {"errors": ("transport unavailable",)},
        )

        for overrides in invalid_overrides:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self._success_result(**overrides)

    def test_measurement_error_is_typed_non_empty_and_immutable(self) -> None:
        error = self._error()

        self.assertEqual(
            error.code,
            MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
        )
        with self.assertRaises(FrozenInstanceError):
            error.message = "changed"
        with self.assertRaises(ValueError):
            MeasurementError(code="measurement_request_failed", message="x")
        with self.assertRaises(ValueError):
            MeasurementError(
                code=MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
                message="  ",
            )
        with self.assertRaises(ValueError):
            MeasurementError(
                code=MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
                message=None,
            )


if __name__ == "__main__":
    unittest.main()
