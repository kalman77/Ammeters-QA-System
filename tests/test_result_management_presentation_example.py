import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from unittest.mock import Mock, call, patch

from examples import run_result_management
from src.domain.models.historical_comparison import HistoricalComparison
from src.domain.models.run_metadata_entry import RunMetadataEntry
from src.presentation.console.format_archived_test_runs_table import (
    format_archived_test_runs_table,
)
from src.presentation.console.format_historical_comparison_table import (
    format_historical_comparison_table,
)
from src.presentation.console.print_archived_test_runs import (
    print_archived_test_runs,
)
from src.presentation.console.print_historical_comparison import (
    print_historical_comparison,
)
from src.presentation.serialization.historical_comparison_to_dict import (
    historical_comparison_to_dict,
)
from tests.result_archive_fixtures import (
    RUN_ID,
    SAMPLING_STARTED_AT,
    SECOND_RUN_ID,
    build_archived_test_run,
    build_failed_archived_test_run,
)


class ResultManagementPresentationTests(unittest.TestCase):
    def test_formats_and_prints_archived_runs_with_no_data(self) -> None:
        successful = build_archived_test_run()
        no_statistics = build_failed_archived_test_run()
        archived_runs = (successful, no_statistics)

        table = format_archived_test_runs_table(archived_runs)

        self.assertIn("Archived Ammeter Test Runs", table)
        self.assertIn(RUN_ID, table)
        self.assertIn(SECOND_RUN_ID, table)
        self.assertIn("| GREENLEE | SUCCESS |", table)
        self.assertIn("| GREENLEE | FAILED", table)
        self.assertIn("|          2/2 |", table)
        self.assertIn("|          0/2 |", table)
        self.assertIn("firmware=1.4.2, operator=Nir", table)
        table_lines = table.splitlines()[1:]
        self.assertEqual(
            {len(line) for line in table_lines},
            {len(table_lines[0])},
        )

        output = io.StringIO()
        with redirect_stdout(output):
            print_archived_test_runs(archived_runs)
        self.assertEqual(output.getvalue(), table + "\n")

    def test_formats_an_empty_archived_run_table(self) -> None:
        table = format_archived_test_runs_table(())

        self.assertIn("Archived Ammeter Test Runs", table)
        self.assertIn("| Run ID ", table)
        self.assertNotIn(RUN_ID, table)
        self.assertEqual(len(table.splitlines()), 5)

    def test_archive_table_escapes_metadata_control_characters(
        self,
    ) -> None:
        archived_run = build_archived_test_run(
            metadata=(
                RunMetadataEntry(
                    key="operator\nname",
                    value="Nir\tQA\nLab",
                ),
            ),
        )

        table = format_archived_test_runs_table((archived_run,))

        self.assertIn(
            r"operator\nname=Nir\tQA\nLab",
            table,
        )
        self.assertEqual(
            {len(line) for line in table.splitlines()[1:]},
            {len(table.splitlines()[1])},
        )

    def test_formats_and_prints_comparison_with_missing_statistics(
        self,
    ) -> None:
        comparison = HistoricalComparison(
            baseline=build_archived_test_run(),
            candidates=(build_failed_archived_test_run(),),
        )

        table = format_historical_comparison_table(comparison)

        self.assertIn("deltas = candidate - baseline", table)
        self.assertIn("BASELINE", table)
        self.assertIn("CANDIDATE 1", table)
        self.assertIn("|          0/2 |", table)
        self.assertIn("| YES", table)
        self.assertIsNone(comparison.statistics_deltas[0])
        table_lines = table.splitlines()[1:]
        self.assertEqual(
            {len(line) for line in table_lines},
            {len(table_lines[0])},
        )

        output = io.StringIO()
        with redirect_stdout(output):
            print_historical_comparison(comparison)
        self.assertEqual(output.getvalue(), table + "\n")

    def test_comparison_serialization_is_json_safe_and_explicit(self) -> None:
        baseline = build_archived_test_run()
        candidate = build_archived_test_run(
            run_id=SECOND_RUN_ID,
            ammeter_type="entes",
            currents=(2.0, 5.0),
        )
        comparison = HistoricalComparison(
            baseline=baseline,
            candidates=(candidate,),
        )

        serialized = historical_comparison_to_dict(comparison)

        self.assertEqual(serialized["baseline"]["run_id"], RUN_ID)
        self.assertEqual(
            serialized["delta_direction"],
            "candidate_minus_baseline",
        )
        candidate_data = serialized["candidates"][0]
        self.assertEqual(
            candidate_data["archived_run"]["run_id"],
            SECOND_RUN_ID,
        )
        self.assertEqual(
            candidate_data["statistics_delta"]["mean_current_delta"],
            1.5,
        )
        self.assertFalse(candidate_data["same_ammeter_type"])
        self.assertTrue(candidate_data["same_sampling_settings"])
        json.dumps(serialized, allow_nan=False)


class ResultManagementExampleTests(unittest.TestCase):
    def test_example_orchestrates_existing_analyses_and_archive_reads(
        self,
    ) -> None:
        baseline = build_archived_test_run()
        candidate = build_archived_test_run(
            run_id=SECOND_RUN_ID,
            currents=(2.0, 4.0),
        )
        comparison = HistoricalComparison(
            baseline=baseline,
            candidates=(candidate,),
        )
        result_manager = Mock()
        result_manager.archive.side_effect = [baseline, candidate]
        result_manager.find.return_value = (candidate, baseline)
        result_manager.compare.return_value = comparison
        framework = Mock()
        framework.results = result_manager
        framework.analyze.side_effect = [
            baseline.analysis,
            candidate.analysis,
        ]

        with (
            patch.object(
                run_result_management,
                "AmmeterTestFramework",
                return_value=framework,
            ) as framework_class,
            patch.object(
                run_result_management,
                "print_archived_test_runs",
            ) as print_archives,
            patch.object(
                run_result_management,
                "print_historical_comparison",
            ) as print_comparison,
        ):
            result = run_result_management.main()

        self.assertIsNone(result)
        framework_class.assert_called_once_with()
        self.assertEqual(
            framework.analyze.call_args_list,
            [call("greenlee"), call("greenlee")],
        )
        self.assertEqual(
            result_manager.archive.call_args_list,
            [
                call(
                    baseline.analysis,
                    metadata={"label": "baseline"},
                ),
                call(
                    candidate.analysis,
                    metadata={"label": "candidate"},
                ),
            ],
        )
        result_manager.find.assert_called_once_with(
            ammeter_type="greenlee"
        )
        result_manager.compare.assert_called_once_with(
            RUN_ID,
            [SECOND_RUN_ID],
        )
        print_archives.assert_called_once_with((candidate, baseline))
        print_comparison.assert_called_once_with(comparison)


if __name__ == "__main__":
    unittest.main()
