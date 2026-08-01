"""Reusable Qt building blocks shared by the desktop pages."""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.presentation.desktop.theme import (
    COLORS,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    status_color,
)


BANNER_STYLES = {
    "error": ("#351a25", "#6b2c40", COLORS["danger"]),
    "warning": ("#33270f", "#6b5424", COLORS["warning"]),
    "info": ("#14263a", "#2c4c6a", COLORS["blue"]),
    "success": ("#13302a", "#2c6d61", COLORS["success"]),
}


class MetricCard(QFrame):
    """Compact labelled value used across the run and results summaries."""

    def __init__(
        self,
        label: str,
        value: str = "—",
        hint: str = "",
        *,
        metric_key: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        if metric_key:
            self.setProperty("metricKey", metric_key)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, 11, SPACE_MD, 11)
        layout.setSpacing(2)

        self.label_widget = QLabel(label)
        self.label_widget.setObjectName("metricLabel")
        self.value_widget = QLabel(value)
        self.value_widget.setObjectName("metricValue")
        self.value_widget.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.hint_widget = QLabel(hint)
        self.hint_widget.setObjectName("metricHint")
        self.hint_widget.setVisible(bool(hint))

        layout.addWidget(self.label_widget)
        layout.addWidget(self.value_widget)
        layout.addWidget(self.hint_widget)

    def update_card(
        self,
        value: object = None,
        hint: object = None,
        *,
        emphasis: Optional[bool] = None,
    ) -> None:
        """Update value, hint, and optional emphasis border in one call."""
        if value is not None:
            self.value_widget.setText(str(value))
        if hint is not None:
            text = str(hint)
            self.hint_widget.setText(text)
            self.hint_widget.setVisible(bool(text))
        if emphasis is not None:
            self.setProperty("emphasis", "true" if emphasis else "false")
            self.style().unpolish(self)
            self.style().polish(self)

    def set_value_color(self, color: str) -> None:
        self.value_widget.setStyleSheet(f"color:{color};")


