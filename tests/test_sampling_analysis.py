import math
import unittest
from datetime import datetime, timezone

from src.application.use_cases.analyze_sampling_result import (
    analyze_sampling_result,
)
from src.domain.services.calculate_current_statistics import (
    calculate_current_statistics,
)
from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import SamplingSettings


TIMESTAMP_UTC = datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc)


class SamplingAnalysisTests(unittest.TestCase):
    def error(
        self,
        code=MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
        message="measurement failed",
    ) -> MeasurementError:
        return MeasurementError(code=code, message=message)

    def sample(
        self,
        index,
        *,
        current=None,
        error_code=None,
        missed=False,
    ) -> SampleResult:
        scheduled = float(index)
        if error_code is None and not missed:
            result = MeasurementResult(
                ammeter_type="greenlee",
                status=MeasurementStatus.SUCCESS,
                timestamp_utc=TIMESTAMP_UTC,
                elapsed_seconds=0.1,
                current=current,
                unit="A",
                request_latency_seconds=0.1,
                errors=(),
            )
        else:
            code = (
                MeasurementErrorCode.SAMPLING_SLOT_MISSED
                if missed
                else error_code
            )
            result = MeasurementResult(
                ammeter_type="greenlee",
                status=MeasurementStatus.FAILED,
                timestamp_utc=TIMESTAMP_UTC,
                elapsed_seconds=0.1,
                current=None,
                unit="A",
                request_latency_seconds=None,
                errors=(self.error(code),),
            )
        return SampleResult(
            sample_index=index,
            scheduled_elapsed_seconds=scheduled,
            started_elapsed_seconds=None if missed else scheduled,
            completed_elapsed_seconds=scheduled + 0.1,
            result=result,
        )

    def started_result(
        self,
        samples,
        *,
        status,
        errors=(),
    ) -> SamplingResult:
        count = len(samples)
        settings = SamplingSettings(
            measurements_count=count,
            total_duration_seconds=float(count),
            sampling_frequency_hz=1.0,
        )
        return SamplingResult(
            ammeter_type="greenlee",
            status=status,
            timestamp_utc=TIMESTAMP_UTC,
            elapsed_seconds=float(count) + 0.1,
            sampling_started_at_utc=TIMESTAMP_UTC,
            sampling_elapsed_seconds=float(count),
            settings=settings,
            samples=tuple(samples),
            errors=errors,
            unit="A",
        )

    def startup_failure_result(self) -> SamplingResult:
        settings = SamplingSettings(
            measurements_count=3,
            total_duration_seconds=3.0,
            sampling_frequency_hz=1.0,
        )
        return SamplingResult(
            ammeter_type="greenlee",
            status=MeasurementStatus.FAILED,
            timestamp_utc=TIMESTAMP_UTC,
            elapsed_seconds=0.1,
            sampling_started_at_utc=None,
            sampling_elapsed_seconds=None,
            settings=settings,
            samples=(),
            errors=(
                self.error(
                    MeasurementErrorCode.EMULATOR_START_FAILED,
                    "startup failed",
                ),
            ),
            unit="A",
        )

    def test_calculates_known_population_statistics(self) -> None:
        statistics = calculate_current_statistics(
            (2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0)
        )

        self.assertIsNotNone(statistics)
        self.assertEqual(statistics.measurements_count, 8)
        self.assertEqual(statistics.mean_current, 5.0)
        self.assertEqual(statistics.median_current, 4.5)
        self.assertEqual(statistics.standard_deviation_current, 2.0)
        self.assertEqual(statistics.minimum_current, 2.0)
        self.assertEqual(statistics.maximum_current, 9.0)
        self.assertEqual(statistics.unit, "A")

    def test_calculates_odd_and_even_medians(self) -> None:
        cases = (
            ((9.0, 1.0, 3.0), 3.0),
            ((10.0, 2.0, 4.0, 8.0), 6.0),
        )

        for currents, expected_median in cases:
            with self.subTest(currents=currents):
                statistics = calculate_current_statistics(currents)
                self.assertIsNotNone(statistics)
                self.assertEqual(
                    statistics.median_current,
                    expected_median,
                )

    def test_handles_singleton_repeated_negative_and_extreme_values(
        self,
    ) -> None:
        cases = (
            (
                (7.25,),
                (7.25, 7.25, 0.0, 7.25, 7.25),
            ),
            (
                (-2.5, -2.5, -2.5, -2.5),
                (-2.5, -2.5, 0.0, -2.5, -2.5),
            ),
            (
                (-9.0, -4.0, -2.0),
                (-5.0, -4.0, math.sqrt(26.0 / 3.0), -9.0, -2.0),
            ),
            (
                (-1e200, 1e200),
                (0.0, 0.0, 1e200, -1e200, 1e200),
            ),
        )

        for currents, expected in cases:
            with self.subTest(currents=currents):
                statistics = calculate_current_statistics(currents)
                self.assertIsNotNone(statistics)
                self.assertEqual(
                    statistics.measurements_count,
                    len(currents),
                )
                self.assertAlmostEqual(
                    statistics.mean_current,
                    expected[0],
                )
                self.assertAlmostEqual(
                    statistics.median_current,
                    expected[1],
                )
                self.assertAlmostEqual(
                    statistics.standard_deviation_current,
                    expected[2],
                )
                self.assertEqual(
                    statistics.minimum_current,
                    expected[3],
                )
                self.assertEqual(
                    statistics.maximum_current,
                    expected[4],
                )

    def test_empty_input_has_no_statistics(self) -> None:
        self.assertIsNone(calculate_current_statistics(()))
        self.assertIsNone(
            calculate_current_statistics(current for current in ())
        )

    def test_mixed_failed_and_missed_samples_are_excluded(self) -> None:
        sampling_result = self.started_result(
            (
                self.sample(0, current=10.0),
                self.sample(
                    1,
                    error_code=(
                        MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED
                    ),
                ),
                self.sample(2, missed=True),
                self.sample(3, current=20.0),
            ),
            status=MeasurementStatus.PARTIAL,
        )

        analysis = analyze_sampling_result(sampling_result)

        self.assertIs(analysis.sampling_result, sampling_result)
        self.assertIsNotNone(analysis.statistics)
        self.assertEqual(analysis.statistics.measurements_count, 2)
        self.assertEqual(analysis.statistics.mean_current, 15.0)
        self.assertEqual(analysis.statistics.median_current, 15.0)
        self.assertEqual(
            analysis.statistics.standard_deviation_current,
            5.0,
        )
        self.assertEqual(analysis.statistics.minimum_current, 10.0)
        self.assertEqual(analysis.statistics.maximum_current, 20.0)

    def test_all_failed_and_startup_failure_have_no_statistics(self) -> None:
        all_failed = self.started_result(
            (
                self.sample(
                    0,
                    error_code=(
                        MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED
                    ),
                ),
                self.sample(1, missed=True),
            ),
            status=MeasurementStatus.FAILED,
        )
        startup_failure = self.startup_failure_result()

        for sampling_result in (all_failed, startup_failure):
            with self.subTest(
                sampling_started=(
                    sampling_result.sampling_started_at_utc is not None
                )
            ):
                analysis = analyze_sampling_result(sampling_result)
                self.assertIs(analysis.sampling_result, sampling_result)
                self.assertIsNone(analysis.statistics)

    def test_stop_failure_keeps_successful_samples_in_analysis(self) -> None:
        stop_error = self.error(
            MeasurementErrorCode.EMULATOR_STOP_FAILED,
            "shutdown timed out",
        )
        sampling_result = self.started_result(
            (
                self.sample(0, current=2.0),
                self.sample(1, current=6.0),
            ),
            status=MeasurementStatus.PARTIAL,
            errors=(stop_error,),
        )

        analysis = analyze_sampling_result(sampling_result)

        self.assertIsNotNone(analysis.statistics)
        self.assertEqual(analysis.statistics.measurements_count, 2)
        self.assertEqual(analysis.statistics.mean_current, 4.0)
        self.assertEqual(analysis.statistics.median_current, 4.0)
        self.assertEqual(
            analysis.statistics.standard_deviation_current,
            2.0,
        )
        self.assertEqual(sampling_result.errors, (stop_error,))

    def test_rejects_invalid_statistics_inputs(self) -> None:
        for currents in (None, 1, True):
            with self.subTest(currents=currents):
                with self.assertRaisesRegex(
                    ValueError,
                    "iterable of finite numbers",
                ):
                    calculate_current_statistics(currents)

        invalid_values = (
            True,
            "1.0",
            None,
            math.nan,
            math.inf,
            -math.inf,
        )
        for invalid_value in invalid_values:
            with self.subTest(value=invalid_value):
                with self.assertRaisesRegex(
                    ValueError,
                    "only finite numbers",
                ):
                    calculate_current_statistics((invalid_value,))

    def test_rejects_non_sampling_result_analysis_input(self) -> None:
        for invalid_result in (None, "sampling result", object()):
            with self.subTest(result=invalid_result):
                with self.assertRaisesRegex(
                    ValueError,
                    "sampling_result must be SamplingResult",
                ):
                    analyze_sampling_result(invalid_result)


if __name__ == "__main__":
    unittest.main()
