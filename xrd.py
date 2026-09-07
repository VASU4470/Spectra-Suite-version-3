import sys
import os
import traceback
from pathlib import Path
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from config import state
from qt_plot_viewer import run_plot_viewer
from qt_setup import run_setup_dialog
from readers import robust_read_spectrum as robust_read_xrd
# robust_read_xrd is now imported from readers.py (was duplicated here and
# in ir.py -- unified after confirming byte-for-byte equivalent parsing
# behavior for comma/tab/space/semicolon-delimited input).


def load_data_files(parent=None):
    if state.pending_data:
        state.all_data.extend(state.pending_data)
        state.pending_data = []
        return True
    file_list = [Path(f) for f in state.settings.get('files', [])]
    if not file_list:
        QMessageBox.critical(parent, "Error", "No files selected or found.")
        return False

    accepted_formats = ".csv, .txt, .xy, .dat, .xlsx"
    bad_files = []

    for p in file_list:
        try:
            x, y = robust_read_xrd(p)
            if len(x) > 10:
                state.all_data.append((p.stem, x, y))
            else:
                bad_files.append(p)
        except Exception:
            bad_files.append(p)

    # --- ERROR HANDLING POP-UP ---
    if bad_files:
        ext = bad_files[0].suffix.lower() if bad_files[0].suffix else "Unknown"
        msg = (f"You uploaded a file format '{ext}' which is not processed by the program.\n\n"
               f"Please upload the list of these formats: {accepted_formats}, or try a different format file.")
        QMessageBox.critical(parent, "File Format Error", msg)

        if not state.all_data:
            return False
    # ----------------------------------

    state.technique = 'XRD'
    return True


def main():
    state.technique = 'XRD'
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SpectraSuite XRD")

    # Set default global axes labels for XRD
    state.global_set['xlabel'] = '2θ (°)'
    state.global_set['ylabel'] = 'Intensity (a.u.)'
    # -----------------------

    # ==========================================
    # OUTER LOOP: each pass is one full "setup -> view -> exit/menu" cycle.
    # Mirrors ir.py's main() -- see that file for the detailed explanation of
    # why this replaced the old os.execl() re-exec approach (broken under
    # multiprocessing + PyInstaller on Windows).
    # ==========================================
    while True:
        state.restart_to_menu = False
        state.mode_switched_mid_session = False

        # ==========================================
        # RETRY LOOP: Keeps app open if files fail
        # ==========================================
        while True:
            state.all_data.clear()  # Clear out old memory if we are retrying

            setup_app = run_setup_dialog()

            if not setup_app.ready:
                sys.exit()  # If they clicked the red X to close the window, actually close.

            if getattr(setup_app, 'loaded_from_session', False):
                break  # Success! Break the loop and go to plotter.
            else:
                if load_data_files():
                    state.init_file_settings()
                    break  # Success! Break the loop and go to plotter.
                else:
                    continue
        # ==========================================

        mode = state.settings.get('mode', 'individual')

        if mode in ['overlay', 'stack', 'grid']:
            title = {
                "overlay": "XRD Overlay Mode", "stack": "XRD Vertical Stack",
                "grid": "XRD Grid Mode",
            }[mode]
            run_plot_viewer(state.all_data, title, out_dir=None)

        elif mode == 'individual':
            for i, data_tuple in enumerate(state.all_data):
                stem = data_tuple[0]
                result = run_plot_viewer(
                    [data_tuple], f"XRD File {i+1}/{len(state.all_data)}: {stem}", out_dir=None
                )

                if result != QDialog.DialogCode.Accepted:
                    break

                if state.restart_to_menu:
                    # User asked to return to the main menu mid-way through
                    # a multi-file individual run -- stop showing the rest.
                    break
                if state.mode_switched_mid_session:
                    # See ir.py's identical comment: "Add File(s)" ->
                    # Overlay/Stack from inside the window that just closed
                    # means state.all_data now has file(s) this loop never
                    # expected, already shown together -- stop here.
                    break

        if not state.restart_to_menu:
            break  # Normal end of this pass (the "exit" path already terminated the process directly)
        # else: loop back around to the shared Qt setup dialog
    # ==========================================


def run():
    """Entry point for launcher.py's multiprocessing.Process(target=...) --
    see the identical comment in ir.py's run() for why this wrapper exists
    (the old __main__-guard-only crash handler never actually ran when
    main() was invoked this way)."""
    try:
        main()
    except Exception:
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "CRASH_REPORT_XRD.txt")
        try:
            with open(desktop_path, "w") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise


if __name__ == "__main__":
    run()
