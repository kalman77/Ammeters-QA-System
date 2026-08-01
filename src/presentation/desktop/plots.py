"""PyQtGraph charts for live sampling, archived runs, and comparisons."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget

from src.presentation.desktop.formatting import finite
from src.presentation.desktop.theme import COLORS, SPACE_SM, ammeter_color
from src.presentation.desktop.view_models import build_plot_series


pg.setConfigOption("antialias", True)


def _styled_plot(
    *,
    left_label: str,
    left_units: Optional[str],
    bottom_label: str,
) -> pg.PlotWidget:
    plot = pg.PlotWidget()
    plot.setBackground(COLORS["surface"])
    plot.showGrid(x=True, y=True, alpha=0.15)
    plot.setLabel("left", left_label, units=left_units, color=COLORS["muted"])
    plot.setLabel(
        "bottom",
        bottom_label,
        units="s",
        color=COLORS["muted"],
    )
    item = plot.getPlotItem()
    item.setMenuEnabled(False)
    item.getAxis("left").setTextPen(COLORS["muted"])
    item.getAxis("bottom").setTextPen(COLORS["muted"])
    item.getAxis("left").setPen(COLORS["border_strong"])
    item.getAxis("bottom").setPen(COLORS["border_strong"])
    return plot


class MeasurementPlot(QWidget):
    """Current-versus-time chart paired with a request-timing chart."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_SM)

        self.current_plot = _styled_plot(
            left_label="Current",
            left_units="A",
            bottom_label="Elapsed",
        )
        self.current_plot.setObjectName("currentPlot")
        self.current_plot.getPlotItem().addLegend(
            offset=(10, 10),
            labelTextColor=COLORS["text_dim"],
            brush=pg.mkBrush(COLORS["surface_alt"]),
            pen=pg.mkPen(COLORS["border"]),
        )

        self.timing_plot = _styled_plot(
            left_label="Latency",
            left_units=None,
            bottom_label="Elapsed",
        )
        self.timing_plot.setObjectName("timingPlot")
        self.timing_plot.setMaximumHeight(170)
        self.timing_plot.getAxis("left").enableAutoSIPrefix(False)
        self.timing_plot.getAxis("left").setWidth(58)
        self.timing_plot.setLabel("left", "ms", color=COLORS["muted"])
        self.timing_plot.getPlotItem().addLegend(
            offset=(-12, 10),
            labelTextColor=COLORS["text_dim"],
            brush=pg.mkBrush(COLORS["surface_alt"]),
            pen=pg.mkPen(COLORS["border"]),
        )

        layout.addWidget(self.current_plot, 3)
        layout.addWidget(self.timing_plot, 1)

        self._live: Dict[str, Dict[str, List[float]]] = {}
        self._current_curves: Dict[str, pg.PlotDataItem] = {}
        self._failure_items: Dict[str, pg.ScatterPlotItem] = {}
        self._latency_curves: Dict[str, pg.PlotDataItem] = {}

    def reset(self) -> None:
        """Clear both charts and every cached live series."""
        self.current_plot.clear()
        self.timing_plot.clear()
        self._live.clear()
        self._current_curves.clear()
        self._failure_items.clear()
        self._latency_curves.clear()
        for plot in (self.current_plot, self.timing_plot):
            legend = plot.getPlotItem().legend
            if legend is not None:
                legend.clear()

    def extend_live(
        self,
        batch: Sequence[Tuple[str, Mapping[str, Any]]],
    ) -> None:
        """Append a batch of streamed samples and redraw affected series."""
        touched = set()
        for ammeter_type, sample in batch:
            series = self._live.setdefault(
                ammeter_type,
                {"x": [], "y": [], "failure_x": [], "latency": []},
            )
            elapsed = finite(sample.get("elapsed_seconds"))
            if elapsed is None:
                elapsed = float(len(series["x"]))
            value = finite(sample.get("current"))
            if str(sample.get("status")) == "success" and value is not None:
                series["x"].append(elapsed)
                series["y"].append(value)
            else:
                series["failure_x"].append(elapsed)
            latency = finite(sample.get("latency_seconds"))
            series["latency"].append(
                (elapsed, latency * 1000.0 if latency is not None else 0.0)
            )
            touched.add(ammeter_type)

        for index, ammeter_type in enumerate(sorted(touched)):
            self._redraw_live(ammeter_type, index)

    def _redraw_live(self, ammeter_type: str, index: int) -> None:
        series = self._live[ammeter_type]
        color = ammeter_color(ammeter_type, index=index)
        label = str(ammeter_type).title()

        curve = self._current_curves.get(ammeter_type)
        if curve is None:
            curve = self.current_plot.plot(
                name=label,
                pen=pg.mkPen(color, width=2),
                symbol="o",
                symbolSize=6,
                symbolBrush=color,
                symbolPen=pg.mkPen(color),
            )
            self._current_curves[ammeter_type] = curve
        curve.setData(series["x"], series["y"])

        if series["failure_x"]:
            failures = self._failure_items.get(ammeter_type)
            if failures is None:
                failures = pg.ScatterPlotItem(
                    symbol="x",
                    size=12,
                    pen=pg.mkPen(COLORS["danger"], width=2),
                    brush=None,
                )
                self.current_plot.addItem(failures)
                self._failure_items[ammeter_type] = failures
            baseline = (
                sum(series["y"]) / len(series["y"]) if series["y"] else 0.0
            )
            failures.setData(
                series["failure_x"],
                [baseline] * len(series["failure_x"]),
            )

        latency_curve = self._latency_curves.get(ammeter_type)
        if latency_curve is None:
            latency_curve = self.timing_plot.plot(
                name=f"{label} latency",
                pen=pg.mkPen(color, width=2),
            )
            self._latency_curves[ammeter_type] = latency_curve
        latency_curve.setData(
            [point[0] for point in series["latency"]],
            [point[1] for point in series["latency"]],
        )

    def show_analysis(self, analysis: Mapping[str, Any]) -> None:
        """Render one completed analysis, replacing any live series."""
        self.reset()
        series = build_plot_series(analysis)
        ammeter_type = series["ammeter_type"]
        color = ammeter_color(ammeter_type)
        label = str(ammeter_type).title() or "Samples"

        if series["current_x"]:
            self.current_plot.plot(
                series["current_x"],
                series["current_y"],
                name=label,
                pen=pg.mkPen(color, width=2),
                symbol="o",
                symbolSize=7,
                symbolBrush=color,
                symbolPen=pg.mkPen(color),
            )

        span = series["span"]
        for key, line_label, line_color, style in (
            ("mean", "Mean", COLORS["accent"], Qt.PenStyle.DashLine),
            ("minimum", "Min", COLORS["muted"], Qt.PenStyle.DotLine),
            ("maximum", "Max", COLORS["muted"], Qt.PenStyle.DotLine),
        ):
            value = series[key]
            if value is None:
                continue
            self.current_plot.plot(
                span,
                [value, value],
                name=line_label,
                pen=pg.mkPen(line_color, width=1.6, style=style),
            )

        if series["failure_x"]:
            baseline = series["mean"]
            if baseline is None:
                baseline = (
                    sum(series["current_y"]) / len(series["current_y"])
                    if series["current_y"]
                    else 0.0
                )
            self.current_plot.addItem(
                pg.ScatterPlotItem(
                    x=series["failure_x"],
                    y=[baseline] * len(series["failure_x"]),
                    symbol="x",
                    size=13,
                    pen=pg.mkPen(COLORS["danger"], width=2),
                    brush=None,
                )
            )

        if series["latency_x"]:
            self.timing_plot.plot(
                series["latency_x"],
                series["latency_y"],
                name="Request latency",
                pen=pg.mkPen(COLORS["blue"], width=2),
            )
        if series["timing_x"]:
            self.timing_plot.plot(
                series["timing_x"],
                series["timing_y"],
                name="Schedule error",
                pen=pg.mkPen(
                    COLORS["warning"],
                    width=1.6,
                    style=Qt.PenStyle.DashLine,
                ),
            )


