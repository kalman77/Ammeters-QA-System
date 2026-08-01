"""Tests for the Qt-free parts of the desktop presentation adapter.

The view models, formatters, and injected ports carry all of the desktop
behaviour that is worth asserting, and none of them require a display server.
"""

import unittest

from src.application.errors.measurement_request_error import (
    MeasurementRequestError,
)
from src.presentation.desktop.formatting import (
    PLACEHOLDER,
    finite,
    format_current,
    format_milliseconds,
    format_number,
    format_percentage,
    format_seconds,
    format_signed,
    short_run_id,
)
from src.presentation.desktop.run_service import (
    CancellableSleeper,
    FaultInjection,
    LiveAmmeterClient,
    RunCancelled,
    RunRequest,
    StopToken,
)
from src.presentation.desktop.view_models import (
    build_comparison_view,
    count_retried_samples,
    describe_retry_policy,
    build_error_lines,
    build_history_row,
    build_plot_series,
    build_sample_rows,
    build_summary_cards,
    comparison_metric_series,
    row_matches_search,
)


def _sample(
    index,
    *,
    current=1.5,
    status="success",
    started=None,
    errors=(),
    request_attempts=1,
):
    scheduled = index * 0.2
    started_elapsed = scheduled if started is None else started
    return {
        "sample_index": index,
        "scheduled_elapsed_seconds": scheduled,
        "scheduled_at_utc": "2026-01-01T00:00:00Z",
        "started_elapsed_seconds": started_elapsed,
        "started_at_utc": "2026-01-01T00:00:00Z",
        "completed_elapsed_seconds": started_elapsed + 0.01,
        "timing_error_seconds": (
            None if started_elapsed is None else started_elapsed - scheduled
        ),
        "request_attempts": request_attempts,
        "result": {
            "ammeter_type": "greenlee",
            "status": status,
            "timestamp_utc": "2026-01-01T00:00:00Z",
            "elapsed_seconds": 0.01,
            "current": current,
            "unit": "A",
            "request_latency_seconds": 0.004,
            "errors": list(errors),
        },
    }


def _analysis(ammeter_type="greenlee", statistics=True):
    samples = [
        _sample(0, current=1.0),
        _sample(1, current=2.0, request_attempts=2),
        _sample(
            2,
            current=None,
            status="failed",
            errors=[
                {
                    "code": "MEASUREMENT_REQUEST_FAILED",
                    "message": "socket closed",
                }
            ],
        ),
    ]
    return {
        "ammeter_type": ammeter_type,
        "status": "partial",
        "timestamp_utc": "2026-01-01T00:00:02Z",
        "unit": "A",
        "summary": {
            "planned_samples": 3,
            "recorded_samples": 3,
            "analyzed_samples": 2,
            "excluded_samples": 1,
            "failed_samples": 1,
            "missed_samples": 0,
        },
        "statistics": (
            {
                "measurements_count": 2,
                "mean_current": 1.5,
                "median_current": 1.5,
                "standard_deviation_current": 0.5,
                "standard_deviation_method": "population",
                "minimum_current": 1.0,
                "maximum_current": 2.0,
                "unit": "A",
            }
            if statistics
            else None
        ),
        "sampling_result": {
            "ammeter_type": ammeter_type,
            "status": "partial",
            "timestamp_utc": "2026-01-01T00:00:02Z",
            "elapsed_seconds": 0.7,
            "sampling_started_at_utc": "2026-01-01T00:00:00Z",
            "sampling_elapsed_seconds": 0.6,
            "unit": "A",
            "settings": {
                "measurements_count": 3,
                "total_duration_seconds": 0.6,
                "sampling_frequency_hz": 5.0,
            },
            "retry": {
                "max_attempts": 3,
                "retry_delay_seconds": 0.02,
            },
            "summary": {
                "successful_samples": 2,
                "failed_samples": 1,
                "missed_samples": 0,
            },
            "samples": samples,
            "errors": [
                {
                    "code": "EMULATOR_STOP_FAILED",
                    "message": "shutdown timed out",
                }
            ],
        },
    }


