"""Qt-free view models built from serialized framework results.

Every function here maps one of the project's JSON-friendly dictionaries onto
the exact rows, cards, and series the desktop pages render. Keeping them free
of Qt makes the presentation logic testable without a display server.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.presentation.desktop.formatting import (
    PLACEHOLDER,
    finite,
    format_current,
    format_milliseconds,
    format_number,
    format_seconds,
    format_signed,
    format_timestamp,
    mapping,
    sequence,
    short_run_id,
    title_case,
)


STATISTICS_METRICS: Tuple[Dict[str, Any], ...] = (
    {
        "key": "mean_current",
        "delta_key": "mean_current_delta",
        "label": "Mean current",
        "unit": "A",
        "digits": 5,
    },
    {
        "key": "median_current",
        "delta_key": "median_current_delta",
        "label": "Median current",
        "unit": "A",
        "digits": 5,
    },
    {
        "key": "standard_deviation_current",
        "delta_key": "standard_deviation_current_delta",
        "label": "Std deviation (population)",
        "unit": "A",
        "digits": 4,
    },
    {
        "key": "minimum_current",
        "delta_key": "minimum_current_delta",
        "label": "Minimum current",
        "unit": "A",
        "digits": 5,
    },
    {
        "key": "maximum_current",
        "delta_key": "maximum_current_delta",
        "label": "Maximum current",
        "unit": "A",
        "digits": 5,
    },
    {
        "key": "measurements_count",
        "delta_key": "measurements_count_delta",
        "label": "Analyzed samples",
        "unit": "",
        "digits": 0,
    },
)


def _analysis(archived_run: Mapping[str, Any]) -> Mapping[str, Any]:
    return mapping(archived_run.get("analysis"))


def count_retried_samples(analysis: Mapping[str, Any]) -> int:
    """Count slots that needed more than one request.

    Derived from the samples themselves so both the archive schema and the
    JSON-friendly analysis shape are handled by one code path.
    """
    sampling_result = mapping(mapping(analysis).get("sampling_result"))
    return sum(
        1
        for sample in sequence(sampling_result.get("samples"))
        if (finite(mapping(sample).get("request_attempts")) or 0) > 1
    )


def describe_retry_policy(analysis: Mapping[str, Any]) -> str:
    """Describe the retry allowance one run executed under."""
    sampling_result = mapping(mapping(analysis).get("sampling_result"))
    retry = mapping(sampling_result.get("retry"))
    attempts = finite(retry.get("max_attempts"))
    if attempts is None:
        return "1 attempt per slot"
    if attempts <= 1:
        return "1 attempt per slot"
    delay = finite(retry.get("retry_delay_seconds")) or 0.0
    return f"up to {int(attempts)} attempts, {format_seconds(delay)} apart"


def _success_ratio(summary: Mapping[str, Any]) -> Optional[float]:
    recorded = finite(summary.get("recorded_samples"))
    analyzed = finite(summary.get("analyzed_samples"))
    if recorded is None or analyzed is None or recorded <= 0:
        return None
    return analyzed / recorded


def build_metadata_label(metadata: Mapping[str, Any]) -> str:
    """Collapse archive metadata into one compact table cell."""
    items = mapping(metadata)
    if not items:
        return PLACEHOLDER
    return ", ".join(
        f"{key}={value}" for key, value in sorted(items.items())
    )


def build_history_row(archived_run: Mapping[str, Any]) -> Dict[str, Any]:
    """Build one Results-page table row from an archived run dictionary."""
    run = mapping(archived_run)
    analysis = _analysis(run)
    summary = mapping(analysis.get("summary"))
    statistics = mapping(analysis.get("statistics"))
    settings = mapping(
        mapping(analysis.get("sampling_result")).get("settings")
    )
    metadata = mapping(run.get("metadata"))
    ratio = _success_ratio(summary)

    return {
        "run_id": str(run.get("run_id", "")),
        "short_id": short_run_id(run.get("run_id")),
        "ammeter_type": str(analysis.get("ammeter_type", "")),
        "ammeter_display": title_case(analysis.get("ammeter_type")),
        "status": str(analysis.get("status", "")).lower(),
        "status_display": title_case(analysis.get("status")),
        "archived_at_raw": str(run.get("archived_at_utc", "")),
        "archived_at": format_timestamp(run.get("archived_at_utc")),
        "samples_display": (
            f"{summary.get('analyzed_samples', 0)}"
            f"/{summary.get('recorded_samples', 0)}"
        ),
        "analyzed_samples": summary.get("analyzed_samples"),
        "recorded_samples": summary.get("recorded_samples"),
        "failed_samples": summary.get("failed_samples"),
        "missed_samples": summary.get("missed_samples"),
        "success_ratio": ratio,
        "mean_current": statistics.get("mean_current"),
        "mean_display": format_number(
            statistics.get("mean_current"),
            digits=5,
        ),
        "standard_deviation_current": statistics.get(
            "standard_deviation_current"
        ),
        "deviation_display": format_number(
            statistics.get("standard_deviation_current"),
            digits=4,
        ),
        "frequency_hz": settings.get("sampling_frequency_hz"),
        "frequency_display": format_number(
            settings.get("sampling_frequency_hz"),
            digits=4,
            suffix=" Hz",
        ),
        "retried_samples": count_retried_samples(analysis),
        "retry_display": describe_retry_policy(analysis),
        "has_statistics": bool(statistics),
        "metadata": dict(metadata),
        "metadata_display": build_metadata_label(metadata),
        "unit": str(analysis.get("unit", "A")),
    }


def build_history_rows(
    archived_runs: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Build every Results-page row, preserving the manager's ordering."""
    return [build_history_row(run) for run in archived_runs]


