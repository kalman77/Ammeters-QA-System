from src.presentation.console.print_archived_test_runs import (
    print_archived_test_runs,
)
from src.presentation.console.print_historical_comparison import (
    print_historical_comparison,
)
from src.testing.test_framework import AmmeterTestFramework


def main() -> None:
    """Archive two analyses, list history, and compare the new runs."""
    framework = AmmeterTestFramework()
    baseline_analysis = framework.analyze("greenlee")
    candidate_analysis = framework.analyze("greenlee")
    baseline = framework.results.archive(
        baseline_analysis,
        metadata={"label": "baseline"},
    )
    candidate = framework.results.archive(
        candidate_analysis,
        metadata={"label": "candidate"},
    )

    print_archived_test_runs(
        framework.results.find(ammeter_type="greenlee")
    )
    print_historical_comparison(
        framework.results.compare(
            baseline.run_id,
            [candidate.run_id],
        )
    )


if __name__ == "__main__":
    main()