def _archived_run(run_id, *, ammeter_type="greenlee", statistics=True):
    return {
        "schema_version": 1,
        "run_id": run_id,
        "archived_at_utc": "2026-01-01T00:00:03Z",
        "metadata": {"label": "bench-a", "operator": "nir"},
        "analysis": _analysis(ammeter_type, statistics=statistics),
    }


class FormattingTests(unittest.TestCase):
    def test_finite_rejects_non_numbers_and_specials(self) -> None:
        self.assertIsNone(finite("1.0"))
        self.assertIsNone(finite(True))
        self.assertIsNone(finite(float("nan")))
        self.assertIsNone(finite(float("inf")))
        self.assertEqual(finite(2), 2.0)

    def test_missing_values_use_one_placeholder(self) -> None:
        for formatted in (
            format_number(None),
            format_current(None),
            format_seconds(None),
            format_milliseconds(None),
            format_signed(None),
            format_percentage(None),
        ):
            self.assertEqual(formatted, PLACEHOLDER)

    def test_durations_scale_by_magnitude(self) -> None:
        self.assertEqual(format_seconds(0.25), "250.0 ms")
        self.assertEqual(format_seconds(3.5), "3.500 s")
        self.assertEqual(format_seconds(150.0), "2m 30.0s")

    def test_signed_values_keep_their_direction(self) -> None:
        self.assertEqual(format_signed(0), "0")
        self.assertTrue(format_signed(0.5).startswith("+"))
        self.assertTrue(format_signed(-0.5).startswith("-"))

    def test_run_ids_are_shortened_only_when_long(self) -> None:
        self.assertEqual(short_run_id("abc"), "abc")
        self.assertEqual(
            short_run_id("c7d13098-cfd0-4b33-a1cb-d757964b512a"),
            "c7d13098…512a",
        )


class HistoryRowTests(unittest.TestCase):
    def test_row_exposes_sortable_and_display_values(self) -> None:
        row = build_history_row(_archived_run("run-1"))
        self.assertEqual(row["run_id"], "run-1")
        self.assertEqual(row["ammeter_display"], "Greenlee")
        self.assertEqual(row["status"], "partial")
        self.assertEqual(row["samples_display"], "2/3")
        self.assertAlmostEqual(row["success_ratio"], 2 / 3)
        self.assertEqual(row["mean_current"], 1.5)
        self.assertTrue(row["has_statistics"])
        self.assertIn("label=bench-a", row["metadata_display"])

    def test_row_without_statistics_is_still_renderable(self) -> None:
        row = build_history_row(
            _archived_run("run-2", statistics=False)
        )
        self.assertFalse(row["has_statistics"])
        self.assertEqual(row["mean_display"], PLACEHOLDER)
        self.assertIsNone(row["mean_current"])

    def test_malformed_documents_do_not_raise(self) -> None:
        row = build_history_row({})
        self.assertEqual(row["run_id"], "")
        self.assertEqual(row["mean_display"], PLACEHOLDER)

    def test_search_matches_metadata_and_identity(self) -> None:
        row = build_history_row(_archived_run("run-1"))
        self.assertTrue(row_matches_search(row, ""))
        self.assertTrue(row_matches_search(row, "GREENLEE"))
        self.assertTrue(row_matches_search(row, "bench-a"))
        self.assertFalse(row_matches_search(row, "circutor"))


