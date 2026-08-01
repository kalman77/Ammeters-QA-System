from src.presentation.console.print_analysis_results import (
    print_analysis_results,
)
from src.testing.test_framework import AmmeterTestFramework


def main() -> None:
    """Sample every configured ammeter and print current statistics."""
    framework = AmmeterTestFramework()
    analyses = framework.analyze_all()
    print_analysis_results(analyses.values())


if __name__ == "__main__":
    main()
