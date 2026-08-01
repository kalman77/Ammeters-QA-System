import json
from typing import Iterable

from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.archived_test_run import ArchivedTestRun


def format_archived_test_runs_table(
    archived_runs: Iterable[ArchivedTestRun],
) -> str:
    """Return archived test runs as an aligned console table."""
    headers = (
        "Run ID",
        "Archived (UTC)",
        "Ammeter",
        "Status",
        "Used/Planned",
        "Mean (A)",
        "Pop StdDev (A)",
        "Metadata",
    )
    rows = []
    for archived_run in archived_runs:
        if not isinstance(archived_run, ArchivedTestRun):
            raise ValueError(
                "archived_runs must contain ArchivedTestRun values"
            )
        analysis = archived_run.analysis
        sampling_result = analysis.sampling_result
        used_samples = sum(
            sample.result.status is MeasurementStatus.SUCCESS
            for sample in sampling_result.samples
        )
        if analysis.statistics is None:
            mean_current = "-"
            standard_deviation = "-"
        else:
            mean_current = f"{analysis.statistics.mean_current:.6f}"
            standard_deviation = (
                f"{analysis.statistics.standard_deviation_current:.6f}"
            )
        metadata_parts = []
        for entry in archived_run.metadata:
            rendered_key = json.dumps(
                entry.key,
                ensure_ascii=False,
            )[1:-1]
            rendered_value = json.dumps(
                entry.value,
                allow_nan=False,
                ensure_ascii=False,
            )
            if isinstance(entry.value, str):
                rendered_value = rendered_value[1:-1]
            metadata_parts.append(
                f"{rendered_key}={rendered_value}"
            )
        metadata = ", ".join(metadata_parts)
        rows.append(
            (
                archived_run.run_id,
                archived_run.archived_at_utc.isoformat().replace(
                    "+00:00",
                    "Z",
                ),
                sampling_result.ammeter_type.upper(),
                sampling_result.status.value.upper(),
                (
                    f"{used_samples}/"
                    f"{sampling_result.settings.measurements_count}"
                ),
                mean_current,
                standard_deviation,
                metadata or "-",
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
    numeric_columns = {4, 5, 6}
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
            "Archived Ammeter Test Runs",
            border,
            formatted_rows[0],
            border,
            *formatted_rows[1:],
            border,
        ]
    )
