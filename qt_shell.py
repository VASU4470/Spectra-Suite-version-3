"""Persistent single-window shell for SpectraSuite workspaces."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PySide6.QtCore import Signal, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app_version import APP_VERSION, RELEASE_TAG
from config import SessionState, state
from dataset_reader import discover_many
from dataset_reader import SpectrumDataset
from qt_import_support import install_import_support
from qt_plot_viewer import PlotViewer
from qt_theme import AppearanceDialog, LIGHT_STYLE, apply_theme, apply_window_icon
from qt_updates import (
    PrivacyPreferencesDialog,
    UpdateController,
    open_release_page,
    open_update_signup,
    show_about,
)


SPECTROSCOPY = {
    "xps": {"technique": "XPS", "label": "XPS",
            "xlabel": "Binding energy (eV)", "ylabel": "Intensity (a.u.)"},
    "libs": {"technique": "LIBS", "label": "LIBS",
             "xlabel": "Wavelength (nm)", "ylabel": "Intensity (a.u.)"},
    "ir": {
        "technique": "FTIR",
        "label": "FT–IR",
        "xlabel": "Wavenumber (cm⁻¹)",
        "ylabel": "Transmittance (%)",
    },
    "xrd": {
        "technique": "XRD",
        "label": "XRD",
        "xlabel": "2θ (°)",
        "ylabel": "Intensity (a.u.)",
    },
    "uvvis": {
        "technique": "UVVIS",
        "label": "UV–Vis",
        "xlabel": "Wavelength (nm)",
        "ylabel": "Absorbance",
    },
    "raman": {
        "technique": "RAMAN",
        "label": "Raman",
        "xlabel": "Raman shift (cm⁻¹)",
        "ylabel": "Intensity (a.u.)",
    },
}


SHELL_STYLE = LIGHT_STYLE + """
QMainWindow#spectraSuiteWindow { background-color: #eef3f9; }
QWidget#homePage, QWidget#importPage { background-color: #f4f7fb; }
QFrame#homeHero {
    background-color: #ffffff;
    border: 1px solid #d7e0ec;
    border-radius: 12px;
}
QLabel#homeTitle { color: #172033; font-size: 23px; font-weight: 800; }
QLabel#homeSubtitle { color: #64748b; font-size: 14px; }
QPushButton#workspaceTile {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    text-align: left;
    padding: 8px 12px;
    font-size: 14px;
    font-weight: 700;
}
QPushButton#workspaceTile:hover { background-color: #eff6ff; border-color: #60a5fa; }
QPushButton#workspaceTile[comingSoon="true"] {
    background-color: #f8fafc;
    color: #8491a3;
    border-color: #d7e0ec;
}
QFrame#dropZone {
    background-color: #ffffff;
    border: 2px dashed #93a4ba;
    border-radius: 12px;
}
QFrame#dropZone[ready="true"] { border-color: #2563eb; background-color: #eff6ff; }
QFrame#importSidebar, QFrame#importSettingsPanel {
    background-color: #ffffff;
    border: 1px solid #d7e0ec;
    border-radius: 10px;
}
QFrame#importFooter {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 9px;
}
QFrame#updateBanner {
    background-color: #eaf3ff;
    border-bottom: 1px solid #93c5fd;
}
QLabel#updateBannerBadge {
    color: #ffffff;
    background-color: #2563eb;
    border-radius: 5px;
    padding: 3px 7px;
    font-size: 11px;
    font-weight: 800;
}
QLabel#updateBannerTitle { color: #172033; font-weight: 800; }
QLabel#updateBannerNote { color: #475569; }
QLabel#importTitle { color: #172033; font-size: 22px; font-weight: 800; }
QTabWidget#documentTabs::pane { border: none; background-color: #f4f7fb; }
QTabWidget#documentTabs > QTabBar::tab {
    min-width: 85px;
    padding: 6px 12px;
}
"""


class InlineImportPage(QWidget):
    """Non-modal file and dataset selection shown inside the document area."""

    analysisReady = Signal(object)
    cancelRequested = Signal(object)

    def __init__(self, workspace, resource_path, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.resource_path = resource_path
        self.paths: list[str] = []
        self.datasets = []
        self.failures = []
        self.image_datasets = []
        self.image_metadata = {}
        self._last_reference = -1
        self.setObjectName("importPage")
        self.setAcceptDrops(True)
        self._build_ui()
        install_import_support(self, self.add_paths, self.import_digitized,
                               suffixes={".csv", ".tsv", ".txt", ".dat", ".xy", ".xlsx", ".xls", ".dpt", ".asc"}
                               | ({".zip"} if self.technique == "LIBS" else set()))

    @property
    def technique(self):
        return SPECTROSCOPY[self.workspace.key]["technique"]

    def _build_ui(self):
        root = QVBoxLayout(self)
        margins = (20, 14, 20, 12) if self.technique == "LIBS" else (28, 20, 28, 18)
        root.setContentsMargins(*margins)
        root.setSpacing(8 if self.technique == "LIBS" else 12)

        title_row = QHBoxLayout()
        back = QPushButton("← Home")
        back.clicked.connect(lambda: self.cancelRequested.emit(self))
        title_row.addWidget(back)
        heading = QLabel(f"Import {SPECTROSCOPY[self.workspace.key]['label']} data")
        heading.setObjectName("importTitle")
        title_row.addWidget(heading)
        title_row.addStretch()
        root.addLayout(title_row)

        note = QLabel(
            "Open a ZIP, folder or data files. Click a spectrum to preview, then check the "
            "spectra to plot. A single data file opens immediately."
            if self.technique == "LIBS" else
            "Drop one or more files here. A single detected spectrum opens immediately; "
            "multi-column files stay here so you can choose the required series."
        )
        note.setObjectName("homeSubtitle")
        note.setWordWrap(True)
        root.addWidget(note)

        self.import_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.import_splitter.setChildrenCollapsible(False)

        self.import_sidebar = QFrame()
        self.import_sidebar.setObjectName("importSidebar")
        self.import_sidebar.setMinimumWidth(300)
        self.import_sidebar.setMaximumWidth(440)
        sidebar_layout = QVBoxLayout(self.import_sidebar)
        sidebar_layout.setContentsMargins(14, 14, 14, 14)
        sidebar_layout.setSpacing(10)

        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("dropZone")
        self.drop_zone.setMinimumHeight(145)
        self.drop_zone.setMaximumHeight(180)
        drop_layout = QVBoxLayout(self.drop_zone)
        drop_layout.setContentsMargins(14, 14, 14, 14)
        drop_layout.setSpacing(6)
        drop_title = QLabel("Drop data files here")
        drop_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_title.setStyleSheet("font-size:15px;font-weight:700;")
        drop_layout.addWidget(drop_title)
        drop_note = QLabel("ZIP · TXT · CSV · Excel" if self.technique == "LIBS"
                          else "CSV · TXT · DPT · XY · DAT · Excel")
        drop_note.setObjectName("homeSubtitle")
        drop_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_note.setWordWrap(True)
        drop_layout.addWidget(drop_note)
        choose = QPushButton("Choose files…")
        choose.setObjectName("primary")
        choose.clicked.connect(self.choose_files)
        drop_layout.addWidget(choose, alignment=Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(self.drop_zone)

        files_group = QGroupBox("Selected files")
        files_layout = QVBoxLayout(files_group)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setMinimumHeight(180)
        files_layout.addWidget(self.file_list)
        file_actions = QHBoxLayout()
        add_files = QPushButton("+ Files")
        add_files.clicked.connect(self.choose_files)
        add_folder = QPushButton("+ Folder")
        add_folder.clicked.connect(self.choose_folder)
        remove = QPushButton("Remove")
        remove.clicked.connect(self.remove_selected)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_files)
        for button in (add_files, add_folder, remove, clear):
            file_actions.addWidget(button)
        files_layout.addLayout(file_actions)
        sidebar_layout.addWidget(files_group, 1)
        if self.technique == "LIBS":
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            self.drop_zone.setMinimumHeight(100)
            self.drop_zone.setMaximumHeight(120)
            self.file_list.setMinimumHeight(55)
            self.file_list.setMaximumHeight(85)
            self.preview_figure = Figure(figsize=(3.5, 2.0))
            self.preview_canvas = FigureCanvasQTAgg(self.preview_figure)
            self.preview_canvas.setMinimumHeight(150)
            sidebar_layout.addWidget(self.preview_canvas, 2)
            self.preview_info = QLabel("Click a spectrum in the list to preview its raw signal.")
            self.preview_info.setWordWrap(True)
            sidebar_layout.addWidget(self.preview_info)
        self.import_splitter.addWidget(self.import_sidebar)

        self.settings_panel = QFrame()
        self.settings_panel.setObjectName("importSettingsPanel")
        settings_layout = QVBoxLayout(self.settings_panel)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.setSpacing(12)

        options = QGroupBox("Plot preparation")
        option_form = QFormLayout(options)
        option_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        option_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.mode_combo = QComboBox()
        for label, value in (
            ("Overlay", "overlay"),
            ("Vertical stack", "stack"),
            ("Grid subplots", "grid"),
        ):
            self.mode_combo.addItem(label, value)
        self.smoothing = QSpinBox()
        self.smoothing.setRange(0, 999)
        self.smoothing.setSpecialValueText("Off")
        self.smoothing.setValue(0 if self.technique in {"XPS", "LIBS"} else 15)
        option_form.addRow("Multiple-series layout", self.mode_combo)
        option_form.addRow("Default smoothing", self.smoothing)
        settings_layout.addWidget(options)

        status_group = QGroupBox("Import status")
        status_layout = QVBoxLayout(status_group)
        self.discovery_status = QLabel(
            "Choose files or drop them onto the card. Supported numeric spectra are checked automatically."
        )
        self.discovery_status.setWordWrap(True)
        status_layout.addWidget(self.discovery_status)
        settings_layout.addWidget(status_group)

        self.review_group = QGroupBox("Choose datasets")
        review_layout = QVBoxLayout(self.review_group)
        if self.technique == "LIBS":
            self.dataset_search = QLineEdit()
            self.dataset_search.setPlaceholderText("Filter filename, folder or sample…")
            self.dataset_search.textChanged.connect(self._filter_datasets)
            review_layout.addWidget(self.dataset_search)
            selection_row = QHBoxLayout()
            select_visible = QPushButton("Select visible")
            select_visible.clicked.connect(lambda: self._check_visible_datasets(True))
            clear_selection = QPushButton("Clear selection")
            clear_selection.clicked.connect(lambda: self._check_visible_datasets(False))
            selection_row.addWidget(select_visible)
            selection_row.addWidget(clear_selection)
            review_layout.addLayout(selection_row)
        self.dataset_list = QListWidget()
        self.dataset_list.itemChanged.connect(self._update_selection_summary)
        if self.technique == "LIBS":
            self.dataset_list.currentRowChanged.connect(self._preview_dataset)
        review_layout.addWidget(self.dataset_list, 1)
        reference_form = QFormLayout()
        self.reference_combo = QComboBox()
        self.reference_combo.currentIndexChanged.connect(self._reference_changed)
        reference_form.addRow("Baseline / reference", self.reference_combo)
        review_layout.addLayout(reference_form)
        self.review_group.hide()
        settings_layout.addWidget(self.review_group, 1)
        if self.technique != "LIBS":
            settings_layout.addStretch()
        self.import_splitter.addWidget(self.settings_panel)
        self.import_splitter.setStretchFactor(0, 0)
        self.import_splitter.setStretchFactor(1, 1)
        self.import_splitter.setSizes([360, 920])
        root.addWidget(self.import_splitter, 1)

        self.import_footer = QFrame()
        self.import_footer.setObjectName("importFooter")
        footer_layout = QHBoxLayout(self.import_footer)
        footer_layout.setContentsMargins(14, 9, 10, 9)
        self.footer_status = QLabel("No data selected")
        self.footer_status.setObjectName("homeSubtitle")
        footer_layout.addWidget(self.footer_status, 1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(lambda: self.cancelRequested.emit(self))
        footer_layout.addWidget(cancel)
        technique_label = SPECTROSCOPY[self.workspace.key]["label"]
        self.open_button = QPushButton(f"Open {technique_label} analysis")
        self.open_button.setObjectName("primary")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_ready)
        footer_layout.addWidget(self.open_button)
        root.addWidget(self.import_footer)

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            f"Open {SPECTROSCOPY[self.workspace.key]['label']} data",
            "",
            ("LIBS files (*.zip *.txt *.csv *.tsv *.dat *.xy *.asc *.xlsx *.xls);;All files (*)"
             if self.technique == "LIBS" else
             "Data files (*.dpt *.csv *.tsv *.txt *.xy *.dat *.asr *.raw *.xlsx *.xls);;All files (*)"),
        )
        if paths:
            self.add_paths(paths)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose data folder")
        if not folder:
            return
        allowed = {".dpt", ".csv", ".tsv", ".txt", ".xy", ".dat", ".asr", ".raw", ".xlsx", ".xls"}
        if self.technique == "LIBS":
            allowed.update({".zip", ".asc"})
        entries = Path(folder).rglob("*") if self.technique == "LIBS" else Path(folder).iterdir()
        paths = sorted(str(path) for path in entries if path.is_file() and path.suffix.lower() in allowed
                       and not any(part.startswith(".") or part == "__MACOSX"
                                   for part in path.relative_to(folder).parts))
        if not paths:
            QMessageBox.information(self, "No data", "No supported data files were found in that folder.")
            return
        self.add_paths(paths)

    def add_paths(self, paths):
        existing = set(self.paths)
        for value in paths:
            path = str(Path(value).resolve())
            if path not in existing and Path(path).is_file():
                self.paths.append(path)
                existing.add(path)
        self._refresh_files()
        self.inspect_files()

    def _refresh_files(self):
        self.file_list.clear()
        for value in self.paths:
            self.file_list.addItem(Path(value).name)
        count = len(self.paths)
        self.footer_status.setText(
            f"{count} file{'s' if count != 1 else ''} selected"
            if count else "No data selected"
        )
        self.drop_zone.setProperty("ready", bool(self.paths))
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

    def remove_selected(self):
        rows = sorted({self.file_list.row(item) for item in self.file_list.selectedItems()}, reverse=True)
        for row in rows:
            self.paths.pop(row)
        self._refresh_files()
        if self.paths or self.image_datasets:
            self.inspect_files(automatic=False)
        else:
            self.datasets = []
            self.failures = []
            self.dataset_list.clear()
            self._preview_dataset(-1)
            self.review_group.hide()
            self.open_button.setEnabled(False)
            self.discovery_status.setText(
                "Choose files or drop them onto the card. Supported numeric spectra "
                "are checked automatically."
            )
            self.discovery_status.setToolTip("")

    def clear_files(self):
        self.paths.clear()
        self.image_datasets.clear()
        self.image_metadata.clear()
        self.datasets = []
        self.failures = []
        self.dataset_list.clear()
        self._preview_dataset(-1)
        self._refresh_files()
        self.review_group.hide()
        self.open_button.setEnabled(False)
        self.discovery_status.setText(
            "Choose files or drop them onto the card. Supported numeric spectra "
            "are checked automatically."
        )
        self.discovery_status.setToolTip("")

    def inspect_files(self, *, automatic=True):
        self.datasets, self.failures = discover_many(self.paths, minimum_points=11,
                                                    technique=self.technique)
        self.datasets.extend(self.image_datasets)
        self.discovery_status.setToolTip("\n".join(f"{name}: {reason}" for name, reason in self.failures))
        if not self.datasets:
            details = "\n".join(f"{name}: {reason}" for name, reason in self.failures)
            QMessageBox.warning(self, "No plottable data", details or "No numeric X/Y datasets were found.")
            self.review_group.hide()
            self.dataset_list.clear()
            self._preview_dataset(-1)
            self.open_button.setEnabled(False)
            self.discovery_status.setText("No supported numeric X/Y datasets were found.")
            return
        self.open_button.setEnabled(True)
        # ZIP imports always stay in review, even when they contain one spectrum.
        automatic = automatic and not any(Path(path).suffix.lower() == ".zip" for path in self.paths)
        failed = f" · {len(self.failures)} file(s) skipped" if self.failures else ""
        self.discovery_status.setText(
            f"Found {len(self.datasets)} dataset(s){failed}. "
            + ("Opening automatically…" if len(self.datasets) == 1 and automatic
               else "Review the selection, then open the analysis.")
        )
        if len(self.datasets) == 1 and automatic:
            self._emit_payload(self.datasets, None)
            return
        self._populate_dataset_review()

    def _populate_dataset_review(self):
        self.dataset_list.blockSignals(True)
        self.dataset_list.clear()
        for dataset in self.datasets:
            source = Path(dataset.source).name
            sheet = f" · {dataset.sheet}" if dataset.sheet else ""
            if self.technique == "LIBS":
                text = (f"{dataset.name}\n"
                        f"{float(np.min(dataset.x)):.3f}–{float(np.max(dataset.x)):.3f} nm"
                        f"  ·  {len(dataset.x):,} points")
            else:
                text = f"{dataset.name}  ·  {len(dataset.x):,} points  ·  {source}{sheet}"
            item = QListWidgetItem(text)
            item.setToolTip(dataset.source)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked if self.technique == "LIBS"
                               else Qt.CheckState.Checked)
            self.dataset_list.addItem(item)
        self.dataset_list.blockSignals(False)

        self.reference_combo.blockSignals(True)
        self.reference_combo.clear()
        self.reference_combo.addItem("None", -1)
        for index, dataset in enumerate(self.datasets):
            self.reference_combo.addItem(dataset.name, index)
        candidate = -1
        if self.technique in {"UVVIS", "RAMAN"}:
            words = ("baseline", "background", "blank", "reference", "dark", "substrate")
            candidate = next(
                (index for index, item in enumerate(self.datasets)
                 if any(word in item.name.casefold() for word in words)),
                -1,
            )
        self.reference_combo.setCurrentIndex(candidate + 1)
        self.reference_combo.blockSignals(False)
        self._last_reference = -1
        if candidate >= 0:
            self.dataset_list.item(candidate).setCheckState(Qt.CheckState.Unchecked)
            self._last_reference = candidate
        self.review_group.show()
        self.open_button.setEnabled(True)
        self._update_selection_summary()
        if self.technique == "LIBS":
            self._filter_datasets(self.dataset_search.text())

    def _filter_datasets(self, text):
        text = text.casefold().strip()
        first = -1
        for index, dataset in enumerate(self.datasets):
            item = self.dataset_list.item(index)
            visible = text in (dataset.name + " " + dataset.source).casefold()
            item.setHidden(not visible)
            if visible and first < 0:
                first = index
        self.dataset_list.setCurrentRow(first)
        self._preview_dataset(first)
        self._update_selection_summary()

    def _check_visible_datasets(self, checked):
        self.dataset_list.blockSignals(True)
        reference = self.reference_combo.currentData()
        for index in range(self.dataset_list.count()):
            item = self.dataset_list.item(index)
            if not checked or not item.isHidden():
                item.setCheckState(Qt.CheckState.Checked if checked and index != reference
                                   else Qt.CheckState.Unchecked)
        self.dataset_list.blockSignals(False)
        self._update_selection_summary()

    def _preview_dataset(self, index):
        if not hasattr(self, "preview_figure"):
            return
        self.preview_figure.clear()
        # Figure.clear resets subplot margins; keep labels inside the small canvas.
        self.preview_figure.subplots_adjust(left=.20, right=.97, bottom=.30, top=.95)
        if 0 <= index < len(self.datasets):
            dataset = self.datasets[index]
            ax = self.preview_figure.add_subplot()
            ax.plot(dataset.x, dataset.y, color="#0284c7", linewidth=.8)
            ax.set_xlabel("Wavelength (nm)", fontsize=8)
            ax.set_ylabel("Intensity (a.u.)", fontsize=8)
            ax.tick_params(labelsize=7)
            self.preview_info.setText(
                f"{len(dataset.x):,} points · "
                f"{float(np.min(dataset.x)):.3f}–{float(np.max(dataset.x)):.3f} nm")
            self.preview_info.setToolTip(dataset.source)
        else:
            self.preview_info.setText("Click a spectrum in the list to preview its raw signal.")
            self.preview_info.setToolTip("")
        self.preview_canvas.draw_idle()

    def _reference_changed(self):
        current = int(self.reference_combo.currentData())
        if self.technique != "LIBS" and 0 <= self._last_reference < self.dataset_list.count():
            self.dataset_list.item(self._last_reference).setCheckState(Qt.CheckState.Checked)
        if 0 <= current < self.dataset_list.count():
            self.dataset_list.item(current).setCheckState(Qt.CheckState.Unchecked)
        self._last_reference = current
        self._update_selection_summary()

    def _selected_datasets(self):
        reference = int(self.reference_combo.currentData()) if self.reference_combo.count() else -1
        return [
            dataset for index, dataset in enumerate(self.datasets)
            if index != reference
            and self.dataset_list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def _update_selection_summary(self, *_args):
        count = len(self._selected_datasets()) if self.dataset_list.count() else 0
        failed = f" · {len(self.failures)} file(s) skipped" if self.failures else ""
        self.discovery_status.setText(
            f"Found {len(self.datasets)} dataset(s); {count} selected{failed}."
            + (f" {sum(not self.dataset_list.item(i).isHidden() for i in range(self.dataset_list.count()))} visible."
               if self.technique == "LIBS" else "")
        )
        self.open_button.setEnabled(count > 0)

    def open_ready(self):
        """Open parsed data from the fixed import footer."""
        if len(self.datasets) == 1 and self.dataset_list.count() == 0:
            self._emit_payload(self.datasets, None)
        else:
            self.open_selected()

    def open_selected(self):
        selected = self._selected_datasets()
        if not selected:
            QMessageBox.information(self, "Choose data", "Select at least one sample dataset.")
            return
        reference_index = int(self.reference_combo.currentData())
        reference = self.datasets[reference_index] if reference_index >= 0 else None
        self._emit_payload(selected, reference)

    def _emit_payload(self, datasets, reference):
        mode = "individual" if len(datasets) == 1 else self.mode_combo.currentData()
        self.analysisReady.emit({
            "workspace": self.workspace,
            "datasets": list(datasets),
            "reference": reference,
            "mode": mode,
            "smooth": self.smoothing.value(),
            "files": list(self.paths),
            "digitization": dict(self.image_metadata),
        })

    def import_digitized(self, curve):
        name = curve.name
        while name in {item.name for item in self.datasets}:
            name += " (image)"
        dataset = SpectrumDataset(name, curve.x, curve.y, "Image: " + curve.metadata["source_image"])
        self.image_metadata[name] = curve.metadata
        self.image_datasets.append(dataset)
        if not self.datasets:
            self.datasets = [dataset]
            self._emit_payload([dataset], None)
            return
        selected = {item.name for item in self._selected_datasets()} if self.dataset_list.count() else set()
        reference = self.reference_combo.currentData()
        self.datasets.append(dataset); self._populate_dataset_review()
        reference = int(reference) if reference is not None else -1
        self.reference_combo.blockSignals(True)
        self.reference_combo.setCurrentIndex(reference + 1)
        self.reference_combo.blockSignals(False)
        self._last_reference = reference
        self.dataset_list.blockSignals(True)
        for index, item in enumerate(self.datasets):
            self.dataset_list.item(index).setCheckState(Qt.CheckState.Checked if item.name in selected | {name} else Qt.CheckState.Unchecked)
        self.dataset_list.blockSignals(False); self._update_selection_summary()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()


class SpectraSuiteWindow(QMainWindow):
    """One persistent window containing Home, Import and analysis documents."""

    def __init__(self, workspaces, resource_path, parent=None):
        super().__init__(parent)
        self.workspaces = tuple(workspaces)
        self.resource_path = resource_path
        self._buttons = {}
        self._document_states: dict[QWidget, dict] = {}
        self._active_state_widget = None
        self._skip_close_prompt = False
        self.setObjectName("spectraSuiteWindow")
        self.setWindowTitle(f"SpectraSuite {APP_VERSION}")
        self.resize(1500, 900)
        self.setMinimumSize(1050, 680)
        apply_theme(self, SHELL_STYLE)
        apply_window_icon(self)
        self._build_ui()
        self._build_menu()
        self.update_controller = UpdateController(
            self, update_handler=self._show_update_banner
        )
        self._sync_update_menu()
        self.update_controller.schedule_automatic_check()

    def _build_ui(self):
        self.shell_central = QWidget()
        central_layout = QVBoxLayout(self.shell_central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        self.update_banner = QFrame()
        self.update_banner.setObjectName("updateBanner")
        banner_layout = QHBoxLayout(self.update_banner)
        banner_layout.setContentsMargins(14, 8, 10, 8)
        banner_layout.setSpacing(10)
        badge = QLabel("UPDATE")
        badge.setObjectName("updateBannerBadge")
        banner_layout.addWidget(badge)
        banner_text = QWidget()
        banner_text_layout = QVBoxLayout(banner_text)
        banner_text_layout.setContentsMargins(0, 0, 0, 0)
        banner_text_layout.setSpacing(1)
        self.update_banner_title = QLabel()
        self.update_banner_title.setObjectName("updateBannerTitle")
        self.update_banner_note = QLabel()
        self.update_banner_note.setObjectName("updateBannerNote")
        self.update_banner_note.setWordWrap(True)
        banner_text_layout.addWidget(self.update_banner_title)
        banner_text_layout.addWidget(self.update_banner_note)
        banner_layout.addWidget(banner_text, 1)
        self.update_download_button = QPushButton("View release")
        self.update_download_button.clicked.connect(self._open_pending_update)
        banner_layout.addWidget(self.update_download_button)
        later = QPushButton("Later")
        later.clicked.connect(self._dismiss_update_banner)
        banner_layout.addWidget(later)
        self.update_banner.hide()
        central_layout.addWidget(self.update_banner)

        self.document_tabs = QTabWidget()
        self.document_tabs.setObjectName("documentTabs")
        self.document_tabs.setDocumentMode(True)
        self.document_tabs.setMovable(False)
        self.document_tabs.setTabsClosable(True)
        self.document_tabs.tabCloseRequested.connect(self.close_document)
        self.document_tabs.currentChanged.connect(self._document_activated)
        central_layout.addWidget(self.document_tabs, 1)
        self.setCentralWidget(self.shell_central)

        self.home_page = self._build_home_page()
        self.document_tabs.addTab(self.home_page, "Home")
        self._hide_home_close_button()
        new_button = QPushButton("+ New analysis")
        new_button.setToolTip("Return to Home and start another analysis")
        new_button.clicked.connect(self.show_home)
        self.document_tabs.setCornerWidget(new_button, Qt.Corner.TopRightCorner)

    def _build_home_page(self):
        page = QWidget()
        page.setObjectName("homePage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("homeHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(20, 14, 20, 14)
        title = QLabel("What would you like to analyse?")
        title.setObjectName("homeTitle")
        hero_layout.addWidget(title)
        subtitle = QLabel(
            "Open a workspace, drag in your data, and continue in this window. "
            "Your open analyses remain available as tabs above."
        )
        subtitle.setObjectName("homeSubtitle")
        subtitle.setWordWrap(True)
        hero_layout.addWidget(subtitle)
        actions = QHBoxLayout()
        open_session = QPushButton("Open saved session…")
        open_session.clicked.connect(self.open_session)
        actions.addWidget(open_session)
        digitize = QPushButton("Image to data…")
        digitize.clicked.connect(self.open_digitizer)
        actions.addWidget(digitize)
        appearance = QPushButton("Appearance…")
        appearance.setToolTip("Choose a light accent or gradient theme")
        appearance.clicked.connect(self._show_appearance)
        actions.addWidget(appearance)
        actions.addStretch()
        self.email_updates_button = QPushButton("Get update emails…")
        self.email_updates_button.setToolTip(
            "Open the optional SpectraSuite email-update form in your web browser"
        )
        self.email_updates_button.clicked.connect(self._open_update_signup)
        actions.addWidget(self.email_updates_button)
        hero_layout.addLayout(actions)
        outer.addWidget(hero)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        for index, workspace in enumerate(self.workspaces):
            button = QPushButton()
            button.setObjectName("workspaceTile")
            button.setProperty("comingSoon", workspace.coming_soon)
            title_text = workspace.title.replace("\n", " ")
            display_title = "Multi-X / Multi-Y" if workspace.key == "multiaxis" else title_text
            status = "Coming soon" if workspace.coming_soon else "Preview" if workspace.experimental else ""
            button.setText(display_title + (f"\n{status}" if status else ""))
            button.setAccessibleName(title_text)
            button.setToolTip(
                f"{title_text}\n{status}" if status else f"Open {title_text}"
            )
            icon_path = self.resource_path(workspace.icon)
            if icon_path.exists():
                button.setIcon(QIcon(str(icon_path)))
                button.setIconSize(QSize(28, 28))
            button.setFixedSize(235, 64)
            button.setEnabled(not workspace.coming_soon)
            button.clicked.connect(
                lambda _checked=False, selected=workspace: self.launch_workspace(selected)
            )
            self._buttons[workspace.key] = button
            grid.addWidget(button, index // 4, index % 4)
        workspace_panel = QWidget()
        workspace_panel.setLayout(grid)
        workspace_panel.setMaximumWidth(990)
        workspace_scroll = QScrollArea()
        workspace_scroll.setWidgetResizable(True)
        workspace_scroll.setFrameShape(QFrame.Shape.NoFrame)
        workspace_scroll.setWidget(workspace_panel)
        workspace_scroll.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        outer.addWidget(workspace_scroll, 1)
        footer = QLabel(f"SpectraSuite {RELEASE_TAG.removeprefix('v')} · One project window")
        footer.setObjectName("homeSubtitle")
        outer.addWidget(footer, alignment=Qt.AlignmentFlag.AlignRight)
        return page

    def _build_menu(self):
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(True)
        self._menu_order = (
            "File", "Edit", "History", "View", "Analysis", "Account", "Help",
        )
        self._top_menus = {
            name: menu_bar.addMenu(f"&{name}") for name in self._menu_order
        }

        self.new_analysis_action = QAction("&New analysis", self)
        self.new_analysis_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_analysis_action.triggered.connect(self.show_home)
        self.digitize_action = QAction("Image to data…", self)
        self.digitize_action.triggered.connect(self.open_digitizer)
        self.open_session_action = QAction("Open &session…", self)
        self.open_session_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_session_action.triggered.connect(self.open_session)
        self.close_analysis_action = QAction("&Close analysis", self)
        self.close_analysis_action.setShortcut(QKeySequence.StandardKey.Close)
        self.close_analysis_action.triggered.connect(self.close_current_document)
        self.close_analysis_action.setEnabled(False)
        self.quit_action = QAction("&Quit SpectraSuite", self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.close)

        self.home_action = QAction("Show &Home", self)
        self.home_action.setShortcut(QKeySequence("Ctrl+Shift+H"))
        self.home_action.triggered.connect(self.show_home)
        self.appearance_action = QAction("&Appearance…", self)
        self.appearance_action.triggered.connect(self._show_appearance)

        self.edition_action = QAction("Community edition · Offline-ready", self)
        self.edition_action.setEnabled(False)
        self.email_updates_action = QAction("Get &update emails…", self)
        self.email_updates_action.triggered.connect(self._open_update_signup)
        self.privacy_preferences_action = QAction(
            "Privacy && update &preferences…", self
        )
        self.privacy_preferences_action.triggered.connect(
            self._show_privacy_preferences
        )
        self.account_options_action = QAction("Account && &license options…", self)
        self.account_options_action.triggered.connect(self._show_account_options)

        self.check_update_action = QAction("Check for &Updates…", self)
        self.check_update_action.triggered.connect(lambda: self.update_controller.check(silent=False))
        self.automatic_update_action = QAction("Automatically check for updates", self)
        self.automatic_update_action.setCheckable(True)
        self.automatic_update_action.toggled.connect(self._set_automatic_updates)
        about = QAction("&About SpectraSuite", self)
        about.triggered.connect(lambda: show_about(self))
        self._shell_menu_groups = {
            "File": [
                self.new_analysis_action, self.open_session_action, self.digitize_action, None,
                self.close_analysis_action, None, self.quit_action,
            ],
            "View": [self.home_action, None, self.appearance_action],
            "Account": [
                self.edition_action, None, self.email_updates_action,
                self.privacy_preferences_action, None,
                self.account_options_action,
            ],
            "Help": [
                self.check_update_action, self.automatic_update_action, None, about,
            ],
        }
        self._apply_menu_groups(self._shell_menu_groups)

    def _apply_menu_groups(self, groups):
        """Populate permanent native menus without moving or deleting QMenus."""
        for name in self._menu_order:
            target = self._top_menus[name]
            target.clear()
            items = groups.get(name, ())
            for item in items:
                if item is None:
                    target.addSeparator()
                else:
                    target.addAction(item)
            target.menuAction().setVisible(bool(items))

    def _show_account_options(self):
        QMessageBox.information(
            self,
            "Account and licensing",
            "<b>Current status: Community edition</b><br><br>"
            "No account, login, or license key is required, and SpectraSuite remains "
            "fully usable offline.<br><br>"
            "Email update registration is optional and is kept separate from app "
            "access. SpectraSuite opens the secure subscription form only when you "
            "choose <b>Get update emails</b>.<br><br>"
            "This menu is the reserved home for optional sign-in and signed offline "
            "licenses if a paid edition is introduced later. No user or installation "
            "identifier is currently collected.",
        )

    def _show_appearance(self):
        AppearanceDialog(self).exec()

    def _open_update_signup(self):
        open_update_signup(self)

    def _show_privacy_preferences(self):
        dialog = PrivacyPreferencesDialog(self.update_controller, self)
        dialog.exec()
        self._sync_update_menu()

    def _show_update_banner(self, release):
        """Present a release unobtrusively without interrupting active analysis."""
        self._pending_update_release = dict(release)
        self.update_banner_title.setText(
            f"{release['name']} is available · You are using {RELEASE_TAG}"
        )
        note = " ".join(str(release.get("notes", "")).split())
        if len(note) > 220:
            note = note[:220].rstrip() + "…"
        self.update_banner_note.setText(note or "A newer SpectraSuite release is ready.")
        self.update_banner.show()

    def _dismiss_update_banner(self):
        self.update_banner.hide()

    def _open_pending_update(self):
        release = getattr(self, "_pending_update_release", None)
        if release and open_release_page(release["url"], self):
            self.update_banner.hide()

    def _hide_home_close_button(self):
        bar = self.document_tabs.tabBar()
        bar.setTabButton(0, QTabBar.ButtonPosition.LeftSide, None)
        bar.setTabButton(0, QTabBar.ButtonPosition.RightSide, None)

    def _sync_update_menu(self):
        self.automatic_update_action.blockSignals(True)
        self.automatic_update_action.setChecked(self.update_controller.automatic_enabled())
        self.automatic_update_action.blockSignals(False)

    def _set_automatic_updates(self, enabled):
        self.update_controller.set_automatic_enabled(enabled)

    def show_home(self):
        self.document_tabs.setCurrentWidget(self.home_page)

    def open_digitizer(self):
        widget = self.document_tabs.currentWidget()
        if hasattr(widget, "import_support"):
            widget.import_support.open_digitizer()
            return
        from qt_digitizer import ImageDigitizerDialog
        from PySide6.QtWidgets import QDialog
        dialog = ImageDigitizerDialog(self, action_label="Open as 2D plot")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.add_digitized_document(dialog.result_curve)

    def add_digitized_document(self, curve):
        from qt_general_plotter import GeneralPlotter
        workspace = next(item for item in self.workspaces if item.key == "general")
        plotter = GeneralPlotter()
        self._add_widget_document(plotter, workspace, "Digitized image")
        plotter.import_digitized(curve)
        return plotter

    def launch_workspace(self, workspace):
        if workspace.coming_soon:
            return
        if workspace.key in SPECTROSCOPY:
            page = InlineImportPage(workspace, self.resource_path, self.document_tabs)
            page.analysisReady.connect(self._open_spectroscopy)
            page.cancelRequested.connect(self._cancel_import)
            index = self.document_tabs.addTab(
                page,
                QIcon(str(self.resource_path(workspace.icon))),
                f"Import {SPECTROSCOPY[workspace.key]['label']}",
            )
            self.document_tabs.setCurrentIndex(index)
            QTimer.singleShot(0, page.choose_files)
            return
        if workspace.key == "general":
            from qt_general_plotter import GeneralPlotter

            self._add_widget_document(GeneralPlotter(), workspace, "2D Plot")
            return
        if workspace.key == "fluid":
            from qt_fluid_plotter import FluidPlotter

            self._add_widget_document(FluidPlotter(), workspace, "Fluid dynamics")
            return
        if workspace.key == "plot3d":
            from qt_3d_plotter import Plot3D

            self._add_widget_document(Plot3D(), workspace, "3D Plot")

    def _cancel_import(self, page):
        index = self.document_tabs.indexOf(page)
        if index > 0:
            self._remove_tab(index)

    def _open_spectroscopy(self, payload):
        workspace = payload["workspace"]
        config = SPECTROSCOPY[workspace.key]
        fresh = SessionState()
        fresh.technique = config["technique"]
        fresh.settings.update({
            "files": payload["files"],
            "mode": payload["mode"],
            "smooth": payload["smooth"],
            "is_all": False,
        })
        fresh.global_set["xlabel"] = config["xlabel"]
        fresh.global_set["ylabel"] = config["ylabel"]
        fresh.all_data = [
            (item.name, np.asarray(item.x), np.asarray(item.y))
            for item in payload["datasets"]
        ]
        reference = payload.get("reference")
        if reference is not None:
            fresh.pending_reference = (
                reference.name,
                np.asarray(reference.x),
                np.asarray(reference.y),
            )
        fresh.init_file_settings()
        for item in payload["datasets"]:
            fresh.file_set[item.name]["source"] = item.source
            metadata = payload.get("digitization", {}).get(item.name)
            if metadata:
                fresh.file_set[item.name].update(digitization=metadata, smooth=0, do_baseline=False, auto_clean_edges=False)
        self._create_spectroscopy_document(fresh, workspace, source_page=self.sender())

    def _create_spectroscopy_document(self, session, workspace, *, source_page=None, title=None):
        state.__dict__ = session.__dict__
        if title is None:
            if len(session.all_data) == 1:
                title = f"{SPECTROSCOPY[workspace.key]['label']} — {session.all_data[0][0]}"
            else:
                title = f"{SPECTROSCOPY[workspace.key]['label']} — {len(session.all_data)} spectra"
        viewer = PlotViewer(
            session.all_data,
            title,
            parent=self.document_tabs,
            embedded=True,
        )
        self._prepare_embedded_menus(viewer)
        viewer._session_data = state.__dict__
        viewer.closeRequested.connect(self._close_widget_request)
        self._document_states[viewer] = viewer._session_data
        icon = QIcon(str(self.resource_path(workspace.icon)))

        source_index = self.document_tabs.indexOf(source_page) if source_page is not None else -1
        index = self.document_tabs.addTab(viewer, icon, title)
        self.document_tabs.setTabToolTip(index, title)
        self.document_tabs.setCurrentIndex(index)
        if source_index > 0:
            self._remove_tab(source_index)

    def _add_widget_document(self, widget, workspace, title):
        widget.setParent(self.document_tabs)
        icon = QIcon(str(self.resource_path(workspace.icon)))
        index = self.document_tabs.addTab(widget, icon, title)
        self.document_tabs.setCurrentIndex(index)

    def _document_activated(self, index):
        widget = self.document_tabs.widget(index)
        session_data = self._document_states.get(widget)
        if session_data is not None:
            state.__dict__ = session_data
            self._active_state_widget = widget
            self._show_document_menus(widget)
        else:
            self._active_state_widget = None
            self._show_shell_menus()

    def _prepare_embedded_menus(self, viewer):
        """Expose viewer actions without moving macOS-owned QMenu objects."""
        child_bar = getattr(viewer, "desktop_menu_bar", None)
        if child_bar is None:
            child_bar = viewer.findChild(QMenuBar)
        if child_bar is None:
            viewer._embedded_menu_groups = {}
            return
        child_bar.setNativeMenuBar(False)
        child_bar.hide()
        viewer._embedded_menu_groups = {
            name: list(items)
            for name, items in getattr(viewer, "menu_action_groups", {}).items()
        }

    def _show_document_menus(self, viewer):
        source = getattr(viewer, "_embedded_menu_groups", {})
        groups = {name: list(items) for name, items in source.items()}
        groups["File"] = [
            self.new_analysis_action, self.open_session_action, self.digitize_action, None,
        ] + groups.get("File", []) + [None, self.quit_action]
        groups["View"] = groups.get("View", []) + [None, self.home_action]
        groups["Account"] = list(self._shell_menu_groups["Account"])
        groups["Help"] = list(self._shell_menu_groups["Help"])
        self._apply_menu_groups(groups)

    def _show_shell_menus(self):
        if not hasattr(self, "_shell_menu_groups"):
            return
        self.close_analysis_action.setEnabled(self.document_tabs.currentIndex() > 0)
        self._apply_menu_groups(self._shell_menu_groups)

    def _close_widget_request(self, widget):
        index = self.document_tabs.indexOf(widget)
        if index > 0:
            self.close_document(index)

    def close_current_document(self):
        index = self.document_tabs.currentIndex()
        if index > 0:
            self.close_document(index)
        else:
            self.show_home()

    def close_document(self, index):
        if index <= 0:
            self.show_home()
            return
        widget = self.document_tabs.widget(index)
        if widget in self._document_states:
            state.__dict__ = self._document_states[widget]
            box = QMessageBox(self)
            box.setWindowTitle("Close analysis")
            box.setText("Save this analysis session before closing it?")
            save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
            discard = box.addButton("Don't Save", QMessageBox.ButtonRole.DestructiveRole)
            cancel = box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() == cancel:
                return
            if box.clickedButton() == save and not widget.save_session(
                save_as=not bool(state.current_session_file)
            ):
                return
            if box.clickedButton() == discard:
                widget.sync_annotations_to_state()
        self._remove_tab(index)
        if self.document_tabs.count() == 1:
            self.show_home()

    def _remove_tab(self, index):
        widget = self.document_tabs.widget(index)
        self._document_states.pop(widget, None)
        self.document_tabs.removeTab(index)
        if hasattr(widget, "_skip_close_prompt"):
            widget._skip_close_prompt = True
        widget.close()
        widget.deleteLater()
        self._hide_home_close_button()

    def open_session(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open SpectraSuite session", "", "Session files (*.json)"
        )
        if not filename:
            return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8"))
            technique = data.get("technique") or self._infer_session_technique(data)
            workspace_key = {
                "FTIR": "ir", "XRD": "xrd", "UVVIS": "uvvis", "RAMAN": "raman",
                "XPS": "xps", "LIBS": "libs",
            }[technique]
            workspace = next(item for item in self.workspaces if item.key == workspace_key)
            fresh = SessionState()
            fresh.technique = technique
            fresh.settings = data["settings"]
            fresh.all_data = [
                (stem, np.asarray(x, dtype=float), np.asarray(y, dtype=float))
                for stem, x, y in data["all_data"]
            ]
            fresh.master_folder = data.get("master_folder")
            fresh.file_set = data["file_set"]
            fresh.global_set = data["global_set"]
            fresh.current_session_file = filename
            fresh.general_format = fresh.settings.get("general_format")
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            QMessageBox.critical(self, "Session error", f"Could not open this session:\n{error}")
            return
        self._create_spectroscopy_document(
            fresh,
            workspace,
            title=f"{SPECTROSCOPY[workspace_key]['label']} — {Path(filename).stem}",
        )

    @staticmethod
    def _infer_session_technique(data):
        xlabel = str(data.get("global_set", {}).get("xlabel", "")).casefold()
        if "2θ" in xlabel or "2theta" in xlabel:
            return "XRD"
        if "wavelength" in xlabel:
            return "UVVIS"
        if "raman" in xlabel:
            return "RAMAN"
        return "FTIR"

    def closeEvent(self, event):
        if self._skip_close_prompt:
            for widget in list(self._document_states):
                widget._skip_close_prompt = True
            event.accept()
            return
        if self.document_tabs.count() <= 1:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "Quit SpectraSuite",
            "Close SpectraSuite and all open analyses?\n\nSave any sessions you want to continue later first.",
            QMessageBox.StandardButton.Close | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Close:
            for widget in list(self._document_states):
                widget._skip_close_prompt = True
            event.accept()
        else:
            event.ignore()
