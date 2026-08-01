from typing import Iterable

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.sampling_analysis import SamplingAnalysis


def format_analysis_results_table(
    analyses: Iterable[SamplingAnalysis],
) -> str:
    """Return statistical sampling analyses as an aligned console table."""
    headers = (
        "Ammeter",
        "Status",
        "Used/Planned",
        "Failed/Missed",
        "Mean (A)",
        "Median (A)",
        "Pop StdDev (A)",
        "Min (A)",
        "Max (A)",
        "Errors",
    )
    rows = []
    for analysis in analyses:
        sampling_result = analysis.sampling_result
        successful_samples = sum(
            sample.result.status is MeasurementStatus.SUCCESS
            for sample in sampling_result.samples
        )
        missed_samples = sum(
            any(
                error.code is MeasurementErrorCode.SAMPLING_SLOT_MISSED
                for error in sample.result.errors
            )
            for sample in sampling_result.samples
        )
        failed_samples = (
            len(sampling_result.samples)
            - successful_samples
            - missed_samples
        )
        error_codes = [
            f"#{sample.sample_index + 1}:{error.code.value}"
            for sample in sampling_result.samples
            for error in sample.result.errors
        ]
        error_codes.extend(
            error.code.value for error in sampling_result.errors
        )
        if analysis.statistics is None:
            metric_values = ("-", "-", "-", "-", "-")
        else:
            metric_values = (
                f"{analysis.statistics.mean_current:.6f}",
                f"{analysis.statistics.median_current:.6f}",
                (
                    f"{analysis.statistics.standard_deviation_current:.6f}"
                ),
                f"{analysis.statistics.minimum_current:.6f}",
                f"{analysis.statistics.maximum_current:.6f}",
            )
        rows.append(
            (
                sampling_result.ammeter_type.upper(),
                sampling_result.status.value.upper(),
                (
                    f"{successful_samples}/"
                    f"{sampling_result.settings.measurements_count}"
                ),
                f"{failed_samples}/{missed_samples}",
                *metric_values,
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
    numeric_columns = {2, 3, 4, 5, 6, 7, 8}
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
            "Ammeter Statistical Analysis",
            border,
            formatted_rows[0],
            border,
            *formatted_rows[1:],
            border,
        ]
    )