class DetailViewTests(unittest.TestCase):
    def test_summary_cards_cover_every_detail_tile(self) -> None:
        cards = build_summary_cards(_analysis())
        keys = [card["key"] for card in cards]
        self.assertEqual(
            keys,
            [
                "status",
                "samples",
                "mean",
                "deviation",
                "span",
                "window",
                "retries",
            ],
        )
        by_key = {card["key"]: card for card in cards}
        self.assertEqual(by_key["samples"]["value"], "2 / 3")
        self.assertEqual(by_key["mean"]["value"], "1.5000 A")

    def test_sample_rows_preserve_slot_order_and_errors(self) -> None:
        rows = build_sample_rows(_analysis())
        self.assertEqual([row["index"] for row in rows], [0, 1, 2])
        self.assertEqual(rows[2]["status"], "failed")
        self.assertIn("socket closed", rows[2]["error_display"])
        self.assertEqual(rows[0]["error_display"], PLACEHOLDER)

    def test_error_lines_include_lifecycle_and_slot_failures(self) -> None:
        lines = build_error_lines(_analysis())
        self.assertIn("EMULATOR_STOP_FAILED: shutdown timed out", lines)
        self.assertTrue(
            any(line.startswith("slot 2 · ") for line in lines)
        )

    def test_plot_series_separates_successes_from_failures(self) -> None:
        series = build_plot_series(_analysis())
        self.assertEqual(series["current_y"], [1.0, 2.0])
        self.assertEqual(len(series["failure_x"]), 1)
        self.assertEqual(series["mean"], 1.5)
        self.assertEqual(len(series["latency_x"]), 3)
        self.assertEqual(series["span"], [0.0, 0.4])

    def test_plot_series_of_empty_analysis_has_a_default_span(self) -> None:
        series = build_plot_series({})
        self.assertEqual(series["current_x"], [])
        self.assertEqual(series["span"], [0.0, 1.0])


class RetryViewTests(unittest.TestCase):
    def test_retried_slots_are_counted_from_the_samples(self) -> None:
        self.assertEqual(count_retried_samples(_analysis()), 1)

    def test_a_run_without_attempt_counts_reports_no_retries(self) -> None:
        analysis = _analysis()
        for sample in analysis["sampling_result"]["samples"]:
            sample.pop("request_attempts")
        self.assertEqual(count_retried_samples(analysis), 0)

    def test_the_policy_description_reflects_the_allowance(self) -> None:
        self.assertEqual(
            describe_retry_policy(_analysis()),
            "up to 3 attempts, 20.0 ms apart",
        )

    def test_a_missing_or_single_attempt_policy_reads_plainly(self) -> None:
        self.assertEqual(
            describe_retry_policy({}),
            "1 attempt per slot",
        )
        analysis = _analysis()
        analysis["sampling_result"]["retry"] = {
            "max_attempts": 1,
            "retry_delay_seconds": 0.0,
        }
        self.assertEqual(
            describe_retry_policy(analysis),
            "1 attempt per slot",
        )

    def test_sample_rows_expose_their_attempt_counts(self) -> None:
        rows = build_sample_rows(_analysis())
        self.assertEqual([row["attempts"] for row in rows], [1, 2, 1])
        self.assertEqual(rows[1]["attempts_display"], "2")

    def test_the_detail_cards_include_a_retry_tile(self) -> None:
        cards = {card["key"]: card for card in build_summary_cards(_analysis())}
        self.assertEqual(cards["retries"]["value"], "1")
        self.assertEqual(
            cards["retries"]["hint"],
            "up to 3 attempts, 20.0 ms apart",
        )

    def test_history_rows_carry_the_retry_summary(self) -> None:
        row = build_history_row(_archived_run("run-1"))
        self.assertEqual(row["retried_samples"], 1)
        self.assertEqual(
            row["retry_display"],
            "up to 3 attempts, 20.0 ms apart",
        )


class RetryRequestTests(unittest.TestCase):
    def _request(self, **overrides):
        payload = {
            "ammeter_types": ("greenlee",),
            "measurements_count": 4,
            "sampling_frequency_hz": 2.0,
        }
        payload.update(overrides)
        return RunRequest(**payload)

    def test_retries_are_disabled_by_default(self) -> None:
        request = self._request()
        self.assertEqual(request.max_attempts, 1)
        self.assertFalse(request.retries_enabled)

    def test_a_valid_retry_budget_is_accepted(self) -> None:
        request = self._request(max_attempts=3, retry_delay_seconds=0.05)
        self.assertTrue(request.retries_enabled)

    def test_out_of_range_attempts_are_rejected(self) -> None:
        for attempts in (0, 99, 2.5, True):
            with self.subTest(max_attempts=attempts):
                with self.assertRaises(ValueError):
                    self._request(max_attempts=attempts)

    def test_a_delay_without_retries_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._request(max_attempts=1, retry_delay_seconds=0.5)

    def test_an_out_of_range_delay_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._request(max_attempts=2, retry_delay_seconds=-1.0)
        with self.assertRaises(ValueError):
            self._request(max_attempts=2, retry_delay_seconds=1000.0)


