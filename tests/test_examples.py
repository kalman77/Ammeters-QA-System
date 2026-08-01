import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest.mock import patch

from examples import run_tests
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_result import MeasurementResult


class RunTestsExampleTests(unittest.TestCase):
    def test_example_prints_results_from_the_unified_api(self) -> None:
        result = MeasurementResult(
            ammeter_type="greenlee",
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
            current=1.25,
            unit="A",
            request_latency_seconds=0.002,
            errors=(),
        )

        class FakeFramework:
            def measure_all(self):
                return {"greenlee": result}

        output = io.StringIO()
        with (
            patch.object(
                run_tests,
                "AmmeterTestFramework",
                return_value=FakeFramework(),
            ),
            redirect_stdout(output),
        ):
            run_tests.main()

        self.assertIn("Ammeter Test Results", output.getvalue())
        self.assertIn("| GREENLEE | SUCCESS | 1.250000 | A", output.getvalue())


if __name__ == "__main__":
    unittest.main()
