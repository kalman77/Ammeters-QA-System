import io
import unittest
from contextlib import redirect_stdout

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
