# ui.py
# AnalytX — Main Window (PyQt6)
# Matches the design from the approved HTML dummy.
# Handles: browse, start, stop/save, new-session modal,
#          live event tables, autoscroll, search/filter,
#          metric cards, export report.

import logging
import os
import sys
import webbrowser
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QDialog, QFrame, QSizePolicy,
    QAbstractItemView, QApplication, QGraphicsOpacityEffect
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, QObject, pyqtSignal, QSize,
    QPropertyAnimation, QEasingCurve, pyqtProperty
)
from PyQt6.QtGui import (
    QColor, QFont, QIcon, QPalette, QBrush,
    QLinearGradient, QPainter, QPen, QPixmap
)

import database as db
import reporter as rpt
from launcher import Launcher


# ─────────────────────────────────────────────
#  Colour Palette  (mirrors CSS variables)
# ─────────────────────────────────────────────

C = {
    "bg":           "#08090d",
    "bg_surface":   "#0c0e14",
    "bg_elevated":  "#111420",
    "bg_card":      "#161a26",
    "bg_hover":     "#1a1f2e",
    "border":       "rgba(255,255,255,0.055)",
    "border_md":    "#1e2538",

    "blue":         "#6395ff",
    "blue_soft":    "#0f1a30",
    "green":        "#3ecf8e",
    "green_soft":   "#0b1f16",
    "red":          "#f55f5f",
    "red_soft":     "#200f0f",
    "amber":        "#f5a623",
    "amber_soft":   "#201508",
    "purple":       "#a78bfa",
    "purple_soft":  "#160f2a",
    "teal":         "#2dd4bf",
    "teal_soft":    "#081e1c",

    "text_1":       "#eef0f6",
    "text_2":       "#8892a4",
    "text_3":       "#4a5366",
    "text_4":       "#2a3044",
}

# ─────────────────────────────────────────────
#  Stylesheet
# ─────────────────────────────────────────────

