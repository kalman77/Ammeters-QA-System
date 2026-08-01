"""Palette, spacing scale, and the Qt stylesheet for the desktop UI."""

from __future__ import annotations

from typing import Dict


COLORS: Dict[str, str] = {
    "background": "#0a1018",
    "sidebar": "#0d141f",
    "surface": "#121b28",
    "surface_alt": "#182333",
    "surface_hover": "#1f2c3f",
    "border": "#243247",
    "border_strong": "#33455f",
    "text": "#e9f0fa",
    "text_dim": "#b6c6da",
    "muted": "#7f95af",
    "accent": "#3fd9b4",
    "accent_hover": "#5ce8c6",
    "accent_ink": "#04231d",
    "blue": "#5aa9ff",
    "purple": "#a08cff",
    "warning": "#ffb44d",
    "danger": "#ff6b7d",
    "success": "#3fd98a",
}


AMMETER_COLORS: Dict[str, str] = {
    "greenlee": "#5aa9ff",
    "entes": "#a08cff",
    "circutor": "#3fd9b4",
}


FALLBACK_SERIES_COLORS = (
    "#ffb44d",
    "#ff6b7d",
    "#3fd98a",
    "#7f95af",
)


STATUS_COLORS: Dict[str, str] = {
    "success": COLORS["success"],
    "partial": COLORS["warning"],
    "failed": COLORS["danger"],
}


# One spacing scale keeps every page aligned to the same rhythm.
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 14
SPACE_LG = 20
SPACE_XL = 28


def ammeter_color(name: object, *, index: int = 0) -> str:
    """Return a stable plot colour for one ammeter name."""
    key = str(name).strip().lower()
    if key in AMMETER_COLORS:
        return AMMETER_COLORS[key]
    return FALLBACK_SERIES_COLORS[index % len(FALLBACK_SERIES_COLORS)]


def status_color(status: object) -> str:
    """Return the palette colour matching a measurement status string."""
    return STATUS_COLORS.get(str(status).strip().lower(), COLORS["muted"])


