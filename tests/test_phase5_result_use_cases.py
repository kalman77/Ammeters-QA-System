import unittest
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from src.application.errors.invalid_archive_query_error import (
    InvalidArchiveQueryError,
)
from src.application.errors.invalid_historical_comparison_error import (
    InvalidHistoricalComparisonError,
)
from src.application.errors.invalid_run_id_error import InvalidRunIdError
from src.application.errors.invalid_run_metadata_error import (
    InvalidRunMetadataError,
)
from src.application.errors.result_storage_error import ResultStorageError
from src.application.use_cases.archive_sampling_analyses import (
    archive_sampling_analyses,
)
from src.application.use_cases.archive_sampling_analysis import (
    archive_sampling_analysis,
)
from src.application.use_cases.compare_archived_test_runs import (
    compare_archived_test_runs,
)
from src.application.use_cases.find_archived_test_runs import (
    find_archived_test_runs,
)
from src.application.use_cases.resolve_archived_run_query import (
    resolve_archived_run_query,
)
from src.application.use_cases.resolve_run_metadata import (
    resolve_run_metadata,
)
from src.application.use_cases.retrieve_archived_test_run import (
    retrieve_archived_test_run,
)
from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.archived_run_query import ArchivedRunQuery
from src.domain.models.archived_test_run import ArchivedTestRun
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.run_metadata_entry import (
    MAX_METADATA_KEY_LENGTH,
    RunMetadataEntry,
)
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_analysis import SamplingAnalysis
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import SamplingSettings


BASE_TIME = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
RUN_ID_1 = "00000000-0000-4000-8000-000000000001"
RUN_ID_2 = "00000000-0000-4000-8000-000000000002"
RUN_ID_3 = "00000000-0000-4000-8000-000000000003"
RUN_ID_4 = "00000000-0000-4000-8000-000000000004"
RUN_ID_5 = "00000000-0000-4000-8000-000000000005"


