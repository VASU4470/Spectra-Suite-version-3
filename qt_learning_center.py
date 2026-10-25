"""Offline Learning Center for SpectraSuite.

The Learning Center explains the scientific workflow around the application's
measurements and analyses.  It is educational documentation only; it does not
modify scientific calculations or processing defaults.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from qt_theme import LIGHT_STYLE, apply_theme, apply_window_icon


TOPICS = [(
    "User Manual",
    "Offline learning resources unavailable",
    "<h2>Documentation resources missing</h2><p>The installed application could not locate its bundled offline Learning Center content. Please reinstall the complete application package.</p>",
)]


# Read bundled offline documentation by stable topic ID.
import json
import sys
from pathlib import Path
from PySide6.QtWidgets import QLineEdit

def _learn_resource():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / "docs" / "learn" / "topics.json"

def load_topics():
    path = _learn_resource()
    if not path.is_file():
        return TOPICS
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload["topics"]
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate Learning Center topic IDs")
    return [(item["category"], item["title"], item["html"], item["id"]) for item in items]

class LearningCenterDialog(QDialog):
    """Offline, searchable-by-navigation scientific help center."""

    def __init__(self, parent=None, initial_topic=None):
        super().__init__(parent)
        self.setWindowTitle("SpectraSuite Learning Center")
        self.resize(1000, 720)
        self.setMinimumSize(760, 520)
        apply_theme(self, LIGHT_STYLE)
        apply_window_icon(self, "APP")

        root = QVBoxLayout(self)
        heading = QLabel("Learn — science, instrumentation, processing and analysis")
        heading.setStyleSheet("font-size: 18px; font-weight: 700;")
        root.addWidget(heading)

        self.search = QLineEdit()
        self.search.setPlaceholderText('Search topics and scientific explanations (offline)')
        root.addWidget(self.search)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        self.topic_list = QListWidget()
        self.topic_list.setMinimumWidth(250)
        self.topic_list.setMaximumWidth(340)
        splitter.addWidget(self.topic_list)

        content_wrap = QWidget()
        content_layout = QVBoxLayout(content_wrap)
        content_layout.setContentsMargins(8, 0, 0, 0)
        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(True)
        content_layout.addWidget(self.content)
        splitter.addWidget(content_wrap)
        splitter.setSizes([280, 720])

        last_category = None
        target_row = 0
        self._all_topics = load_topics()
        for topic in self._all_topics:
            category, title, html = topic[:3]
            topic_id = topic[3] if len(topic) > 3 else title
            if category != last_category:
                header = QListWidgetItem(category)
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                font = header.font()
                font.setBold(True)
                header.setFont(font)
                self.topic_list.addItem(header)
                last_category = category
            item = QListWidgetItem(f"   {title}")
            item.setData(Qt.ItemDataRole.UserRole, html)
            item.setData(Qt.ItemDataRole.UserRole + 1, title)
            item.setData(Qt.ItemDataRole.UserRole + 2, topic_id)
            item.setData(Qt.ItemDataRole.UserRole + 3, category)
            self.topic_list.addItem(item)
            if initial_topic and (initial_topic == topic_id or initial_topic.lower() in title.lower()):
                target_row = self.topic_list.count() - 1

        self.search.textChanged.connect(self._filter_topics)
        self.topic_list.currentItemChanged.connect(self._topic_changed)
        self.topic_list.setCurrentRow(target_row if target_row else 1)

    def _topic_changed(self, item, _previous=None):
        if item is None:
            return
        html = item.data(Qt.ItemDataRole.UserRole)
        if html:
            self.content.setHtml(html)

    def _filter_topics(self, query):
        query = query.strip().lower()
        for row in range(self.topic_list.count()):
            item = self.topic_list.item(row)
            html = item.data(Qt.ItemDataRole.UserRole)
            if html is None:
                item.setHidden(bool(query))
            else:
                haystack = " ".join((item.text(), str(item.data(Qt.ItemDataRole.UserRole + 3) or ""), html))
                item.setHidden(query not in haystack.lower())
        if query:
            for row in range(self.topic_list.count()):
                item = self.topic_list.item(row)
                if not item.isHidden() and item.data(Qt.ItemDataRole.UserRole):
                    self.topic_list.setCurrentItem(item)
                    break