STYLESHEET = f"""
/* ── Base ── */
QMainWindow, QWidget {{
    background: {C['bg']};
    color: {C['text_1']};
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}}

/* ── Header ── */
#header {{
    background: {C['bg_surface']};
    border-bottom: 1px solid {C['border_md']};
    min-height: 52px;
    max-height: 52px;
}}

#brandName {{
    font-size: 16px;
    font-weight: 700;
    color: {C['text_1']};
    letter-spacing: -0.3px;
}}

#brandX {{ color: {C['blue']}; }}

#versionChip {{
    font-size: 11px;
    color: {C['text_3']};
    background: {C['bg_elevated']};
    border: 1px solid {C['border_md']};
    border-radius: 999px;
    padding: 3px 10px;
}}

#statusChip {{
    font-size: 11px;
    font-weight: 500;
    background: {C['bg_elevated']};
    border: 1px solid {C['border_md']};
    border-radius: 999px;
    padding: 5px 12px;
    color: {C['text_2']};
}}

#statusChip[state="running"] {{
    background: {C['green_soft']};
    border-color: #1a4a30;
    color: {C['green']};
}}

#statusChip[state="stopped"] {{
    background: {C['red_soft']};
    border-color: #3a1a1a;
    color: {C['red']};
}}

#sessionInfoLabel {{
    font-size: 11px;
    color: {C['text_3']};
    font-family: 'Consolas', 'Courier New', monospace;
}}

/* ── Toolbar ── */
#toolbar {{
    background: {C['bg_surface']};
    border-bottom: 1px solid {C['border_md']};
    min-height: 58px;
    max-height: 58px;
    padding: 0 20px;
}}

#targetField {{
    background: {C['bg_elevated']};
    border: 1px solid {C['border_md']};
    border-radius: 12px;
    padding: 0px;
    color: {C['text_1']};
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    selection-background-color: {C['blue_soft']};
}}

#targetField:focus {{
    border-color: {C['blue']};
    background: {C['bg_elevated']};
    outline: none;
}}

/* ── Buttons ── */
QPushButton {{
    border-radius: 10px;
    font-size: 13px;
    font-weight: 500;
    padding: 8px 18px;
    border: 1px solid transparent;
    outline: none;
}}

#btnBrowse {{
    background: {C['bg_elevated']};
    border-color: {C['border_md']};
    color: {C['text_2']};
    border-radius: 0 10px 10px 0;
    padding: 8px 14px;
    min-width: 70px;
}}

#btnBrowse:hover {{ color: {C['blue']}; border-color: #2a3f6a; background: {C['blue_soft']}; }}

#btnStart {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #2e7d56, stop:1 #3ecf8e);
    color: white;
    font-weight: 600;
    border: none;
    min-width: 140px;
}}

#btnStart:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #357a57, stop:1 #45d898); }}
#btnStart:pressed {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #256144, stop:1 #35b87c); }}

#btnStop {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #a83535, stop:1 #f55f5f);
    color: white;
    font-weight: 600;
    border: none;
    min-width: 120px;
}}

#btnStop:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #b84040, stop:1 #f57070); }}

#btnReport {{
    background: {C['blue_soft']};
    border-color: #2a3f6a;
    color: {C['blue']};
    font-weight: 500;
    min-width: 130px;
}}

#btnReport:hover {{ background: #162040; border-color: {C['blue']}; }}

/* ── Metrics ── */
#metricsBar {{
    background: {C['bg_surface']};
    border-bottom: 1px solid {C['border_md']};
    min-height: 62px;
    max-height: 62px;
}}

.MetricCard {{
    background: {C['bg_surface']};
    border-right: 1px solid {C['border_md']};
}}

.MetricCard:hover {{ background: {C['bg_elevated']}; }}

#metricVal {{
    font-size: 22px;
    font-weight: 700;
    color: {C['text_1']};
    letter-spacing: -0.5px;
}}

#metricLbl {{
    font-size: 11px;
    color: {C['text_3']};
    font-weight: 500;
}}

/* ── Tabs ── */
QTabWidget::pane {{
    border: none;
    background: {C['bg']};
}}

QTabBar {{
    background: {C['bg_surface']};
}}

QTabBar::tab {{
    background: {C['bg_surface']};
    color: {C['text_3']};
    padding: 10px 18px;
    font-size: 12px;
    font-weight: 500;
    border: none;
    border-bottom: 2px solid transparent;
    min-width: 100px;
}}

QTabBar::tab:hover {{ color: {C['text_2']}; background: {C['bg_surface']}; }}

QTabBar::tab:selected {{
    color: {C['text_1']};
    border-bottom: 2px solid {C['blue']};
    background: {C['bg_surface']};
}}

/* ── Tables ── */
QTableWidget {{
    background: {C['bg']};
    border: none;
    gridline-color: {C['border_md']};
    color: {C['text_1']};
    selection-background-color: {C['bg_hover']};
    selection-color: {C['text_1']};
    font-size: 12px;
    outline: none;
}}

QTableWidget::item {{
    padding: 6px 14px;
    border-bottom: 1px solid {C['border_md']};
}}

QTableWidget::item:hover {{ background: {C['bg_hover']}; }}
QTableWidget::item:selected {{ background: {C['bg_hover']}; color: {C['text_1']}; }}

QHeaderView::section {{
    background: {C['bg_elevated']};
    color: {C['text_3']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 8px 14px;
    border: none;
    border-bottom: 1px solid {C['border_md']};
    border-right: 1px solid {C['border_md']};
}}

/* ── Search ── */
#searchInput {{
    background: {C['bg_elevated']};
    border: 1px solid {C['border_md']};
    border-radius: 999px;
    padding: 6px 14px;
    color: {C['text_1']};
    font-size: 12px;
    min-width: 160px;
}}

#searchInput:focus {{ border-color: {C['blue']}; outline: none; }}

/* ── Autoscroll button ── */
#autoscrollBtn {{
    background: {C['bg_elevated']};
    border: 1px solid {C['border_md']};
    border-radius: 999px;
    color: {C['text_3']};
    font-size: 11px;
    padding: 6px 12px;
}}

#autoscrollBtn[on="true"] {{
    background: {C['green_soft']};
    border-color: #1a4a30;
    color: {C['green']};
}}

/* ── Status bar ── */
#statusBar {{
    background: {C['bg_surface']};
    border-top: 1px solid {C['border_md']};
    min-height: 28px;
    max-height: 28px;
}}

#sbLabel {{ font-size: 11px; color: {C['text_3']}; }}
#sbFile    {{ font-size: 11px; font-weight: 600; color: {C['blue']}; }}
#sbNetwork {{ font-size: 11px; font-weight: 600; color: {C['green']}; }}
#sbProcess {{ font-size: 11px; font-weight: 600; color: {C['purple']}; }}

/* ── Scrollbars ── */
QScrollBar:vertical {{
    background: {C['bg']};
    width: 5px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {C['border_md']};
    border-radius: 2px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {C['text_3']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: {C['bg']};
    height: 5px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {C['border_md']};
    border-radius: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {C['text_3']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Modal dialog ── */
#NewSessionDialog {{
    background: {C['bg_card']};
    border: 1px solid {C['border_md']};
    border-radius: 20px;
}}

#modalTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {C['text_1']};
    letter-spacing: -0.3px;
}}

#modalDesc {{
    font-size: 13px;
    color: {C['text_2']};
    line-height: 1.6;
}}

#btnDiscard {{
    background: {C['red_soft']};
    border: 1px solid #3a1a1a;
    color: {C['red']};
    font-weight: 600;
    border-radius: 10px;
    padding: 8px 16px;
}}
#btnDiscard:hover {{ background: #2a1010; }}

#btnSaveStart {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #2e7d56, stop:1 #3ecf8e);
    color: white;
    font-weight: 600;
    border: none;
    border-radius: 10px;
    padding: 8px 16px;
}}
#btnSaveStart:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #357a57, stop:1 #45d898); }}

#btnCancelModal {{
    background: {C['bg_elevated']};
    border: 1px solid {C['border_md']};
    color: {C['text_2']};
    border-radius: 10px;
    padding: 8px 16px;
}}
#btnCancelModal:hover {{ color: {C['text_1']}; background: {C['bg_hover']}; }}
"""