def _analysis(
    *,
    ammeter_type: str = "greenlee",
    currents: Tuple[Optional[float], ...] = (1.0, 3.0),
    frequency_hz: float = 2.0,
) -> SamplingAnalysis:
    settings = SamplingSettings(
        measurements_count=len(currents),
        total_duration_seconds=len(currents) / frequency_hz,
        sampling_frequency_hz=frequency_hz,
    )
    samples = []
    for index, current in enumerate(currents):
        scheduled = index / frequency_hz
        timestamp = BASE_TIME + timedelta(seconds=scheduled)
        if current is None:
            measurement = MeasurementResult(
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
            measurement = MeasurementResult(
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
                result=measurement,
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
        SamplingResult(
            ammeter_type=ammeter_type,
            status=status,
            timestamp_utc=BASE_TIME,
            elapsed_seconds=sampling_elapsed,
            sampling_started_at_utc=BASE_TIME,
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


class ResolveResultManagementInputsTests(unittest.TestCase):
    def test_resolve_metadata_copies_sorts_and_validates_scalars(
        self,
    ) -> None:
        metadata = OrderedDict(
            (
                ("temperature_c", 24.5),
                ("operator", "Nir"),
                ("approved", True),
                ("comment", None),
            )
        )

        resolved = resolve_run_metadata(metadata)
        metadata["operator"] = "changed"

        self.assertEqual(
            tuple(entry.key for entry in resolved),
            ("approved", "comment", "operator", "temperature_c"),
        )
        self.assertEqual(
            dict((entry.key, entry.value) for entry in resolved),
            {
                "approved": True,
                "comment": None,
                "operator": "Nir",
                "temperature_c": 24.5,
            },
        )
        self.assertEqual(resolve_run_metadata(None), ())

    def test_resolve_metadata_wraps_invalid_public_input(self) -> None:
        invalid_metadata = (
            [],
            {"": "value"},
            {"x" * (MAX_METADATA_KEY_LENGTH + 1): "value"},
            {"value": float("nan")},
            {"value": []},
        )
        for metadata in invalid_metadata:
            with self.subTest(metadata=metadata):
                with self.assertRaises(InvalidRunMetadataError):
                    resolve_run_metadata(metadata)

    def test_resolve_query_normalizes_all_public_filters(self) -> None:
        query = resolve_archived_run_query(
            ammeter_type=" GreenLee ",
            status=" PARTIAL ",
            archived_from_utc=BASE_TIME,
            archived_until_utc=BASE_TIME + timedelta(hours=1),
            metadata={"z": 2, "a": 1},
            has_statistics=False,
            limit=7,
        )

        self.assertIsInstance(query, ArchivedRunQuery)
        self.assertEqual(query.ammeter_type, "greenlee")
        self.assertIs(query.status, MeasurementStatus.PARTIAL)
        self.assertEqual(
            tuple(entry.key for entry in query.metadata),
            ("a", "z"),
        )
        self.assertFalse(query.has_statistics)
        self.assertEqual(query.limit, 7)

    def test_resolve_query_wraps_invalid_filters(self) -> None:
        invalid_arguments = (
            {"ammeter_type": ""},
            {"ammeter_type": 1},
            {"status": "unknown"},
            {"status": object()},
            {"archived_from_utc": BASE_TIME.replace(tzinfo=None)},
            {
                "archived_from_utc": BASE_TIME + timedelta(seconds=1),
                "archived_until_utc": BASE_TIME,
            },
            {"metadata": {"bad": []}},
            {"has_statistics": 1},
            {"limit": True},
            {"limit": 0},
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(InvalidArchiveQueryError):
                    resolve_archived_run_query(**arguments)


class ArchiveSamplingAnalysisUseCaseTests(unittest.TestCase):
    def test_archive_analysis_builds_and_saves_one_typed_record(
        self,
    ) -> None:
        analysis = _analysis()
        saved = []

        archived_run = archive_sampling_analysis(
            analysis,
            {"operator": "Nir", "approved": True},
            save_archived_run=saved.append,
            generate_run_id=lambda: RUN_ID_1,
            utc_clock=lambda: BASE_TIME,
        )

        self.assertEqual(saved, [archived_run])
        self.assertIs(archived_run.analysis, analysis)
        self.assertEqual(archived_run.run_id, RUN_ID_1)
        self.assertEqual(archived_run.archived_at_utc, BASE_TIME)
        self.assertEqual(
            tuple(entry.key for entry in archived_run.metadata),
            ("approved", "operator"),
        )

    def test_archive_analysis_rejects_bad_id_or_clock_before_save(
        self,
    ) -> None:
        analysis = _analysis()
        saved = []

        with self.assertRaises(InvalidRunIdError):
            archive_sampling_analysis(
                analysis,
                None,
                save_archived_run=saved.append,
                generate_run_id=lambda: "../unsafe",
                utc_clock=lambda: BASE_TIME,
            )
        with self.assertRaises(ResultStorageError):
            archive_sampling_analysis(
                analysis,
                None,
                save_archived_run=saved.append,
                generate_run_id=lambda: RUN_ID_1,
                utc_clock=lambda: BASE_TIME.replace(tzinfo=None),
            )

        self.assertEqual(saved, [])

    def test_archive_analysis_does_not_wrap_saver_failures(self) -> None:
        class SaveFailure(Exception):
            pass

        def fail_save(archived_run):
            raise SaveFailure("save failed")

        with self.assertRaisesRegex(SaveFailure, "save failed"):
            archive_sampling_analysis(
                _analysis(),
                None,
                save_archived_run=fail_save,
                generate_run_id=lambda: RUN_ID_1,
                utc_clock=lambda: BASE_TIME,
            )

    def test_archive_all_preserves_order_and_includes_no_stat_runs(
        self,
    ) -> None:
        analyses = OrderedDict(
            (
                ("greenlee", _analysis(ammeter_type="greenlee")),
                (
                    "entes",
                    _analysis(
                        ammeter_type="entes",
                        currents=(None, None),
                    ),
                ),
                ("circutor", _analysis(ammeter_type="circutor")),
            )
        )
        run_ids = iter((RUN_ID_1, RUN_ID_2, RUN_ID_3))
        archived_times = iter(
            (
                BASE_TIME,
                BASE_TIME + timedelta(seconds=1),
                BASE_TIME + timedelta(seconds=2),
            )
        )
        saved = []

        archived = archive_sampling_analyses(
            analyses,
            {"batch": "nightly"},
            save_archived_run=saved.append,
            generate_run_id=lambda: next(run_ids),
            utc_clock=lambda: next(archived_times),
        )

        self.assertEqual(
            list(archived),
            ["greenlee", "entes", "circutor"],
        )
        self.assertEqual(
            [run.run_id for run in saved],
            [RUN_ID_1, RUN_ID_2, RUN_ID_3],
        )
        self.assertIsNone(archived["entes"].analysis.statistics)
        self.assertEqual(
            tuple(entry.key for entry in archived["entes"].metadata),
            ("batch",),
        )

    def test_archive_all_rejects_invalid_mapping_contract(self) -> None:
        with self.assertRaises(ValueError):
            archive_sampling_analyses(
                [],
                None,
                save_archived_run=lambda run: None,
                generate_run_id=lambda: RUN_ID_1,
                utc_clock=lambda: BASE_TIME,
            )
        with self.assertRaises(ValueError):
            archive_sampling_analyses(
                {"entes": _analysis(ammeter_type="greenlee")},
                None,
                save_archived_run=lambda run: None,
                generate_run_id=lambda: RUN_ID_1,
                utc_clock=lambda: BASE_TIME,
            )


class RetrieveAndFindArchivedRunsUseCaseTests(unittest.TestCase):
    def test_retrieve_validates_id_and_loader_result(self) -> None:
        expected = _archived_run(RUN_ID_1)
        observed_ids = []

        result = retrieve_archived_test_run(
            RUN_ID_1,
            load_archived_run=lambda run_id: (
                observed_ids.append(run_id) or expected
            ),
        )

        self.assertIs(result, expected)
        self.assertEqual(observed_ids, [RUN_ID_1])

        loader_called = []
        with self.assertRaises(InvalidRunIdError):
            retrieve_archived_test_run(
                "../unsafe",
                load_archived_run=lambda run_id: loader_called.append(
                    run_id
                ),
            )
        self.assertEqual(loader_called, [])

    def test_retrieve_rejects_wrong_loader_contract(self) -> None:
        mismatched = _archived_run(RUN_ID_2)
        for loaded in (object(), mismatched):
            with self.subTest(loaded=loaded):
                with self.assertRaises(ResultStorageError):
                    retrieve_archived_test_run(
                        RUN_ID_1,
                        load_archived_run=lambda run_id, value=loaded: value,
                    )

    def test_find_orders_newest_first_then_run_id(self) -> None:
        older = _archived_run(
            RUN_ID_3,
            archived_at_utc=BASE_TIME,
        )
        tie_high = _archived_run(
            RUN_ID_2,
            archived_at_utc=BASE_TIME + timedelta(hours=1),
        )
        tie_low = _archived_run(
            RUN_ID_1,
            archived_at_utc=BASE_TIME + timedelta(hours=1),
        )
        query = resolve_archived_run_query()

        found = find_archived_test_runs(
            query,
            list_archived_runs=lambda: (older, tie_high, tie_low),
        )

        self.assertEqual(
            tuple(run.run_id for run in found),
            (RUN_ID_1, RUN_ID_2, RUN_ID_3),
        )

    def test_find_combines_filters_and_applies_limit_after_order(
        self,
    ) -> None:
        matching_newest = _archived_run(
            RUN_ID_1,
            archived_at_utc=BASE_TIME + timedelta(minutes=50),
            metadata=(
                RunMetadataEntry("batch", "nightly"),
                RunMetadataEntry("operator", "Nir"),
            ),
        )
        matching_older = _archived_run(
            RUN_ID_2,
            archived_at_utc=BASE_TIME + timedelta(minutes=10),
            metadata=(
                RunMetadataEntry("batch", "nightly"),
                RunMetadataEntry("operator", "Nir"),
            ),
        )
        wrong_meter = _archived_run(
            RUN_ID_3,
            archived_at_utc=BASE_TIME + timedelta(minutes=55),
            ammeter_type="entes",
            metadata=(RunMetadataEntry("batch", "nightly"),),
        )
        no_statistics = _archived_run(
            RUN_ID_4,
            archived_at_utc=BASE_TIME + timedelta(minutes=45),
            currents=(None, None),
            metadata=(RunMetadataEntry("batch", "nightly"),),
        )
        wrong_metadata = _archived_run(
            RUN_ID_5,
            archived_at_utc=BASE_TIME + timedelta(minutes=40),
            metadata=(RunMetadataEntry("batch", "manual"),),
        )
        query = resolve_archived_run_query(
            ammeter_type="GREENLEE",
            status=MeasurementStatus.SUCCESS,
            archived_from_utc=BASE_TIME + timedelta(minutes=10),
            archived_until_utc=BASE_TIME + timedelta(minutes=55),
            metadata={"batch": "nightly"},
            has_statistics=True,
            limit=1,
        )

        found = find_archived_test_runs(
            query,
            list_archived_runs=lambda: (
                matching_older,
                wrong_meter,
                no_statistics,
                wrong_metadata,
                matching_newest,
            ),
        )

        self.assertEqual(found, (matching_newest,))

    def test_find_uses_inclusive_start_and_exclusive_until(self) -> None:
        at_start = _archived_run(
            RUN_ID_1,
            archived_at_utc=BASE_TIME,
        )
        inside = _archived_run(
            RUN_ID_2,
            archived_at_utc=BASE_TIME + timedelta(seconds=1),
        )
        at_until = _archived_run(
            RUN_ID_3,
            archived_at_utc=BASE_TIME + timedelta(seconds=2),
        )
        query = resolve_archived_run_query(
            archived_from_utc=BASE_TIME,
            archived_until_utc=BASE_TIME + timedelta(seconds=2),
        )

        found = find_archived_test_runs(
            query,
            list_archived_runs=lambda: (at_until, inside, at_start),
        )

        self.assertEqual(found, (inside, at_start))

    def test_find_rejects_invalid_lister_contract(self) -> None:
        query = resolve_archived_run_query()
        invalid_results = ([], (object(),))
        for result in invalid_results:
            with self.subTest(result=result):
                with self.assertRaises(ResultStorageError):
                    find_archived_test_runs(
                        query,
                        list_archived_runs=lambda value=result: value,
                    )


class CompareArchivedRunsUseCaseTests(unittest.TestCase):
    def test_compare_uses_candidate_minus_baseline_direction(self) -> None:
        baseline = _archived_run(
            RUN_ID_1,
            currents=(1.0, 3.0),
        )
        candidate = _archived_run(
            RUN_ID_2,
            currents=(4.0, 6.0),
        )

        comparison = compare_archived_test_runs(
            baseline,
            (candidate,),
        )

        delta = comparison.statistics_deltas[0]
        self.assertEqual(delta.mean_current_delta, 3.0)
        self.assertEqual(delta.median_current_delta, 3.0)
        self.assertEqual(delta.minimum_current_delta, 3.0)
        self.assertEqual(delta.maximum_current_delta, 3.0)

    def test_compare_supports_cross_meter_and_no_stat_analyses(
        self,
    ) -> None:
        baseline = _archived_run(
            RUN_ID_1,
            currents=(None, None),
        )
        candidate = _archived_run(
            RUN_ID_2,
            ammeter_type="entes",
            currents=(4.0, 6.0),
            frequency_hz=4.0,
        )

        comparison = compare_archived_test_runs(
            baseline,
            (candidate,),
        )

        self.assertEqual(comparison.statistics_deltas, (None,))
        self.assertEqual(comparison.same_ammeter_types, (False,))
        self.assertEqual(comparison.same_sampling_settings, (False,))

    def test_compare_wraps_invalid_model_inputs(self) -> None:
        baseline = _archived_run(RUN_ID_1)
        invalid_candidates = ((), [baseline], (baseline,))
        for candidates in invalid_candidates:
            with self.subTest(candidates=candidates):
                with self.assertRaises(
                    InvalidHistoricalComparisonError
                ):
                    compare_archived_test_runs(
                        baseline,
                        candidates,
                    )


if __name__ == "__main__":
    unittest.main()
