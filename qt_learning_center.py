"""Offline manual, technique guides and worked examples for the 3.5 workspace."""

from html import escape
import json

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import (
    QDialog, QLineEdit, QListWidget, QPushButton, QSplitter, QTabWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)

from qt_theme import apply_theme, apply_window_icon


class LearningPage(QWidget):
    def __init__(self, entries, asset_url):
        super().__init__()
        self.entries = entries
        self.visible_entries = []
        layout = QVBoxLayout(self)
        self.search = QLineEdit(placeholderText="Search this tab")
        layout.addWidget(self.search)
        splitter = QSplitter()
        self.items = QListWidget()
        self.content = QTextBrowser()
        self.content.document().setBaseUrl(asset_url)
        splitter.addWidget(self.items)
        splitter.addWidget(self.content)
        splitter.setSizes([250, 600])
        layout.addWidget(splitter, 1)
        self.items.currentRowChanged.connect(self.show_entry)
        self.search.textChanged.connect(self.filter_entries)
        self.filter_entries("")

    def filter_entries(self, query):
        self.items.clear()
        self.visible_entries = [
            entry for entry in self.entries
            if query.strip().casefold() in f"{entry['title']} {entry['html']}".casefold()
        ]
        self.items.addItems([entry.get("navigation_title", entry["title"]) for entry in self.visible_entries])
        self.items.setCurrentRow(0)
        if not self.visible_entries:
            self.content.setPlainText("No matching topics.")

    def show_entry(self, row):
        if row >= 0:
            entry = self.visible_entries[row]
            body = entry["html"]
            if "figure" in entry:
                image = escape(entry["figure"])
                caption = escape(entry["caption"])
                body += f'<p><img src="figures/{image}" width="500" alt="{caption}"></p><p><i>{caption}</i></p>'
            self.content.setHtml(body)


class LearningCenterDialog(QDialog):
    exampleRequested = Signal(str, str)

    def __init__(self, resource_path, workspaces, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SpectraSuite Learning Center")
        self.resize(940, 650)
        self.setMinimumSize(780, 480)
        apply_theme(self)
        apply_window_icon(self)
        self.examples = []
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        try:
            topics = json.loads(resource_path("docs/learn/topics.json").read_text(encoding="utf-8"))["topics"]
            examples = json.loads(resource_path("docs/learn/examples.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            message = QTextBrowser()
            message.setPlainText("The offline Learning Center resources could not be loaded. Reinstall the complete application package.")
            layout.addWidget(message)
            self.tabs.hide()
            return
        asset_url = QUrl.fromLocalFile(str(resource_path("docs/learn")) + "/")
        manual = [topic for topic in topics if topic["id"].startswith("manual.")]
        guides = [topic for topic in topics if not topic["id"].startswith("manual.")]
        self.tabs.addTab(LearningPage(manual, asset_url), "User Manual")
        self.tabs.addTab(LearningPage(guides, asset_url), "Learning Center")

        for workspace in workspaces:
            if workspace.coming_soon or workspace.key not in examples:
                continue
            name = workspace.title.replace("\n", " ")
            status = " (Preview)" if workspace.experimental else ""
            for entry in examples[workspace.key]:
                navigation_title = name + status
                if entry.get("kind") == "Measured":
                    navigation_title += " (Measured)"
                title = f"{navigation_title} · {entry['title']}"
                fields = [("Units", "units"), ("Dataset provenance", "provenance")]
                if "source" in entry:
                    fields.extend([("Source", "source"), ("License", "license")])
                fields.append(("Expected result", "expected"))
                details = "".join(
                    f"<p><b>{label}</b> {escape(entry[key])}</p>"
                    for label, key in fields
                )
                walkthrough = "".join(f"<li>{escape(step)}</li>" for step in entry["steps"])
                self.examples.append(dict(
                    entry, workspace=workspace.key, title=title, navigation_title=navigation_title,
                    html=f"<h2>{escape(title)}</h2>{details}<h3>Walkthrough</h3><ol>{walkthrough}</ol>",
                ))

        self.library = LearningPage(self.examples, asset_url)
        self.open_button = QPushButton("Open Example")
        self.library.layout().addWidget(self.open_button)
        self.open_button.setEnabled(self.library.items.currentRow() >= 0)
        self.library.items.currentRowChanged.connect(lambda row: self.open_button.setEnabled(row >= 0))
        self.open_button.clicked.connect(self.open_example)
        self.tabs.addTab(self.library, "Example Library")

    def open_example(self):
        row = self.library.items.currentRow()
        if row >= 0:
            entry = self.library.visible_entries[row]
            self.exampleRequested.emit(entry["workspace"], entry["file"])
