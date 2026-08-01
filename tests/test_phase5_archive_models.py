import math
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.archived_run_query import (
    MAX_ARCHIVE_QUERY_LIMIT,
    ArchivedRunQuery,
)
from src.domain.models.archived_test_run import (
    MAX_METADATA_ENTRIES,
    ArchivedTestRun,
)
from src.domain.models.current_statistics import CurrentStatistics
from src.domain.models.current_statistics_delta import (
    CurrentStatisticsDelta,
)
from src.domain.models.historical_comparison import HistoricalComparison
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.run_metadata_entry import (
    MAX_METADATA_KEY_LENGTH,
    MAX_METADATA_STRING_LENGTH,
    RunMetadataEntry,
)
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_analysis import SamplingAnalysis
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import SamplingSettings
from src.domain.services.calculate_current_statistics_delta import (
    calculate_current_statistics_delta,
)
from src.domain.services.normalize_run_id import normalize_run_id
from src.infrastructure.identifiers.generate_run_id import generate_run_id


BASE_TIME = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
RUN_ID_1 = "00000000-0000-4000-8000-000000000001"
RUN_ID_2 = "00000000-0000-4000-8000-000000000002"
RUN_ID_3 = "00000000-0000-4000-8000-000000000003"


def _analysis(
    *,
    ammeter_type: str = "greenlee",
    currents: Tuple[Optional[float], ...] = (1.0, 3.0),
    frequency_hz: float = 2.0,
    started_at_utc: datetime = BASE_TIME,
) -> SamplingAnalysis:
    settings = SamplingSettings(
        measurements_count=len(currents),
        total_duration_seconds=len(currents) / frequency_hz,
        sampling_frequency_hz=frequency_hz,
    )
    samples = []
    for index, current in enumerate(currents):
        scheduled = index / frequency_hz
        timestamp = started_at_utc + timedelta(seconds=scheduled)
        if current is None:
            result = MeasurementResult(
                ammeter_type=ammeter_type,
                status=MeasurementStatus.FAILED,
                timestamp_utc=timestamp,
                elapsed_seconds=0.01,
                current=None,
                unit="A",
                request_latency_seconds=None,
                errors=(
                    MeasurementError(
                        code=(
                            MeasurementErrorCode
                            .MEASUREMENT_REQUEST_FAILED
                        ),
                        message="request failed",
                    ),
                ),
            )
        else:
            result = MeasurementResult(
                ammeter_type=ammeter_type,
                status=MeasurementStatus.SUCCESS,
                timestamp_utc=timestamp,
                elapsed_seconds=0.01,
                current=current,
                unit="A",
                request_latency_seconds=0.01,
                errors=(),
            )
        samples.append(
            SampleResult(
                sample_index=index,
                scheduled_elapsed_seconds=scheduled,
                started_elapsed_seconds=scheduled,
                completed_elapsed_seconds=scheduled + 0.01,
                result=result,
            )
        )

    successful_count = sum(
        current is not None for current in currents
    )
    if successful_count == len(currents):
        status = MeasurementStatus.SUCCESS
    elif successful_count == 0:
        status = MeasurementStatus.FAILED
    else:
        status = MeasurementStatus.PARTIAL
    sampling_elapsed = max(
        settings.total_duration_seconds,
        samples[-1].completed_elapsed_seconds,
    )
    return SamplingAnalysis(
        sampling_result=SamplingResult(
            ammeter_type=ammeter_type,
            status=status,
            timestamp_utc=started_at_utc,
            elapsed_seconds=sampling_elapsed,
            sampling_started_at_utc=started_at_utc,
            sampling_elapsed_seconds=sampling_elapsed,
            settings=settings,
            samples=tuple(samples),
            errors=(),
            unit="A",
        )
    )


def _archived_run(
    run_id: str,
    *,
    archived_at_utc: datetime = BASE_TIME,
    ammeter_type: str = "greenlee",
    currents: Tuple[Optional[float], ...] = (1.0, 3.0),
    frequency_hz: float = 2.0,
    metadata: Tuple[RunMetadataEntry, ...] = (),
) -> ArchivedTestRun:
    return ArchivedTestRun(
        run_id=run_id,
        archived_at_utc=archived_at_utc,
        analysis=_analysis(
            ammeter_type=ammeter_type,
            currents=currents,
            frequency_hz=frequency_hz,
        ),
        metadata=metadata,
    )


