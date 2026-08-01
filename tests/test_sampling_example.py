import unittest
from unittest.mock import patch

from examples import run_sampling


class SamplingExampleTests(unittest.TestCase):
    @patch.object(run_sampling, "print_sampling_results")
    def test_example_prints_results_from_sample_all(
        self,
        print_sampling_results,
    ) -> None:
        result = object()

        class FakeFramework:
            def sample_all(self):
                return {"greenlee": result}

        with patch.object(
            run_sampling,
            "AmmeterTestFramework",
            return_value=FakeFramework(),
        ):
            run_sampling.main()

        print_sampling_results.assert_called_once()
        printed_results = print_sampling_results.call_args.args[0]
        self.assertEqual(list(printed_results), [result])


if __name__ == "__main__":
    unittest.main()
