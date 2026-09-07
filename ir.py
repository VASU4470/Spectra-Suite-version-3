import sys
import os
import traceback

try:
    # --- YOUR ACTUAL IR.PY CODE STARTS HERE ---
    from pathlib import Path
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
    from config import state
    from qt_plot_viewer import run_plot_viewer
    from qt_setup import run_setup_dialog
    from readers import robust_read_spectrum as robust_read_ftir

    # (The imports at the top of your file stay exactly the same)

    # robust_read_ftir is now imported from readers.py (was duplicated here
    # and in xrd.py -- unified after confirming byte-for-byte equivalent
    # parsing behavior for comma/tab/space/semicolon-delimited input).

    def load_data_files(parent=None):
        if state.pending_data:
            state.all_data.extend(state.pending_data)
            state.pending_data = []
            return True
        # The shared Qt setup dialog stores the ordered selection here.
        file_list = [Path(f) for f in state.settings.get('files', [])]
            
        if not file_list:
            QMessageBox.critical(parent, "Error", "No files selected or found.")
            return False # <--- Changed from sys.exit()

        accepted_formats = ".dpt, .csv, .txt, .xy, .xlsx"
        bad_files = []

        for p in file_list:
            try:
                x, y = robust_read_ftir(p)
                if len(x) > 10: 
                    state.all_data.append((p.stem, x, y))
                else:
                    bad_files.append(p)
            except Exception:
                bad_files.append(p)

        # --- NEW: ERROR HANDLING POP-UP ---
        if bad_files:
            ext = bad_files[0].suffix.lower() if bad_files[0].suffix else "Unknown"
            msg = (f"You uploaded a file format '{ext}' which is not processed by the program.\n\n"
                   f"Please upload the list of these formats: {accepted_formats}, or try a different format file.")
            QMessageBox.critical(parent, "File Format Error", msg)
            
            # If no files worked at all, we must return to setup
            if not state.all_data:
                return False # <--- Changed from sys.exit()
        # ----------------------------------
        
        return True # <--- Signal that the files loaded successfully!

    def main():
               
        from config import state
        state.technique = 'FTIR'
        app = QApplication.instance() or QApplication(sys.argv)
        app.setApplicationName("SpectraSuite FT-IR")

        # ==========================================
        # OUTER LOOP: each pass is one full "setup -> view -> exit/menu" cycle.
        # A pass ends when the viewer closes or loops back when the user picks
        # "Return to file-selection screen" in the Qt close dialog.
        # ==========================================
        while True:
            state.restart_to_menu = False
            state.mode_switched_mid_session = False

            # ==========================================
            # RETRY LOOP: Keeps app open if files fail
            # ==========================================
            while True:
                state.all_data.clear() # Clear out old memory if we are retrying

                setup_app = run_setup_dialog()

                if not setup_app.ready:
                    sys.exit() # If they clicked the red X to close the window, actually close.

                if getattr(setup_app, 'loaded_from_session', False):
                    break # Success! Break the loop and go to plotter.
                else:
                    if load_data_files():
                        state.init_file_settings()
                        break # Success! Break the loop and go to plotter.
                    else:
                        continue
            # ==========================================

            mode = state.settings.get('mode', 'individual')

            if mode in ['overlay', 'stack', 'grid']:
                title = {
                    "overlay": "FT-IR Overlay Mode", "stack": "FT-IR Vertical Stack",
                    "grid": "FT-IR Grid Mode",
                }[mode]

                run_plot_viewer(state.all_data, title, out_dir=None)

            elif mode == 'individual':
                for i, data_tuple in enumerate(state.all_data):
                    stem = data_tuple[0]

                    result = run_plot_viewer(
                        [data_tuple], f"File {i+1}/{len(state.all_data)}: {stem}", out_dir=None
                    )

                    if result != QDialog.DialogCode.Accepted:
                        break

                    if state.restart_to_menu:
                        # User asked to return to the main menu mid-way through
                        # a multi-file individual run -- stop showing the rest.
                        break
                    if state.mode_switched_mid_session:
                        # User used "Add File(s)" -> Overlay/Stack from inside
                        # the window that just closed. state.all_data now
                        # contains file(s) this loop never expected, already
                        # shown together in that window -- continuing here
                        # would pop open a second, stale individual-mode
                        # window for them. Stop; the session is effectively
                        # already finished.
                        break

            if not state.restart_to_menu:
                break # Normal end of this pass (the "exit" path already terminated the process directly)
            # else: loop back around to the shared Qt setup dialog
        # ==========================================

    def run():
        """Entry point for launcher.py's multiprocessing.Process(target=...).

        The module-level try/except wrapping this whole file only guards the
        *initial import* of ir.py -- it does NOT wrap later calls to main()
        made via multiprocessing.Process(target=ir.main), since that call
        happens well outside this try block's dynamic extent. That meant any
        exception inside main() silently killed the child process with no
        error message at all -- indistinguishable from "the window just
        never opened." This wrapper gives main() its own crash handling that
        actually fires regardless of how it's invoked.
        """
        try:
            main()
        except Exception:
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "CRASH_REPORT.txt")
            try:
                with open(desktop_path, "w") as f:
                    f.write("THE APP CRASHED. HERE IS THE EXACT ERROR:\n\n")
                    f.write(traceback.format_exc())
            except Exception:
                pass
            raise

    if __name__ == "__main__":
        run()

# --- THE FAILSAFE ---
except Exception:
    # Get the cross-platform path to the user's Desktop
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "CRASH_REPORT.txt")
    
    # If the app crashes, write the exact error to the Desktop!
    with open(desktop_path, "w") as f:
        f.write("THE APP CRASHED. HERE IS THE EXACT ERROR:\n\n")
        f.write(traceback.format_exc())