# ─────────────────────────────────────────────
#  Helper: make a coloured label badge
# ─────────────────────────────────────────────

OP_COLORS = {
    "create":  ("#6395ff", "#0f1a30"),
    "read":    ("#8892a4", "#111420"),
    "write":   ("#f5a623", "#201508"),
    "delete":  ("#f55f5f", "#200f0f"),
    "query":   ("#8892a4", "#111420"),
    "connect": ("#3ecf8e", "#0b1f16"),
    "send":    ("#5cd49a", "#0b1f16"),
    "receive": ("#7cb8ff", "#0d1828"),
    "spawn":   ("#a78bfa", "#160f2a"),
    "exit":    ("#f55f5f", "#200f0f"),
}

CAT_COLORS = {
    "file":    ("#6395ff", "#0f1a30"),
    "network": ("#3ecf8e", "#0b1f16"),
    "process": ("#a78bfa", "#160f2a"),
}


def make_badge_item(text: str, color_map: dict) -> QTableWidgetItem:
    """Returns a QTableWidgetItem styled as a colored badge."""
    key   = text.lower()
    fg, bg = color_map.get(key, (C["text_2"], C["bg_elevated"]))
    item  = QTableWidgetItem(f"  {text.upper()}  ")
    item.setForeground(QColor(fg))
    item.setBackground(QColor(bg))
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    return item


def make_item(text: str, color: str = None, mono: bool = False,
              align=Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text))
    if color:
        item.setForeground(QColor(color))
    if mono:
        f = QFont("Consolas", 11)
        item.setFont(f)
    item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    return item


# ─────────────────────────────────────────────
#  New Session Confirmation Dialog
# ─────────────────────────────────────────────

