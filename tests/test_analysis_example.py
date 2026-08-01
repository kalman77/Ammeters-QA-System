import unittest
from unittest.mock import patch

from examples import run_analysis


class AnalysisExampleTests(unittest.TestCase):
    @patch.object(run_analysis, "print_analysis_results")
    def test_example_prints_results_from_analyze_all(
        self,
        print_analysis_results,
    ) -> None:
        analysis = object()

        class FakeFramework:
            def analyze_all(self):
                return {"greenlee": analysis}

        with patch.object(
            run_analysis,
            "AmmeterTestFramework",
            return_value=FakeFramework(),
        ):
            run_analysis.main()

        print_analysis_results.assert_called_once()
        printed_results = print_analysis_results.call_args.args[0]
        self.assertEqual(list(printed_results), [analysis])


if __name__ == "__main__":
    unittest.main()