class ComparisonViewTests(unittest.TestCase):
    def _comparison(self):
        return {
            "baseline": _archived_run("baseline-id"),
            "delta_direction": "candidate_minus_baseline",
            "candidates": [
                {
                    "archived_run": _archived_run(
                        "candidate-id",
                        ammeter_type="entes",
                    ),
                    "statistics_delta": {
                        "measurements_count_delta": 1,
                        "mean_current_delta": 0.25,
                        "median_current_delta": 0.25,
                        "standard_deviation_current_delta": -0.1,
                        "minimum_current_delta": 0.0,
                        "maximum_current_delta": 0.5,
                        "unit": "A",
                    },
                    "same_ammeter_type": False,
                    "same_sampling_settings": True,
                }
            ],
        }

    def test_baseline_is_listed_first(self) -> None:
        view = build_comparison_view(self._comparison())
        self.assertTrue(view["runs"][0]["is_baseline"])
        self.assertFalse(view["runs"][1]["is_baseline"])
        self.assertIsNone(view["runs"][0]["deltas"])
        self.assertFalse(view["runs"][1]["same_ammeter_type"])

    def test_metric_series_carries_values_and_signed_deltas(self) -> None:
        view = build_comparison_view(self._comparison())
        series = comparison_metric_series(view, "mean_current")
        self.assertEqual(len(series), 2)
        self.assertEqual(series[0]["value"], 1.5)
        self.assertIsNone(series[0]["delta"])
        self.assertEqual(series[1]["delta"], 0.25)
        self.assertTrue(series[1]["delta_display"].startswith("+0.25"))

    def test_unknown_metric_falls_back_to_the_first_metric(self) -> None:
        view = build_comparison_view(self._comparison())
        series = comparison_metric_series(view, "not-a-metric")
        self.assertEqual(series[0]["value"], 1.5)


class RunRequestTests(unittest.TestCase):
    def test_duration_follows_the_sampling_identity(self) -> None:
        request = RunRequest(
            ammeter_types=("greenlee",),
            measurements_count=10,
            sampling_frequency_hz=5.0,
        )
        self.assertEqual(request.total_duration_seconds, 2.0)
        self.assertEqual(request.total_samples, 10)

    def test_invalid_selections_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RunRequest(
                ammeter_types=(),
                measurements_count=1,
                sampling_frequency_hz=1.0,
            )
        with self.assertRaises(ValueError):
            RunRequest(
                ammeter_types=("greenlee", "greenlee"),
                measurements_count=1,
                sampling_frequency_hz=1.0,
            )
        with self.assertRaises(ValueError):
            RunRequest(
                ammeter_types=("greenlee",),
                measurements_count=0,
                sampling_frequency_hz=1.0,
            )
        with self.assertRaises(ValueError):
            RunRequest(
                ammeter_types=("greenlee",),
                measurements_count=1,
                sampling_frequency_hz=0.0,
            )

    def test_fault_probabilities_are_bounded(self) -> None:
        with self.assertRaises(ValueError):
            FaultInjection(outlier_probability=1.5)
        with self.assertRaises(ValueError):
            FaultInjection(extra_latency_seconds=-1.0)
        self.assertFalse(FaultInjection(enabled=True).active)
        self.assertTrue(
            FaultInjection(
                enabled=True,
                outlier_probability=0.5,
            ).active
        )