class SectionCard(QFrame):
    """Panel with a heading, optional caption, and a vertical content area."""

    def __init__(
        self,
        title: str,
        caption: str = "",
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        outer.setSpacing(SPACE_SM)

        header = QHBoxLayout()
        header.setSpacing(SPACE_SM)
        heading = QVBoxLayout()
        heading.setSpacing(1)
        self.title_widget = QLabel(title)
        self.title_widget.setObjectName("sectionTitle")
        heading.addWidget(self.title_widget)
        self.caption_widget = QLabel(caption)
        self.caption_widget.setObjectName("sectionCaption")
        self.caption_widget.setVisible(bool(caption))
        heading.addWidget(self.caption_widget)
        header.addLayout(heading, 1)
        self.header_row = header
        outer.addLayout(header)

        self.content = QVBoxLayout()
        self.content.setSpacing(SPACE_SM)
        outer.addLayout(self.content, 1)

    def add_header_widget(self, widget: QWidget) -> None:
        """Place an action next to the section heading."""
        self.header_row.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_caption(self, caption: str) -> None:
        self.caption_widget.setText(caption)
        self.caption_widget.setVisible(bool(caption))


class StatusPill(QLabel):
    """Coloured status token used in tables, headers, and run stages."""

    def __init__(
        self,
        text: str = "—",
        status: str = "",
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setContentsMargins(10, 4, 10, 4)
        self.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.set_status(text, status)

    def set_status(self, text: str, status: str = "") -> None:
        color = status_color(status or text)
        self.setText(str(text))
        self.setStyleSheet(
            f"color:{color};"
            f"background:{color}22;"
            f"border:1px solid {color}55;"
            "border-radius:9px;font-size:11px;font-weight:700;"
        )


class InlineBanner(QFrame):
    """Dismissable inline message shown above page content."""

    dismissed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("inlineBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_SM, SPACE_SM, SPACE_SM)
        layout.setSpacing(SPACE_SM)

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.dismiss_button = QPushButton("Dismiss")
        self.dismiss_button.setObjectName("linkButton")
        self.dismiss_button.clicked.connect(self._dismiss)

        layout.addWidget(self.message, 1)
        layout.addWidget(self.dismiss_button, 0)
        self.hide()

    def show_message(self, message: str, level: str = "error") -> None:
        background, border, text_color = BANNER_STYLES.get(
            level,
            BANNER_STYLES["error"],
        )
        self.setStyleSheet(
            "QFrame#inlineBanner {"
            f"background:{background};"
            f"border:1px solid {border};"
            "border-radius:10px;}"
        )
        self.message.setStyleSheet(f"color:{text_color};")
        self.message.setText(str(message))
        self.show()

    def clear(self) -> None:
        self.message.clear()
        self.hide()

    def _dismiss(self) -> None:
        self.clear()
        self.dismissed.emit()


class EmptyState(QFrame):
    """Placeholder shown instead of an empty table or detail pane."""

    def __init__(
        self,
        title: str,
        hint: str = "",
        *,
        framed: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        if framed:
            self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_XS)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_widget = QLabel(title)
        self.title_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_widget.setStyleSheet(
            f"color:{COLORS['text_dim']};font-size:15px;font-weight:650;"
        )
        self.hint_widget = QLabel(hint)
        self.hint_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_widget.setWordWrap(True)
        self.hint_widget.setStyleSheet(f"color:{COLORS['muted']};")
        self.hint_widget.setVisible(bool(hint))

        layout.addWidget(self.title_widget)
        layout.addWidget(self.hint_widget)

    def update_text(self, title: str, hint: str = "") -> None:
        self.title_widget.setText(title)
        self.hint_widget.setText(hint)
        self.hint_widget.setVisible(bool(hint))


def field_label(text: str) -> QLabel:
    """Return a small uppercase-style label used above inputs."""
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


def horizontal_divider() -> QFrame:
    """Return a one-pixel separator line."""
    line = QFrame()
    line.setObjectName("divider")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line


def configure_table(
    table: QTableWidget,
    headers: Sequence[str],
    *,
    stretch_column: int = 0,
    row_height: int = 30,
) -> None:
    """Apply the shared table look and selection behaviour."""
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSortingEnabled(True)
    table.verticalHeader().setDefaultSectionSize(row_height)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if 0 <= stretch_column < len(headers):
        header.setSectionResizeMode(
            stretch_column,
            QHeaderView.ResizeMode.Stretch,
        )
    header.setHighlightSections(False)
    # Qt's default indicator is descending, which silently reverses the first
    # fill; pages that want newest-first set their own indicator afterwards.
    table.sortByColumn(0, Qt.SortOrder.AscendingOrder)


SORT_ROLE = Qt.ItemDataRole.UserRole + 1


class SortableTableWidgetItem(QTableWidgetItem):
    """Cell that sorts by a hidden key while displaying formatted text.

    Setting Qt's edit role would also replace the displayed text, so the sort
    key is kept in a private role and compared here instead.
    """

    def __lt__(self, other: object) -> bool:
        if isinstance(other, QTableWidgetItem):
            mine = self.data(SORT_ROLE)
            theirs = other.data(SORT_ROLE)
            if mine is not None and theirs is not None:
                try:
                    return mine < theirs
                except TypeError:
                    return str(mine) < str(theirs)
        return super().__lt__(other)


def table_item(
    text: object,
    *,
    sort_value: Any = None,
    color: Optional[str] = None,
    monospace: bool = False,
    align_right: bool = False,
    tooltip: str = "",
) -> QTableWidgetItem:
    """Create a table cell with optional numeric sorting and styling."""
    item = SortableTableWidgetItem(str(text))
    if sort_value is not None:
        item.setData(SORT_ROLE, sort_value)
    if color:
        item.setForeground(QColor(color))
    if monospace:
        font = QFont()
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamilies(["JetBrains Mono", "DejaVu Sans Mono", "monospace"])
        item.setFont(font)
    if align_right:
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
    if tooltip:
        item.setToolTip(tooltip)
    return item


def fill_table(
    table: QTableWidget,
    rows: Iterable[Sequence[QTableWidgetItem]],
) -> None:
    """Replace a table's contents while keeping sorting stable."""
    materialized = [list(row) for row in rows]
    was_sorting = table.isSortingEnabled()
    table.setSortingEnabled(False)
    table.clearContents()
    table.setRowCount(len(materialized))
    for row_index, cells in enumerate(materialized):
        for column_index, cell in enumerate(cells):
            table.setItem(row_index, column_index, cell)
    table.setSortingEnabled(was_sorting)
