import math
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.current_statistics import CurrentStatistics
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_analysis import SamplingAnalysis
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import SamplingSettings


TIMESTAMP_UTC = datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc)


def successful_sampling_result() -> SamplingResult:
    settings = SamplingSettings(
        measurements_count=1,
        total_duration_seconds=1.0,
        sampling_frequency_hz=1.0,
    )
    measurement = MeasurementResult(
        ammeter_type="greenlee",
        status=MeasurementStatus.SUCCESS,
        timestamp_utc=TIMESTAMP_UTC,
        elapsed_seconds=0.1,
        current=4.0,
        unit="A",
        request_latency_seconds=0.1,
        errors=(),
    )
    sample = SampleResult(
        sample_index=0,
        scheduled_elapsed_seconds=0.0,
        started_elapsed_seconds=0.0,
        completed_elapsed_seconds=0.1,
        result=measurement,
    )
    return SamplingResult(
        ammeter_type="greenlee",
        status=MeasurementStatus.SUCCESS,
        timestamp_utc=TIMESTAMP_UTC,
        elapsed_seconds=1.1,
        sampling_started_at_utc=TIMESTAMP_UTC,
        sampling_elapsed_seconds=1.0,
        settings=settings,
        samples=(sample,),
        errors=(),
        unit="A",
    )


def failed_sampling_result() -> SamplingResult:
    settings = SamplingSettings(
        measurements_count=1,
        total_duration_seconds=1.0,
        sampling_frequency_hz=1.0,
    )
    error = MeasurementError(
        code=MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
        message="request failed",
    )
    measurement = MeasurementResult(
        ammeter_type="greenlee",
        status=MeasurementStatus.FAILED,
        timestamp_utc=TIMESTAMP_UTC,
        elapsed_seconds=0.1,
        current=None,
        unit="A",
        request_latency_seconds=None,
        errors=(error,),
    )
    sample = SampleResult(
        sample_index=0,
        scheduled_elapsed_seconds=0.0,
        started_elapsed_seconds=0.0,
        completed_elapsed_seconds=0.1,
        result=measurement,
    )
    return SamplingResult(
        ammeter_type="greenlee",
        status=MeasurementStatus.FAILED,
        timestamp_utc=TIMESTAMP_UTC,
        elapsed_seconds=1.1,
        sampling_started_at_utc=TIMESTAMP_UTC,
        sampling_elapsed_seconds=1.0,
        settings=settings,
        samples=(sample,),
        errors=(),
        unit="A",
    )


