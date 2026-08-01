"""Allow ``python -m src.presentation.desktop`` to start the console."""

from src.presentation.desktop.app import main


if __name__ == "__main__":
    raise SystemExit(main())
