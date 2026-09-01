import json
import numpy as np
from tkinter import filedialog, messagebox
from config import state

class NumpyEncoder(json.JSONEncoder):
    """ Custom encoder to safely convert NumPy data types to standard JSON format """
    def default(self, obj):
        if isinstance(obj, np.generic):
            return obj.item()
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

def save_session(root_window, viewer_instance=None, save_as=False):
    """Saves the current session. Prompts for location if new, otherwise overwrites."""
    # Tell the GUI to grab all drawn shapes and put them into state
    if viewer_instance:
        viewer_instance.sync_annotations_to_state()

    filepath = state.current_session_file

    # If we don't have a file yet, OR the user clicked "Save As", ask for a location
    if save_as or not filepath:
        filepath = filedialog.asksaveasfilename(
            parent=root_window,
            defaultextension=".json",
            filetypes=[("FTIR Session Files", "*.json")],
            title="Save Session As"
        )
        if not filepath: return False
        state.current_session_file = filepath # Remember this for next time!

    session_data = {
        'settings': state.settings,
        'all_data': [(stem, x.tolist(), y.tolist()) for stem, x, y in state.all_data],
        'master_folder': state.master_folder,
        'file_set': state.file_set,
        'global_set': state.global_set
    }

    try:
        with open(filepath, 'w') as f:
            json.dump(session_data, f, cls=NumpyEncoder, indent=4)
        # Only show the success popup if they explicitly clicked Save As, to avoid annoyance
        if save_as: 
            messagebox.showinfo("Success", f"Session saved to\n{filepath}", parent=root_window)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save session:\n{e}", parent=root_window)
        return False

def load_session(root_window):
    filepath = filedialog.askopenfilename(
        parent=root_window,
        filetypes=[("FTIR Session Files", "*.json")],
        title="Load Session File"
    )
    if not filepath: return False

    try:
        with open(filepath, 'r') as f:
            session_data = json.load(f)

        state.settings = session_data['settings']
        state.all_data = [(stem, np.array(x), np.array(y)) for stem, x, y in session_data['all_data']]
        state.master_folder = session_data.get('master_folder')
        state.file_set = session_data['file_set']
        state.global_set = session_data['global_set']
        state.current_session_file = filepath # NEW: Remember the loaded file!

        messagebox.showinfo("Success", "Session loaded successfully!", parent=root_window)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load session:\n{e}", parent=root_window)
        return False