class RunIdentityAndMetadataTests(unittest.TestCase):
    def test_generated_run_ids_are_unique_and_canonical(self) -> None:
        generated_run_ids = tuple(
            generate_run_id() for _ in range(1_000)
        )

        self.assertEqual(
            len(set(generated_run_ids)),
            len(generated_run_ids),
        )
        self.assertEqual(
            tuple(map(normalize_run_id, generated_run_ids)),
            generated_run_ids,
        )

    def test_normalize_run_id_accepts_only_canonical_uuid_strings(
        self,
    ) -> None:
        self.assertEqual(normalize_run_id(RUN_ID_1), RUN_ID_1)
        alphabetic_run_id = "abcdefab-cdef-4abc-8def-abcdefabcdef"

        invalid_values = (
            None,
            True,
            123,
            "",
            f" {RUN_ID_1}",
            alphabetic_run_id.upper(),
            RUN_ID_1.replace("-", ""),
            f"{{{RUN_ID_1}}}",
            "../archive",
            "/tmp/archive",
            "folder/archive",
            "folder\\archive",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "canonical UUID",
                ):
                    normalize_run_id(value)

    def test_metadata_entry_accepts_json_scalars_and_is_frozen(
        self,
    ) -> None:
        values = (None, True, False, 0, -7, 2.5, "operator-α", "")
        for value in values:
            with self.subTest(value=value):
                entry = RunMetadataEntry(key="environment", value=value)
                self.assertEqual(entry.value, value)

        entry = RunMetadataEntry(key="operator", value="Nir")
        with self.assertRaises(FrozenInstanceError):
            entry.value = "changed"

    def test_metadata_entry_rejects_invalid_keys_and_values(self) -> None:
        invalid_keys = (
            None,
            1,
            "",
            " ",
            " leading",
            "trailing ",
            "x" * (MAX_METADATA_KEY_LENGTH + 1),
        )
        for key in invalid_keys:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    RunMetadataEntry(key=key, value="value")

        invalid_values = (
            math.nan,
            math.inf,
            -math.inf,
            (),
            [],
            {},
            object(),
            "x" * (MAX_METADATA_STRING_LENGTH + 1),
        )
        for value in invalid_values:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    RunMetadataEntry(key="key", value=value)


