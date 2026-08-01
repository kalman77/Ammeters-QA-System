import math
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import SamplingSettings


TIMESTAMP_UTC = datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc)


class SamplingModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = SamplingSettings(
            measurements_count=2,
            total_duration_seconds=1.0,
            sampling_frequency_hz=2.0,
        )

    def _error(
        self,
        code=MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
        message="measurement failed",
    ) -> MeasurementError:
        return MeasurementError(code=code, message=message)

    def _measurement(
        self,
        *,
        ammeter_type="greenlee",
        status=MeasurementStatus.SUCCESS,
        current=1.25,
        latency=0.05,
        errors=(),
    ) -> MeasurementResult:
        return MeasurementResult(
            ammeter_type=ammeter_type,
            status=status,
            timestamp_utc=TIMESTAMP_UTC,
            elapsed_seconds=0.1,
            current=current,
            unit="A",
            request_latency_seconds=latency,
            errors=errors,
        )

    def _successful_sample(
        self,
        sample_index,
        *,
        ammeter_type="greenlee",
    ) -> SampleResult:
        scheduled = sample_index / self.settings.sampling_frequency_hz
        return SampleResult(
            sample_index=sample_index,
            scheduled_elapsed_seconds=scheduled,
            started_elapsed_seconds=scheduled,
            completed_elapsed_seconds=scheduled + 0.1,
            result=self._measurement(ammeter_type=ammeter_type),
        )

    def _failed_sample(
        self,
        sample_index,
        *,
        missed=False,
    ) -> SampleResult:
        scheduled = sample_index / self.settings.sampling_frequency_hz
        code = (
            MeasurementErrorCode.SAMPLING_SLOT_MISSED
            if missed
            else MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED
        )
        return SampleResult(
            sample_index=sample_index,
            scheduled_elapsed_seconds=scheduled,
            started_elapsed_seconds=None if missed else scheduled,
            completed_elapsed_seconds=scheduled + 0.1,
            result=self._measurement(
                status=MeasurementStatus.FAILED,
                current=None,
                latency=None,
                errors=(self._error(code),),
            ),
        )

    def _sampling_result(
        self,
        *,
        status=MeasurementStatus.SUCCESS,
        samples=None,
        errors=(),
        sampling_started_at_utc=TIMESTAMP_UTC,
        sampling_elapsed_seconds=1.0,
        **overrides,
    ) -> SamplingResult:
        if samples is None:
            samples = (
                self._successful_sample(0),
                self._successful_sample(1),
            )
        values = {
            "ammeter_type": "greenlee",
            "status": status,
            "timestamp_utc": TIMESTAMP_UTC,
            "elapsed_seconds": 1.2,
            "sampling_started_at_utc": sampling_started_at_utc,
            "sampling_elapsed_seconds": sampling_elapsed_seconds,
            "settings": self.settings,
            "samples": samples,
            "errors": errors,
            "unit": "A",
        }
        values.update(overrides)
        return SamplingResult(**values)

    def test_sample_result_supports_success_failure_and_missed_slot(
        self,
    ) -> None:
        successful = self._successful_sample(0)
        failed = self._failed_sample(0)
        missed = self._failed_sample(0, missed=True)

        self.assertIs(
            successful.result.status,
            MeasurementStatus.SUCCESS,
        )
        self.assertEqual(failed.started_elapsed_seconds, 0.0)
        self.assertIs(failed.result.status, MeasurementStatus.FAILED)
        self.assertIsNone(missed.started_elapsed_seconds)
        self.assertEqual(
            missed.result.errors[0].code,
            MeasurementErrorCode.SAMPLING_SLOT_MISSED,
        )
        with self.assertRaises(FrozenInstanceError):
            successful.sample_index = 1

    def test_sample_result_rejects_invalid_indexes_and_timing_values(
        self,
    ) -> None:
        base_values = {
            "sample_index": 0,
            "scheduled_elapsed_seconds": 0.0,
            "started_elapsed_seconds": 0.0,
            "completed_elapsed_seconds": 0.1,
            "result": self._measurement(),
        }
        invalid_overrides = (
            {"sample_index": True},
            {"sample_index": -1},
            {"sample_index": 1.5},
            {"scheduled_elapsed_seconds": True},
            {"scheduled_elapsed_seconds": -0.1},
            {"scheduled_elapsed_seconds": math.nan},
            {"completed_elapsed_seconds": -0.1},
            {"completed_elapsed_seconds": math.inf},
            {"started_elapsed_seconds": True},
            {"started_elapsed_seconds": -0.1},
            {"started_elapsed_seconds": math.nan},
            {
                "started_elapsed_seconds": 0.2,
                "completed_elapsed_seconds": 0.1,
            },
            {
                "scheduled_elapsed_seconds": 0.2,
                "started_elapsed_seconds": 0.1,
                "completed_elapsed_seconds": 0.3,
            },
        )

        for overrides in invalid_overrides:
            values = dict(base_values)
            values.update(overrides)
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    SampleResult(**values)

    def test_sample_result_requires_a_non_partial_measurement_result(
        self,
    ) -> None:
        error = self._error()
        partial = self._measurement(
            status=MeasurementStatus.PARTIAL,
            errors=(error,),
        )

        with self.assertRaisesRegex(ValueError, "must be MeasurementResult"):
            SampleResult(
                sample_index=0,
                scheduled_elapsed_seconds=0.0,
                started_elapsed_seconds=0.0,
                completed_elapsed_seconds=0.1,
                result="not a result",
            )
        with self.assertRaisesRegex(ValueError, "cannot be partial"):
            SampleResult(
                sample_index=0,
                scheduled_elapsed_seconds=0.0,
                started_elapsed_seconds=0.0,
                completed_elapsed_seconds=0.1,
                result=partial,
            )

    def test_sample_start_and_missed_slot_error_must_agree(self) -> None:
        request_failure = self._measurement(
            status=MeasurementStatus.FAILED,
            current=None,
            latency=None,
            errors=(self._error(),),
        )
        missed_failure = self._measurement(
            status=MeasurementStatus.FAILED,
            current=None,
            latency=None,
            errors=(
                self._error(
                    MeasurementErrorCode.SAMPLING_SLOT_MISSED,
                    "slot missed",
                ),
            ),
        )

        with self.assertRaisesRegex(ValueError, "must be a missed slot"):
            SampleResult(
                sample_index=0,
                scheduled_elapsed_seconds=0.0,
                started_elapsed_seconds=None,
                completed_elapsed_seconds=0.1,
                result=request_failure,
            )
        with self.assertRaisesRegex(ValueError, "cannot have a start time"):
            SampleResult(
                sample_index=0,
                scheduled_elapsed_seconds=0.0,
                started_elapsed_seconds=0.0,
                completed_elapsed_seconds=0.1,
                result=missed_failure,
            )

    def test_sampling_result_supports_success_partial_and_failed_statuses(
        self,
    ) -> None:
        successful = self._sampling_result()
        partial = self._sampling_result(
            status=MeasurementStatus.PARTIAL,
            samples=(
                self._successful_sample(0),
                self._failed_sample(1),
            ),
        )
        failed = self._sampling_result(
            status=MeasurementStatus.FAILED,
            samples=(
                self._failed_sample(0),
                self._failed_sample(1, missed=True),
            ),
        )
        startup_failure = self._sampling_result(
            status=MeasurementStatus.FAILED,
            samples=(),
            errors=(
                self._error(
                    MeasurementErrorCode.EMULATOR_START_FAILED,
                    "startup failed",
                ),
            ),
            sampling_started_at_utc=None,
            sampling_elapsed_seconds=None,
        )

        self.assertIs(
            successful.status,
            MeasurementStatus.SUCCESS,
        )
        self.assertIs(partial.status, MeasurementStatus.PARTIAL)
        self.assertIs(failed.status, MeasurementStatus.FAILED)
        self.assertIsNone(startup_failure.sampling_started_at_utc)
        self.assertEqual(startup_failure.samples, ())
        with self.assertRaises(FrozenInstanceError):
            successful.status = MeasurementStatus.FAILED

    def test_sampling_result_accepts_run_error_as_partial_after_samples(
        self,
    ) -> None:
        result = self._sampling_result(
            status=MeasurementStatus.PARTIAL,
            errors=(
                self._error(
                    MeasurementErrorCode.EMULATOR_STOP_FAILED,
                    "shutdown failed",
                ),
            ),
        )

        self.assertEqual(
            result.errors[0].code,
            MeasurementErrorCode.EMULATOR_STOP_FAILED,
        )
        self.assertTrue(
            all(
                sample.result.status is MeasurementStatus.SUCCESS
                for sample in result.samples
            )
        )

    def test_sampling_result_rejects_statuses_inconsistent_with_samples(
        self,
    ) -> None:
        all_successful = (
            self._successful_sample(0),
            self._successful_sample(1),
        )
        mixed = (
            self._successful_sample(0),
            self._failed_sample(1),
        )
        all_failed = (
            self._failed_sample(0),
            self._failed_sample(1),
        )
        run_error = (
            self._error(
                MeasurementErrorCode.EMULATOR_STOP_FAILED,
                "shutdown failed",
            ),
        )
        invalid_cases = (
            {
                "status": MeasurementStatus.SUCCESS,
                "samples": mixed,
            },
            {
                "status": MeasurementStatus.SUCCESS,
                "samples": all_successful,
                "errors": run_error,
            },
            {
                "status": MeasurementStatus.PARTIAL,
                "samples": all_successful,
            },
            {
                "status": MeasurementStatus.PARTIAL,
                "samples": all_failed,
            },
            {
                "status": MeasurementStatus.FAILED,
                "samples": mixed,
            },
            {
                "status": MeasurementStatus.FAILED,
                "samples": (),
                "sampling_started_at_utc": None,
                "sampling_elapsed_seconds": None,
            },
        )

        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self._sampling_result(**values)

    def test_sampling_start_fields_and_sample_count_must_agree(self) -> None:
        invalid_cases = (
            {
                "sampling_started_at_utc": None,
                "sampling_elapsed_seconds": 1.0,
                "samples": (),
                "status": MeasurementStatus.FAILED,
                "errors": (self._error(),),
            },
            {
                "sampling_started_at_utc": TIMESTAMP_UTC,
                "sampling_elapsed_seconds": None,
            },
            {
                "samples": (self._successful_sample(0),),
            },
        )

        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self._sampling_result(**values)

    def test_sampling_result_requires_contiguous_matching_schedule(
        self,
    ) -> None:
        wrong_index = SampleResult(
            sample_index=2,
            scheduled_elapsed_seconds=0.5,
            started_elapsed_seconds=0.5,
            completed_elapsed_seconds=0.6,
            result=self._measurement(),
        )
        wrong_offset = SampleResult(
            sample_index=1,
            scheduled_elapsed_seconds=0.6,
            started_elapsed_seconds=0.6,
            completed_elapsed_seconds=0.7,
            result=self._measurement(),
        )

        for samples in (
            (self._successful_sample(0), wrong_index),
            (self._successful_sample(0), wrong_offset),
        ):
            with self.subTest(samples=samples):
                with self.assertRaises(ValueError):
                    self._sampling_result(samples=samples)

    def test_sampling_result_requires_matching_ammeter_type(self) -> None:
        samples = (
            self._successful_sample(0),
            self._successful_sample(1, ammeter_type="entes"),
        )

        with self.assertRaisesRegex(ValueError, "ammeter type"):
            self._sampling_result(samples=samples)

    def test_sampling_result_rejects_invalid_metadata_and_collections(
        self,
    ) -> None:
        invalid_cases = (
            {"ammeter_type": ""},
            {"ammeter_type": 42},
            {"status": "success"},
            {"timestamp_utc": datetime(2026, 8, 1, 9, 30)},
            {"timestamp_utc": "2026-08-01T09:30:00Z"},
            {"elapsed_seconds": True},
            {"elapsed_seconds": -0.1},
            {"elapsed_seconds": math.nan},
            {"settings": "not settings"},
            {"samples": list(self._sampling_result().samples)},
            {"samples": ("not a sample", "not a sample")},
            {"errors": []},
            {"errors": ("not an error",)},
            {"unit": "mA"},
        )

        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self._sampling_result(**values)

    def test_sampling_result_rejects_invalid_sampling_timing_metadata(
        self,
    ) -> None:
        invalid_cases = (
            {
                "sampling_started_at_utc": datetime(
                    2026,
                    8,
                    1,
                    9,
                    30,
                )
            },
            {"sampling_started_at_utc": "not a timestamp"},
            {"sampling_elapsed_seconds": True},
            {"sampling_elapsed_seconds": -0.1},
            {"sampling_elapsed_seconds": math.nan},
            {"sampling_elapsed_seconds": math.inf},
        )

        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self._sampling_result(**values)

    def test_sampling_result_requires_complete_window_timing(self) -> None:
        invalid_cases = (
            {"sampling_elapsed_seconds": 0.9},
            {
                "sampling_elapsed_seconds": 1.0,
                "samples": (
                    self._successful_sample(0),
                    SampleResult(
                        sample_index=1,
                        scheduled_elapsed_seconds=0.5,
                        started_elapsed_seconds=0.9,
                        completed_elapsed_seconds=1.1,
                        result=self._measurement(),
                    ),
                ),
            },
            {
                "elapsed_seconds": 0.9,
                "sampling_elapsed_seconds": 1.0,
            },
        )

        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self._sampling_result(**values)


if __name__ == "__main__":
    unittest.main()
