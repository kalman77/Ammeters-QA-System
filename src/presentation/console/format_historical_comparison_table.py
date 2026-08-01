from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.historical_comparison import HistoricalComparison


def format_historical_comparison_table(
    comparison: HistoricalComparison,
) -> str:
    """Return a descriptive candidate-minus-baseline comparison table."""
    if not isinstance(comparison, HistoricalComparison):
        raise ValueError("comparison must be HistoricalComparison")

    headers = (
        "Role",
        "Run ID",
        "Ammeter",
        "Status",
        "Used/Planned",
        "Mean (A)",
        "Δ Mean (A)",
        "Median (A)",
        "Pop StdDev (A)",
        "Min (A)",
        "Max (A)",
        "Same Meter",
        "Same Plan",
    )
    rows = []
    archived_runs = (comparison.baseline, *comparison.candidates)
    for row_index, archived_run in enumerate(archived_runs):
        analysis = archived_run.analysis
        sampling_result = analysis.sampling_result
        used_samples = sum(
            sample.result.status is MeasurementStatus.SUCCESS
            for sample in sampling_result.samples
        )
        if analysis.statistics is None:
            statistics_values = ("-", "-", "-", "-", "-")
        else:
            statistics_values = (
                f"{analysis.statistics.mean_current:.6f}",
                f"{analysis.statistics.median_current:.6f}",
                (
                    f"{analysis.statistics.standard_deviation_current:.6f}"
                ),
                f"{analysis.statistics.minimum_current:.6f}",
                f"{analysis.statistics.maximum_current:.6f}",
            )

        if row_index == 0:
            role = "BASELINE"
            mean_delta = "-"
            same_ammeter = "-"
            same_settings = "-"
        else:
            role = f"CANDIDATE {row_index}"
            delta = comparison.statistics_deltas[row_index - 1]
            mean_delta = (
                f"{delta.mean_current_delta:+.6f}"
                if delta is not None
                else "-"
            )
            same_ammeter = (
                "YES"
                if comparison.same_ammeter_types[row_index - 1]
                else "NO"
            )
            same_settings = (
                "YES"
                if comparison.same_sampling_settings[row_index - 1]
                else "NO"
            )

        rows.append(
            (
                role,
                archived_run.run_id,
                sampling_result.ammeter_type.upper(),
                sampling_result.status.value.upper(),
                (
                    f"{used_samples}/"
                    f"{sampling_result.settings.measurements_count}"
                ),
                statistics_values[0],
                mean_delta,
                statistics_values[1],
                statistics_values[2],
                statistics_values[3],
                statistics_values[4],
                same_ammeter,
                same_settings,
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
    numeric_columns = {4, 5, 6, 7, 8, 9, 10}
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
            "Historical Ammeter Comparison "
            "(deltas = candidate - baseline)",
            border,
            formatted_rows[0],
            border,
            *formatted_rows[1:],
            border,
        ]
    )