APP_STYLESHEET = """
* {
    font-family: "Inter", "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 13px;
    color: #e9f0fa;
}
QMainWindow, QWidget#appRoot, QStackedWidget {
    background: #0a1018;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: 0;
}

/* ---------- sidebar ---------- */
QWidget#sidebar {
    background: #0d141f;
    border-right: 1px solid #1d2a3c;
}
QLabel#brandMark {
    color: #3fd9b4;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 2.5px;
}
QLabel#brandTitle {
    color: #ffffff;
    font-size: 19px;
    font-weight: 700;
}
QLabel#brandCaption {
    color: #7f95af;
    font-size: 11px;
}
QPushButton#navButton {
    background: transparent;
    border: 0;
    border-left: 3px solid transparent;
    border-radius: 8px;
    color: #93a8c2;
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
}
QPushButton#navButton:hover {
    background: #162334;
    color: #ffffff;
}
QPushButton#navButton:checked {
    background: #162c3a;
    border-left: 3px solid #3fd9b4;
    color: #5ce8c6;
}
QLabel#sidebarFooter {
    color: #64798f;
    font-size: 11px;
}

/* ---------- headings and panels ---------- */
QLabel#pageTitle {
    color: #ffffff;
    font-size: 24px;
    font-weight: 700;
}
QLabel#pageSubtitle, QLabel[muted="true"] {
    color: #7f95af;
}
QLabel#sectionTitle {
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
}
QLabel#sectionCaption {
    color: #7f95af;
    font-size: 11px;
}
QLabel#fieldLabel {
    color: #b6c6da;
    font-size: 11px;
    font-weight: 650;
}
QFrame#panel {
    background: #121b28;
    border: 1px solid #243247;
    border-radius: 12px;
}
QFrame#metricCard {
    background: #121b28;
    border: 1px solid #243247;
    border-radius: 12px;
    min-height: 74px;
}
QFrame#metricCard[emphasis="true"] {
    border: 1px solid #2c6d61;
}
QLabel#metricLabel {
    color: #7f95af;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
}
QLabel#metricValue {
    color: #ffffff;
    font-size: 20px;
    font-weight: 700;
}
QLabel#metricHint {
    color: #64798f;
    font-size: 10px;
}
QFrame#divider {
    background: #243247;
    max-height: 1px;
    border: 0;
}

/* ---------- buttons ---------- */
QPushButton {
    background: #1a2739;
    border: 1px solid #2e4059;
    border-radius: 8px;
    padding: 8px 13px;
    font-weight: 600;
}
QPushButton:hover {
    background: #223349;
    border-color: #435c7c;
}
QPushButton:pressed {
    background: #16202f;
}
QPushButton:disabled {
    background: #141d2b;
    border-color: #212e41;
    color: #55697f;
}
QPushButton#primaryButton {
    background: #3fd9b4;
    border: 0;
    color: #04231d;
    font-size: 14px;
    font-weight: 800;
    padding: 11px 18px;
}
QPushButton#primaryButton:hover {
    background: #5ce8c6;
}
QPushButton#primaryButton:disabled {
    background: #1d3c37;
    color: #5c8b82;
}
QPushButton#dangerButton {
    background: #351a25;
    border-color: #6b2c40;
    color: #ff8f9e;
}
QPushButton#dangerButton:hover {
    background: #46212f;
}
QPushButton#linkButton {
    background: transparent;
    border: 0;
    color: #5aa9ff;
    padding: 4px 2px;
    text-align: left;
}
QPushButton#linkButton:hover {
    color: #8cc4ff;
}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit,
QTextEdit {
    background: #0e1724;
    border: 1px solid #2a3a52;
    border-radius: 7px;
    padding: 7px 9px;
    min-height: 20px;
    selection-background-color: #2a6055;
    selection-color: #ffffff;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #3a4f6e;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid #3fd9b4;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled {
    background: #101823;
    color: #55697f;
}
QComboBox::drop-down {
    border: 0;
    width: 18px;
}
QComboBox QAbstractItemView {
    background: #16202f;
    border: 1px solid #2e4059;
    selection-background-color: #22544b;
    outline: 0;
    padding: 4px;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background: #1a2739;
    border: 0;
    width: 15px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background: #2a3d56;
}
QCheckBox {
    spacing: 8px;
    color: #cfdcec;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #45597a;
    border-radius: 4px;
    background: #0e1724;
}
QCheckBox::indicator:hover {
    border-color: #3fd9b4;
}
QCheckBox::indicator:checked {
    background: #3fd9b4;
    border-color: #3fd9b4;
}
QGroupBox {
    border: 1px solid #243247;
    border-radius: 10px;
    margin-top: 16px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #b6c6da;
    font-size: 11px;
    font-weight: 700;
}

/* ---------- tables ---------- */
QTableWidget, QTableView, QListWidget {
    background: #0f1826;
    alternate-background-color: #121c2b;
    border: 1px solid #243247;
    border-radius: 10px;
    gridline-color: #1c2739;
    selection-background-color: #1e4f49;
    selection-color: #ffffff;
    outline: 0;
}
QListWidget::item {
    padding: 7px 9px;
    border-radius: 6px;
}
QListWidget::item:hover {
    background: #1a2739;
}
QHeaderView::section {
    background: #182333;
    color: #9db1c8;
    border: 0;
    border-right: 1px solid #243247;
    border-bottom: 1px solid #243247;
    padding: 8px;
    font-size: 11px;
    font-weight: 700;
}
QHeaderView::section:hover {
    background: #21304a;
}
QTableCornerButton::section {
    background: #182333;
    border: 0;
}

/* ---------- tabs ---------- */
QTabWidget::pane {
    border: 1px solid #243247;
    border-radius: 10px;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #8ea3c0;
    padding: 8px 16px;
    margin-right: 4px;
    border-radius: 8px;
    font-weight: 650;
}
QTabBar::tab:hover {
    color: #ffffff;
}
QTabBar::tab:selected {
    background: #1b2f3c;
    color: #5ce8c6;
}

/* ---------- misc ---------- */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #2f4460;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #3d587a;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #2f4460;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QProgressBar {
    background: #14202f;
    border: 0;
    border-radius: 4px;
    max-height: 7px;
    text-align: center;
}
QProgressBar::chunk {
    background: #3fd9b4;
    border-radius: 4px;
}
QSplitter::handle {
    background: transparent;
    width: 10px;
    height: 10px;
}
QToolTip {
    background: #1b2839;
    color: #ffffff;
    border: 1px solid #3a5271;
    border-radius: 6px;
    padding: 5px 7px;
}
QStatusBar {
    background: #0d141f;
    border-top: 1px solid #1d2a3c;
    color: #7f95af;
}
"""
