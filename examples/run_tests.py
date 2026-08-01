from src.presentation.console.print_measurement_results import (
    print_measurement_results,
)
from src.testing.test_framework import AmmeterTestFramework


def main() -> None:
    """Run one typed measurement for every configured ammeter."""
    framework = AmmeterTestFramework()
    results = framework.measure_all()
    print_measurement_results(results.values())


if __name__ == "__main__":
    main()
