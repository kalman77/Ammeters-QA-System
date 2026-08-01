from src.presentation.console.print_sampling_results import (
    print_sampling_results,
)
from src.testing.test_framework import AmmeterTestFramework


def main() -> None:
    """Run the configured sampling window for every ammeter."""
    framework = AmmeterTestFramework()
    results = framework.sample_all()
    print_sampling_results(results.values())


if __name__ == "__main__":
    main()