class NewSessionDialog(QDialog):
    """
    Shown when Start is clicked while a session already exists.
    Returns:  "cancel" | "discard" | "save"
    """

    def __init__(self, parent, event_count: int):
        super().__init__(parent)
        self.choice = "cancel"
        self.setObjectName("NewSessionDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build(event_count)
        self.setFixedWidth(430)

    def _build(self, event_count: int):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("NewSessionDialog")
        card.setStyleSheet(f"""
            #NewSessionDialog {{
                background: {C['bg_card']};
                border: 1px solid {C['border_md']};
                border-radius: 20px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        # Icon
        icon_lbl = QLabel("⚠")
        icon_lbl.setStyleSheet(f"""
            font-size: 20px;
            color: {C['amber']};
            background: {C['amber_soft']};
            border: 1px solid #3a2a08;
            border-radius: 10px;
            padding: 10px;
            max-width: 44px;
            max-height: 44px;
            min-width: 44px;
            min-height: 44px;
        """)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setFixedSize(44, 44)

        title = QLabel("Start a New Session?")
        title.setObjectName("modalTitle")
        title.setStyleSheet(f"font-size:16px; font-weight:700; color:{C['text_1']}; letter-spacing:-0.3px;")

        desc = QLabel(
            f"A previous monitoring session already exists with "
            f"<b style='color:{C['text_1']}'>{event_count:,}</b> captured events.<br><br>"
            f"Would you like to save a report before starting fresh, "
            f"or discard the session data?"
        )
        desc.setObjectName("modalDesc")
        desc.setStyleSheet(f"font-size:13px; color:{C['text_2']}; line-height:1.6;")
        desc.setWordWrap(True)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel  = QPushButton("Cancel")
        btn_discard = QPushButton("Discard && Start New")
        btn_save    = QPushButton("Save Report && Start New")

        btn_cancel.setObjectName("btnCancelModal")
        btn_discard.setObjectName("btnDiscard")
        btn_save.setObjectName("btnSaveStart")

        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_discard.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_cancel.clicked.connect(self._cancel)
        btn_discard.clicked.connect(self._discard)
        btn_save.clicked.connect(self._save)

        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(btn_discard)
        btn_row.addWidget(btn_save)

        layout.addWidget(icon_lbl)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addSpacing(6)
        layout.addLayout(btn_row)

        outer.addWidget(card)

    def _cancel(self):
        self.choice = "cancel"
        self.reject()

    def _discard(self):
        self.choice = "discard"
        self.accept()

    def _save(self):
        self.choice = "save"
        self.accept()


# ─────────────────────────────────────────────
#  Metric Card Widget
# ─────────────────────────────────────────────

class MetricCard(QWidget):
    def __init__(self, label: str, icon: str, icon_color: str, icon_bg: str):
        super().__init__()
        self.setProperty("class", "MetricCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        # Icon box
        icon_box = QLabel(icon)
        icon_box.setFixedSize(34, 34)
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setStyleSheet(f"""
            font-size: 15px;
            background: {icon_bg};
            color: {icon_color};
            border-radius: 8px;
        """)

        # Text column
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self._val_lbl = QLabel("0")
        self._val_lbl.setObjectName("metricVal")
        self._val_lbl.setStyleSheet(
            f"font-size:22px; font-weight:700; color:{C['text_1']}; letter-spacing:-0.5px;"
        )

        lbl = QLabel(label)
        lbl.setObjectName("metricLbl")
        lbl.setStyleSheet(f"font-size:11px; color:{C['text_3']}; font-weight:500;")

        text_col.addWidget(self._val_lbl)
        text_col.addWidget(lbl)

        layout.addWidget(icon_box)
        layout.addLayout(text_col)
        layout.addStretch()

        self.setStyleSheet(f"""
            MetricCard {{
                background: {C['bg_surface']};
                border-right: 1px solid {C['border_md']};
            }}
        """)

    def set_value(self, n: int):
        self._val_lbl.setText(f"{n:,}")


# ─────────────────────────────────────────────
#  Event Table Widget
# ─────────────────────────────────────────────

class EventTable(QTableWidget):
    """
    A QTableWidget configured for live event streaming.
    Column definitions are passed in as [(header, width), ...].
    width=0 means stretch to fill.
    """

    def __init__(self, columns: list[tuple[str, int]]):
        super().__init__()
        self._autoscroll = True
        self._columns    = columns

        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels([c[0] for c in columns])
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setSortingEnabled(False)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalHeader().setDefaultSectionSize(34)
        self.horizontalHeader().setHighlightSections(False)

        # Column widths
        for i, (_, w) in enumerate(columns):
            if w == 0:
                self.horizontalHeader().setSectionResizeMode(
                    i, QHeaderView.ResizeMode.Stretch)
            else:
                self.horizontalHeader().setSectionResizeMode(
                    i, QHeaderView.ResizeMode.Fixed)
                self.setColumnWidth(i, w)

    def set_autoscroll(self, on: bool):
        self._autoscroll = on

    def prepend_row(self, items: list[QTableWidgetItem]):
        """Insert a new row at the top (row 0) with the given items."""
        self.insertRow(0)
        for col, item in enumerate(items):
            self.setItem(0, col, item)

        # Cap at 500 rows for performance
        while self.rowCount() > 500:
            self.removeRow(self.rowCount() - 1)

        if self._autoscroll:
            self.scrollToTop()

    def clear_rows(self):
        self.setRowCount(0)

    def filter_rows(self, query: str):
        q = query.lower()
        for row in range(self.rowCount()):
            match = False
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item and q in item.text().lower():
                    match = True
                    break
            self.setRowHidden(row, not match)


# ─────────────────────────────────────────────
#  UI Update Worker — runs on main thread via QTimer
# ─────────────────────────────────────────────

class UIUpdater(QObject):
    """
    Receives events from the pipeline callback (which runs on a
    background thread) and emits them safely to the main thread.
    """
    event_received = pyqtSignal(str, dict)   # category, event dict

    def emit_event(self, category: str, event: dict):
        self.event_received.emit(category, event)


# ─────────────────────────────────────────────
#  Main Window
# ─────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self, base_dir: str):
        super().__init__()
        self._base_dir      = base_dir
        self._launcher      = Launcher()
        self._session_exists= False
        self._autoscroll    = True
        self._counts        = {"file": 0, "network": 0, "process": 0}
        self._updater       = UIUpdater()
        self._updater.event_received.connect(self._on_event)

        self.setWindowTitle("AnalytX")
        self.setMinimumSize(1100, 680)
        self.resize(1280, 760)
        self.setStyleSheet(STYLESHEET)

        # Wire launcher callbacks through the updater
        self._launcher.set_event_callback(self._updater.emit_event)
        self._launcher.set_status_callback(self._on_status)

        self._build_ui()
        self._set_state("idle")

    # ─────────────────────────────────────────
    #  UI Construction
    # ─────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_header())
        root_layout.addWidget(self._build_toolbar())
        root_layout.addWidget(self._build_metrics())
        root_layout.addWidget(self._build_tabs(), 1)
        root_layout.addWidget(self._build_statusbar())

    # ── Header ───────────────────────────────
    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("header")
        header.setFixedHeight(52)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        # Brand icon (coloured box)
        icon_box = QLabel("🛡")
        icon_box.setFixedSize(30, 30)
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setStyleSheet(f"""
            font-size: 14px;
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 #3a6fd8, stop:1 #5b9cf6);
            border-radius: 7px;
        """)

        # Brand name
        brand_lbl = QLabel("Analyt<span style='color:#6395ff'>X</span>")
        brand_lbl.setTextFormat(Qt.TextFormat.RichText)
        brand_lbl.setStyleSheet(
            "font-size:16px; font-weight:700; letter-spacing:-0.3px;"
        )

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"color: {C['border_md']};")

        # Status chip
        self._status_chip = QLabel("  ●  Ready  ")
        self._status_chip.setObjectName("statusChip")
        self._status_chip.setProperty("state", "idle")
        self._status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Session info (hidden until monitoring)
        self._session_info_lbl = QLabel("")
        self._session_info_lbl.setObjectName("sessionInfoLabel")
        self._session_info_lbl.setVisible(False)

        # Right side
        self._version_chip = QLabel("Version 1.0")
        self._version_chip.setObjectName("versionChip")

        layout.addWidget(icon_box)
        layout.addWidget(brand_lbl)
        layout.addWidget(sep)
        layout.addWidget(self._status_chip)
        layout.addWidget(self._session_info_lbl)
        layout.addStretch()
        layout.addWidget(self._version_chip)

        return header

    # ── Toolbar ──────────────────────────────
    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(58)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        # Target field wrapper (folder icon + input + browse btn)
        field_wrap = QWidget()
        field_wrap.setObjectName("targetField")
        field_wrap.setStyleSheet(f"""
            QWidget#targetField {{
                background: {C['bg_elevated']};
                border: 1px solid {C['border_md']};
                border-radius: 12px;
            }}
        """)
        field_layout = QHBoxLayout(field_wrap)
        field_layout.setContentsMargins(12, 0, 0, 0)
        field_layout.setSpacing(0)

        folder_icon = QLabel("📁")
        folder_icon.setStyleSheet(f"color:{C['text_3']}; font-size:14px; padding-right:6px;")

        self._target_input = QLineEdit()
        self._target_input.setPlaceholderText(
            "Select a target executable or batch file to monitor..."
        )
        self._target_input.setReadOnly(True)
        self._target_input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {C['text_1']};
                font-family: 'Consolas', monospace;
                font-size: 12px;
                padding: 0;
            }}
        """)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{C['border_md']};")
        sep.setFixedWidth(1)

        self._btn_browse = QPushButton("Browse")
        self._btn_browse.setObjectName("btnBrowse")
        self._btn_browse.setFixedHeight(38)
        self._btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_browse.clicked.connect(self._browse)

        field_layout.addWidget(folder_icon)
        field_layout.addWidget(self._target_input, 1)
        field_layout.addWidget(sep)
        field_layout.addWidget(self._btn_browse)

        # Separator
        tsep = QFrame()
        tsep.setFrameShape(QFrame.Shape.VLine)
        tsep.setFixedWidth(1)
        tsep.setFixedHeight(26)
        tsep.setStyleSheet(f"color:{C['border_md']};")

        # Action buttons
        self._btn_start = QPushButton("▶  Start Monitoring")
        self._btn_start.setObjectName("btnStart")
        self._btn_start.setFixedHeight(38)
        self._btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_start.clicked.connect(self._on_start_clicked)

        self._btn_stop = QPushButton("■  Stop / Save")
        self._btn_stop.setObjectName("btnStop")
        self._btn_stop.setFixedHeight(38)
        self._btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_stop.clicked.connect(self._on_stop_clicked)

        self._btn_report = QPushButton("↓  Export Report")
        self._btn_report.setObjectName("btnReport")
        self._btn_report.setFixedHeight(38)
        self._btn_report.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_report.clicked.connect(self._export_report)

        layout.addWidget(field_wrap, 1)
        layout.addWidget(tsep)
        layout.addWidget(self._btn_start)
        layout.addWidget(self._btn_stop)
        layout.addWidget(self._btn_report)

        return bar

    # ── Metrics bar ──────────────────────────
    def _build_metrics(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("metricsBar")
        bar.setFixedHeight(62)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._mc_file    = MetricCard("File Events",    "📄", C["blue"],   C["blue_soft"])
        self._mc_network = MetricCard("Network Events", "📶", C["green"],  C["green_soft"])
        self._mc_process = MetricCard("Process Events", "⚙",  C["purple"], C["purple_soft"])
        self._mc_total   = MetricCard("Total Events",   "☰",  C["teal"],   C["teal_soft"])

        for mc in [self._mc_file, self._mc_network, self._mc_process, self._mc_total]:
            layout.addWidget(mc, 1)

        return bar

    # ── Tabs + Tables ─────────────────────────
    def _build_tabs(self) -> QWidget:
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Tab bar row (tabs + search + autoscroll)
        tab_row = QWidget()
        tab_row.setStyleSheet(f"background:{C['bg_surface']}; border-bottom:1px solid {C['border_md']};")
        tab_row_layout = QHBoxLayout(tab_row)
        tab_row_layout.setContentsMargins(0, 0, 16, 0)
        tab_row_layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabWidget::tab-bar { alignment: left; }
        """)
        self._tabs.tabBar().setExpanding(False)
        # Note: currentChanged is connected AFTER _search is created below

        # Tables
        self._tbl_all = EventTable([
            ("Timestamp", 150), ("PID", 68), ("Category", 82),
            ("Operation", 110), ("Detail", 0)
        ])
        self._tbl_file = EventTable([
            ("Timestamp", 150), ("PID", 68), ("Operation", 110),
            ("File Path", 0), ("I/O Size", 90)
        ])
        self._tbl_network = EventTable([
            ("Timestamp", 150), ("PID", 68), ("Operation", 110),
            ("Connection", 0), ("Dest IP", 130), ("Port", 60), ("Size", 78)
        ])
        self._tbl_process = EventTable([
            ("Timestamp", 150), ("PID", 68), ("Operation", 118),
            ("Image / Process", 0), ("Child PID", 88), ("Exit Code", 88)
        ])

        self._tabs.addTab(self._tbl_all,     "  All Events  ")
        self._tabs.addTab(self._tbl_file,    "  File System  ")
        self._tabs.addTab(self._tbl_network, "  Network  ")
        self._tabs.addTab(self._tbl_process, "  Process  ")

        tab_row_layout.addWidget(self._tabs, 1)

        # Right controls
        right = QHBoxLayout()
        right.setSpacing(8)
        right.setContentsMargins(0, 0, 0, 0)

        self._search = QLineEdit()
        self._search.setObjectName("searchInput")
        self._search.setPlaceholderText("Search events…")
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._filter_events)

        self._autoscroll_btn = QPushButton("⬇  Auto-scroll")
        self._autoscroll_btn.setObjectName("autoscrollBtn")
        self._autoscroll_btn.setProperty("on", "true")
        self._autoscroll_btn.setFixedHeight(30)
        self._autoscroll_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._autoscroll_btn.clicked.connect(self._toggle_autoscroll)

        # Connect tab change AFTER _search exists
        self._tabs.currentChanged.connect(self._on_tab_changed)

        right.addWidget(self._search)
        right.addWidget(self._autoscroll_btn)

        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setStyleSheet(f"background:{C['bg_surface']};")

        tab_row_layout.addWidget(right_widget)

        v.addWidget(tab_row)

        # Content area (just the tab widget pane)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._tabs)

        v.addWidget(content, 1)
        return container

    # ── Status bar ───────────────────────────
    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("statusBar")
        bar.setFixedHeight(28)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(16)

        def sb_pair(dot_color, label):
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(5)
            dot = QLabel("●")
            dot.setStyleSheet(f"font-size:7px; color:{dot_color};")
            lbl = QLabel(label)
            lbl.setObjectName("sbLabel")
            val = QLabel("0")
            h.addWidget(dot)
            h.addWidget(lbl)
            h.addWidget(val)
            return w, val

        file_row,    self._sb_file    = sb_pair(C["blue"],   "File")
        network_row, self._sb_network = sb_pair(C["green"],  "Network")
        process_row, self._sb_process = sb_pair(C["purple"], "Process")

        self._sb_file.setObjectName("sbFile")
        self._sb_network.setObjectName("sbNetwork")
        self._sb_process.setObjectName("sbProcess")

        layout.addWidget(file_row)
        layout.addWidget(network_row)
        layout.addWidget(process_row)
        layout.addStretch()

        self._sb_pid_lbl = QLabel("")
        self._sb_pid_lbl.setObjectName("sbLabel")
        self._sb_pid_lbl.setVisible(False)
        self._sb_sess_lbl = QLabel("")
        self._sb_sess_lbl.setObjectName("sbLabel")
        self._sb_sess_lbl.setVisible(False)

        layout.addWidget(self._sb_pid_lbl)
        layout.addWidget(self._sb_sess_lbl)

        return bar

    # ─────────────────────────────────────────
    #  State Management
    # ─────────────────────────────────────────

    def _set_state(self, state: str):
        """Switch UI between 'idle', 'running', 'stopped' states."""

        if state == "idle":
            self._btn_start.setVisible(True)
            self._btn_stop.setVisible(False)
            self._btn_report.setVisible(False)
            self._update_chip("idle", "Ready")
            self._session_info_lbl.setVisible(False)

        elif state == "running":
            self._btn_start.setVisible(False)
            self._btn_stop.setVisible(True)
            self._btn_report.setVisible(False)
            self._update_chip("running", "  ●  Monitoring")

        elif state == "stopped":
            self._btn_start.setVisible(True)
            self._btn_stop.setVisible(False)
            self._btn_report.setVisible(True)
            self._update_chip("stopped", "  ■  Session Saved")

    def _update_chip(self, state: str, text: str):
        self._status_chip.setText(text)
        self._status_chip.setProperty("state", state)
        # Force stylesheet re-evaluation
        self._status_chip.style().unpolish(self._status_chip)
        self._status_chip.style().polish(self._status_chip)

    # ─────────────────────────────────────────
    #  Button Handlers
    # ─────────────────────────────────────────

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Target Executable",
            "",
            "Executables (*.exe *.bat *.cmd);;All Files (*)"
        )
        if path:
            self._target_input.setText(path)
            self._target_input.setStyleSheet(
                f"background:transparent; border:none; "
                f"color:{C['blue']}; font-family:'Consolas',monospace; font-size:12px;"
            )

    def _on_start_clicked(self):
        path = self._target_input.text().strip()
        if not path:
            self._target_input.setPlaceholderText("⚠  Please select a target file first")
            QTimer.singleShot(2500, lambda: self._target_input.setPlaceholderText(
                "Select a target executable or batch file to monitor..."
            ))
            return

        # If session already exists — show modal
        if self._session_exists:
            total = sum(self._counts.values())
            dlg   = NewSessionDialog(self, total)
            dlg.exec()

            if dlg.choice == "cancel":
                return
            elif dlg.choice == "save":
                self._generate_report_silent()
                self._clear_session()
            elif dlg.choice == "discard":
                self._clear_session()

        self._begin_monitoring(path)

    def _on_stop_clicked(self):
        self._launcher.stop()
        self._set_state("stopped")

    def _export_report(self):
        db_path = self._launcher.get_db_path()
        if not db_path or not os.path.isfile(db_path):
            return
        report_path = rpt.generate_report(db_path)
        webbrowser.open(f"file:///{report_path.replace(os.sep, '/')}")

    # ─────────────────────────────────────────
    #  Session Management
    # ─────────────────────────────────────────

    def _begin_monitoring(self, path: str):
        ok, err = self._launcher.start(target_path=path)
        if not ok:
            self._update_chip("stopped", f"Error: {err[:60]}")
            return

        self._session_exists = True
        self._set_state("running")

        # Show session info in header
        db_path = self._launcher.get_db_path()
        sess_name = os.path.basename(os.path.dirname(db_path)) if db_path else "—"
        pid = "..."
        self._session_info_lbl.setText(
            f"  PID: ...  ·  {sess_name}"
        )
        self._session_info_lbl.setVisible(True)

        # Status bar session
        self._sb_sess_lbl.setText(f"  {sess_name}")
        self._sb_sess_lbl.setVisible(True)

    def _clear_session(self):
        """Wipe all table rows and reset counters."""
        for tbl in [self._tbl_all, self._tbl_file,
                    self._tbl_network, self._tbl_process]:
            tbl.clear_rows()

        self._counts = {"file": 0, "network": 0, "process": 0}
        self._update_counters()
        self._session_exists = False
        self._session_info_lbl.setVisible(False)
        self._sb_pid_lbl.setVisible(False)
        self._sb_sess_lbl.setVisible(False)

    def _generate_report_silent(self):
        """Generate report without opening browser (called before clearing)."""
        db_path = self._launcher.get_db_path()
        if db_path and os.path.isfile(db_path):
            try:
                rpt.generate_report(db_path)
            except Exception as e:
                logging.error(f"[UI] Report generation error: {e}")

    # ─────────────────────────────────────────
    #  Live Event Handler  (called from pipeline via signal)
    # ─────────────────────────────────────────

    def _on_event(self, category: str, event: dict):
        ts        = event.get("timestamp", "")
        pid       = str(event.get("pid", ""))
        operation = event.get("operation", "")
        detail    = event.get("detail", "")

        # ── All Events tab ───────────────────
        self._tbl_all.prepend_row([
            make_item(ts,        color=C["text_3"], mono=True),
            make_item(pid,       color=C["text_3"], mono=True),
            make_badge_item(category,  CAT_COLORS),
            make_badge_item(operation, OP_COLORS),
            make_item(detail,    color=C["text_2"]),
        ])

        # ── Category-specific tab ────────────
        if category == "file":
            io_size = str(event.get("io_size", "—"))
            self._tbl_file.prepend_row([
                make_item(ts,        color=C["text_3"], mono=True),
                make_item(pid,       color=C["text_3"], mono=True),
                make_badge_item(operation, OP_COLORS),
                make_item(detail,    color=C["blue"],   mono=True),
                make_item(io_size + " B" if io_size.isdigit() and io_size != "0"
                          else "—", color=C["text_2"]),
            ])
            self._counts["file"] += 1

        elif category == "network":
            dst_ip   = event.get("dst_ip",   "")
            dst_port = str(event.get("dst_port", ""))
            size     = str(event.get("size",  ""))
            self._tbl_network.prepend_row([
                make_item(ts,        color=C["text_3"], mono=True),
                make_item(pid,       color=C["text_3"], mono=True),
                make_badge_item(operation, OP_COLORS),
                make_item(detail,    color=C["text_2"]),
                make_item(dst_ip,    color=C["teal"],   mono=True),
                make_item(dst_port,  color=C["text_2"]),
                make_item(size + " B" if size.isdigit() else "—",
                          color=C["text_2"]),
            ])
            self._counts["network"] += 1

        elif category == "process":
            child_pid = str(event.get("child_pid",  "—"))
            exit_code = event.get("exit_code", None)
            exit_str  = str(exit_code) if exit_code is not None else "—"
            self._tbl_process.prepend_row([
                make_item(ts,        color=C["text_3"], mono=True),
                make_item(pid,       color=C["text_3"], mono=True),
                make_badge_item(operation, OP_COLORS),
                make_item(detail,    color=C["text_2"]),
                make_item(child_pid, color=C["text_3"], mono=True),
                make_item(exit_str,  color=C["text_2"]),
            ])
            self._counts["process"] += 1

        elif category == "control":
            # Update PID in header when target launches
            if operation == "TargetLaunched":
                pid_val = str(event.get("pid", ""))
                self._sb_pid_lbl.setText(f"PID {pid_val}")
                self._sb_pid_lbl.setVisible(True)
                self._session_info_lbl.setText(
                    self._session_info_lbl.text().replace("...", pid_val)
                )
            elif operation in ("TargetExited", "EngineShutdown"):
                self._set_state("stopped")

        self._update_counters()

    def _update_counters(self):
        total = sum(self._counts.values())
        self._mc_file.set_value(self._counts["file"])
        self._mc_network.set_value(self._counts["network"])
        self._mc_process.set_value(self._counts["process"])
        self._mc_total.set_value(total)
        self._sb_file.setText(str(self._counts["file"]))
        self._sb_network.setText(str(self._counts["network"]))
        self._sb_process.setText(str(self._counts["process"]))

        # Update tab labels with counts
        self._tabs.setTabText(0, f"  All Events ({total})  ")
        self._tabs.setTabText(1, f"  File System ({self._counts['file']})  ")
        self._tabs.setTabText(2, f"  Network ({self._counts['network']})  ")
        self._tabs.setTabText(3, f"  Process ({self._counts['process']})  ")

    # ─────────────────────────────────────────
    #  Status callback (from launcher)
    # ─────────────────────────────────────────

    def _on_status(self, message: str):
        # Could drive a status bar message — for now just print
        logging.info(f"[UI STATUS] {message}")

    # ─────────────────────────────────────────
    #  Search / Filter
    # ─────────────────────────────────────────

    def _filter_events(self, query: str):
        active = self._tabs.currentWidget()
        if isinstance(active, EventTable):
            active.filter_rows(query)

    def _on_tab_changed(self):
        # Guard: _search may not exist yet during UI construction
        if not hasattr(self, '_search'):
            return
        query = self._search.text()
        if query:
            self._filter_events(query)

    # ─────────────────────────────────────────
    #  Autoscroll
    # ─────────────────────────────────────────

    def _toggle_autoscroll(self):
        self._autoscroll = not self._autoscroll
        state = "true" if self._autoscroll else "false"
        self._autoscroll_btn.setProperty("on", state)
        label = "⬇  Auto-scroll" if self._autoscroll else "   Auto-scroll"
        self._autoscroll_btn.setText(label)

        # Force stylesheet re-evaluation
        self._autoscroll_btn.style().unpolish(self._autoscroll_btn)
        self._autoscroll_btn.style().polish(self._autoscroll_btn)

        for tbl in [self._tbl_all, self._tbl_file,
                    self._tbl_network, self._tbl_process]:
            tbl.set_autoscroll(self._autoscroll)

    # ─────────────────────────────────────────
    #  Window close — clean shutdown
    # ─────────────────────────────────────────

    def closeEvent(self, event):
        if self._launcher.is_running():
            self._launcher.stop()
        event.accept()