class ArchivedTestRunModelTests(unittest.TestCase):
    def test_valid_archive_preserves_provenance_and_is_frozen(
        self,
    ) -> None:
        metadata = (
            RunMetadataEntry("operator", "Nir"),
            RunMetadataEntry("temperature_c", 24.5),
        )
        archived_run = _archived_run(RUN_ID_1, metadata=metadata)

        self.assertEqual(archived_run.run_id, RUN_ID_1)
        self.assertEqual(archived_run.archived_at_utc, BASE_TIME)
        self.assertEqual(archived_run.analysis.statistics.mean_current, 2.0)
        self.assertEqual(archived_run.metadata, metadata)
        with self.assertRaises(FrozenInstanceError):
            archived_run.run_id = RUN_ID_2

    def test_archive_rejects_invalid_identity_time_and_analysis(
        self,
    ) -> None:
        valid = _archived_run(RUN_ID_1)
        invalid_changes = (
            {"run_id": "not-an-id"},
            {"archived_at_utc": BASE_TIME.replace(tzinfo=None)},
            {
                "archived_at_utc": BASE_TIME.astimezone(
                    timezone(timedelta(hours=2))
                )
            },
            {"analysis": object()},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    replace(valid, **changes)

    def test_archive_requires_sorted_unique_bounded_metadata(self) -> None:
        valid = _archived_run(RUN_ID_1)
        invalid_metadata = (
            [RunMetadataEntry("a", 1)],
            (
                RunMetadataEntry("b", 2),
                RunMetadataEntry("a", 1),
            ),
            (
                RunMetadataEntry("a", 1),
                RunMetadataEntry("a", 2),
            ),
            tuple(
                RunMetadataEntry(f"key-{index:02d}", index)
                for index in range(MAX_METADATA_ENTRIES + 1)
            ),
        )
        for metadata in invalid_metadata:
            with self.subTest(length=len(metadata)):
                with self.assertRaises(ValueError):
                    replace(valid, metadata=metadata)


class ArchivedRunQueryModelTests(unittest.TestCase):
    def test_valid_query_is_frozen(self) -> None:
        query = ArchivedRunQuery(
            ammeter_type="greenlee",
            status=MeasurementStatus.PARTIAL,
            archived_from_utc=BASE_TIME,
            archived_until_utc=BASE_TIME + timedelta(hours=1),
            metadata=(RunMetadataEntry("operator", "Nir"),),
            has_statistics=True,
            limit=25,
        )

        self.assertEqual(query.ammeter_type, "greenlee")
        self.assertEqual(query.limit, 25)
        with self.assertRaises(FrozenInstanceError):
            query.limit = 10

    def test_query_rejects_invalid_filters(self) -> None:
        valid = ArchivedRunQuery(
            ammeter_type=None,
            status=None,
            archived_from_utc=None,
            archived_until_utc=None,
            metadata=(),
            has_statistics=None,
            limit=None,
        )
        invalid_changes = (
            {"ammeter_type": ""},
            {"ammeter_type": " Greenlee "},
            {"ammeter_type": "GREENLEE"},
            {"status": "success"},
            {"archived_from_utc": BASE_TIME.replace(tzinfo=None)},
            {
                "archived_until_utc": BASE_TIME.astimezone(
                    timezone(timedelta(hours=2))
                )
            },
            {
                "archived_from_utc": BASE_TIME + timedelta(seconds=1),
                "archived_until_utc": BASE_TIME,
            },
            {"metadata": [RunMetadataEntry("a", 1)]},
            {
                "metadata": (
                    RunMetadataEntry("b", 2),
                    RunMetadataEntry("a", 1),
                )
            },
            {
                "metadata": (
                    RunMetadataEntry("a", 1),
                    RunMetadataEntry("a", 2),
                )
            },
            {"has_statistics": 1},
            {"limit": True},
            {"limit": 0},
            {"limit": MAX_ARCHIVE_QUERY_LIMIT + 1},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    replace(valid, **changes)


class HistoricalComparisonModelTests(unittest.TestCase):
    def test_statistics_delta_is_candidate_minus_baseline(self) -> None:
        baseline = CurrentStatistics(
            measurements_count=2,
            mean_current=2.0,
            median_current=2.0,
            standard_deviation_current=1.0,
            minimum_current=1.0,
            maximum_current=3.0,
            unit="A",
        )
        candidate = CurrentStatistics(
            measurements_count=3,
            mean_current=5.0,
            median_current=4.0,
            standard_deviation_current=2.0,
            minimum_current=2.0,
            maximum_current=8.0,
            unit="A",
        )

        delta = calculate_current_statistics_delta(
            baseline,
            candidate,
        )

        self.assertEqual(
            delta,
            CurrentStatisticsDelta(
                measurements_count_delta=1,
                mean_current_delta=3.0,
                median_current_delta=2.0,
                standard_deviation_current_delta=1.0,
                minimum_current_delta=1.0,
                maximum_current_delta=5.0,
                unit="A",
            ),
        )
        self.assertIsNone(
            calculate_current_statistics_delta(None, candidate)
        )
        self.assertIsNone(
            calculate_current_statistics_delta(baseline, None)
        )

    def test_statistics_delta_rejects_invalid_values_and_overflow(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            CurrentStatisticsDelta(
                measurements_count_delta=True,
                mean_current_delta=0.0,
                median_current_delta=0.0,
                standard_deviation_current_delta=0.0,
                minimum_current_delta=0.0,
                maximum_current_delta=0.0,
                unit="A",
            )
        with self.assertRaises(ValueError):
            CurrentStatisticsDelta(
                measurements_count_delta=0,
                mean_current_delta=math.inf,
                median_current_delta=0.0,
                standard_deviation_current_delta=0.0,
                minimum_current_delta=0.0,
                maximum_current_delta=0.0,
                unit="A",
            )

        high = CurrentStatistics(
            measurements_count=1,
            mean_current=1e308,
            median_current=1e308,
            standard_deviation_current=0.0,
            minimum_current=1e308,
            maximum_current=1e308,
            unit="A",
        )
        low = CurrentStatistics(
            measurements_count=1,
            mean_current=-1e308,
            median_current=-1e308,
            standard_deviation_current=0.0,
            minimum_current=-1e308,
            maximum_current=-1e308,
            unit="A",
        )
        with self.assertRaisesRegex(ValueError, "finite"):
            calculate_current_statistics_delta(high, low)

    def test_historical_comparison_derives_deltas_and_compatibility(
        self,
    ) -> None:
        baseline = _archived_run(RUN_ID_1, currents=(1.0, 3.0))
        same_plan = _archived_run(RUN_ID_2, currents=(3.0, 5.0))
        different = _archived_run(
            RUN_ID_3,
            ammeter_type="entes",
            currents=(10.0, 14.0),
            frequency_hz=4.0,
        )

        comparison = HistoricalComparison(
            baseline=baseline,
            candidates=(same_plan, different),
        )

        self.assertEqual(
            comparison.statistics_deltas[0].mean_current_delta,
            2.0,
        )
        self.assertEqual(
            comparison.statistics_deltas[1].mean_current_delta,
            10.0,
        )
        self.assertEqual(comparison.same_ammeter_types, (True, False))
        self.assertEqual(
            comparison.same_sampling_settings,
            (True, False),
        )
        with self.assertRaises(FrozenInstanceError):
            comparison.baseline = same_plan

    def test_historical_comparison_uses_none_for_unavailable_stats(
        self,
    ) -> None:
        baseline = _archived_run(
            RUN_ID_1,
            currents=(None, None),
        )
        candidate = _archived_run(RUN_ID_2, currents=(2.0, 4.0))

        comparison = HistoricalComparison(
            baseline=baseline,
            candidates=(candidate,),
        )

        self.assertIsNone(baseline.analysis.statistics)
        self.assertEqual(comparison.statistics_deltas, (None,))

    def test_historical_comparison_rejects_invalid_candidates_and_ids(
        self,
    ) -> None:
        baseline = _archived_run(RUN_ID_1)
        candidate = _archived_run(RUN_ID_2)
        invalid_candidates = (
            (),
            [candidate],
            (object(),),
            (baseline,),
            (candidate, candidate),
        )
        for candidates in invalid_candidates:
            with self.subTest(candidates=candidates):
                with self.assertRaises(ValueError):
                    HistoricalComparison(
                        baseline=baseline,
                        candidates=candidates,
                    )


if __name__ == "__main__":
    unittest.main()