def row_matches_search(row: Mapping[str, Any], text: str) -> bool:
    """Return whether a row matches a free-text filter."""
    needle = str(text or "").strip().lower()
    if not needle:
        return True
    haystack = " ".join(
        str(row.get(key, ""))
        for key in (
            "run_id",
            "ammeter_display",
            "status_display",
            "archived_at",
            "metadata_display",
        )
    ).lower()
    return needle in haystack


def build_summary_cards(
    analysis: Mapping[str, Any],
) -> List[Dict[str, str]]:
    """Build the metric cards shown above a run's detail view."""
    payload = mapping(analysis)
    summary = mapping(payload.get("summary"))
    statistics = mapping(payload.get("statistics"))
    sampling_result = mapping(payload.get("sampling_result"))
    unit = str(payload.get("unit", "A"))
    ratio = _success_ratio(summary)

    return [
        {
            "key": "status",
            "label": "STATUS",
            "value": title_case(payload.get("status")),
            "hint": title_case(payload.get("ammeter_type")),
        },
        {
            "key": "samples",
            "label": "ANALYZED SAMPLES",
            "value": (
                f"{summary.get('analyzed_samples', 0)}"
                f" / {summary.get('recorded_samples', 0)}"
            ),
            "hint": (
                PLACEHOLDER
                if ratio is None
                else f"{ratio * 100:.1f}% usable"
            ),
        },
        {
            "key": "mean",
            "label": "MEAN CURRENT",
            "value": format_current(statistics.get("mean_current"), unit),
            "hint": (
                "median "
                + format_number(statistics.get("median_current"), digits=5)
            ),
        },
        {
            "key": "deviation",
            "label": "STD DEVIATION",
            "value": format_current(
                statistics.get("standard_deviation_current"),
                unit,
            ),
            "hint": "population",
        },
        {
            "key": "span",
            "label": "MIN / MAX",
            "value": (
                format_number(statistics.get("minimum_current"), digits=4)
                + " / "
                + format_number(statistics.get("maximum_current"), digits=4)
            ),
            "hint": unit,
        },
        {
            "key": "window",
            "label": "SAMPLING WINDOW",
            "value": format_seconds(
                sampling_result.get("sampling_elapsed_seconds")
            ),
            "hint": format_number(
                mapping(sampling_result.get("settings")).get(
                    "sampling_frequency_hz"
                ),
                digits=4,
                suffix=" Hz",
            ),
        },
        {
            "key": "retries",
            "label": "RETRIED SLOTS",
            "value": str(count_retried_samples(payload)),
            "hint": describe_retry_policy(payload),
        },
    ]


