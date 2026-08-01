"""Tests for bounded per-slot retries and their archive compatibility."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from src.application.errors.invalid_measurement_error import (
    InvalidMeasurementError,
)
from src.application.errors.measurement_request_error import (
    MeasurementRequestError,
)
from src.application.errors.sampling_configuration_error import (
    SamplingConfigurationError,
)
from src.application.use_cases.collect_scheduled_sample import (
    collect_scheduled_sample,
)
from src.application.use_cases.measure_with_retries import (
    measure_with_retries,
)
from src.application.use_cases.resolve_retry_policy import (
    resolve_retry_policy,
)
from src.application.use_cases.run_ammeter_sampling_test import (
    run_ammeter_sampling_test,
)
from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.ammeter_settings import AmmeterSettings
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.network_settings import NetworkSettings
from src.domain.models.retry_policy import (
    MAX_ATTEMPTS_PER_SLOT,
    RetryPolicy,
)
from src.domain.models.runtime_settings import RuntimeSettings
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_analysis import SamplingAnalysis
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import SamplingSettings
from src.infrastructure.config.read_retry_policy import read_retry_policy
from src.infrastructure.persistence.archive_schema_version import (
    ARCHIVE_SCHEMA_VERSION,
)
from src.infrastructure.persistence.archived_test_run_from_dict import (
    archived_test_run_from_dict,
)
from src.infrastructure.persistence.archived_test_run_to_archive_dict import (
    archived_test_run_to_archive_dict,
)
from src.infrastructure.persistence.load_archived_test_run import (
    load_archived_test_run,
)
from src.presentation.serialization.sampling_result_to_dict import (
    sampling_result_to_dict,
)
from tests.result_archive_fixtures import RUN_ID, build_archived_test_run


NETWORK = NetworkSettings(
    host="127.0.0.1",
    connect_timeout_seconds=1.0,
    read_timeout_seconds=2.0,
    startup_timeout_seconds=3.0,
    shutdown_timeout_seconds=4.0,
)


class FakeTimeline:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now
        self.sleeps = []
        self.utc_origin = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise AssertionError("the scheduler must not sleep negatively")
        self.sleeps.append(seconds)
        self.now += seconds

    def utc(self) -> datetime:
        return self.utc_origin + timedelta(seconds=self.now)

    def advance(self, seconds: float) -> None:
        self.now += seconds


def running_emulator(name: str = "greenlee") -> SimpleNamespace:
    return SimpleNamespace(
        settings=AmmeterSettings(name=name, port=0, command=b"COMMAND"),
        emulator=SimpleNamespace(port=43210),
    )


def runtime_settings() -> RuntimeSettings:
    return RuntimeSettings(
        network=NETWORK,
        ammeters=(
            AmmeterSettings(
                name="greenlee",
                port=0,
                command=b"GREENLEE_COMMAND",
            ),
        ),
    )


class RetryPolicyModelTests(unittest.TestCase):
    def test_default_policy_permits_exactly_one_attempt(self) -> None:
        policy = RetryPolicy()
        self.assertEqual(policy.max_attempts, 1)
        self.assertEqual(policy.retry_delay_seconds, 0.0)
        self.assertFalse(policy.retries_enabled)

    def test_bounds_are_enforced(self) -> None:
        for attempts in (0, -1, True, 1.5, MAX_ATTEMPTS_PER_SLOT + 1):
            with self.subTest(max_attempts=attempts):
                with self.assertRaises(ValueError):
                    RetryPolicy(max_attempts=attempts)
        for delay in (-0.1, float("nan"), float("inf"), 61.0, True):
            with self.subTest(delay=delay):
                with self.assertRaises(ValueError):
                    RetryPolicy(max_attempts=2, retry_delay_seconds=delay)

    def test_retries_enabled_reflects_the_attempt_budget(self) -> None:
        self.assertTrue(RetryPolicy(max_attempts=2).retries_enabled)


class ResolveRetryPolicyTests(unittest.TestCase):
    def test_absent_values_resolve_to_no_retries(self) -> None:
        self.assertEqual(resolve_retry_policy(None, None), RetryPolicy())

    def test_invalid_values_raise_configuration_errors(self) -> None:
        with self.assertRaises(SamplingConfigurationError):
            resolve_retry_policy(0, None)
        with self.assertRaises(SamplingConfigurationError):
            resolve_retry_policy(2, -1.0)

    def test_a_delay_without_retries_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            SamplingConfigurationError,
            "max_attempts greater than 1",
        ):
            resolve_retry_policy(1, 0.5)

    def test_configuration_without_retry_keeps_the_default(self) -> None:
        self.assertEqual(read_retry_policy({}), RetryPolicy())
        self.assertEqual(
            read_retry_policy({"testing": {}}),
            RetryPolicy(),
        )
        self.assertEqual(
            read_retry_policy({"testing": {"retry": None}}),
            RetryPolicy(),
        )

    def test_configured_retry_is_resolved(self) -> None:
        policy = read_retry_policy(
            {
                "testing": {
                    "retry": {
                        "max_attempts": 3,
                        "retry_delay_seconds": 0.01,
                    }
                }
            }
        )
        self.assertEqual(policy, RetryPolicy(3, 0.01))

    def test_malformed_retry_section_is_rejected(self) -> None:
        with self.assertRaises(SamplingConfigurationError):
            read_retry_policy({"testing": {"retry": []}})


class MeasureWithRetriesTests(unittest.TestCase):
    def _measure(self, responses, policy, *, slot_end=10.0, now=0.0):
        timeline = FakeTimeline(now=now)
        calls = []

        def request_current(port, command, **network):
            calls.append(timeline.now)
            timeline.advance(0.01)
            outcome = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        measurement, failure, attempts = measure_with_retries(
            running_emulator(),
            NETWORK,
            slot_end,
            policy,
            request_current=request_current,
            monotonic_clock=timeline.monotonic,
            utc_clock=timeline.utc,
            sleeper=timeline.sleep,
        )
        return measurement, failure, attempts, timeline, calls

    def test_a_first_attempt_success_issues_one_request(self) -> None:
        measurement, failure, attempts, _timeline, calls = self._measure(
            [1.5],
            RetryPolicy(max_attempts=3, retry_delay_seconds=0.01),
        )
        self.assertEqual(attempts, 1)
        self.assertIsNone(failure)
        self.assertEqual(measurement.current, 1.5)
        self.assertEqual(len(calls), 1)

    def test_a_recovered_request_reports_no_failure(self) -> None:
        measurement, failure, attempts, timeline, _calls = self._measure(
            [MeasurementRequestError("refused"), 2.5],
            RetryPolicy(max_attempts=3, retry_delay_seconds=0.02),
        )
        self.assertEqual(attempts, 2)
        self.assertIsNone(failure)
        self.assertEqual(measurement.current, 2.5)
        self.assertEqual(len(timeline.sleeps), 1)
        self.assertAlmostEqual(timeline.sleeps[0], 0.02)

    def test_exhausted_attempts_report_the_last_failure(self) -> None:
        _measurement, failure, attempts, _timeline, calls = self._measure(
            [MeasurementRequestError("refused")],
            RetryPolicy(max_attempts=3, retry_delay_seconds=0.0),
        )
        self.assertEqual(attempts, 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(
            failure.code,
            MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
        )

    def test_invalid_readings_keep_their_own_error_code(self) -> None:
        _measurement, failure, attempts, _timeline, _calls = self._measure(
            [InvalidMeasurementError("not finite")],
            RetryPolicy(max_attempts=2, retry_delay_seconds=0.0),
        )
        self.assertEqual(attempts, 2)
        self.assertEqual(
            failure.code,
            MeasurementErrorCode.INVALID_MEASUREMENT,
        )

    def test_a_backoff_that_would_overrun_the_slot_stops_retrying(
        self,
    ) -> None:
        _measurement, failure, attempts, timeline, calls = self._measure(
            [MeasurementRequestError("refused")],
            RetryPolicy(max_attempts=5, retry_delay_seconds=1.0),
            slot_end=0.5,
        )
        self.assertEqual(attempts, 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(timeline.sleeps, [])
        self.assertIsNotNone(failure)
        self.assertLess(timeline.now, 0.5)

    def test_retrying_stops_once_the_slot_has_expired(self) -> None:
        _measurement, _failure, attempts, timeline, _calls = self._measure(
            [MeasurementRequestError("refused")],
            RetryPolicy(max_attempts=5, retry_delay_seconds=0.05),
            slot_end=0.2,
        )
        self.assertLess(attempts, 5)
        self.assertLessEqual(timeline.now, 0.2 + 0.01)


class CollectScheduledSampleRetryTests(unittest.TestCase):
    def _collect(self, responses, policy, *, frequency=2.0, index=0):
        timeline = FakeTimeline(now=0.0)
        calls = []
        settings = SamplingSettings(
            measurements_count=4,
            total_duration_seconds=4.0 / frequency,
            sampling_frequency_hz=frequency,
        )

        def request_current(port, command, **network):
            calls.append(timeline.now)
            timeline.advance(0.01)
            outcome = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        sample = collect_scheduled_sample(
            running_emulator(),
            NETWORK,
            settings,
            index,
            0.0,
            request_current=request_current,
            monotonic_clock=timeline.monotonic,
            utc_clock=timeline.utc,
            sleeper=timeline.sleep,
            retry_policy=policy,
        )
        return sample, timeline, calls

    def test_a_recovered_slot_is_successful_and_records_its_attempts(
        self,
    ) -> None:
        sample, _timeline, calls = self._collect(
            [MeasurementRequestError("refused"), 3.5],
            RetryPolicy(max_attempts=3, retry_delay_seconds=0.01),
        )
        self.assertIs(sample.result.status, MeasurementStatus.SUCCESS)
        self.assertEqual(sample.result.errors, ())
        self.assertEqual(sample.request_attempts, 2)
        self.assertEqual(sample.result.current, 3.5)
        self.assertEqual(len(calls), 2)

    def test_an_unrecovered_slot_fails_with_its_attempt_count(self) -> None:
        sample, _timeline, _calls = self._collect(
            [MeasurementRequestError("refused")],
            RetryPolicy(max_attempts=2, retry_delay_seconds=0.0),
        )
        self.assertIs(sample.result.status, MeasurementStatus.FAILED)
        self.assertEqual(sample.request_attempts, 2)
        self.assertEqual(len(sample.result.errors), 1)

    def test_retries_never_run_past_the_slot_window(self) -> None:
        frequency = 2.0
        sample, timeline, _calls = self._collect(
            [MeasurementRequestError("refused")],
            RetryPolicy(max_attempts=8, retry_delay_seconds=0.1),
            frequency=frequency,
        )
        slot_end = 1.0 / frequency
        self.assertLessEqual(sample.completed_elapsed_seconds, slot_end)
        self.assertLessEqual(timeline.now, slot_end)

    def test_the_default_policy_still_issues_one_request(self) -> None:
        sample, _timeline, calls = self._collect(
            [MeasurementRequestError("refused")],
            RetryPolicy(),
        )
        self.assertEqual(sample.request_attempts, 1)
        self.assertEqual(len(calls), 1)


class SamplingRunRetryTests(unittest.TestCase):
    def test_every_slot_recovers_and_the_run_reports_success(self) -> None:
        timeline = FakeTimeline(now=50.0)
        settings = SamplingSettings(
            measurements_count=3,
            total_duration_seconds=1.5,
            sampling_frequency_hz=2.0,
        )
        attempts_per_slot = []

        def start_emulators(selected_runtime, stop_event):
            timeline.advance(0.05)
            return [
                SimpleNamespace(
                    settings=selected_runtime.ammeters[0],
                    emulator=SimpleNamespace(port=43210),
                )
            ]

        def stop_emulators(running, stop_event, timeout_seconds):
            timeline.advance(0.01)

        state = {"calls": 0}

        def request_current(port, command, **network):
            state["calls"] += 1
            timeline.advance(0.01)
            # Every odd request fails, so each slot needs exactly two.
            if state["calls"] % 2 == 1:
                raise MeasurementRequestError("transient refusal")
            return 4.0

        result = run_ammeter_sampling_test(
            runtime_settings(),
            settings,
            "greenlee",
            start_emulators=start_emulators,
            stop_emulators=stop_emulators,
            request_current=request_current,
            monotonic_clock=timeline.monotonic,
            utc_clock=timeline.utc,
            sleeper=timeline.sleep,
            retry_policy=RetryPolicy(max_attempts=2, retry_delay_seconds=0.0),
        )

        attempts_per_slot = [
            sample.request_attempts for sample in result.samples
        ]
        self.assertIs(result.status, MeasurementStatus.SUCCESS)
        self.assertEqual(attempts_per_slot, [2, 2, 2])
        self.assertEqual(result.errors, ())
        self.assertEqual(
            result.retry_policy,
            RetryPolicy(max_attempts=2, retry_delay_seconds=0.0),
        )

    def test_the_run_records_the_policy_it_executed_under(self) -> None:
        timeline = FakeTimeline(now=0.0)
        settings = SamplingSettings(
            measurements_count=1,
            total_duration_seconds=0.5,
            sampling_frequency_hz=2.0,
        )

        def start_emulators(selected_runtime, stop_event):
            return [
                SimpleNamespace(
                    settings=selected_runtime.ammeters[0],
                    emulator=SimpleNamespace(port=1),
                )
            ]

        result = run_ammeter_sampling_test(
            runtime_settings(),
            settings,
            "greenlee",
            start_emulators=start_emulators,
            stop_emulators=lambda *args: None,
            request_current=lambda *args, **kwargs: 1.0,
            monotonic_clock=timeline.monotonic,
            utc_clock=timeline.utc,
            sleeper=timeline.sleep,
            retry_policy=RetryPolicy(max_attempts=4, retry_delay_seconds=0.2),
        )
        self.assertEqual(result.retry_policy.max_attempts, 4)
        serialized = sampling_result_to_dict(result)
        self.assertEqual(
            serialized["retry"],
            {"max_attempts": 4, "retry_delay_seconds": 0.2},
        )
        self.assertEqual(serialized["summary"]["retried_samples"], 0)
        self.assertEqual(serialized["samples"][0]["request_attempts"], 1)


class SampleResultAttemptTests(unittest.TestCase):
    def _measurement(self, *, missed: bool) -> MeasurementResult:
        if missed:
            return MeasurementResult(
                ammeter_type="greenlee",
                status=MeasurementStatus.FAILED,
                timestamp_utc=datetime(2026, 8, 1, tzinfo=timezone.utc),
                elapsed_seconds=0.0,
                current=None,
                unit="A",
                request_latency_seconds=None,
                errors=(
                    MeasurementError(
                        code=MeasurementErrorCode.SAMPLING_SLOT_MISSED,
                        message="missed",
                    ),
                ),
            )
        return MeasurementResult(
            ammeter_type="greenlee",
            status=MeasurementStatus.SUCCESS,
            timestamp_utc=datetime(2026, 8, 1, tzinfo=timezone.utc),
            elapsed_seconds=0.01,
            current=1.0,
            unit="A",
            request_latency_seconds=0.005,
            errors=(),
        )

    def test_a_started_slot_defaults_to_one_attempt(self) -> None:
        sample = SampleResult(
            sample_index=0,
            scheduled_elapsed_seconds=0.0,
            started_elapsed_seconds=0.0,
            completed_elapsed_seconds=0.01,
            result=self._measurement(missed=False),
        )
        self.assertEqual(sample.request_attempts, 1)

    def test_a_missed_slot_defaults_to_no_attempts(self) -> None:
        sample = SampleResult(
            sample_index=0,
            scheduled_elapsed_seconds=0.0,
            started_elapsed_seconds=None,
            completed_elapsed_seconds=0.5,
            result=self._measurement(missed=True),
        )
        self.assertEqual(sample.request_attempts, 0)

    def test_contradictory_attempt_counts_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SampleResult(
                sample_index=0,
                scheduled_elapsed_seconds=0.0,
                started_elapsed_seconds=None,
                completed_elapsed_seconds=0.5,
                request_attempts=1,
                result=self._measurement(missed=True),
            )
        with self.assertRaises(ValueError):
            SampleResult(
                sample_index=0,
                scheduled_elapsed_seconds=0.0,
                started_elapsed_seconds=0.0,
                completed_elapsed_seconds=0.01,
                request_attempts=0,
                result=self._measurement(missed=False),
            )
        with self.assertRaises(ValueError):
            SampleResult(
                sample_index=0,
                scheduled_elapsed_seconds=0.0,
                started_elapsed_seconds=0.0,
                completed_elapsed_seconds=0.01,
                request_attempts=MAX_ATTEMPTS_PER_SLOT + 1,
                result=self._measurement(missed=False),
            )

    def test_a_run_rejects_samples_beyond_its_retry_policy(self) -> None:
        sample = SampleResult(
            sample_index=0,
            scheduled_elapsed_seconds=0.0,
            started_elapsed_seconds=0.0,
            completed_elapsed_seconds=0.01,
            request_attempts=3,
            result=self._measurement(missed=False),
        )
        with self.assertRaisesRegex(
            ValueError,
            "attempts cannot exceed the retry policy",
        ):
            SamplingResult(
                ammeter_type="greenlee",
                status=MeasurementStatus.SUCCESS,
                timestamp_utc=datetime(2026, 8, 1, tzinfo=timezone.utc),
                elapsed_seconds=1.0,
                sampling_started_at_utc=datetime(
                    2026,
                    8,
                    1,
                    tzinfo=timezone.utc,
                ),
                sampling_elapsed_seconds=0.5,
                settings=SamplingSettings(
                    measurements_count=1,
                    total_duration_seconds=0.5,
                    sampling_frequency_hz=2.0,
                ),
                samples=(sample,),
                errors=(),
                unit="A",
                retry_policy=RetryPolicy(max_attempts=2),
            )


class ArchiveSchemaCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.archive_directory = Path(self._temporary_directory.name)

    def _write(self, document: dict) -> None:
        (self.archive_directory / f"{RUN_ID}.json").write_text(
            json.dumps(document),
            encoding="utf-8",
        )

    def test_the_current_schema_records_retries(self) -> None:
        document = archived_test_run_to_archive_dict(
            build_archived_test_run()
        )
        self.assertEqual(document["schema_version"], ARCHIVE_SCHEMA_VERSION)
        sampling = document["analysis"]["sampling_result"]
        self.assertEqual(
            sampling["retry"],
            {"max_attempts": 1, "retry_delay_seconds": 0.0},
        )
        self.assertIn("request_attempts", sampling["samples"][0])

    def test_version_one_documents_still_load(self) -> None:
        document = archived_test_run_to_archive_dict(
            build_archived_test_run(),
            1,
        )
        self.assertEqual(document["schema_version"], 1)
        sampling = document["analysis"]["sampling_result"]
        self.assertNotIn("retry", sampling)
        self.assertNotIn("request_attempts", sampling["samples"][0])

        self._write(document)
        loaded = load_archived_test_run(self.archive_directory, RUN_ID)
        self.assertEqual(loaded.analysis.sampling_result.retry_policy, RetryPolicy())
        for sample in loaded.analysis.sampling_result.samples:
            expected = 0 if sample.started_elapsed_seconds is None else 1
            self.assertEqual(sample.request_attempts, expected)

    def test_a_version_two_document_round_trips_with_retries(self) -> None:
        archived_run = build_archived_test_run()
        document = archived_test_run_to_archive_dict(archived_run)
        self._write(document)
        loaded = load_archived_test_run(self.archive_directory, RUN_ID)
        self.assertEqual(loaded, archived_run)

    def test_retry_fields_in_a_version_one_document_are_corruption(
        self,
    ) -> None:
        document = archived_test_run_to_archive_dict(
            build_archived_test_run(),
            1,
        )
        document["analysis"]["sampling_result"]["retry"] = {
            "max_attempts": 2,
            "retry_delay_seconds": 0.0,
        }
        with self.assertRaises(ValueError):
            archived_test_run_from_dict(document)

    def test_an_unknown_schema_version_is_rejected(self) -> None:
        document = archived_test_run_to_archive_dict(
            build_archived_test_run()
        )
        document["schema_version"] = 99
        with self.assertRaises(Exception) as captured:
            archived_test_run_from_dict(document)
        self.assertIn("Unsupported archive schema", str(captured.exception))

    def test_a_retried_run_survives_an_archive_round_trip(self) -> None:
        archived_run = build_archived_test_run()
        sampling = archived_run.analysis.sampling_result
        retried_samples = tuple(
            SampleResult(
                sample_index=sample.sample_index,
                scheduled_elapsed_seconds=sample.scheduled_elapsed_seconds,
                started_elapsed_seconds=sample.started_elapsed_seconds,
                completed_elapsed_seconds=sample.completed_elapsed_seconds,
                request_attempts=(
                    0 if sample.started_elapsed_seconds is None else 2
                ),
                result=sample.result,
            )
            for sample in sampling.samples
        )
        retried_run = SamplingResult(
            ammeter_type=sampling.ammeter_type,
            status=sampling.status,
            timestamp_utc=sampling.timestamp_utc,
            elapsed_seconds=sampling.elapsed_seconds,
            sampling_started_at_utc=sampling.sampling_started_at_utc,
            sampling_elapsed_seconds=sampling.sampling_elapsed_seconds,
            settings=sampling.settings,
            samples=retried_samples,
            errors=sampling.errors,
            unit=sampling.unit,
            retry_policy=RetryPolicy(max_attempts=3, retry_delay_seconds=0.02),
        )
        archived = type(archived_run)(
            run_id=archived_run.run_id,
            archived_at_utc=archived_run.archived_at_utc,
            analysis=SamplingAnalysis(sampling_result=retried_run),
            metadata=archived_run.metadata,
        )

        document = archived_test_run_to_archive_dict(archived)
        self._write(document)
        loaded = load_archived_test_run(self.archive_directory, RUN_ID)
        self.assertEqual(
            loaded.analysis.sampling_result.retry_policy,
            RetryPolicy(max_attempts=3, retry_delay_seconds=0.02),
        )
        self.assertEqual(
            [
                sample.request_attempts
                for sample in loaded.analysis.sampling_result.samples
            ],
            [sample.request_attempts for sample in retried_samples],
        )


if __name__ == "__main__":
    unittest.main()
