"""Desktop application entry point and Qt bootstrap."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from src.infrastructure.config.default_config_path import DEFAULT_CONFIG_PATH
from src.presentation.desktop.main_window import MainWindow
from src.presentation.desktop.run_service import DesktopRunService
from src.presentation.desktop.theme import APP_STYLESHEET, COLORS


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the desktop entry point."""
    parser = argparse.ArgumentParser(
        prog="ammeter-desktop",
        description=(
            "Desktop console for running, archiving, and comparing ammeter "
            "sampling tests."
        ),
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to the YAML configuration file.",
    )
    return parser


def application_icon() -> QIcon:
    """Draw a small program icon so the window has a stable identity."""
    pixmap = QPixmap(QSize(64, 64))
    pixmap.fill(QColor(COLORS["background"]))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(COLORS["accent"]))
    painter.setBrush(QColor(COLORS["surface_alt"]))
    painter.drawRoundedRect(6, 6, 52, 52, 14, 14)
    painter.setPen(QColor(COLORS["accent"]))
    font = painter.font()
    font.setPointSize(26)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(
        pixmap.rect(),
        Qt.AlignmentFlag.AlignCenter,
        "A",
    )
    painter.end()
    return QIcon(pixmap)


def create_window(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> Tuple[MainWindow, DesktopRunService]:
    """Create the service and main window without starting the event loop."""
    service = DesktopRunService(config_path)
    return MainWindow(service), service


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Start the Qt application and run the desktop console."""
    arguments = build_parser().parse_args(
        list(argv) if argv is not None else None
    )

    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName("Ammeter QA Test Console")
    application.setOrganizationName("AmmeterQA")
    application.setStyleSheet(APP_STYLESHEET)
    application.setWindowIcon(application_icon())

    try:
        window, _service = create_window(arguments.config)
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Configuration error",
            f"The desktop console could not start:\n\n{exc}",
        )
        return 1

    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
