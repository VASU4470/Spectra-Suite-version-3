"""UV-Vis spectroscopy workspace."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from config import state
from qt_plot_viewer import run_plot_viewer
from qt_setup import run_setup_dialog
from readers import robust_read_spectrum


def load_data_files(parent=None):
    if state.pending_data:
        state.all_data.extend(state.pending_data)
        state.pending_data = []
        return True
    files = [Path(value) for value in state.settings.get("files", [])]
    if not files:
        QMessageBox.critical(parent, "Error", "No files selected or found.")
        return False
    bad_files = []
    for path in files:
        try:
            x, y = robust_read_spectrum(path)
            if len(x) > 10:
                state.all_data.append((path.stem, x, y))
            else:
                bad_files.append(path)
        except Exception:
            bad_files.append(path)
    if bad_files:
        QMessageBox.critical(
            parent, "File format error",
            "Could not read: " + ", ".join(item.name for item in bad_files) +
            "\n\nUse a two-column delimited-text or Excel spectrum.",
        )
    return bool(state.all_data)


def main():
    state.technique = "UVVIS"
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SpectraSuite UV-Vis")
    state.global_set["xlabel"] = "Wavelength (nm)"
    state.global_set["ylabel"] = "Absorbance"

    while True:
        state.restart_to_menu = False
        state.mode_switched_mid_session = False
        while True:
            state.all_data.clear()
            setup = run_setup_dialog()
            if not setup.ready:
                return
            if setup.loaded_from_session:
                break
            if load_data_files():
                state.init_file_settings()
                break
        mode = state.settings.get("mode", "individual")
        if mode in {"overlay", "stack", "grid"}:
            title = {
                "overlay": "UV-Vis Overlay Mode", "stack": "UV-Vis Vertical Stack",
                "grid": "UV-Vis Grid Mode",
            }[mode]
            run_plot_viewer(state.all_data, title, out_dir=None)
        else:
            for index, data in enumerate(state.all_data):
                result = run_plot_viewer(
                    [data], f"UV-Vis File {index + 1}/{len(state.all_data)}: {data[0]}", out_dir=None
                )
                if result != QDialog.DialogCode.Accepted or state.restart_to_menu or state.mode_switched_mid_session:
                    break
        if not state.restart_to_menu:
            break


def run():
    try:
        main()
    except Exception:
        details = traceback.format_exc()
        try:
            QMessageBox.critical(None, "UV-Vis workspace error", details)
        finally:
            raise


if __name__ == "__main__":
    run()
