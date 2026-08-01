import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.presentation.console.format_measurement_results_table import (
    format_measurement_results_table,
)
from src.presentation.console.print_measurement_results import (
    print_measurement_results,
)
from src.presentation.console.format_measurements_table import (
    format_measurements_table,
)
from src.presentation.console.print_measurements import print_measurements


class MeasurementPresentationTests(unittest.TestCase):
    def test_formats_an_aligned_measurement_table(self) -> None:
        table = format_measurements_table(
            {
                "greenlee": 1.25,
                "entes": 123.5,
                "circutor": 0.03125,
            }
        )

        self.assertEqual(
            table,
            "\n".join(
                [
                    "Ammeter Measurement Results",
                    "+----------+------------+------+",
                    "| Ammeter  |    Current | Unit |",
                    "+----------+------------+------+",
                    "| GREENLEE |   1.250000 | A    |",
                    "| ENTES    | 123.500000 | A    |",
                    "| CIRCUTOR |   0.031250 | A    |",
                    "+----------+------------+------+",
                ]
            ),
        )

    def test_prints_the_formatted_table(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            print_measurements({"greenlee": 1.25})

        self.assertEqual(
            output.getvalue(),
            "\n".join(
                [
                    "Ammeter Measurement Results",
                    "+----------+----------+------+",
                    "| Ammeter  |  Current | Unit |",
                    "+----------+----------+------+",
                    "| GREENLEE | 1.250000 | A    |",
                    "+----------+----------+------+",
                    "",
                ]
            ),
        )

    def test_formats_typed_results_with_status_latency_and_errors(self) -> None:
        timestamp = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        results = [
            MeasurementResult(
                ammeter_type="greenlee",
                status=MeasurementStatus.SUCCESS,
                timestamp_utc=timestamp,
                elapsed_seconds=0.02,
                current=1.25,
                unit="A",
                request_latency_seconds=0.0025,
                errors=(),
            ),
            MeasurementResult(
                ammeter_type="entes",
                status=MeasurementStatus.FAILED,
                timestamp_utc=timestamp,
                elapsed_seconds=0.03,
                current=None,
                unit="A",
                request_latency_seconds=None,
                errors=(
                    MeasurementError(
                        code=(
                            MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED
                        ),
                        message="connection refused",
                    ),
                ),
            ),
        ]

        table = format_measurement_results_table(results)

        self.assertIn("| GREENLEE | SUCCESS | 1.250000 | A", table)
        self.assertIn("| A    |        2.500 | -", table)
        self.assertIn("| ENTES    | FAILED  |        - | A", table)
        self.assertIn(
            "measurement_request_failed: connection refused",
            table,
        )

    def test_prints_typed_results_table(self) -> None:
        result = MeasurementResult(
            ammeter_type="circutor",
            status=MeasurementStatus.SUCCESS,
            timestamp_utc=datetime(
                2026,
                8,
                1,
                12,
                0,
                tzinfo=timezone.utc,
            ),
            elapsed_seconds=0.01,
            current=0.03125,
            unit="A",
            request_latency_seconds=0.001,
            errors=(),
        )
        output = io.StringIO()

        with redirect_stdout(output):
            print_measurement_results([result])

        self.assertIn("Ammeter Test Results", output.getvalue())
        self.assertIn("| CIRCUTOR | SUCCESS | 0.031250 | A", output.getvalue())