class LiveClientTests(unittest.TestCase):
    def _client(self, *, faults=None, delegate=None, stop_token=None):
        self.emitted = []
        return LiveAmmeterClient(
            port_to_ammeter={5000: "greenlee"},
            stop_token=stop_token or StopToken(),
            faults=faults or FaultInjection(),
            on_sample=lambda name, sample: self.emitted.append((name, sample)),
            delegate=delegate or (lambda *args, **kwargs: 1.25),
            monotonic_clock=lambda: next(self._clock),
        )

    def setUp(self) -> None:
        self._clock = iter([float(tick) for tick in range(0, 2000)])

    def _call(self, client):
        return client(
            5000,
            b"MEASURE",
            host="127.0.0.1",
            connect_timeout_seconds=1.0,
            read_timeout_seconds=1.0,
        )

    def test_successful_reads_are_streamed_with_identity(self) -> None:
        client = self._client()
        self.assertEqual(self._call(client), 1.25)
        name, sample = self.emitted[0]
        self.assertEqual(name, "greenlee")
        self.assertEqual(sample["sample_index"], 0)
        self.assertEqual(sample["status"], "success")
        self.assertEqual(sample["current"], 1.25)
        self.assertIsNone(sample["error"])

    def test_indexes_restart_for_each_ammeter(self) -> None:
        client = self._client()
        self._call(client)
        client.begin_ammeter()
        self._call(client)
        self.assertEqual(
            [sample["sample_index"] for _name, sample in self.emitted],
            [0, 0],
        )

    def test_delegate_failures_are_reported_then_reraised(self) -> None:
        def failing(*_args, **_kwargs):
            raise MeasurementRequestError("connection refused")

        client = self._client(delegate=failing)
        with self.assertRaises(MeasurementRequestError):
            self._call(client)
        _name, sample = self.emitted[0]
        self.assertEqual(sample["status"], "failed")
        self.assertIn("connection refused", sample["error"])

    def test_injected_communication_failure_replaces_the_read(self) -> None:
        client = self._client(
            faults=FaultInjection(
                enabled=True,
                communication_failure_probability=1.0,
            ),
            delegate=lambda *args, **kwargs: self.fail("delegate was called"),
        )
        with self.assertRaises(MeasurementRequestError):
            self._call(client)

    def test_injected_invalid_data_is_streamed_as_a_failure(self) -> None:
        client = self._client(
            faults=FaultInjection(
                enabled=True,
                invalid_data_probability=1.0,
            )
        )
        value = self._call(client)
        self.assertNotEqual(value, value)  # NaN
        _name, sample = self.emitted[0]
        self.assertEqual(sample["status"], "failed")

    def test_injected_outlier_offsets_the_reading(self) -> None:
        client = self._client(
            faults=FaultInjection(
                enabled=True,
                outlier_probability=1.0,
                outlier_offset_amperes=2.0,
            )
        )
        self.assertEqual(self._call(client), 3.25)

    def test_disabled_faults_never_alter_a_reading(self) -> None:
        client = self._client(
            faults=FaultInjection(
                enabled=False,
                communication_failure_probability=1.0,
                outlier_probability=1.0,
            )
        )
        self.assertEqual(self._call(client), 1.25)

    def test_a_stop_request_aborts_the_next_read(self) -> None:
        stop_token = StopToken()
        client = self._client(stop_token=stop_token)
        stop_token.request()
        with self.assertRaises(RunCancelled):
            self._call(client)
        self.assertEqual(self.emitted, [])


class CancellableSleeperTests(unittest.TestCase):
    def test_sleeping_completes_when_no_stop_is_requested(self) -> None:
        stop_token = StopToken()
        CancellableSleeper(stop_token)(0.001)

    def test_sleeping_raises_once_a_stop_is_requested(self) -> None:
        stop_token = StopToken()
        stop_token.request()
        with self.assertRaises(RunCancelled):
            CancellableSleeper(stop_token)(0.001)

    def test_a_stop_during_a_long_sleep_interrupts_it(self) -> None:
        class InterruptingToken(StopToken):
            def __init__(self) -> None:
                super().__init__()
                self.checks = 0

            def raise_if_requested(self) -> None:
                self.checks += 1
                if self.checks > 2:
                    raise RunCancelled("stopped")

        interrupting = InterruptingToken()
        sleeper = CancellableSleeper(interrupting)
        with self.assertRaises(RunCancelled):
            sleeper(10.0)
        self.assertLess(interrupting.checks, 10)


if __name__ == "__main__":
    unittest.main()