class ComparisonBarChart(pg.PlotWidget):
    """Categorical chart for one statistic across compared runs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonChart")
        self.setBackground(COLORS["surface"])
        self.showGrid(x=False, y=True, alpha=0.15)
        item = self.getPlotItem()
        item.setMenuEnabled(False)
        item.getAxis("left").setTextPen(COLORS["muted"])
        item.getAxis("bottom").setTextPen(COLORS["muted"])
        self.setLabel("bottom", "Compared runs", color=COLORS["muted"])

    def set_series(
        self,
        series: Sequence[Mapping[str, Any]],
        *,
        label: str,
        unit: str = "",
    ) -> None:
        """Draw one bar per run, highlighting the baseline."""
        self.clear()
        points = [
            entry for entry in series if finite(entry.get("value")) is not None
        ]
        if not points:
            self.setTitle(
                "No comparable values for this metric",
                color=COLORS["muted"],
                size="11pt",
            )
            self.getAxis("bottom").setTicks([[]])
            return

        heights = [float(entry["value"]) for entry in points]
        positions = list(range(len(points)))
        brushes = []
        pens = []
        for index, entry in enumerate(points):
            color = QColor(
                ammeter_color(entry.get("ammeter_type"), index=index)
            )
            if entry.get("is_baseline"):
                pens.append(pg.mkPen(COLORS["accent"], width=2))
            else:
                pens.append(pg.mkPen(color, width=1))
            brushes.append(color)

        self.addItem(
            pg.BarGraphItem(
                x=positions,
                height=heights,
                width=0.58,
                brushes=brushes,
                pens=pens,
            )
        )
        self.getAxis("bottom").setTicks(
            [
                [
                    (
                        index,
                        f"{entry.get('ammeter_display', '')}\n"
                        f"{entry.get('short_id', '')}"
                        + ("\n(baseline)" if entry.get("is_baseline") else ""),
                    )
                    for index, entry in enumerate(points)
                ]
            ]
        )
        self.setLabel(
            "left",
            f"{label} ({unit})" if unit else label,
            color=COLORS["muted"],
        )
        self.setTitle(label, color=COLORS["text"], size="11pt")

        finite_heights = [value for value in heights if math.isfinite(value)]
        if finite_heights:
            low = min(finite_heights + [0.0])
            high = max(finite_heights + [0.0])
            padding = (high - low) * 0.15 or 1.0
            self.setYRange(low - padding, high + padding)