def build_sample_rows(
    analysis: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Build one table row per recorded sampling slot."""
    sampling_result = mapping(mapping(analysis).get("sampling_result"))
    rows: List[Dict[str, Any]] = []
    for sample in sequence(sampling_result.get("samples")):
        entry = mapping(sample)
        result = mapping(entry.get("result"))
        errors = [mapping(error) for error in sequence(result.get("errors"))]
        rows.append(
            {
                "index": entry.get("sample_index"),
                "scheduled_display": format_seconds(
                    entry.get("scheduled_elapsed_seconds")
                ),
                "started_display": format_seconds(
                    entry.get("started_elapsed_seconds")
                ),
                "timing_error_display": format_milliseconds(
                    entry.get("timing_error_seconds")
                ),
                "latency_display": format_milliseconds(
                    result.get("request_latency_seconds")
                ),
                "attempts": entry.get("request_attempts"),
                "attempts_display": (
                    PLACEHOLDER
                    if entry.get("request_attempts") is None
                    else str(entry.get("request_attempts"))
                ),
                "current_display": format_number(
                    result.get("current"),
                    digits=6,
                ),
                "status": str(result.get("status", "")).lower(),
                "status_display": title_case(result.get("status")),
                "error_display": (
                    "; ".join(
                        f"{error.get('code', '')}: {error.get('message', '')}"
                        for error in errors
                    )
                    or PLACEHOLDER
                ),
            }
        )
    return rows


def build_error_lines(analysis: Mapping[str, Any]) -> List[str]:
    """Collect lifecycle and per-sample errors as readable lines."""
    sampling_result = mapping(mapping(analysis).get("sampling_result"))
    lines = [
        f"{mapping(error).get('code', '')}: "
        f"{mapping(error).get('message', '')}"
        for error in sequence(sampling_result.get("errors"))
    ]
    for sample in sequence(sampling_result.get("samples")):
        entry = mapping(sample)
        result = mapping(entry.get("result"))
        for error in sequence(result.get("errors")):
            detail = mapping(error)
            lines.append(
                f"slot {entry.get('sample_index')} · "
                f"{detail.get('code', '')}: {detail.get('message', '')}"
            )
    return lines


def build_plot_series(analysis: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the archived-run plot series for the measurement charts."""
    sampling_result = mapping(mapping(analysis).get("sampling_result"))
    statistics = mapping(mapping(analysis).get("statistics"))

    current_x: List[float] = []
    current_y: List[float] = []
    failure_x: List[float] = []
    latency_x: List[float] = []
    latency_y: List[float] = []
    timing_x: List[float] = []
    timing_y: List[float] = []

    for position, sample in enumerate(sequence(sampling_result.get("samples"))):
        entry = mapping(sample)
        result = mapping(entry.get("result"))
        x_value = finite(entry.get("started_elapsed_seconds"))
        if x_value is None:
            x_value = finite(entry.get("scheduled_elapsed_seconds"))
        if x_value is None:
            x_value = float(position)

        value = finite(result.get("current"))
        if str(result.get("status", "")).lower() == "success" and (
            value is not None
        ):
            current_x.append(x_value)
            current_y.append(value)
        else:
            failure_x.append(x_value)

        latency = finite(result.get("request_latency_seconds"))
        if latency is not None:
            latency_x.append(x_value)
            latency_y.append(latency * 1000.0)

        timing_error = finite(entry.get("timing_error_seconds"))
        if timing_error is not None:
            timing_x.append(x_value)
            timing_y.append(timing_error * 1000.0)

    span = (
        [min(current_x + failure_x), max(current_x + failure_x)]
        if (current_x or failure_x)
        else [0.0, 1.0]
    )

    return {
        "current_x": current_x,
        "current_y": current_y,
        "failure_x": failure_x,
        "latency_x": latency_x,
        "latency_y": latency_y,
        "timing_x": timing_x,
        "timing_y": timing_y,
        "span": span,
        "mean": finite(statistics.get("mean_current")),
        "minimum": finite(statistics.get("minimum_current")),
        "maximum": finite(statistics.get("maximum_current")),
        "unit": str(mapping(analysis).get("unit", "A")),
        "ammeter_type": str(mapping(analysis).get("ammeter_type", "")),
    }


def _comparison_entry(
    archived_run: Mapping[str, Any],
    *,
    is_baseline: bool,
    deltas: Optional[Mapping[str, Any]] = None,
    same_ammeter_type: Optional[bool] = None,
    same_sampling_settings: Optional[bool] = None,
) -> Dict[str, Any]:
    run = mapping(archived_run)
    analysis = _analysis(run)
    statistics = mapping(analysis.get("statistics"))
    return {
        "run_id": str(run.get("run_id", "")),
        "short_id": short_run_id(run.get("run_id")),
        "ammeter_type": str(analysis.get("ammeter_type", "")),
        "ammeter_display": title_case(analysis.get("ammeter_type")),
        "status": str(analysis.get("status", "")).lower(),
        "status_display": title_case(analysis.get("status")),
        "archived_at": format_timestamp(run.get("archived_at_utc")),
        "is_baseline": is_baseline,
        "statistics": dict(statistics),
        "deltas": dict(mapping(deltas)) if deltas is not None else None,
        "same_ammeter_type": same_ammeter_type,
        "same_sampling_settings": same_sampling_settings,
        "unit": str(analysis.get("unit", "A")),
    }


def build_comparison_view(
    comparison: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build baseline-first rows and metric metadata for the Compare page."""
    payload = mapping(comparison)
    entries = [
        _comparison_entry(payload.get("baseline"), is_baseline=True)
    ]
    for candidate in sequence(payload.get("candidates")):
        item = mapping(candidate)
        entries.append(
            _comparison_entry(
                item.get("archived_run"),
                is_baseline=False,
                deltas=item.get("statistics_delta"),
                same_ammeter_type=item.get("same_ammeter_type"),
                same_sampling_settings=item.get("same_sampling_settings"),
            )
        )
    return {
        "runs": entries,
        "metrics": [dict(metric) for metric in STATISTICS_METRICS],
        "delta_direction": str(
            payload.get("delta_direction", "candidate_minus_baseline")
        ),
    }


def comparison_metric_series(
    view: Mapping[str, Any],
    metric_key: str,
) -> List[Dict[str, Any]]:
    """Extract one metric across every compared run for charting."""
    metric = next(
        (
            item
            for item in STATISTICS_METRICS
            if item["key"] == metric_key
        ),
        STATISTICS_METRICS[0],
    )
    series: List[Dict[str, Any]] = []
    for entry in sequence(mapping(view).get("runs")):
        row = mapping(entry)
        statistics = mapping(row.get("statistics"))
        deltas = row.get("deltas")
        delta_value = (
            mapping(deltas).get(metric["delta_key"])
            if isinstance(deltas, Mapping)
            else None
        )
        series.append(
            {
                "run_id": row.get("run_id", ""),
                "short_id": row.get("short_id", ""),
                "ammeter_type": row.get("ammeter_type", ""),
                "ammeter_display": row.get("ammeter_display", ""),
                "is_baseline": bool(row.get("is_baseline")),
                "value": finite(statistics.get(metric["key"])),
                "delta": finite(delta_value),
                "delta_display": format_signed(
                    delta_value,
                    digits=max(1, int(metric["digits"]) or 1),
                    suffix=(
                        f" {metric['unit']}" if metric["unit"] else ""
                    ),
                ),
            }
        )
    return series
