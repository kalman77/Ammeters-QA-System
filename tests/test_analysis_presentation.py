import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from src.application.use_cases.analyze_sampling_result import (
    analyze_sampling_result,
)
from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import SamplingSettings
from src.presentation.console.format_analysis_results_table import (
    format_analysis_results_table,
)
from src.presentation.console.print_analysis_results import (
    print_analysis_results,
)
from src.presentation.serialization.sampling_analysis_to_dict import (
    sampling_analysis_to_dict,
)


STARTED_AT = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


class AnalysisPresentationTests(unittest.TestCase):
    def _measurement(
        self,
        *,
        status,
        current=None,
        error=None,
        timestamp_offset=0.0,
    ) -> MeasurementResult:
        return MeasurementResult(
            ammeter_type="greenlee",
            status=status,
            timestamp_utc=STARTED_AT + timedelta(
                seconds=timestamp_offset
            ),
            elapsed_seconds=0.1 if current is not None else 0.0,
            current=current,
            unit="A",
            request_latency_seconds=(
                0.05 if current is not None else None
            ),
            errors=() if error is None else (error,),
        )

    def _partial_sampling_result(self) -> SamplingResult:
        request_error = MeasurementError(
            code=MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
            message="request failed",
        )
        missed_error = MeasurementError(
            code=MeasurementErrorCode.SAMPLING_SLOT_MISSED,
            message="slot missed",
        )
        samples = (
            SampleResult(
                sample_index=0,
                scheduled_elapsed_seconds=0.0,
                started_elapsed_seconds=0.0,
                completed_elapsed_seconds=0.1,
                result=self._measurement(
                    status=MeasurementStatus.SUCCESS,
                    current=1.0,
                    timestamp_offset=0.1,
                ),
            ),
            SampleResult(
                sample_index=1,
                scheduled_elapsed_seconds=0.5,
                started_elapsed_seconds=0.5,
                completed_elapsed_seconds=0.6,
                result=self._measurement(
                    status=MeasurementStatus.FAILED,
                    error=request_error,
                    timestamp_offset=0.6,
                ),
            ),
            SampleResult(
                sample_index=2,
                scheduled_elapsed_seconds=1.0,
                started_elapsed_seconds=1.0,
                completed_elapsed_seconds=1.1,
                result=self._measurement(
                    status=MeasurementStatus.SUCCESS,
                    current=3.0,
                    timestamp_offset=1.1,
                ),
            ),
            SampleResult(
                sample_index=3,
                scheduled_elapsed_seconds=1.5,
                started_elapsed_seconds=None,
                completed_elapsed_seconds=2.0,
                result=self._measurement(
                    status=MeasurementStatus.FAILED,
                    error=missed_error,
                    timestamp_offset=2.0,
                ),
            ),
        )
        return SamplingResult(
            ammeter_type="greenlee",
            status=MeasurementStatus.PARTIAL,
            timestamp_utc=STARTED_AT + timedelta(seconds=2.1),
            elapsed_seconds=2.1,
            sampling_started_at_utc=STARTED_AT,
            sampling_elapsed_seconds=2.0,
            settings=SamplingSettings(
                measurements_count=4,
                total_duration_seconds=2.0,
                sampling_frequency_hz=2.0,
            ),
            samples=samples,
            errors=(),
            unit="A",
        )

    def _startup_failure(self) -> SamplingResult:
        return SamplingResult(
            ammeter_type="greenlee",
            status=MeasurementStatus.FAILED,
            timestamp_utc=STARTED_AT,
            elapsed_seconds=0.1,
            sampling_started_at_utc=None,
            sampling_elapsed_seconds=None,
            settings=SamplingSettings(
                measurements_count=2,
                total_duration_seconds=1.0,
                sampling_frequency_hz=2.0,
            ),
            samples=(),
            errors=(
                MeasurementError(
                    code=MeasurementErrorCode.EMULATOR_START_FAILED,
                    message="startup failed",
                ),
            ),
            unit="A",
        )

    def test_serializes_statistics_counts_and_source_provenance(
        self,
    ) -> None:
        serialized = sampling_analysis_to_dict(
            analyze_sampling_result(self._partial_sampling_result())
        )

        self.assertEqual(serialized["ammeter_type"], "greenlee")
        self.assertEqual(serialized["status"], "partial")
        self.assertEqual(
            serialized["summary"],
            {
                "planned_samples": 4,
                "recorded_samples": 4,
                "analyzed_samples": 2,
                "excluded_samples": 2,
                "failed_samples": 1,
                "missed_samples": 1,
            },
        )
        self.assertEqual(
            serialized["statistics"],
            {
                "measurements_count": 2,
                "mean_current": 2.0,
                "median_current": 2.0,
                "standard_deviation_current": 1.0,
                "standard_deviation_method": "population",
                "minimum_current": 1.0,
                "maximum_current": 3.0,
                "unit": "A",
            },
        )
        self.assertEqual(
            serialized["sampling_result"]["samples"][1]["result"][
                "errors"
            ][0]["code"],
            "measurement_request_failed",
        )
        json.dumps(serialized)

    def test_serializes_no_data_as_null_without_inventing_failed_slots(
        self,
    ) -> None:
        serialized = sampling_analysis_to_dict(
            analyze_sampling_result(self._startup_failure())
        )

        self.assertIsNone(serialized["statistics"])
        self.assertEqual(
            serialized["summary"],
            {
                "planned_samples": 2,
                "recorded_samples": 0,
                "analyzed_samples": 0,
                "excluded_samples": 0,
                "failed_samples": 0,
                "missed_samples": 0,
            },
        )
        self.assertEqual(
            serialized["sampling_result"]["errors"][0]["code"],
            "emulator_start_failed",
        )
        json.dumps(serialized)

    def test_formats_and_prints_partial_and_no_data_rows(self) -> None:
        analyses = (
            analyze_sampling_result(self._partial_sampling_result()),
            analyze_sampling_result(self._startup_failure()),
        )

        table = format_analysis_results_table(analyses)

        self.assertIn("Ammeter Statistical Analysis", table)
        self.assertIn("Pop StdDev (A)", table)
        self.assertIn("| GREENLEE | PARTIAL", table)
        self.assertIn("|          2/4 |", table)
        self.assertIn("|           1/1 |", table)
        self.assertIn("| 2.000000 |", table)
        self.assertIn("#2:measurement_request_failed", table)
        self.assertIn("emulator_start_failed", table)

        output = io.StringIO()
        with redirect_stdout(output):
            print_analysis_results(analyses)
        self.assertEqual(output.getvalue(), table + "\n")

    def test_formats_an_empty_analysis_table(self) -> None:
        table = format_analysis_results_table(())

        self.assertIn("Ammeter Statistical Analysis", table)
        self.assertIn("| Ammeter", table)
        self.assertIn("| Mean (A)", table)


if __name__ == "__main__":
    unittest.main()
