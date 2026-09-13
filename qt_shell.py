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
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app_version import APP_VERSION
from config import SessionState, state
from dataset_reader import discover_many
from qt_plot_viewer import PlotViewer
from qt_theme import LIGHT_STYLE, apply_window_icon
from qt_updates import UpdateController, show_about


SPECTROSCOPY = {
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
QLabel#homeTitle { color: #172033; font-size: 28px; font-weight: 800; }
QLabel#homeSubtitle { color: #64748b; font-size: 14px; }
QPushButton#workspaceTile {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    text-align: left;
    padding: 14px;
    font-size: 15px;
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
QLabel#importTitle { color: #172033; font-size: 22px; font-weight: 800; }
QTabWidget#documentTabs::pane { border: none; background-color: #f4f7fb; }
QTabWidget#documentTabs > QTabBar::tab {
    min-width: 145px;
    padding: 9px 16px;
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
        self._last_reference = -1
        self.setObjectName("importPage")
        self.setAcceptDrops(True)
        self._build_ui()

    @property
    def technique(self):
        return SPECTROSCOPY[self.workspace.key]["technique"]

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 24, 34, 28)
        root.setSpacing(14)

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
            "Drop one or more files here. A single detected spectrum opens immediately; "
            "multi-column files stay here so you can choose the required series."
        )
        note.setObjectName("homeSubtitle")
        note.setWordWrap(True)
        root.addWidget(note)

        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("dropZone")
        drop_layout = QVBoxLayout(self.drop_zone)
        drop_layout.setContentsMargins(18, 18, 18, 18)
        drop_title = QLabel("Drop data files here")
        drop_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_title.setStyleSheet("font-size:17px;font-weight:700;")
        drop_layout.addWidget(drop_title)
        drop_note = QLabel("CSV · TSV · TXT · DPT · XY · DAT · Excel")
        drop_note.setObjectName("homeSubtitle")
        drop_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(drop_note)
        choose = QPushButton("Choose files…")
        choose.setObjectName("primary")
        choose.clicked.connect(self.choose_files)
        drop_layout.addWidget(choose, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.drop_zone)

        files_group = QGroupBox("Selected files")
        files_layout = QVBoxLayout(files_group)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setMinimumHeight(100)
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
        file_actions.addStretch()
        files_layout.addLayout(file_actions)
        root.addWidget(files_group)

        options = QGroupBox("Plot preparation")
        option_form = QFormLayout(options)
        self.mode_combo = QComboBox()
        for label, value in (
            ("Overlay", "overlay"),
            ("Vertical stack", "stack"),
            ("Grid subplots", "grid"),
        ):
            self.mode_combo.addItem(label, value)
        self.smoothing = QSpinBox()
        self.smoothing.setRange(1, 999)
        self.smoothing.setValue(15)
        option_form.addRow("Multiple-series layout", self.mode_combo)
        option_form.addRow("Default smoothing", self.smoothing)
        root.addWidget(options)

        self.review_group = QGroupBox("Choose datasets")
        review_layout = QVBoxLayout(self.review_group)
        self.discovery_status = QLabel()
        self.discovery_status.setWordWrap(True)
        review_layout.addWidget(self.discovery_status)
        self.dataset_list = QListWidget()
        self.dataset_list.itemChanged.connect(self._update_selection_summary)
        review_layout.addWidget(self.dataset_list, 1)
        reference_form = QFormLayout()
        self.reference_combo = QComboBox()
        self.reference_combo.currentIndexChanged.connect(self._reference_changed)
        reference_form.addRow("Baseline / reference", self.reference_combo)
        review_layout.addLayout(reference_form)
        plot = QPushButton("Open selected data")
        plot.setObjectName("primary")
        plot.clicked.connect(self.open_selected)
        review_layout.addWidget(plot)
        self.review_group.hide()
        root.addWidget(self.review_group, 1)

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            f"Open {SPECTROSCOPY[self.workspace.key]['label']} data",
            "",
            "Data files (*.dpt *.csv *.tsv *.txt *.xy *.dat *.asr *.raw *.xlsx *.xls);;All files (*)",
        )
        if paths:
            self.add_paths(paths)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose data folder")
        if not folder:
            return
        allowed = {".dpt", ".csv", ".tsv", ".txt", ".xy", ".dat", ".asr", ".raw", ".xlsx", ".xls"}
        paths = sorted(str(path) for path in Path(folder).iterdir() if path.suffix.lower() in allowed)
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
        self.drop_zone.setProperty("ready", bool(self.paths))
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

    def remove_selected(self):
        rows = sorted({self.file_list.row(item) for item in self.file_list.selectedItems()}, reverse=True)
        for row in rows:
            self.paths.pop(row)
        self._refresh_files()
        if self.paths:
            self.inspect_files(automatic=False)
        else:
            self.datasets = []
            self.review_group.hide()

    def clear_files(self):
        self.paths.clear()
        self.datasets = []
        self._refresh_files()
        self.review_group.hide()

    def inspect_files(self, *, automatic=True):
        self.datasets, self.failures = discover_many(self.paths, minimum_points=11)
        if not self.datasets:
            details = "\n".join(f"{name}: {reason}" for name, reason in self.failures)
            QMessageBox.warning(self, "No plottable data", details or "No numeric X/Y datasets were found.")
            self.review_group.hide()
            return
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
            item = QListWidgetItem(
                f"{dataset.name}  ·  {len(dataset.x):,} points  ·  {source}{sheet}"
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
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
        self._update_selection_summary()

    def _reference_changed(self):
        current = int(self.reference_combo.currentData())
        if 0 <= self._last_reference < self.dataset_list.count():
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
        )

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
        })

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
        self.setStyleSheet(SHELL_STYLE)
        apply_window_icon(self)
        self._build_ui()
        self._build_menu()
        self.update_controller = UpdateController(self)
        self._sync_update_menu()
        self.update_controller.schedule_automatic_check()

    def _build_ui(self):
        self.document_tabs = QTabWidget()
        self.document_tabs.setObjectName("documentTabs")
        self.document_tabs.setDocumentMode(True)
        self.document_tabs.setMovable(False)
        self.document_tabs.setTabsClosable(True)
        self.document_tabs.tabCloseRequested.connect(self.close_document)
        self.document_tabs.currentChanged.connect(self._document_activated)
        self.setCentralWidget(self.document_tabs)

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
        outer.setContentsMargins(42, 34, 42, 34)
        outer.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("homeHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 22, 28, 22)
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
        actions.addStretch()
        hero_layout.addLayout(actions)
        outer.addWidget(hero)

        active_label = QLabel("WORKSPACES")
        active_label.setObjectName("sectionLabel")
        outer.addWidget(active_label)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        for index, workspace in enumerate(self.workspaces):
            button = QPushButton()
            button.setObjectName("workspaceTile")
            button.setProperty("comingSoon", workspace.coming_soon)
            title_text = workspace.title.replace("\n", " ")
            button.setText(
                f"{title_text}\n"
                + ("Coming soon" if workspace.coming_soon else "Open workspace")
            )
            icon_path = self.resource_path(workspace.icon)
            if icon_path.exists():
                button.setIcon(QIcon(str(icon_path)))
                button.setIconSize(QSize(42, 42))
            button.setMinimumHeight(96)
            button.setEnabled(not workspace.coming_soon)
            button.clicked.connect(
                lambda _checked=False, selected=workspace: self.launch_workspace(selected)
            )
            self._buttons[workspace.key] = button
            grid.addWidget(button, index // 3, index % 3)
        outer.addLayout(grid)
        outer.addStretch()
        footer = QLabel(f"SpectraSuite {APP_VERSION} · One project window")
        footer.setObjectName("homeSubtitle")
        outer.addWidget(footer, alignment=Qt.AlignmentFlag.AlignRight)
        return page

    def _build_menu(self):
        menu = self.menuBar()
        menu.setNativeMenuBar(True)
        file_menu = menu.addMenu("&File")
        new_action = QAction("&New analysis", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.show_home)
        file_menu.addAction(new_action)
        open_session = QAction("Open &session…", self)
        open_session.setShortcut(QKeySequence.StandardKey.Open)
        open_session.triggered.connect(self.open_session)
        file_menu.addAction(open_session)
        file_menu.addSeparator()
        close_action = QAction("&Close analysis", self)
        close_action.setShortcut(QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.close_current_document)
        file_menu.addAction(close_action)
        file_menu.addSeparator()
        quit_action = QAction("&Quit SpectraSuite", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = menu.addMenu("&View")
        home_action = QAction("Show &Home", self)
        home_action.setShortcut(QKeySequence("Ctrl+Shift+H"))
        home_action.triggered.connect(self.show_home)
        view_menu.addAction(home_action)

        help_menu = menu.addMenu("&Help")
        self.check_update_action = QAction("Check for &Updates…", self)
        self.check_update_action.triggered.connect(lambda: self.update_controller.check(silent=False))
        help_menu.addAction(self.check_update_action)
        self.automatic_update_action = QAction("Automatically check for updates", self)
        self.automatic_update_action.setCheckable(True)
        self.automatic_update_action.toggled.connect(self._set_automatic_updates)
        help_menu.addAction(self.automatic_update_action)
        help_menu.addSeparator()
        about = QAction("&About SpectraSuite", self)
        about.triggered.connect(lambda: show_about(self))
        help_menu.addAction(about)
        self._shell_menu_actions = list(menu.actions())

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
        """Promote the active viewer's menus to the one top-level menu bar."""
        child_bar = viewer.findChild(QMenuBar)
        if child_bar is None:
            viewer._embedded_menu_actions = []
            return
        child_bar.setNativeMenuBar(False)
        child_bar.hide()
        menus = [action.menu() for action in child_bar.actions() if action.menu() is not None]
        file_menu = next(
            (menu for menu in menus if menu.title().replace("&", "") == "File"),
            None,
        )
        if file_menu is not None:
            first = file_menu.actions()[0] if file_menu.actions() else None
            new_action = QAction("New &analysis", viewer)
            new_action.setShortcut(QKeySequence.StandardKey.New)
            new_action.triggered.connect(self.show_home)
            open_action = QAction("Open another &session…", viewer)
            open_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
            open_action.triggered.connect(self.open_session)
            file_menu.insertAction(first, open_action)
            file_menu.insertAction(open_action, new_action)
            file_menu.insertSeparator(first)
            file_menu.addSeparator()
            quit_action = QAction("Quit SpectraSuite", viewer)
            quit_action.setShortcut(QKeySequence.StandardKey.Quit)
            quit_action.triggered.connect(self.close)
            file_menu.addAction(quit_action)
        view_menu = next(
            (menu for menu in menus if menu.title().replace("&", "") == "View"),
            None,
        )
        if view_menu is not None:
            view_menu.addSeparator()
            home_action = QAction("Show &Home", viewer)
            home_action.triggered.connect(self.show_home)
            view_menu.addAction(home_action)
        viewer._embedded_menu_actions = list(child_bar.actions())

    def _show_document_menus(self, viewer):
        menu = self.menuBar()
        for action in list(menu.actions()):
            menu.removeAction(action)
        for action in getattr(viewer, "_embedded_menu_actions", []):
            menu.addAction(action)

    def _show_shell_menus(self):
        if not hasattr(self, "_shell_menu_actions"):
            return
        menu = self.menuBar()
        for action in list(menu.actions()):
            menu.removeAction(action)
        for action in self._shell_menu_actions:
            menu.addAction(action)

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
