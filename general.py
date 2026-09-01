import sys
import os
import traceback
import tkinter as tk
from tkinter import messagebox

from config import state
from gui import SetupGUI, PlotViewer, ColumnPickerDialog
from theme import apply_theme


def load_data_files(root_window, fmt):
    """Reads every selected file using the column configuration the user
    confirmed in ColumnPickerDialog (same config applied to all files in
    this session -- see readers.read_generic_configured)."""
    from pathlib import Path
    from readers import read_generic_configured

    file_list = [Path(f) for f in state.settings.get('files', [])]
    if not file_list:
        messagebox.showerror("Error", "No files selected or found.", parent=root_window)
        return False

    bad_files = []
    for p in file_list:
        try:
            x, y = read_generic_configured(p, **fmt)
            if len(x) > 2:
                state.all_data.append((p.stem, x, y))
            else:
                bad_files.append(p)
        except Exception:
            bad_files.append(p)

    if bad_files:
        names = "\n".join(f"  - {p.name}" for p in bad_files[:10])
        more = f"\n  ...and {len(bad_files) - 10} more" if len(bad_files) > 10 else ""
        msg = (f"The following file(s) produced no usable numeric data with the "
               f"current column configuration:\n\n{names}{more}\n\n"
               f"Try adjusting the delimiter, header rows, or column indices.")
        messagebox.showerror("Parsing Error", msg, parent=root_window)

        if not state.all_data:
            return False

    state.technique = 'GENERAL'
    return True


def main():
    state.technique = 'GENERAL'
    state.global_set['xlabel'] = 'X'
    state.global_set['ylabel'] = 'Y'

    # ==========================================
    # OUTER LOOP: mirrors ir.py/xrd.py's main() -- see ir.py for the detailed
    # explanation of why this replaced os.execl() for the "Return to Menu" flow.
    # ==========================================
    while True:
        state.restart_to_menu = False
        state.mode_switched_mid_session = False

        # ==========================================
        # RETRY LOOP: Keeps app open if files fail or the user cancels the
        # column-picker instead of committing to a configuration.
        # ==========================================
        while True:
            state.all_data.clear()

            root = tk.Tk()
            apply_theme(root)
            setup_app = SetupGUI(root)
            root.mainloop()

            if not setup_app.ready:
                sys.exit()

            dummy_root = tk.Tk()
            apply_theme(dummy_root)
            dummy_root.withdraw()

            if getattr(setup_app, 'loaded_from_session', False):
                break  # Success! Go straight to the plotter.
            else:
                files = state.settings.get('files', [])
                if not files:
                    messagebox.showerror("Error", "No files selected.", parent=dummy_root)
                    dummy_root.destroy()
                    continue

                # Unlike FTIR/XRD, general data doesn't follow a known
                # convention -- ask once how to parse it (using the first
                # selected file as a live preview), then apply that
                # configuration to every selected file.
                picker = ColumnPickerDialog(dummy_root, files[0])
                dummy_root.wait_window(picker)

                if picker.result is None:
                    # Cancelled -- back to setup rather than guessing a config.
                    dummy_root.destroy()
                    continue

                state.general_format = picker.result
                if load_data_files(dummy_root, picker.result):
                    state.init_file_settings()
                    break
                else:
                    dummy_root.destroy()
                    continue
        # ==========================================

        mode = state.settings.get('mode', 'individual')

        if mode in ['overlay', 'stack']:
            title = "Overlay Mode" if mode == 'overlay' else "Stacked Grid Mode"
            viewer = PlotViewer(dummy_root, state.all_data, title, out_dir=None)
            dummy_root.wait_window(viewer)

        elif mode == 'individual':
            for i, data_tuple in enumerate(state.all_data):
                stem = data_tuple[0]
                viewer = PlotViewer(dummy_root, [data_tuple], f"File {i+1}/{len(state.all_data)}: {stem}", out_dir=None)
                dummy_root.wait_window(viewer)

                if state.restart_to_menu:
                    break
                if state.mode_switched_mid_session:
                    # See ir.py's identical comment.
                    break

        dummy_root.destroy()

        if not state.restart_to_menu:
            break
    # ==========================================


def run():
    """Entry point for launcher.py's multiprocessing.Process(target=...).

    IMPORTANT: this exists because the old 'if __name__ == "__main__":
    main()' crash handler below NEVER actually runs when main() is invoked
    this way -- multiprocessing.Process(target=general.main) calls the main
    function object directly; it doesn't re-trigger this module's
    __main__ guard. That meant any exception inside main() (a bug in a
    dialog, a bad file read, anything) silently killed the child process
    with zero error message -- which looks exactly like 'the window just
    never opened'. Wrapping main() in its own try/except here means errors
    get written to CRASH_REPORT_GENERAL.txt regardless of entry path.
    """
    try:
        main()
    except Exception:
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "CRASH_REPORT_GENERAL.txt")
        try:
            with open(desktop_path, "w") as f:
                f.write("THE APP CRASHED. HERE IS THE EXACT ERROR:\n\n")
                f.write(traceback.format_exc())
        except Exception:
            pass  # last resort -- don't let the crash-reporter itself crash silently


if __name__ == "__main__":
    run()
