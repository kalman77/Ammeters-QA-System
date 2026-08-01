from typing import Iterable

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.sampling_result import SamplingResult


def format_sampling_results_table(
    results: Iterable[SamplingResult],
) -> str:
    """Return sampling outcomes as an aligned console summary table."""
    headers = (
        "Ammeter",
        "Status",
        "Good/Total",
        "Missed",
        "Window (s)",
        "Actual (s)",
        "Hz",
        "Max Drift (ms)",
        "Errors",
    )
    rows = []
    for result in results:
        successful_samples = sum(
            sample.result.status is MeasurementStatus.SUCCESS
            for sample in result.samples
        )
        missed_samples = sum(
            any(
                error.code is MeasurementErrorCode.SAMPLING_SLOT_MISSED
                for error in sample.result.errors
            )
            for sample in result.samples
        )
        timing_errors = [
            abs(
                sample.started_elapsed_seconds
                - sample.scheduled_elapsed_seconds
            )
            for sample in result.samples
            if sample.started_elapsed_seconds is not None
        ]
        error_codes = [
            f"#{sample.sample_index + 1}:{error.code.value}"
            for sample in result.samples
            for error in sample.result.errors
        ]
        error_codes.extend(error.code.value for error in result.errors)
        rows.append(
            (
                result.ammeter_type.upper(),
                result.status.value.upper(),
                (
                    f"{successful_samples}/"
                    f"{result.settings.measurements_count}"
                ),
                str(missed_samples),
                f"{result.settings.total_duration_seconds:.3f}",
                (
                    f"{result.sampling_elapsed_seconds:.3f}"
                    if result.sampling_elapsed_seconds is not None
                    else "-"
                ),
                f"{result.settings.sampling_frequency_hz:.3f}",
                (
                    f"{max(timing_errors) * 1000:.3f}"
                    if timing_errors
                    else "-"
                ),
                ", ".join(error_codes) or "-",
            )
        )

    widths = [
        max(
            [
                len(headers[index]),
                *(len(row[index]) for row in rows),
            ]
        )
        for index in range(len(headers))
    ]
    border = "+" + "+".join(
        f"-{'-' * width}-" for width in widths
    ) + "+"
    numeric_columns = {2, 3, 4, 5, 6, 7}
    formatted_rows = []
    for row in (headers, *rows):
        cells = []
        for index, value in enumerate(row):
            if index in numeric_columns:
                cells.append(f" {value:>{widths[index]}} ")
            else:
                cells.append(f" {value:<{widths[index]}} ")
        formatted_rows.append("|" + "|".join(cells) + "|")

    return "\n".join(
        [
            "Ammeter Sampling Results",
            border,
            formatted_rows[0],
            border,
            *formatted_rows[1:],
            border,
        ]
    )
