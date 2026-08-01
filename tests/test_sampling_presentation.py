import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import SamplingSettings
from src.presentation.console.format_sampling_results_table import (
    format_sampling_results_table,
)
from src.presentation.console.print_sampling_results import (
    print_sampling_results,
)
from src.presentation.serialization.sampling_result_to_dict import (
    sampling_result_to_dict,
)


STARTED_AT = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


class SamplingPresentationTests(unittest.TestCase):
    def _partial_result(self) -> SamplingResult:
        missed_error = MeasurementError(
            code=MeasurementErrorCode.SAMPLING_SLOT_MISSED,
            message="Sampling slot 1 at 0.500000s was missed",
        )
        successful = SampleResult(
            sample_index=0,
            scheduled_elapsed_seconds=0.0,
            started_elapsed_seconds=0.01,
            completed_elapsed_seconds=0.02,
            result=MeasurementResult(
                ammeter_type="greenlee",
                status=MeasurementStatus.SUCCESS,
                timestamp_utc=STARTED_AT + timedelta(seconds=0.02),
                elapsed_seconds=0.01,
                current=-1.25,
                unit="A",
                request_latency_seconds=0.005,
                errors=(),
            ),
        )
        missed = SampleResult(
            sample_index=1,
            scheduled_elapsed_seconds=0.5,
            started_elapsed_seconds=None,
            completed_elapsed_seconds=1.1,
            result=MeasurementResult(
                ammeter_type="greenlee",
                status=MeasurementStatus.FAILED,
                timestamp_utc=STARTED_AT + timedelta(seconds=1.1),
                elapsed_seconds=0.0,
                current=None,
                unit="A",
                request_latency_seconds=None,
                errors=(missed_error,),
            ),
        )
        return SamplingResult(
            ammeter_type="greenlee",
            status=MeasurementStatus.PARTIAL,
            timestamp_utc=STARTED_AT + timedelta(seconds=1.2),
            elapsed_seconds=1.2,
            sampling_started_at_utc=STARTED_AT,
            sampling_elapsed_seconds=1.1,
            settings=SamplingSettings(
                measurements_count=2,
                total_duration_seconds=1.0,
                sampling_frequency_hz=2.0,
            ),
            samples=(successful, missed),
            errors=(),
            unit="A",
        )

    def test_serializes_nested_samples_and_timing_as_json_values(self) -> None:
        serialized = sampling_result_to_dict(self._partial_result())

        self.assertEqual(serialized["status"], "partial")
        self.assertEqual(
            serialized["sampling_started_at_utc"],
            "2026-08-01T12:00:00Z",
        )
        self.assertEqual(
            serialized["summary"],
            {
                "successful_samples": 1,
                "failed_samples": 0,
                "missed_samples": 1,
                "retried_samples": 0,
            },
        )
        self.assertEqual(
            serialized["samples"][0]["scheduled_at_utc"],
            "2026-08-01T12:00:00Z",
        )
        self.assertEqual(
            serialized["samples"][0]["started_at_utc"],
            "2026-08-01T12:00:00.010000Z",
        )
        self.assertAlmostEqual(
            serialized["samples"][0]["timing_error_seconds"],
            0.01,
        )
        self.assertEqual(
            serialized["samples"][0]["result"]["current"],
            -1.25,
        )
        self.assertIsNone(
            serialized["samples"][1]["started_elapsed_seconds"]
        )
        self.assertEqual(
            serialized["samples"][1]["result"]["errors"][0]["code"],
            "sampling_slot_missed",
        )
        json.dumps(serialized)

    def test_formats_and_prints_an_aligned_sampling_summary(self) -> None:
        result = self._partial_result()

        table = format_sampling_results_table([result])

        self.assertIn("Ammeter Sampling Results", table)
        self.assertIn("| GREENLEE | PARTIAL", table)
        self.assertIn("|        1/2 |", table)
        self.assertIn("|      1 |", table)
        self.assertIn("#2:sampling_slot_missed", table)

        output = io.StringIO()
        with redirect_stdout(output):
            print_sampling_results([result])
        self.assertEqual(output.getvalue(), table + "\n")

    def test_formats_an_empty_sampling_summary(self) -> None:
        table = format_sampling_results_table([])

        self.assertIn("Ammeter Sampling Results", table)
        self.assertIn("| Ammeter", table)


if __name__ == "__main__":
    unittest.main()