class CurrentStatisticsModelTests(unittest.TestCase):
    def statistics(self, **overrides) -> CurrentStatistics:
        values = {
            "measurements_count": 4,
            "mean_current": 2.5,
            "median_current": 2.5,
            "standard_deviation_current": math.sqrt(1.25),
            "minimum_current": 1.0,
            "maximum_current": 4.0,
            "unit": "A",
        }
        values.update(overrides)
        return CurrentStatistics(**values)

    def test_is_immutable_and_preserves_population_statistics(self) -> None:
        statistics = self.statistics()

        self.assertEqual(statistics.measurements_count, 4)
        self.assertEqual(statistics.mean_current, 2.5)
        self.assertEqual(statistics.median_current, 2.5)
        self.assertAlmostEqual(
            statistics.standard_deviation_current,
            math.sqrt(1.25),
        )
        self.assertEqual(statistics.minimum_current, 1.0)
        self.assertEqual(statistics.maximum_current, 4.0)
        self.assertEqual(statistics.unit, "A")
        with self.assertRaises(FrozenInstanceError):
            statistics.mean_current = 10.0

    def test_rejects_invalid_measurement_counts(self) -> None:
        for count in (True, 0, -1, 1.5, "4"):
            with self.subTest(count=count):
                with self.assertRaisesRegex(
                    ValueError,
                    "positive integer",
                ):
                    self.statistics(measurements_count=count)

    def test_rejects_non_finite_and_non_numeric_metrics(self) -> None:
        metric_names = (
            "mean_current",
            "median_current",
            "standard_deviation_current",
            "minimum_current",
            "maximum_current",
        )
        invalid_values = (True, "2.5", math.nan, math.inf, -math.inf)

        for field_name in metric_names:
            for value in invalid_values:
                with self.subTest(field=field_name, value=value):
                    with self.assertRaisesRegex(
                        ValueError,
                        f"{field_name} must be a finite number",
                    ):
                        self.statistics(**{field_name: value})

    def test_rejects_inconsistent_range_and_deviation_values(self) -> None:
        invalid_cases = (
            (
                {"standard_deviation_current": -0.1},
                "cannot be negative",
            ),
            (
                {"minimum_current": 5.0},
                "cannot exceed maximum",
            ),
            (
                {"mean_current": 5.0},
                "mean_current must be within",
            ),
            (
                {"median_current": 5.0},
                "median_current must be within",
            ),
            (
                {"unit": "mA"},
                "must use unit 'A'",
            ),
        )

        for overrides, message in invalid_cases:
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(ValueError, message):
                    self.statistics(**overrides)

    def test_single_measurement_requires_identical_values_and_zero_stddev(
        self,
    ) -> None:
        singleton = self.statistics(
            measurements_count=1,
            mean_current=-3.5,
            median_current=-3.5,
            standard_deviation_current=0.0,
            minimum_current=-3.5,
            maximum_current=-3.5,
        )

        self.assertEqual(singleton.minimum_current, -3.5)
        with self.assertRaisesRegex(
            ValueError,
            "one measurement requires",
        ):
            self.statistics(
                measurements_count=1,
                mean_current=2.0,
                median_current=2.0,
                standard_deviation_current=0.1,
                minimum_current=2.0,
                maximum_current=2.0,
            )


class SamplingAnalysisModelTests(unittest.TestCase):
    def test_derives_statistics_from_sampling_provenance_immutably(
        self,
    ) -> None:
        sampling_result = successful_sampling_result()
        analysis = SamplingAnalysis(
            sampling_result=sampling_result,
        )

        self.assertIs(analysis.sampling_result, sampling_result)
        self.assertIsNotNone(analysis.statistics)
        self.assertEqual(analysis.statistics.measurements_count, 1)
        self.assertEqual(analysis.statistics.mean_current, 4.0)
        self.assertEqual(analysis.statistics.median_current, 4.0)
        self.assertEqual(
            analysis.statistics.standard_deviation_current,
            0.0,
        )
        self.assertEqual(analysis.statistics.minimum_current, 4.0)
        self.assertEqual(analysis.statistics.maximum_current, 4.0)
        with self.assertRaises(FrozenInstanceError):
            analysis.statistics = None

    def test_allows_no_statistics_when_there_are_no_successful_samples(
        self,
    ) -> None:
        sampling_result = failed_sampling_result()

        analysis = SamplingAnalysis(
            sampling_result=sampling_result,
        )

        self.assertIs(analysis.sampling_result, sampling_result)
        self.assertIsNone(analysis.statistics)

    def test_rejects_invalid_sampling_result_type(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "sampling_result must be SamplingResult",
        ):
            SamplingAnalysis(sampling_result="not a sampling result")

    def test_callers_cannot_supply_statistics_that_conflict_with_source(
        self,
    ) -> None:
        sampling_result = successful_sampling_result()
        forged_statistics = CurrentStatistics(
            measurements_count=1,
            mean_current=999.0,
            median_current=999.0,
            standard_deviation_current=0.0,
            minimum_current=999.0,
            maximum_current=999.0,
            unit="A",
        )

        with self.assertRaises(TypeError):
            SamplingAnalysis(
                sampling_result=sampling_result,
                statistics=forged_statistics,
            )


if __name__ == "__main__":
    unittest.main()
