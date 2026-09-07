"""Raman spectroscopy workspace."""

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
    files = [Path(value) for value in state.settings.get("files", [])]
    if not files:
        QMessageBox.critical(parent, "Error", "No files selected or found.")
        return False
    failed = []
    for path in files:
        try:
            x, y = robust_read_spectrum(path)
            if len(x) > 10:
                state.all_data.append((path.stem, x, y))
            else:
                failed.append(path)
        except Exception:
            failed.append(path)
    if failed:
        QMessageBox.critical(parent, "File format error", "Could not read: " + ", ".join(p.name for p in failed))
    return bool(state.all_data)


def main():
    state.technique = "RAMAN"
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SpectraSuite Raman")
    state.global_set["xlabel"] = "Raman shift (cm⁻¹)"
    state.global_set["ylabel"] = "Intensity (a.u.)"
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
        if mode in {"overlay", "stack"}:
            title = "Raman Overlay Mode" if mode == "overlay" else "Raman Stacked Grid Mode"
            run_plot_viewer(state.all_data, title, out_dir=None)
        else:
            for index, data in enumerate(state.all_data):
                result = run_plot_viewer([data], f"Raman File {index+1}/{len(state.all_data)}: {data[0]}")
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
            QMessageBox.critical(None, "Raman workspace error", details)
        finally:
            raise


if __name__ == "__main__":
    run()
