"""PySide6 setup dialog shared by every SpectraSuite workspace."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from config import state
from readers import read_generic_configured


STYLE = """
QDialog { background: #1e1e2e; color: #cdd6f4; }
QLabel#heading { color: #89b4fa; font-size: 22px; font-weight: 700; }
QGroupBox {
    border: 1px solid #45475a; border-radius: 8px; margin-top: 12px;
    padding-top: 10px; font-weight: 700;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QListWidget, QSpinBox, QComboBox, QPlainTextEdit {
    background: #181825; border: 1px solid #45475a; border-radius: 5px;
    color: #cdd6f4; padding: 4px;
}
QPushButton {
    background: #313244; border: 1px solid #45475a; border-radius: 6px;
    color: #cdd6f4; padding: 7px 10px;
}
QPushButton:hover { border-color: #89b4fa; background: #45475a; }
QPushButton#launch { background: #89b4fa; color: #11111b; font-weight: 700; }
"""


class SetupDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.ready = False
        self.loaded_from_session = False
        self.last_open_dir = ""
        self.setWindowTitle("Processing Suite Launcher")
        self.resize(600, 680)
        self.setMinimumSize(520, 620)
        self.setStyleSheet(STYLE)

        icon_name = {
            "XRD": "xrd_icon.png", "FTIR": "ir_icon.png", "GENERAL": "icon.png"
        }.get(state.technique, "icon.png")
        icon_path = Path(__file__).resolve().parent / icon_name
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        if not isinstance(state.settings.get("files"), list):
            state.settings["files"] = []
        self._build_ui()
        self._refresh_files()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        heading = QLabel("Data Processing Suite")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)

        files_group = QGroupBox("1. Select & Arrange Data")
        files_layout = QVBoxLayout(files_group)
        self.file_count = QLabel()
        self.file_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        files_layout.addWidget(self.file_count)

        add_row = QHBoxLayout()
        add_folder = QPushButton("📂 Add Folder")
        add_folder.clicked.connect(self.add_folder)
        add_files = QPushButton("📄 Add Files")
        add_files.clicked.connect(self.add_files)
        add_row.addWidget(add_folder)
        add_row.addWidget(add_files)
        files_layout.addLayout(add_row)

        list_row = QHBoxLayout()
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.itemDoubleClicked.connect(lambda: self.remove_selected())
        list_row.addWidget(self.file_list, 1)

        order_row = QVBoxLayout()
        move_up = QPushButton("⬆")
        move_up.clicked.connect(lambda: self.move_selected(-1))
        move_down = QPushButton("⬇")
        move_down.clicked.connect(lambda: self.move_selected(1))
        order_row.addWidget(move_up)
        order_row.addWidget(move_down)
        order_row.addStretch()
        list_row.addLayout(order_row)
        files_layout.addLayout(list_row)

        remove_row = QHBoxLayout()
        remove = QPushButton("➖ Remove Selected")
        remove.clicked.connect(self.remove_selected)
        clear = QPushButton("🗑 Clear All")
        clear.clicked.connect(self.clear_files)
        remove_row.addWidget(remove)
        remove_row.addWidget(clear)
        files_layout.addLayout(remove_row)
        layout.addWidget(files_group, 1)

        mode_group = QGroupBox("2. Plotting Mode")
        mode_layout = QVBoxLayout(mode_group)
        self.mode_buttons = {}
        for label, value in (
            ("Individual Plots", "individual"),
            ("Stacked Grid", "stack"),
            ("Overlay", "overlay"),
        ):
            button = QRadioButton(label)
            self.mode_buttons[value] = button
            mode_layout.addWidget(button)
        current_mode = state.settings.get("mode", "individual")
        self.mode_buttons.get(current_mode, self.mode_buttons["individual"]).setChecked(True)

        form = QFormLayout()
        self.smoothing = QSpinBox()
        self.smoothing.setRange(1, 999)
        self.smoothing.setValue(int(state.settings.get("smooth", 15)))
        form.addRow("Default Smoothing (Pts):", self.smoothing)
        mode_layout.addLayout(form)
        layout.addWidget(mode_group)

        info = QGroupBox("Supported File Formats")
        info_layout = QVBoxLayout(info)
        if state.technique == "XRD":
            text = "X-Ray Diffraction: .csv, .txt, .xy, .dat, .xlsx"
        elif state.technique == "GENERAL":
            text = "General Plotter: delimited text or Excel files with numeric X/Y columns"
        else:
            text = "FT-IR Spectroscopy: .dpt, .csv, .txt, .xy, .xlsx"
        info_layout.addWidget(QLabel(text))
        layout.addWidget(info)

        launch = QPushButton("🚀 Launch Processing")
        launch.setObjectName("launch")
        launch.clicked.connect(self.start)
        layout.addWidget(launch)

        load = QPushButton("📂 Load Previous Session (.json)")
        load.clicked.connect(self.load_session)
        layout.addWidget(load)

    def _allowed_extensions(self):
        if state.technique == "XRD":
            return {".csv", ".txt", ".xy", ".dat", ".asr", ".raw", ".xlsx"}
        if state.technique == "GENERAL":
            return {".csv", ".tsv", ".txt", ".xy", ".dat", ".xlsx", ".xls"}
        return {".dpt", ".csv", ".txt", ".xy", ".xlsx"}

    def _refresh_files(self) -> None:
        self.file_list.clear()
        self.file_list.addItems([Path(item).name for item in state.settings["files"]])
        count = len(state.settings["files"])
        self.file_count.setText(f"Loaded: {count} file(s) ready")

    def _add_paths(self, paths) -> None:
        existing = set(state.settings["files"])
        added = 0
        duplicates = 0
        for value in paths:
            path = str(Path(value).resolve())
            if path in existing:
                duplicates += 1
                continue
            state.settings["files"].append(path)
            existing.add(path)
            added += 1
        self._refresh_files()
        if duplicates:
            QMessageBox.information(
                self, "Duplicates Skipped",
                f"Added {added} new file(s).\nSkipped {duplicates} duplicate file(s).",
            )

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder containing Data Files", self.last_open_dir
        )
        if not folder:
            return
        self.last_open_dir = folder
        allowed = self._allowed_extensions()
        paths = sorted(path for path in Path(folder).iterdir() if path.suffix.lower() in allowed)
        if not paths:
            QMessageBox.warning(self, "No Data", "No supported data files were found.")
            return
        self._add_paths(paths)

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Data Files", self.last_open_dir,
            "Data files (*.dpt *.csv *.tsv *.txt *.xy *.dat *.asr *.raw *.xlsx *.xls);;All files (*)",
        )
        if paths:
            self.last_open_dir = str(Path(paths[0]).parent)
            self._add_paths(paths)

    def remove_selected(self) -> None:
        rows = sorted({self.file_list.row(item) for item in self.file_list.selectedItems()}, reverse=True)
        for row in rows:
            state.settings["files"].pop(row)
        self._refresh_files()

    def clear_files(self) -> None:
        state.settings["files"] = []
        state.settings.pop("folder", None)
        self._refresh_files()

    def move_selected(self, direction: int) -> None:
        rows = sorted({self.file_list.row(item) for item in self.file_list.selectedItems()})
        if not rows:
            return
        if direction < 0 and rows[0] == 0:
            return
        if direction > 0 and rows[-1] == len(state.settings["files"]) - 1:
            return
        iteration = rows if direction < 0 else reversed(rows)
        for row in iteration:
            other = row + direction
            files = state.settings["files"]
            files[row], files[other] = files[other], files[row]
        self._refresh_files()
        for row in rows:
            self.file_list.item(row + direction).setSelected(True)

    def start(self) -> None:
        if not state.settings["files"]:
            QMessageBox.warning(self, "Files Required", "Please select at least one data file.")
            return
        state.settings["is_all"] = False
        state.settings["smooth"] = self.smoothing.value()
        state.settings["mode"] = next(
            value for value, button in self.mode_buttons.items() if button.isChecked()
        )
        if state.technique == "GENERAL":
            picker = ColumnPickerDialog(state.settings["files"][0], self)
            if picker.exec() != QDialog.DialogCode.Accepted:
                return
            state.general_format = picker.result
            state.settings["general_format"] = picker.result
        self.ready = True
        self.accept()

    def load_session(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Session File", self.last_open_dir, "Session files (*.json)"
        )
        if not filename:
            return
        try:
            with Path(filename).open("r", encoding="utf-8") as stream:
                data = json.load(stream)
            state.settings = data["settings"]
            state.all_data = [
                (stem, np.asarray(x, dtype=float), np.asarray(y, dtype=float))
                for stem, x, y in data["all_data"]
            ]
            state.master_folder = data.get("master_folder")
            state.file_set = data["file_set"]
            state.global_set = data["global_set"]
            state.current_session_file = filename
            state.general_format = state.settings.get("general_format")
        except (OSError, ValueError, KeyError, TypeError) as error:
            QMessageBox.critical(self, "Session Error", f"Failed to load session:\n{error}")
            return
        self.ready = True
        self.loaded_from_session = True
        self.accept()


def run_setup_dialog():
    """Show the setup dialog and return its result object."""
    app = QApplication.instance()
    owns_application = app is None
    if owns_application:
        app = QApplication(sys.argv)
    dialog = SetupDialog()
    dialog.exec()
    if owns_application:
        app.quit()
    return dialog


class ColumnPickerDialog(QDialog):
    """Configure delimiter, skipped rows, and X/Y columns with a live preview."""

    DELIMITERS = {
        "Comma (,)": ",",
        "Tab": "\t",
        "Whitespace": " ",
        "Semicolon (;)": ";",
    }

    def __init__(self, sample_filepath, parent=None):
        super().__init__(parent)
        self.sample_filepath = Path(sample_filepath)
        self.result = None
        self.setWindowTitle("Configure General Plotter Columns")
        self.resize(680, 650)
        self.setMinimumSize(580, 560)
        self.setStyleSheet(STYLE)
        self._build_ui()
        self.refresh_preview()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        heading = QLabel(f"Sample file: {self.sample_filepath.name}")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        layout.addWidget(QLabel("Raw preview"))
        self.raw_preview = QPlainTextEdit()
        self.raw_preview.setReadOnly(True)
        self.raw_preview.setMaximumBlockCount(12)
        layout.addWidget(self.raw_preview, 1)

        group = QGroupBox("Parsing Options")
        form = QFormLayout(group)
        self.delimiter = QComboBox()
        self.delimiter.addItems(self.DELIMITERS)
        suffix = self.sample_filepath.suffix.lower()
        if suffix == ".tsv":
            self.delimiter.setCurrentText("Tab")
        self.skip_rows = QSpinBox()
        self.skip_rows.setRange(0, 500)
        self.x_column = QSpinBox()
        self.x_column.setRange(0, 100)
        self.y_column = QSpinBox()
        self.y_column.setRange(0, 100)
        self.y_column.setValue(1)
        form.addRow("Delimiter", self.delimiter)
        form.addRow("Header rows to skip", self.skip_rows)
        form.addRow("X column (0 = first)", self.x_column)
        form.addRow("Y column", self.y_column)
        layout.addWidget(group)

        refresh = QPushButton("Refresh Preview")
        refresh.clicked.connect(self.refresh_preview)
        layout.addWidget(refresh)
        for widget in (self.delimiter, self.skip_rows, self.x_column, self.y_column):
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self.refresh_preview)
            else:
                widget.valueChanged.connect(self.refresh_preview)

        layout.addWidget(QLabel("Parsed numeric X/Y preview"))
        self.parsed_preview = QPlainTextEdit()
        self.parsed_preview.setReadOnly(True)
        self.parsed_preview.setMaximumBlockCount(10)
        layout.addWidget(self.parsed_preview, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _configuration(self):
        return {
            "delimiter": self.DELIMITERS[self.delimiter.currentText()],
            "skip_rows": self.skip_rows.value(),
            "x_col": self.x_column.value(),
            "y_col": self.y_column.value(),
        }

    def refresh_preview(self, *_args):
        try:
            if self.sample_filepath.suffix.lower() in {".xlsx", ".xls"}:
                import pandas as pd
                frame = pd.read_excel(self.sample_filepath, header=None, nrows=8)
                raw = frame.to_string(index=False, header=False)
            else:
                with self.sample_filepath.open("r", encoding="utf-8", errors="ignore") as stream:
                    raw = "".join(stream.readline() for _ in range(8))
        except Exception as error:
            raw = f"Could not read file: {error}"
        self.raw_preview.setPlainText(raw)

        try:
            x, y = read_generic_configured(self.sample_filepath, **self._configuration())
            rows = list(zip(x, y))[:8]
            preview = "\n".join(f"{x_value:.6g}\t{y_value:.6g}" for x_value, y_value in rows)
            if not preview:
                preview = "No numeric rows found with these settings."
        except Exception as error:
            preview = f"Parsing error: {error}"
        self.parsed_preview.setPlainText(preview)

    def confirm(self):
        try:
            x, _y = read_generic_configured(self.sample_filepath, **self._configuration())
        except Exception as error:
            QMessageBox.critical(self, "Parsing Error", str(error))
            return
        if len(x) < 3:
            QMessageBox.warning(
                self,
                "No Numeric Data",
                "Choose settings that produce at least three numeric X/Y rows.",
            )
            return
        self.result = self._configuration()
        self.accept()
