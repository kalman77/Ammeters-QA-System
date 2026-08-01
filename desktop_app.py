"""Convenience entry point for the ammeter desktop console."""

import os
import sys


os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

from src.presentation.desktop.app import main


if __name__ == "__main__":
    try:
        exit_code = main()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(exit_code)
