"""PySide6 General Plotter workspace."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from config import state
from qt_plot_viewer import run_plot_viewer
from qt_setup import run_setup_dialog
from readers import read_generic_configured


def _unique_stem(path: Path, used: set[str]) -> str:
    stem = path.stem
    if stem not in used:
        return stem
    index = 2
    while f"{stem}_{index}" in used:
        index += 1
    return f"{stem}_{index}"


def load_data_files(fmt, parent=None):
    """Read selected files using the confirmed General Plotter configuration."""
    file_list = [Path(value) for value in state.settings.get("files", [])]
    if not file_list:
        QMessageBox.critical(parent, "Error", "No files selected or found.")
        return False

    bad_files = []
    used = set()
    for path in file_list:
        try:
            x, y = read_generic_configured(path, **fmt)
            if len(x) <= 2:
                raise ValueError("not enough numeric rows")
        except Exception:
            bad_files.append(path)
            continue
        stem = _unique_stem(path, used)
        used.add(stem)
        state.all_data.append((stem, x, y))

    if bad_files:
        names = "\n".join(f"• {path.name}" for path in bad_files[:10])
        more = f"\n…and {len(bad_files) - 10} more" if len(bad_files) > 10 else ""
        QMessageBox.warning(
            parent,
            "Parsing Error",
            "These files produced no usable numeric data with the selected "
            f"configuration:\n\n{names}{more}\n\nAdjust the delimiter, header rows, or columns.",
        )
    return bool(state.all_data)


def main():
    state.technique = "GENERAL"
    state.global_set["xlabel"] = "X"
    state.global_set["ylabel"] = "Y"
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SpectraSuite General Plotter")

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
            fmt = state.general_format or state.settings.get("general_format")
            if fmt and load_data_files(fmt):
                state.init_file_settings()
                break

        mode = state.settings.get("mode", "individual")
        if mode in {"overlay", "stack"}:
            title = "General Data Overlay" if mode == "overlay" else "General Data Stacked Grid"
            run_plot_viewer(state.all_data, title)
        else:
            for index, data_tuple in enumerate(state.all_data):
                stem = data_tuple[0]
                result = run_plot_viewer(
                    [data_tuple],
                    f"General Data {index + 1}/{len(state.all_data)}: {stem}",
                )
                if result != QDialog.DialogCode.Accepted:
                    break
                if state.restart_to_menu or state.mode_switched_mid_session:
                    break

        if not state.restart_to_menu:
            break


def run():
    try:
        main()
    except Exception:
        desktop_path = Path(os.path.expanduser("~")) / "Desktop" / "CRASH_REPORT_GENERAL.txt"
        try:
            desktop_path.write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass


if __name__ == "__main__":
    run()
