import sys
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import numpy as np

# --- CRUCIAL: Set Backend before importing pyplot for PyInstaller compatibility ---
import matplotlib
matplotlib.use('TkAgg') 
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.colors as mcolors
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.widgets import Cursor
# --------------------------------------------------------------------------------

from scipy.signal import find_peaks
from scipy.optimize import curve_fit
from pathlib import Path

from config import state
from processing import process_spectrum
from annotations import AnnotationManager

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def apply_global_aesthetics(ax, min_xs, max_xs, min_ys, max_ys, is_stack_mode=False):
    gs = state.global_set
    
    # --- SAFE AXIS INVERSION CHECK ---
    if getattr(state, 'technique', 'FTIR') == 'FTIR':
        if gs.get('xlim'): ax.set_xlim(max(gs['xlim']), min(gs['xlim']))
        else: ax.set_xlim(max(max_xs), min(min_xs)) 
    else:
        if gs.get('xlim'): ax.set_xlim(min(gs['xlim']), max(gs['xlim']))
        else: ax.set_xlim(min(min_xs), max(max_xs))
    # ---------------------------------
    
    # --- FIXED Y-LIMITS FOR STACKED GRID ---
    if gs.get('ylim'): 
        ax.set_ylim(min(gs['ylim']), max(gs['ylim']))
    elif not is_stack_mode: 
        # Only force global Y-limits if we are on a single Overlay plot
        b = (max(max_ys) - min(min_ys)) * 0.05
        ax.set_ylim(bottom=min(min_ys) - b, top=max(max_ys) + b)
        
    try:
        if gs.get('xstep'): ax.xaxis.set_major_locator(ticker.MultipleLocator(float(gs['xstep'])))
        if gs.get('ystep'): ax.yaxis.set_major_locator(ticker.MultipleLocator(float(gs['ystep'])))
    except ValueError: pass
    
    if gs.get('show_minor'): ax.minorticks_on()
    else: ax.minorticks_off()
        
    if not gs.get('show_tick_lbls', True):
        ax.set_xticklabels([])
        ax.set_yticklabels([])
    
    if gs.get('title'): ax.set_title(gs['title'], fontweight="bold")
    if gs.get('xlabel'): ax.set_xlabel(gs['xlabel'], fontweight="bold")
    if gs.get('ylabel'): ax.set_ylabel(gs['ylabel'], fontweight="bold")

class SetupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Processing Suite Launcher")
        self.root.geometry("550x700") 
        self.root.minsize(450, 650)
        
        try:
            # Dynamically load the correct icon using the resource_path helper!
            if getattr(state, 'technique', 'FTIR') == 'XRD':
                app_icon = tk.PhotoImage(file=resource_path('xrd_icon.png'))
            else:
                app_icon = tk.PhotoImage(file=resource_path('ir_icon.png'))
            self.root.iconphoto(False, app_icon)
        except Exception:
            pass # If the icon is missing, just ignore it and keep running
        
        self.ready = False
        self.loaded_from_session = False 
        
        self.is_all_var = tk.BooleanVar(value=False) 
        self.plot_mode_var = tk.StringVar(value="individual")
        self.smooth_var = tk.IntVar(value=15)
        
        # Memory for the file browser
        self.last_open_dir = None 
        
        if 'files' not in state.settings or not isinstance(state.settings.get('files'), list):
            state.settings['files'] = []
            
        self._build_ui()

    def _build_ui(self):
        ttk.Label(self.root, text="Data Processing Suite", font=("Arial", 16, "bold")).pack(pady=10)
        
        f_frame = ttk.LabelFrame(self.root, text="1. Select & Arrange Data", padding=10)
        f_frame.pack(fill="x", padx=15, pady=5)
        
        self.lbl_f = ttk.Label(f_frame, text="Loaded: 0 file(s) ready", font=("Arial", 10, "bold"))
        self.lbl_f.pack(pady=5)
        
        btn_f = ttk.Frame(f_frame)
        btn_f.pack(fill="x", pady=2)
        ttk.Button(btn_f, text="📂 Add Folder", command=self.browse_folder).pack(side="left", expand=True, padx=2)
        ttk.Button(btn_f, text="📄 Add Files", command=self.browse_files).pack(side="right", expand=True, padx=2)
        
        # --- Listbox and Reorder Frame ---
        list_container = ttk.Frame(f_frame)
        list_container.pack(fill="x", pady=5)
        
        self.file_listbox = tk.Listbox(list_container, height=6, selectmode=tk.EXTENDED)
        self.file_listbox.pack(side="left", fill="both", expand=True)
        
        # Double-click to remove binding
        self.file_listbox.bind('<Double-1>', lambda e: self.remove_selected())
        
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.file_listbox.yview)
        scrollbar.pack(side="left", fill="y")
        self.file_listbox.config(yscrollcommand=scrollbar.set)
        
        # Reorder Buttons (Up/Down)
        reorder_f = ttk.Frame(list_container)
        reorder_f.pack(side="right", fill="y", padx=(5, 0))
        ttk.Button(reorder_f, text="⬆️", width=3, command=self.move_up).pack(side="top", pady=(0, 2))
        ttk.Button(reorder_f, text="⬇️", width=3, command=self.move_down).pack(side="top", pady=2)
        # ---------------------------------
        
        action_btn_f = ttk.Frame(f_frame)
        action_btn_f.pack(fill="x", pady=(2, 0))
        ttk.Button(action_btn_f, text="➖ Remove Selected", command=self.remove_selected).pack(side="left", expand=True, padx=2)
        ttk.Button(action_btn_f, text="🗑️ Clear All", command=self.clear_selection).pack(side="right", expand=True, padx=2)

        m_frame = ttk.LabelFrame(self.root, text="2. Plotting Mode", padding=10)
        m_frame.pack(fill="x", padx=15, pady=5)
        ttk.Radiobutton(m_frame, text="Individual Plots", variable=self.plot_mode_var, value="individual").pack(anchor="w")
        ttk.Radiobutton(m_frame, text="Stacked Grid", variable=self.plot_mode_var, value="stack").pack(anchor="w")
        ttk.Radiobutton(m_frame, text="Overlay", variable=self.plot_mode_var, value="overlay").pack(anchor="w")
        
        s_frame = ttk.Frame(m_frame)
        s_frame.pack(fill="x", pady=5)
        ttk.Label(s_frame, text="Default Smoothing (Pts):").pack(side="left")
        ttk.Entry(s_frame, textvariable=self.smooth_var, width=5).pack(side="left", padx=10)

        # ==========================================
        # SUPPORTED FORMATS INFO BOX (DYNAMIC)
        # ==========================================
        info_frame = ttk.LabelFrame(self.root, text="ℹ️ Supported File Formats", padding=10)
        info_frame.pack(fill="x", padx=15, pady=10)

        # Show FT-IR formats if ir.py called this window
        if getattr(state, 'technique', 'FTIR') == 'FTIR':
            ttk.Label(info_frame, text="FT-IR Spectroscopy:", font=("Arial", 10, "bold")).pack(anchor="w")
            ttk.Label(info_frame, text="• .dpt or .csv or .txt or .xy or (Comma, Tab, or Space separated Text File)").pack(anchor="w", padx=10, pady=(2, 0))
            
        # Show XRD formats if xrd.py called this window
        elif getattr(state, 'technique', 'FTIR') == 'XRD':
            ttk.Label(info_frame, text="X-Ray Diffraction:", font=("Arial", 10, "bold")).pack(anchor="w")
            ttk.Label(info_frame, text="• .csv or .txt or .xy or .dat or (Standard 2-Column X/Y Numeric Data)").pack(anchor="w", padx=10, pady=(2, 0))

        # General Plotter (any delimited/xlsx data -- columns configured next)
        elif getattr(state, 'technique', 'FTIR') == 'GENERAL':
            ttk.Label(info_frame, text="General Data Plotter:", font=("Arial", 10, "bold")).pack(anchor="w")
            ttk.Label(info_frame, text="• Any delimited text or Excel file with numeric X/Y columns.\n  You'll configure the delimiter, header rows, and columns next.",
                      justify="left").pack(anchor="w", padx=10, pady=(2, 0))
        # ==========================================
        
        ttk.Button(self.root, text="🚀 Launch Processing", command=self.start).pack(pady=10)
        ttk.Separator(self.root, orient='horizontal').pack(fill='x', pady=10)
        ttk.Button(self.root, text="📂 Load Previous Session (.json)", command=self.load_session_cmd).pack(pady=5)

    def _update_file_count(self):
        count = len(state.settings['files'])
        self.lbl_f.config(text=f"Loaded: {count} file(s) ready")

    def _add_to_list(self, file_paths):
        duplicates = 0
        added = 0
        
        for path in file_paths:
            p_str = str(Path(path).resolve()) 
            if p_str not in state.settings['files']:
                state.settings['files'].append(p_str)
                self.file_listbox.insert(tk.END, Path(p_str).name)
                added += 1
            else:
                duplicates += 1
                
        self._update_file_count()
        if duplicates > 0:
            messagebox.showinfo("Duplicates Skipped", f"Successfully added {added} new file(s).\n\nSkipped {duplicates} file(s) that were already loaded.", parent=self.root)

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Select Folder containing Data Files", initialdir=self.last_open_dir)
        if folder:
            self.last_open_dir = folder 
            valid_exts = ['.csv', '.txt', '.xlsx', '.dat', '.asr', '.raw']
            found_files = [p for p in Path(folder).iterdir() if p.suffix.lower() in valid_exts]
            
            if not found_files:
                messagebox.showwarning("No Data", "No valid data files found in this folder!", parent=self.root)
                return
                
            self.is_all_var.set(False) 
            self._add_to_list(found_files)
            
    def browse_files(self):
        f = filedialog.askopenfilenames(title="Select Data Files", initialdir=self.last_open_dir, 
                                        filetypes=[("Data files", "*.csv *.txt *.xlsx *.dat *.asr *.raw *.CSV *.TXT")])
        if f:
            self.last_open_dir = str(Path(f[0]).parent) 
            self.is_all_var.set(False)
            self._add_to_list(f)

    # --- NEW: Reorder Functions ---
    def move_up(self):
        selected = self.file_listbox.curselection()
        if not selected or selected[0] == 0:
            return 
            
        for idx in selected:
            text = self.file_listbox.get(idx)
            self.file_listbox.delete(idx)
            self.file_listbox.insert(idx - 1, text)
            
            file_path = state.settings['files'].pop(idx)
            state.settings['files'].insert(idx - 1, file_path)
            
            self.file_listbox.selection_set(idx - 1)

    def move_down(self):
        selected = self.file_listbox.curselection()
        if not selected or selected[-1] == self.file_listbox.size() - 1:
            return 
            
        for idx in reversed(selected):
            text = self.file_listbox.get(idx)
            self.file_listbox.delete(idx)
            self.file_listbox.insert(idx + 1, text)
            
            file_path = state.settings['files'].pop(idx)
            state.settings['files'].insert(idx + 1, file_path)
            
            self.file_listbox.selection_set(idx + 1)
    # ------------------------------
    def remove_selected(self):
        selected_indices = list(self.file_listbox.curselection())
        if not selected_indices: return
            
        selected_indices.reverse() 
        for idx in selected_indices:
            self.file_listbox.delete(idx)
            state.settings['files'].pop(idx)
            
        self._update_file_count()

    def clear_selection(self):
        self.file_listbox.delete(0, tk.END)
        state.settings['files'] = []
        state.settings.pop('folder', None)
        self._update_file_count()

    def start(self):
        if self.is_all_var.get() and 'folder' not in state.settings:
            state.settings['folder'] = '.' 
            
        state.settings['is_all'] = self.is_all_var.get()
        state.settings['mode'] = self.plot_mode_var.get()
        state.settings['smooth'] = self.smooth_var.get()
        
        if not self.is_all_var.get() and not state.settings.get('files'):
            messagebox.showwarning("Warning", "Please select specific files first!", parent=self.root)
            return
            
        self.ready = True
        self.root.destroy()

    def load_session_cmd(self):
        try:
            from session import load_session
            if load_session(self.root):
                self.ready = True
                self.loaded_from_session = True
                self.root.destroy()
        except ImportError:
            pass

class CloseDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Close Session")
        self.geometry("380x150")
        self.resizable(False, False)
        
        self.transient(parent)
        self.grab_set()
        
        self.choice = None 
        
        ttk.Label(self, text="Do you want to save your session before closing?", font=("Arial", 10, "bold")).pack(pady=(15, 10))
        
        self.return_to_menu = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Return to Main Menu instead of exiting the app", variable=self.return_to_menu).pack(pady=(0, 15))
        
        btn_frame = ttk.Frame(self)
        btn_frame.pack()
        
        ttk.Button(btn_frame, text="Save", width=10, command=lambda: self.set_choice("save")).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Don't Save", width=10, command=lambda: self.set_choice("discard")).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", width=10, command=self.destroy).pack(side="left", padx=5)

    def set_choice(self, action):
        destination = "menu" if self.return_to_menu.get() else "exit"
        self.choice = f"{action}_{destination}"
        self.destroy()


class AddDataChoiceDialog(tk.Toplevel):
    """Shown when 'Add File(s)' is used in Individual mode with data already
    loaded -- Individual mode only ever shows one file at a time, so adding
    another file is ambiguous. Asks whether the new file should replace the
    one currently on screen, or whether the whole session should switch to
    Overlay/Stack mode so everything can be shown together."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Data")
        self.geometry("400x260")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.choice = None  # 'replace' | 'overlay' | 'stack' | None (cancelled)

        ttk.Label(self, text="You're in Individual mode with data already loaded.",
                  font=("Arial", 10, "bold"), wraplength=360, justify="center").pack(pady=(15, 2), padx=15)
        ttk.Label(self, text="How should the new file(s) be added?",
                  wraplength=360, justify="center").pack(pady=(0, 15), padx=15)

        ttk.Button(self, text="🔁 Replace Current File's Data", width=34,
                   command=lambda: self._pick('replace')).pack(pady=4)
        ttk.Button(self, text="🗂 Switch to Overlay (same axes)", width=34,
                   command=lambda: self._pick('overlay')).pack(pady=4)
        ttk.Button(self, text="📊 Switch to Stacked Grid", width=34,
                   command=lambda: self._pick('stack')).pack(pady=4)
        ttk.Button(self, text="Cancel", width=34, command=self.destroy).pack(pady=(12, 4))

    def _pick(self, choice):
        self.choice = choice
        self.destroy()


class ColumnPickerDialog(tk.Toplevel):
    """Used by the General Plotter to configure how to parse arbitrary data:
    delimiter, header rows to skip, and which columns are X/Y. Shows a live
    preview (raw + parsed) from a sample file so the user can confirm the
    configuration looks right before committing to it for all selected files."""
    def __init__(self, parent, sample_filepath):
        super().__init__(parent)
        self.title("Configure Data Columns")
        self.geometry("580x560")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.sample_filepath = sample_filepath
        self.result = None  # dict on OK, stays None on Cancel

        self.var_delimiter = tk.StringVar(value='Comma (,)')
        self.var_skip_rows = tk.IntVar(value=0)
        self.var_x_col = tk.IntVar(value=0)
        self.var_y_col = tk.IntVar(value=1)

        self._build_ui()
        self._refresh_preview()

    def _build_ui(self):
        ttk.Label(self, text=f"Sample file: {Path(self.sample_filepath).name}",
                  font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        ttk.Label(self, text="Raw preview (first 8 lines):", font=("Arial", 9)).pack(anchor="w", padx=10, pady=(6, 2))
        self.raw_text = tk.Text(self, height=6, width=68, font=("Courier", 9))
        self.raw_text.pack(padx=10, pady=(0, 10))
        self.raw_text.config(state="disabled")

        opts_frame = ttk.LabelFrame(self, text="Parsing Options", padding=10)
        opts_frame.pack(fill="x", padx=10, pady=5)

        row1 = ttk.Frame(opts_frame); row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="Delimiter:").pack(side="left")
        delim_options = ['Comma (,)', 'Tab', 'Space', 'Semicolon (;)']
        cb = ttk.Combobox(row1, textvariable=self.var_delimiter, values=delim_options, state="readonly", width=14)
        cb.pack(side="left", padx=5)
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_preview())

        row2 = ttk.Frame(opts_frame); row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="Header Rows to Skip:").pack(side="left")
        ttk.Spinbox(row2, from_=0, to=50, textvariable=self.var_skip_rows, width=5,
                    command=self._refresh_preview).pack(side="left", padx=5)

        row3 = ttk.Frame(opts_frame); row3.pack(fill="x", pady=2)
        ttk.Label(row3, text="X Column Index:").pack(side="left")
        ttk.Spinbox(row3, from_=0, to=20, textvariable=self.var_x_col, width=5,
                    command=self._refresh_preview).pack(side="left", padx=5)
        ttk.Label(row3, text="Y Column Index:").pack(side="left", padx=(15, 0))
        ttk.Spinbox(row3, from_=0, to=20, textvariable=self.var_y_col, width=5,
                    command=self._refresh_preview).pack(side="left", padx=5)
        ttk.Label(opts_frame, text="(0 = first column)", font=("Arial", 8), foreground="gray").pack(anchor="w")

        ttk.Button(opts_frame, text="🔄 Refresh Preview", command=self._refresh_preview).pack(pady=(8, 0))

        ttk.Label(self, text="Parsed preview (first 5 numeric rows):", font=("Arial", 9)).pack(anchor="w", padx=10, pady=(10, 2))
        self.parsed_text = tk.Text(self, height=6, width=68, font=("Courier", 9))
        self.parsed_text.pack(padx=10, pady=(0, 10))
        self.parsed_text.config(state="disabled")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="✅ Use This Configuration", command=self._confirm).pack(side="right")

    def _delim_char(self):
        mapping = {'Comma (,)': ',', 'Tab': '\t', 'Space': ' ', 'Semicolon (;)': ';'}
        return mapping.get(self.var_delimiter.get(), ',')

    def _refresh_preview(self):
        lines = []
        try:
            with open(self.sample_filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for _ in range(8):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line)
        except Exception as e:
            lines = [f"(Could not read file: {e})"]

        self.raw_text.config(state="normal")
        self.raw_text.delete("1.0", tk.END)
        self.raw_text.insert("1.0", "".join(lines))
        self.raw_text.config(state="disabled")

        from readers import read_generic_configured
        try:
            x, y = read_generic_configured(
                Path(self.sample_filepath),
                delimiter=self._delim_char(),
                skip_rows=self.var_skip_rows.get(),
                x_col=self.var_x_col.get(),
                y_col=self.var_y_col.get(),
            )
            rows = list(zip(x, y))[:5]
            preview = "\n".join(f"{xi:.4g}\t{yi:.4g}" for xi, yi in rows) if rows else \
                "(No numeric rows parsed with this configuration -- try adjusting the options above)"
        except Exception as e:
            preview = f"(Error: {e})"

        self.parsed_text.config(state="normal")
        self.parsed_text.delete("1.0", tk.END)
        self.parsed_text.insert("1.0", preview)
        self.parsed_text.config(state="disabled")

    def _confirm(self):
        self.result = {
            'delimiter': self._delim_char(),
            'skip_rows': self.var_skip_rows.get(),
            'x_col': self.var_x_col.get(),
            'y_col': self.var_y_col.get(),
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class TextAnnotationDialog(tk.Toplevel):
    """Rich text-composition dialog for annotation text boxes.

    Superscript/subscript/Greek letters/underline are implemented via
    matplotlib's built-in mathtext (the '$...$' syntax) -- no LaTeX
    installation needed, it's part of matplotlib itself. Bold/italic/color/
    size for plain (non-mathtext) text use the Text artist's native
    fontweight/fontstyle/color/fontsize properties instead, since those work
    everywhere (not just inside '$...$').
    """

    GREEK_LOWER = ['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta',
                   'iota', 'kappa', 'lambda', 'mu', 'nu', 'xi', 'pi', 'rho', 'sigma',
                   'tau', 'upsilon', 'phi', 'chi', 'psi', 'omega']
    GREEK_UPPER = ['Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi', 'Sigma', 'Upsilon', 'Phi', 'Psi', 'Omega']
    MATH_SYMBOLS = [
        ('±', '\\pm'), ('×', '\\times'), ('÷', '\\div'), ('≈', '\\approx'),
        ('≠', '\\neq'), ('≤', '\\leq'), ('≥', '\\geq'), ('∞', '\\infty'),
        ('√', '\\sqrt{}'), ('∑', '\\sum'), ('∫', '\\int'), ('°', '^{\\circ}'),
        ('→', '\\rightarrow'), ('∂', '\\partial'), ('Å', '\\AA'), ('∆', '\\Delta'),
    ]
    GREEK_UNICODE = {
        '\\alpha': 'α', '\\beta': 'β', '\\gamma': 'γ', '\\delta': 'δ', '\\epsilon': 'ε', '\\zeta': 'ζ',
        '\\eta': 'η', '\\theta': 'θ', '\\iota': 'ι', '\\kappa': 'κ', '\\lambda': 'λ', '\\mu': 'μ',
        '\\nu': 'ν', '\\xi': 'ξ', '\\pi': 'π', '\\rho': 'ρ', '\\sigma': 'σ', '\\tau': 'τ',
        '\\upsilon': 'υ', '\\phi': 'φ', '\\chi': 'χ', '\\psi': 'ψ', '\\omega': 'ω',
        '\\Gamma': 'Γ', '\\Delta': 'Δ', '\\Theta': 'Θ', '\\Lambda': 'Λ', '\\Xi': 'Ξ', '\\Pi': 'Π',
        '\\Sigma': 'Σ', '\\Upsilon': 'Υ', '\\Phi': 'Φ', '\\Psi': 'Ψ', '\\Omega': 'Ω',
    }

    def __init__(self, parent, initial_text='', initial_color='black', initial_fontsize=12,
                 initial_bold=False, initial_italic=False, initial_family='sans-serif'):
        super().__init__(parent)
        self.title("Add Text Annotation")
        self.geometry("540x660")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = None  # dict on OK/Add, stays None on Cancel

        self.var_color = tk.StringVar(value=initial_color)
        self.var_fontsize = tk.DoubleVar(value=initial_fontsize)
        self.var_bold = tk.BooleanVar(value=initial_bold)
        self.var_italic = tk.BooleanVar(value=initial_italic)
        self.var_underline = tk.BooleanVar(value=False)
        self.var_family = tk.StringVar(value=initial_family or 'sans-serif')

        self._build_ui(initial_text)

    def _build_ui(self, initial_text):
        ttk.Label(self, text="Text (use the buttons below to insert formatting/symbols at the cursor):",
                  wraplength=500, justify="left").pack(anchor="w", padx=10, pady=(10, 4))

        self.text_entry = tk.Text(self, height=4, width=60, font=("Arial", 11), wrap="word")
        self.text_entry.pack(padx=10, pady=(0, 8))
        self.text_entry.insert("1.0", initial_text)
        self.text_entry.focus_set()

        # --- Whole-box style ---
        style_frame = ttk.LabelFrame(self, text="Style (applies to the whole box)", padding=6)
        style_frame.pack(fill="x", padx=10, pady=4)

        style_row = ttk.Frame(style_frame)
        style_row.pack(fill="x")
        ttk.Checkbutton(style_row, text="Bold", variable=self.var_bold).pack(side="left", padx=4)
        ttk.Checkbutton(style_row, text="Italic", variable=self.var_italic).pack(side="left", padx=4)
        ttk.Checkbutton(style_row, text="Underline", variable=self.var_underline).pack(side="left", padx=4)
        ttk.Label(style_row, text="  Size:").pack(side="left", padx=(10, 0))
        ttk.Entry(style_row, textvariable=self.var_fontsize, width=5).pack(side="left")

        style_row2 = ttk.Frame(style_frame)
        style_row2.pack(fill="x", pady=(4, 0))
        ttk.Label(style_row2, text="Font:").pack(side="left")
        ttk.Combobox(style_row2, textvariable=self.var_family, state="readonly", width=11,
                     values=["sans-serif", "serif", "monospace", "cursive", "fantasy"]).pack(side="left", padx=4)
        ttk.Label(style_row2, text="  Color:").pack(side="left", padx=(10, 0))
        ttk.Entry(style_row2, textvariable=self.var_color, width=10).pack(side="left")
        ttk.Button(style_row2, text="🎨", width=3, command=self._choose_color).pack(side="left", padx=2)

        # --- Superscript / subscript ---
        insert_frame = ttk.LabelFrame(self, text="Insert at Cursor", padding=6)
        insert_frame.pack(fill="x", padx=10, pady=4)
        row1 = ttk.Frame(insert_frame)
        row1.pack(fill="x", pady=2)
        ttk.Button(row1, text="x² Superscript", command=self._insert_superscript).pack(side="left", padx=2)
        ttk.Button(row1, text="x₂ Subscript", command=self._insert_subscript).pack(side="left", padx=2)

        # --- Greek letters ---
        greek_frame = ttk.LabelFrame(self, text="Greek Letters (click to insert)", padding=6)
        greek_frame.pack(fill="x", padx=10, pady=4)
        greek_specs = [(self.GREEK_UNICODE.get(f"\\{n}", n), f"\\{n}") for n in self.GREEK_LOWER] + \
                      [(self.GREEK_UNICODE.get(f"\\{n}", n), f"\\{n}") for n in self.GREEK_UPPER]
        self._build_symbol_grid(greek_frame, greek_specs, cols=12)

        # --- Math symbols ---
        sym_frame = ttk.LabelFrame(self, text="Math Symbols (click to insert)", padding=6)
        sym_frame.pack(fill="x", padx=10, pady=4)
        self._build_symbol_grid(sym_frame, self.MATH_SYMBOLS, cols=8)

        ttk.Label(self, text="These buttons use matplotlib's built-in math mode ($...$) so everything\n"
                              "renders correctly on the graph -- no LaTeX installation needed.",
                  font=("Arial", 8), foreground="gray", justify="left").pack(anchor="w", padx=10, pady=(4, 0))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="✅ Add", command=self._confirm).pack(side="right")

    def _build_symbol_grid(self, parent, specs, cols):
        for i, (label, cmd) in enumerate(specs):
            btn = tk.Button(parent, text=label, width=3, command=lambda c=cmd: self._insert_mathtext(c))
            btn.grid(row=i // cols, column=i % cols, padx=1, pady=1)

    def _insert_mathtext(self, cmd):
        self._ensure_math_wrap_and_insert(cmd + " ")

    def _insert_superscript(self):
        self._ensure_math_wrap_and_insert("^{}", cursor_offset=-1)

    def _insert_subscript(self):
        self._ensure_math_wrap_and_insert("_{}", cursor_offset=-1)

    def _ensure_math_wrap_and_insert(self, snippet, cursor_offset=0):
        """Mathtext commands only render inside '$...$'. If the box isn't
        already wrapped, wrap the whole current content once, then insert
        `snippet` at the (adjusted) cursor position."""
        content = self.text_entry.get("1.0", "end-1c")
        if not (content.startswith('$') and content.endswith('$') and len(content) >= 2):
            self.text_entry.delete("1.0", tk.END)
            self.text_entry.insert("1.0", f"${content}$")
            insert_index = "end-2c"  # just before the trailing $
        else:
            insert_index = tk.INSERT
            if self.text_entry.compare(insert_index, ">=", "end-1c"):
                insert_index = "end-2c"

        self.text_entry.insert(insert_index, snippet)
        if cursor_offset:
            new_pos = f"{insert_index}+{len(snippet)}c{cursor_offset:+d}c"
            try:
                self.text_entry.mark_set(tk.INSERT, new_pos)
            except tk.TclError:
                pass
        self.text_entry.focus_set()

    def _choose_color(self):
        from tkinter.colorchooser import askcolor
        current = self.var_color.get() or "black"
        color = askcolor(initialcolor=current, title="Choose Text Color")
        if color[1]:
            self.var_color.set(color[1])

    def _confirm(self):
        raw_text = self.text_entry.get("1.0", "end-1c").strip()
        if not raw_text:
            self.result = None
            self.destroy()
            return

        is_mathtext = raw_text.startswith('$') and raw_text.endswith('$') and len(raw_text) >= 2
        if self.var_underline.get():
            # Native matplotlib Text has no underline property outside
            # mathtext -- route underline through \underline{} either way.
            inner = raw_text[1:-1] if is_mathtext else f"\\mathrm{{{raw_text}}}"
            raw_text = f"$\\underline{{{inner}}}$"

        self.result = {
            'text': raw_text,
            'color': self.var_color.get() or 'black',
            'fontsize': self.var_fontsize.get(),
            'bold': self.var_bold.get(),
            'italic': self.var_italic.get(),
            'family': self.var_family.get() or 'sans-serif',
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class PlotViewer(tk.Toplevel):
    def __init__(self, master, data_tuples, title, out_dir=None):
        super().__init__(master)
        self.title(title)
        self.geometry("1400x800")
        
        try:
            if getattr(state, 'technique', 'FTIR') == 'XRD':
                app_icon = tk.PhotoImage(file=resource_path('xrd_icon.png'))
            else:
                app_icon = tk.PhotoImage(file=resource_path('ir_icon.png'))
            self.iconphoto(False, app_icon)
        except Exception:
            pass
        
        self.data_dict = {d[0]: (d[1], d[2]) for d in data_tuples}
        self.stems = list(self.data_dict.keys())
        self.current_stem = self.stems[0]
        self.out_dir = Path(out_dir) if out_dir else None

        self.annotations = []             
        self.dragging_ann = None          
        self.is_adding_annotation = False 
        
        self.var_name = tk.StringVar()
        self.var_color = tk.StringVar()
        self.var_offset = tk.DoubleVar()
        self.var_smooth = tk.IntVar()
        self.var_baseline = tk.BooleanVar()
        self.var_norm = tk.BooleanVar()
        self.var_deriv = tk.IntVar(value=0)
        self.var_als_lam = tk.DoubleVar(value=8.0)
        self.var_t2a = tk.BooleanVar()
        self.var_click_mode = tk.StringVar(value='none')
        
        self.var_show_fwhm = tk.BooleanVar(value=True)
        self.var_xrd_min_height = tk.DoubleVar(value=5.0) 
        
        self.var_bg_sub = tk.BooleanVar(value=False)
        self.var_bg_file = tk.StringVar(value="")
        self.var_bg_mult = tk.DoubleVar(value=1.0)
        
        self.cb_files = None
        self.peak_listbox = None
        self.area_start = None
        self.deconv_start = None
        
        self.var_xlim = tk.StringVar(value=state.global_set.get('xlim', ''))
        self.var_ylim = tk.StringVar(value=state.global_set.get('ylim', ''))
        self.var_xstep = tk.StringVar(value=state.global_set.get('xstep', ''))
        self.var_ystep = tk.StringVar(value=state.global_set.get('ystep', ''))
        self.var_xlabel = tk.StringVar(value=state.global_set.get('xlabel', ''))
        self.var_ylabel = tk.StringVar(value=state.global_set.get('ylabel', ''))
        self.var_bg = tk.StringVar(value=state.global_set.get('bg', ''))
        self.var_title_color = tk.StringVar(value=state.global_set.get('title_color', ''))
        self.var_prominence = tk.DoubleVar(value=10.2)
        self.var_title = tk.StringVar(value=state.global_set.get('title', ''))

        # --- Annotation tool state (arrows/shapes/text on the graph) ---
        self.var_ann_tool = tk.StringVar(value='none')
        self.var_ann_text = tk.StringVar(value='')
        self.var_ann_color = tk.StringVar(value='black')
        self.var_ann_lw = tk.DoubleVar(value=2.0)
        self.var_ann_fontsize = tk.DoubleVar(value=12.0)
        self.var_ann_bold = tk.BooleanVar(value=False)
        self.var_ann_italic = tk.BooleanVar(value=False)
        self.var_ann_alpha = tk.DoubleVar(value=1.0)

        self.cursors = []
        self.baseline_pts = []
        self.ax = None  # NEW: primary axis, set in update_plot(); used by cursor readout + annotations
        
        self.build_layout()

        # Focus the canvas on every click so keyboard shortcuts (Delete,
        # arrow-key nudge, Ctrl+C/V) reliably reach AnnotationManager --
        # Tkinter only routes key events to whichever widget last had focus.
        self.canvas.mpl_connect('button_press_event', lambda e: self.canvas.get_tk_widget().focus_set())

        # Annotation manager owns arrow/shape/text drawing on the canvas.
        # Created here (once) so it survives update_plot()'s repeated
        # fig.clear() calls -- only the *axis* it's attached to changes.
        self.annotation_mgr = AnnotationManager(
            self.canvas,
            on_select_callback=self.on_annotation_selected,
            on_list_update_callback=self.sync_annotation_listbox,
            on_tool_change_callback=self.on_annotation_tool_change,
            text_input_provider=self.show_text_annotation_dialog,
        )
        # If this viewer was opened from a loaded session, annotations saved
        # in that session live here until the first update_plot() call
        # restores them onto a real axis.
        self._pending_annotation_load = state.global_set.get('annotations') or []

        self.build_controls()
        self.load_active_settings()
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_plot()

    def build_layout(self):
        self.control_frame = ttk.Frame(self, width=460)  # widened from 400 -- west-side tabs (see build_controls) eat some of this for the tab strip itself
        self.control_frame.pack(side="left", fill="y", padx=5, pady=5)
        self.control_frame.pack_propagate(False)
        
        self.plot_frame = ttk.Frame(self)
        self.plot_frame.pack(side="right", fill="both", expand=True)
        
        self.fig = plt.Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
    
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.plot_frame)
        self.toolbar.update()
        
        self.cursor_label = ttk.Label(self.plot_frame, text="X: -- | Y: --", font=("Arial", 10, "bold"), foreground="blue")
        self.cursor_label.pack(side="bottom", anchor="e", padx=10, pady=5)

        self.canvas.mpl_connect('button_press_event', self.on_click)
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move) 

    def get_processed_data_for_stem(self, stem):
        raw_x, raw_y = self.data_dict[stem]
        fs = state.file_set[stem]
        
        try:
            x, y = process_spectrum(raw_x, raw_y, stem)
        except Exception:
            x, y = raw_x, raw_y
        x_arr, y_arr = np.array(x, dtype=float), np.array(y, dtype=float)

        if fs.get('t2a', False):
            y_safe = np.clip(y_arr, 0.0001, None)
            y_arr = 2 - np.log10(y_safe)

        if fs.get('bg_sub', False) and 'bg_data' in fs:
            bg_x, bg_y = fs['bg_data']
            bg_interp = np.interp(x_arr, bg_x, bg_y)
            y_arr -= (bg_interp * fs.get('bg_mult', 1.0))

        manual_pts = fs.get('manual_baseline_pts', [])
        if len(manual_pts) >= 2:
            from scipy.interpolate import interp1d
            pts_x = np.array([p[0] for p in manual_pts])
            pts_y = np.array([p[1] for p in manual_pts])
            sort_idx = np.argsort(pts_x)
            
            interp_func = interp1d(pts_x[sort_idx], pts_y[sort_idx], kind='linear', fill_value="extrapolate")
            baseline_curve = interp_func(x_arr)
            y_arr -= baseline_curve

        if fs.get('normalize', False):
            y_arr = (y_arr - np.min(y_arr)) / (np.max(y_arr) - np.min(y_arr)) * 100
        y_arr += fs.get('offset', 0.0)
            
        return x_arr, y_arr
    
    def on_mouse_move(self, event):
        if hasattr(self, 'ax') and event.inaxes == self.ax:
            self.cursor_label.config(text=f"X: {event.xdata:.1f} | Y: {event.ydata:.1f}")
        else:
            self.cursor_label.config(text="X: -- | Y: --")
            
        if not self.dragging_ann or event.inaxes != self.ax: return
        self.dragging_ann.set_position((event.xdata, event.ydata))
        self.canvas.draw_idle()

    def _create_scrollable_tab(self, notebook, title):
        outer_frame = ttk.Frame(notebook)
        notebook.add(outer_frame, text=title)
        
        canvas = tk.Canvas(outer_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        inner_frame = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw")
        
        inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        def _on_mousewheel(e):
            if hasattr(e, 'delta') and e.delta != 0:
                canvas.yview_scroll(int(-1*(e.delta/120)), "units")
                
        def _on_linux_up(e): canvas.yview_scroll(-1, "units")
        def _on_linux_down(e): canvas.yview_scroll(1, "units")

        def _bind_mouse(e):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_linux_up)
            canvas.bind_all("<Button-5>", _on_linux_down)

        def _unbind_mouse(e):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_mouse)
        canvas.bind("<Leave>", _unbind_mouse)
        
        return inner_frame
    
    def build_controls(self):
        style = ttk.Style()
        style.configure("TLabelframe", padding=2) 
        style.configure("TButton", padding=2)     
        # Tabs on the left instead of along the top: with 4 tabs (and more
        # likely coming as features grow) horizontal tabs start truncating
        # labels in a 400px-wide control panel. West-side tabs scale to more
        # tabs without getting cramped -- labels stay horizontal (not
        # rotated), just stacked top-to-bottom instead of left-to-right.
        style.configure("TNotebook", tabposition='wn')

        self._build_bottom_buttons()

        self.notebook = ttk.Notebook(self.control_frame)
        
        self.tab_file = self._create_scrollable_tab(self.notebook, "File Settings")
        self.tab_axes = self._create_scrollable_tab(self.notebook, "Axes & Style")
        self.tab_annotate = self._create_scrollable_tab(self.notebook, "Annotations")
        self.tab_tools = self._create_scrollable_tab(self.notebook, "Peaks & Export")
        
        self._build_file_tab()
        self._build_axes_tab()
        self._build_annotation_tab()
        self._build_tools_tab()

        self.notebook.pack(side="top", fill="both", expand=True)

    def _build_file_tab(self):
        # --- Manage Data: add/remove/replace files without closing the window ---
        manage_frame = ttk.LabelFrame(self.tab_file, text="Manage Data", padding=5)
        manage_frame.pack(fill="x", pady=(5, 10))

        btn_row = ttk.Frame(manage_frame)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="➕ Add File(s)", command=self.add_files).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(btn_row, text="🔁 Replace Current", command=self.replace_current_file).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(btn_row, text="➖ Remove Current", command=self.remove_current_file).pack(side="left", expand=True, fill="x", padx=2)

        # Reorder controls only make sense in Stack mode; shown/hidden dynamically
        # since mode can now change mid-session via "Add File(s)" -> Overlay/Stack.
        self.stack_reorder_frame = ttk.Frame(manage_frame)
        reorder_row = ttk.Frame(self.stack_reorder_frame)
        reorder_row.pack(fill="x")
        ttk.Label(reorder_row, text="Reorder in Stack:").pack(side="left")
        ttk.Button(reorder_row, text="⬆️ Move Up", command=self.move_stem_up).pack(side="left", padx=4)
        ttk.Button(reorder_row, text="⬇️ Move Down", command=self.move_stem_down).pack(side="left", padx=4)
        self._refresh_stack_reorder_visibility()

        ttk.Label(self.tab_file, text="Select File to Edit:").pack(anchor="w", pady=(5,0))
        self.cb_files = ttk.Combobox(self.tab_file, values=self.stems, state="readonly")
        self.cb_files.set(self.current_stem)
        self.cb_files.pack(fill="x", pady=2)
        self.cb_files.bind("<<ComboboxSelected>>", self.on_file_select)
        
        f_frame = ttk.LabelFrame(self.tab_file, text="Line Appearance", padding=5)
        f_frame.pack(fill="x", pady=5)
        
        ttk.Label(f_frame, text="Color:").pack(anchor="w")
        
        c_frame = ttk.Frame(f_frame)
        c_frame.pack(fill="x", pady=(0, 2))
        ttk.Entry(c_frame, textvariable=self.var_color).pack(side="left", fill="x", expand=True)
        ttk.Button(c_frame, text="🎨 Pick", width=6, command=self.choose_color).pack(side="left", padx=(2, 0))
        
        pal_frame = ttk.Frame(f_frame)
        pal_frame.pack(fill="x", pady=(0, 5))
        for col in ['black', 'red', '#1f77b4', '#2ca02c', '#9467bd', '#ff7f0e', 'gray']:
            lbl = tk.Label(pal_frame, bg=col, width=2, cursor="hand2", relief="ridge")
            lbl.pack(side="left", padx=1)
            lbl.bind("<Button-1>", lambda e, c=col: self.var_color.set(c))
        
        ttk.Label(f_frame, text="Y-Offset:").pack(anchor="w")
        ttk.Entry(f_frame, textvariable=self.var_offset).pack(fill="x", pady=(0,5))
        
        ttk.Label(f_frame, text="Smoothing (Pts):").pack(anchor="w")
        ttk.Entry(f_frame, textvariable=self.var_smooth).pack(fill="x", pady=(0,5))
        
        ttk.Checkbutton(f_frame, text="Normalize to 0-100%", variable=self.var_norm).pack(anchor="w", pady=2)
        
        if getattr(state, 'technique', 'FTIR') == 'FTIR':
            ttk.Checkbutton(f_frame, text="Convert %T to Absorbance", variable=self.var_t2a).pack(anchor="w", pady=2)

        f_base = ttk.Frame(f_frame)
        f_base.pack(fill="x", pady=2)
        ttk.Checkbutton(f_base, text="Apply ALS Baseline", variable=self.var_baseline).pack(side="left")
        ttk.Label(f_base, text=" Stiffness (10^X):").pack(side="left")
        ttk.Entry(f_base, textvariable=self.var_als_lam, width=4).pack(side="left", padx=2)
        
        f_deriv = ttk.Frame(f_frame)
        f_deriv.pack(fill="x", pady=5)
        ttk.Label(f_deriv, text="Derivative:").pack(side="left")
        ttk.Radiobutton(f_deriv, text="None", variable=self.var_deriv, value=0).pack(side="left", padx=2)
        ttk.Radiobutton(f_deriv, text="1st", variable=self.var_deriv, value=1).pack(side="left", padx=2)
        ttk.Radiobutton(f_deriv, text="2nd", variable=self.var_deriv, value=2).pack(side="left", padx=2)

        bg_frame = ttk.LabelFrame(self.tab_file, text="Reference Baseline Subtraction", padding=5)
        bg_frame.pack(fill="x", pady=(10, 5))
        
        ttk.Checkbutton(bg_frame, text="Subtract Baseline File", variable=self.var_bg_sub).pack(anchor="w", pady=2)
        
        bg_inner1 = ttk.Frame(bg_frame)
        bg_inner1.pack(fill="x", pady=2)
        ttk.Label(bg_inner1, text="Baseline:").pack(side="left")
        
        ttk.Entry(bg_inner1, textvariable=self.var_bg_file, state="readonly", width=15).pack(side="left", fill="x", expand=True, padx=(5, 2))
        ttk.Button(bg_inner1, text="Browse...", width=8, command=self.load_baseline_file).pack(side="left")
        
        bg_inner2 = ttk.Frame(bg_frame)
        bg_inner2.pack(fill="x", pady=2)
        ttk.Label(bg_inner2, text="Multiplier:").pack(side="left")
        ttk.Entry(bg_inner2, textvariable=self.var_bg_mult, width=6).pack(side="left", padx=5)

        ttk.Button(self.tab_file, text="Apply Changes", command=self.save_and_update).pack(fill="x", pady=5)
        ttk.Button(self.tab_file, text="🔄 Reset to Raw Data", command=self.reset_file_settings).pack(fill="x", pady=2)
        ttk.Button(self.tab_file, text="🔄 Apply Math Settings to ALL Files", command=self.apply_to_all).pack(fill="x", pady=2)

    def choose_color(self):
        from tkinter.colorchooser import askcolor
        current = self.var_color.get()
        if not current: current = "black"
        
        color = askcolor(initialcolor=current, title="Choose Line Color")
        if color[1]: 
            self.var_color.set(color[1])

    def load_active_settings(self):
        fs = state.file_set[self.current_stem]
        self.var_name.set(fs.get('custom_name', self.current_stem))
        self.var_color.set(fs.get('color', 'black'))
        self.var_offset.set(fs.get('offset', 0.0))
        self.var_smooth.set(fs.get('smooth', 15))
        self.var_baseline.set(fs.get('do_baseline', False))
        self.var_norm.set(fs.get('normalize', False))
        self.var_deriv.set(fs.get('derivative', 0))
        self.var_als_lam.set(fs.get('als_lam', 8.0))
        self.var_t2a.set(fs.get('t2a', False))

    def on_file_select(self, event=None):
        self.current_stem = self.cb_files.get()
        self.load_active_settings()
        fs = state.file_set.get(self.current_stem, {})
        self.var_bg_sub.set(fs.get('bg_sub', False))
        self.var_bg_file.set(fs.get('bg_filename', ''))
        self.var_bg_mult.set(fs.get('bg_mult', 1.0))
    
    def load_baseline_file(self):
        filepath = filedialog.askopenfilename(
            title="Select Baseline / Empty Substrate File",
            filetypes=[("Data Files", "*.csv *.txt *.xy *.dat"), ("All Files", "*.*")]
        )
        if not filepath: return
        
        try:
            try:
                data = np.loadtxt(filepath, delimiter=',')
            except Exception:
                data = np.loadtxt(filepath, delimiter=None)
                
            if data.shape[1] < 2:
                raise ValueError("File does not contain X and Y columns.")
                
            fs = state.file_set[self.current_stem]
            fs['bg_data'] = (data[:, 0], data[:, 1]) 
            fs['bg_filename'] = Path(filepath).name  
            
            self.var_bg_file.set(fs['bg_filename'])
            self.var_bg_sub.set(True) 
            fs['bg_sub'] = True
            
            self.update_plot()
            messagebox.showinfo("Success", f"Baseline '{fs['bg_filename']}' loaded successfully!", parent=self)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read baseline file. Ensure it is a standard 2-column numeric file.\n\nDetails: {e}", parent=self)

    def _build_axes_tab(self):
        a_frame = ttk.LabelFrame(self.tab_axes, text="Global Axes Settings", padding=5)
        a_frame.pack(fill="x", pady=5)
        
        ttk.Label(a_frame, text="X-Axis Label:").grid(row=0, column=0, sticky="w")
        ttk.Entry(a_frame, textvariable=self.var_xlabel).grid(row=0, column=1, sticky="ew")
        
        ttk.Label(a_frame, text="Y-Axis Label:").grid(row=1, column=0, sticky="w")
        ttk.Entry(a_frame, textvariable=self.var_ylabel).grid(row=1, column=1, sticky="ew")
        
        ttk.Label(a_frame, text="X Limits (min,max):").grid(row=2, column=0, sticky="w")
        ttk.Entry(a_frame, textvariable=self.var_xlim).grid(row=2, column=1, sticky="ew")
        
        ttk.Label(a_frame, text="Y Limits (min,max):").grid(row=3, column=0, sticky="w")
        ttk.Entry(a_frame, textvariable=self.var_ylim).grid(row=3, column=1, sticky="ew")
        
        ttk.Label(a_frame, text="X Tick Step:").grid(row=4, column=0, sticky="w")
        ttk.Entry(a_frame, textvariable=self.var_xstep).grid(row=4, column=1, sticky="ew")
        
        ttk.Label(a_frame, text="Y Tick Step:").grid(row=5, column=0, sticky="w")
        ttk.Entry(a_frame, textvariable=self.var_ystep).grid(row=5, column=1, sticky="ew")

        ttk.Label(a_frame, text="Graph Title:").grid(row=6, column=0, sticky="w")
        ttk.Entry(a_frame, textvariable=self.var_title).grid(row=6, column=1, sticky="ew")
        
        ttk.Button(self.tab_axes, text="Apply Global Settings", command=self.save_and_update).pack(pady=5)

    def _build_annotation_tab(self):
        ttk.Label(self.tab_annotate, text="Drawing Tools:").pack(anchor="w", pady=(5, 0))

        tool_frame = ttk.Frame(self.tab_annotate)
        tool_frame.pack(fill="x", pady=2)

        tools = [
            ("↖ Select / Move", "none"),
            ("▭ Rectangle", "rect"),
            ("◯ Circle / Ellipse", "circle"),
            ("╱ Line", "line"),
            ("➔ Arrow", "arrow"),
            ("🅣 Text Box", "text"),
        ]
        for label, val in tools:
            ttk.Radiobutton(tool_frame, text=label, variable=self.var_ann_tool, value=val,
                             command=self.set_annotation_tool).pack(anchor="w")

        ttk.Label(self.tab_annotate,
                  text="Click+drag to draw. Clicking an EXISTING shape (with\nany tool active) selects it and switches to Select/Move.",
                  font=("Arial", 8), foreground="gray", justify="left").pack(anchor="w", pady=(2, 8))

        ttk.Label(self.tab_annotate,
                  text="With an object selected: drag or arrow-keys to move,\nDelete/Backspace to remove, Ctrl+C/V to copy-paste.",
                  font=("Arial", 8), foreground="gray", justify="left").pack(anchor="w", pady=(0, 8))

        # --- Properties panel for the currently-selected shape ---
        prop_frame = ttk.LabelFrame(self.tab_annotate, text="Selected Object Properties", padding=5)
        prop_frame.pack(fill="x", pady=5)

        ttk.Label(prop_frame, text="Text (text boxes only):").pack(anchor="w")
        text_row = ttk.Frame(prop_frame)
        text_row.pack(fill="x", pady=(0, 4))
        ttk.Entry(text_row, textvariable=self.var_ann_text).pack(side="left", fill="x", expand=True)
        ttk.Button(text_row, text="✏️ Rich Edit...", command=self.edit_selected_text_annotation).pack(side="left", padx=(4, 0))

        color_row = ttk.Frame(prop_frame)
        color_row.pack(fill="x", pady=2)
        ttk.Label(color_row, text="Color:").pack(side="left")
        ttk.Entry(color_row, textvariable=self.var_ann_color, width=10).pack(side="left", padx=4)
        ttk.Button(color_row, text="🎨", width=3, command=self.choose_annotation_color).pack(side="left")

        lw_row = ttk.Frame(prop_frame)
        lw_row.pack(fill="x", pady=2)
        ttk.Label(lw_row, text="Line Width:").pack(side="left")
        ttk.Entry(lw_row, textvariable=self.var_ann_lw, width=6).pack(side="left", padx=4)
        ttk.Label(lw_row, text="Font Size:").pack(side="left", padx=(10, 0))
        ttk.Entry(lw_row, textvariable=self.var_ann_fontsize, width=6).pack(side="left", padx=4)

        style_row = ttk.Frame(prop_frame)
        style_row.pack(fill="x", pady=2)
        ttk.Checkbutton(style_row, text="Bold", variable=self.var_ann_bold).pack(side="left")
        ttk.Checkbutton(style_row, text="Italic", variable=self.var_ann_italic).pack(side="left", padx=10)

        alpha_row = ttk.Frame(prop_frame)
        alpha_row.pack(fill="x", pady=2)
        ttk.Label(alpha_row, text="Opacity (0-1):").pack(side="left")
        ttk.Entry(alpha_row, textvariable=self.var_ann_alpha, width=6).pack(side="left", padx=4)

        ttk.Button(prop_frame, text="✅ Apply Properties", command=self.apply_annotation_properties).pack(fill="x", pady=(5, 0))
        ttk.Button(prop_frame, text="🗑️ Delete Selected", command=self.delete_selected_annotation).pack(fill="x", pady=2)

        # --- Annotation grid: each shape shown as a small card with a radio
        # indicator, laid out in a grid rather than a plain vertical list.
        # Clicking a card selects that shape (same as clicking it on the
        # graph); switching to Select/Move via the tool radio above clears
        # the highlight here (see set_annotation_tool()). ---
        list_frame = ttk.LabelFrame(self.tab_annotate, text="All Annotations", padding=5)
        list_frame.pack(fill="both", expand=True, pady=5)

        ann_canvas = tk.Canvas(list_frame, highlightthickness=0, height=190)
        ann_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=ann_canvas.yview)
        self.ann_grid_frame = ttk.Frame(ann_canvas)
        ann_canvas.configure(yscrollcommand=ann_scrollbar.set)
        ann_canvas_window = ann_canvas.create_window((0, 0), window=self.ann_grid_frame, anchor="nw")
        self.ann_grid_frame.bind("<Configure>", lambda e: ann_canvas.configure(scrollregion=ann_canvas.bbox("all")))
        ann_canvas.bind("<Configure>", lambda e: ann_canvas.itemconfig(ann_canvas_window, width=e.width))
        ann_canvas.pack(side="left", fill="both", expand=True)
        ann_scrollbar.pack(side="right", fill="y")

        self.var_ann_selected_idx = tk.IntVar(value=-1)  # -1 = nothing selected

    def set_annotation_tool(self):
        """Called when the user picks a drawing tool in the Annotations tab.
        Keeps annotation tools and the analysis tools (peak/area/baseline/
        deconv) mutually exclusive so a click can't be interpreted by both.
        Switching to Select/Move here also deactivates any currently
        selected object (AnnotationManager.set_tool() always clears
        selection on a tool switch) -- the grid highlight below follows via
        on_annotation_selected(None, None)."""
        self.var_click_mode.set('none')
        self.annotation_mgr.set_tool(self.var_ann_tool.get())
        self.update_plot()

    def on_annotation_tool_change(self, tool):
        """Callback AnnotationManager fires when IT changes tool internally
        (auto-switch to Select/Move after clicking an existing shape).
        Keeps the Annotations tab's radio buttons in sync -- this is a
        plain StringVar.set(), which does NOT re-invoke set_annotation_tool()
        (Tkinter only calls a Radiobutton's `command` when the button itself
        is clicked, not on programmatic variable writes), so this can't loop
        back and clear the selection AnnotationManager just made."""
        if hasattr(self, 'var_ann_tool'):
            self.var_ann_tool.set(tool)

    def set_click_mode(self, *_):
        """Called when the user picks an analysis tool (Navigation/Peak/Area/
        Baseline/Deconv/XRD) in the Peaks & Export tab. Mirror of
        set_annotation_tool() -- keeps the two tool families mutually
        exclusive."""
        if hasattr(self, 'var_ann_tool'):
            self.var_ann_tool.set('none')
        if hasattr(self, 'annotation_mgr'):
            self.annotation_mgr.set_tool('none')
        self.update_plot()

    def choose_annotation_color(self):
        from tkinter.colorchooser import askcolor
        current = self.var_ann_color.get() or "black"
        color = askcolor(initialcolor=current, title="Choose Annotation Color")
        if color[1]:
            self.var_ann_color.set(color[1])

    def apply_annotation_properties(self):
        if not self.annotation_mgr.selected_artist:
            messagebox.showinfo("No Selection", "Switch to Select mode and click an annotation first.", parent=self)
            return

        props = {}
        if self.var_ann_color.get():
            props['color'] = self.var_ann_color.get()
        try:
            props['linewidth'] = float(self.var_ann_lw.get())
        except (ValueError, tk.TclError):
            pass
        try:
            props['alpha'] = float(self.var_ann_alpha.get())
        except (ValueError, tk.TclError):
            pass
        try:
            props['fontsize'] = float(self.var_ann_fontsize.get())
        except (ValueError, tk.TclError):
            pass
        props['bold'] = self.var_ann_bold.get()
        props['italic'] = self.var_ann_italic.get()
        if self.var_ann_text.get():
            props['text'] = self.var_ann_text.get()
        # text_alpha / box_alpha / show_border are text-specific extras the
        # AnnotationManager supports but this panel doesn't expose controls
        # for yet -- fine to omit, update_selected_properties() only touches
        # keys that are present in props.

        self.annotation_mgr.update_selected_properties(props)

    def delete_selected_annotation(self):
        self.annotation_mgr.delete_selected()

    def show_text_annotation_dialog(self, parent_window):
        """The rich text-composition dialog, passed to AnnotationManager as
        its text_input_provider -- called when the user draws a new text box.
        Returns a dict (text/color/fontsize/bold/italic) or None if cancelled."""
        dialog = TextAnnotationDialog(parent_window)
        parent_window.wait_window(dialog)
        return dialog.result

    def edit_selected_text_annotation(self):
        """Reopens the rich text dialog, pre-filled, for the currently
        selected text annotation -- lets you touch up formatting/Greek/
        symbols after the fact rather than only at creation time."""
        if not self.annotation_mgr.selected_artist:
            messagebox.showinfo("No Selection", "Switch to Select mode and click a text annotation first.", parent=self)
            return
        artist, kind = self.annotation_mgr.selected_artist
        if kind != 'text':
            messagebox.showinfo("Not a Text Box", "The selected object isn't a text annotation.", parent=self)
            return

        dialog = TextAnnotationDialog(
            self, initial_text=artist.get_text(), initial_color=self.var_ann_color.get(),
            initial_fontsize=self.var_ann_fontsize.get(), initial_bold=self.var_ann_bold.get(),
            initial_italic=self.var_ann_italic.get(),
            initial_family=(artist.get_fontfamily()[0] if artist.get_fontfamily() else 'sans-serif')
        )
        self.wait_window(dialog)
        if dialog.result:
            self.annotation_mgr.update_selected_properties({
                'text': dialog.result['text'],
                'color': dialog.result['color'],
                'fontsize': dialog.result['fontsize'],
                'bold': dialog.result['bold'],
                'italic': dialog.result['italic'],
                'family': dialog.result['family'],
            })
            # Keep the plain Entry + panel in sync with what was just set.
            self.var_ann_text.set(dialog.result['text'])
            self.var_ann_color.set(dialog.result['color'])
            self.var_ann_fontsize.set(dialog.result['fontsize'])
            self.var_ann_bold.set(dialog.result['bold'])
            self.var_ann_italic.set(dialog.result['italic'])

    def _select_annotation_from_grid(self, idx):
        """Fired when a card in the annotation grid is clicked. Behaves like
        clicking the object on the graph: selects it AND switches the tool
        to Select/Move (set directly, not via annotation_mgr.set_tool(),
        which would immediately clear the selection we're about to make)."""
        self.annotation_mgr.active_tool = 'none'
        self.var_ann_tool.set('none')
        self.annotation_mgr.select_by_index(idx)

    def sync_annotation_listbox(self, annotations_list):
        """Callback AnnotationManager fires whenever a shape is added/removed/
        selected. Rebuilds the annotation grid (small radio-indicator cards,
        wrapped across a fixed number of columns) rather than a plain list."""
        if not hasattr(self, 'ann_grid_frame'):
            return  # widgets not built yet (can fire during __init__ bootstrap)

        for child in self.ann_grid_frame.winfo_children():
            child.destroy()

        icons = {'rect': '▭', 'circle': '◯', 'line': '╱', 'arrow': '➔', 'text': '🅣'}
        cols = 3
        for i, (artist, kind) in enumerate(annotations_list):
            label_text = f"{icons.get(kind, '•')} {kind.capitalize()}"
            if kind == 'text':
                snippet = artist.get_text()[:12]
                label_text += f'\n"{snippet}"'

            card = ttk.Frame(self.ann_grid_frame, relief="groove", borderwidth=1)
            card.grid(row=i // cols, column=i % cols, padx=3, pady=3, sticky="nsew")

            ttk.Radiobutton(
                card, text=label_text, variable=self.var_ann_selected_idx, value=i,
                command=lambda idx=i: self._select_annotation_from_grid(idx)
            ).pack(padx=4, pady=4)

        for c in range(cols):
            self.ann_grid_frame.columnconfigure(c, weight=1)

        # Reflect the current selection (if any) in the grid; -1 clears every radio.
        if self.annotation_mgr.selected_artist and self.annotation_mgr.selected_artist in annotations_list:
            self.var_ann_selected_idx.set(annotations_list.index(self.annotation_mgr.selected_artist))
        else:
            self.var_ann_selected_idx.set(-1)

    def on_annotation_selected(self, artist, kind):
        """Callback AnnotationManager fires on selection change; populates
        the properties panel with the selected object's current values, and
        clears the grid's radio highlight when nothing is selected (e.g.
        after explicitly switching to Select/Move, or clicking empty space)."""
        if not hasattr(self, 'var_ann_text'):
            return  # widgets not built yet
        if artist is None:
            if hasattr(self, 'var_ann_selected_idx'):
                self.var_ann_selected_idx.set(-1)  # deactivate grid highlight
            return  # keep last-shown property values rather than blanking the panel
        if kind == 'text':
            self.var_ann_text.set(artist.get_text())
            self.var_ann_color.set(artist.get_color())
            self.var_ann_fontsize.set(artist.get_fontsize())
            self.var_ann_bold.set(artist.get_fontweight() == 'bold')
            self.var_ann_italic.set(artist.get_fontstyle() == 'italic')
            self.var_ann_alpha.set(artist.get_alpha() or 1.0)
        else:
            self.var_ann_text.set("")
            try:
                raw_color = artist.get_color() if kind == 'line' else artist.get_edgecolor()
                self.var_ann_color.set(mcolors.to_hex(raw_color))
            except Exception:
                pass
            self.var_ann_lw.set(artist.get_linewidth())
            self.var_ann_alpha.set(artist.get_alpha() or 1.0)

    def _build_tools_tab(self):
        ttk.Label(self.tab_tools, text="Interactive Tools:").pack(anchor="w", pady=(5,0))
        
        mode_frame = ttk.Frame(self.tab_tools)
        mode_frame.pack(fill="x", pady=2)
        
        ttk.Radiobutton(mode_frame, text="Navigation (Zoom/Pan)", variable=self.var_click_mode, value='none', command=self.set_click_mode).pack(anchor="w")
        
        ttk.Radiobutton(mode_frame, text="Draw Manual Baseline", variable=self.var_click_mode, value='baseline', command=self.set_click_mode).pack(anchor="w")
        
        base_btn_frame = ttk.Frame(mode_frame)
        base_btn_frame.pack(fill="x", pady=2)
        ttk.Button(base_btn_frame, text="✅ Apply", width=8, command=self.apply_manual_baseline).pack(side="left", padx=2)
        ttk.Button(base_btn_frame, text="❌ Clear", width=8, command=self.clear_manual_baseline).pack(side="left", padx=2)
        
        if getattr(state, 'technique', 'FTIR') == 'FTIR':
            ttk.Radiobutton(mode_frame, text="Pick Peak", variable=self.var_click_mode, value='peak', command=self.set_click_mode).pack(anchor="w")
            ttk.Radiobutton(mode_frame, text="Calculate Area", variable=self.var_click_mode, value='area', command=self.set_click_mode).pack(anchor="w")
            ttk.Button(self.tab_tools, text="📖 FT-IR Functional Group Cheat Sheet", command=self.show_cheat_sheet).pack(fill="x", pady=(5, 0))
            ttk.Radiobutton(mode_frame, text="Peak Deconvolution", variable=self.var_click_mode, value='deconv', command=self.set_click_mode).pack(anchor="w")

            deconv_btn_frame = ttk.Frame(mode_frame)
            deconv_btn_frame.pack(fill="x", pady=2)
            ttk.Button(deconv_btn_frame, text="❌ Clear Fit", width=10, command=self.clear_deconv).pack(side="left", padx=20)
            ttk.Button(deconv_btn_frame, text="💾 Export Data", width=12, command=self.export_deconv_data).pack(side="left", padx=5)

            auto_frame = ttk.LabelFrame(self.tab_tools, text="Auto-Find Peaks", padding=5)
            auto_frame.pack(fill="x", pady=5)
            ttk.Label(auto_frame, text="Prominence:").pack(side="left")
            ttk.Entry(auto_frame, textvariable=self.var_prominence, width=5).pack(side="left", padx=5)
            ttk.Button(auto_frame, text="Find", width=6, command=self.auto_find_peaks).pack(side="left")

        elif getattr(state, 'technique', 'FTIR') == 'XRD':
            ttk.Radiobutton(mode_frame, text="Pick XRD Peak (Smart Snap)", variable=self.var_click_mode, value='xrd_peak', command=self.set_click_mode).pack(anchor="w")
            ttk.Radiobutton(mode_frame, text="Calculate Peak Area", variable=self.var_click_mode, value='area', command=self.set_click_mode).pack(anchor="w")
            
            xrd_options = ttk.Frame(self.tab_tools)
            xrd_options.pack(fill="x", pady=5)
            ttk.Checkbutton(xrd_options, text="Show FWHM & Grain Size on Graph", variable=self.var_show_fwhm, command=self.update_plot).pack(anchor="w")
            
            auto_xrd = ttk.LabelFrame(self.tab_tools, text="Auto-Find XRD Peaks", padding=5)
            auto_xrd.pack(fill="x", pady=5)
            ttk.Label(auto_xrd, text="Min Height:").pack(side="left")
            ttk.Entry(auto_xrd, textvariable=self.var_xrd_min_height, width=5).pack(side="left", padx=2)
            ttk.Label(auto_xrd, text="Prom:").pack(side="left")
            ttk.Entry(auto_xrd, textvariable=self.var_prominence, width=4).pack(side="left", padx=2)
            ttk.Button(auto_xrd, text="Find", width=5, command=self.auto_find_xrd_peaks).pack(side="left", padx=2)

            ttk.Button(self.tab_tools, text="📊 Plot Grain Size Distribution", command=self.show_grain_size_chart).pack(fill="x", pady=5, ipady=5)

        else:  # GENERAL -- lightweight generic tools (no technique-specific peak table / Scherrer calc)
            ttk.Radiobutton(mode_frame, text="Pick Point", variable=self.var_click_mode, value='peak', command=self.set_click_mode).pack(anchor="w")
            ttk.Radiobutton(mode_frame, text="Calculate Area", variable=self.var_click_mode, value='area', command=self.set_click_mode).pack(anchor="w")

            auto_frame = ttk.LabelFrame(self.tab_tools, text="Auto-Find Peaks", padding=5)
            auto_frame.pack(fill="x", pady=5)
            ttk.Label(auto_frame, text="Prominence:").pack(side="left")
            ttk.Entry(auto_frame, textvariable=self.var_prominence, width=5).pack(side="left", padx=5)
            ttk.Button(auto_frame, text="Find", width=6, command=self.auto_find_peaks).pack(side="left")
            
        list_frame = ttk.LabelFrame(self.tab_tools, text="Saved Peaks", padding=5)
        list_frame.pack(fill="both", expand=True, pady=5)
        
        self.peak_listbox = tk.Listbox(list_frame, height=8)
        self.peak_listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.peak_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.peak_listbox.config(yscrollcommand=scrollbar.set)
        
        btn_frame = ttk.Frame(self.tab_tools)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Delete Selected", command=self.delete_selected_peak).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(btn_frame, text="Clear All", command=self.clear_peaks).pack(side="left", expand=True, fill="x", padx=2)
        
        ttk.Separator(self.tab_tools, orient='horizontal').pack(fill='x', pady=5)
        export_frame = ttk.Frame(self.tab_tools)
        export_frame.pack(fill="x", pady=5)
        ttk.Button(export_frame, text="💾 Export Data, Peaks & Graph", command=self.export_data).pack(fill="x", ipady=5)
        ttk.Button(export_frame, text="📁 Save Workspace Session (.json)", command=self.save_session_cmd).pack(fill="x", ipady=4)
    
    def save_and_update(self):
        fs = state.file_set[self.current_stem]
        
        fs['bg_sub'] = self.var_bg_sub.get()
        fs['bg_filename'] = self.var_bg_file.get()
        fs['bg_mult'] = self.var_bg_mult.get()
        
        if fs.get('t2a', False) != self.var_t2a.get() or fs.get('normalize', False) != self.var_norm.get():
            self.clear_peaks()
        
        fs['custom_name'] = self.var_name.get()
        fs['color'] = self.var_color.get()
        
        try:
            fs['offset'] = float(self.var_offset.get())
        except ValueError: pass
        
        try:
            fs['smooth'] = int(self.var_smooth.get())
        except ValueError: pass
        
        fs['do_baseline'] = self.var_baseline.get()
        fs['normalize'] = self.var_norm.get()
        fs['t2a'] = self.var_t2a.get()
        fs['derivative'] = self.var_deriv.get()
        
        try:
            fs['als_lam'] = float(self.var_als_lam.get())
        except ValueError: pass
        
        gs = state.global_set
        gs['xlabel'] = self.var_xlabel.get()
        gs['ylabel'] = self.var_ylabel.get()
        gs['title'] = self.var_title.get() 
        
        def parse_lims(val):
            if not val: return None
            try:
                return [float(x.strip()) for x in val.split(',')]
            except:
                return None
                
        gs['xlim'] = parse_lims(self.var_xlim.get())
        gs['ylim'] = parse_lims(self.var_ylim.get())
        gs['xstep'] = self.var_xstep.get()
        gs['ystep'] = self.var_ystep.get()
        
        if hasattr(self, 'update_plot'):
            self.update_plot()
    
    def apply_to_all(self):
        self.save_and_update() 
        
        current_fs = state.file_set[self.current_stem]
        keys_to_copy = ['smooth', 'do_baseline', 'normalize', 'derivative', 'als_lam', 't2a', 'offset']
        
        for stem in self.stems:
            if stem != self.current_stem:
                for key in keys_to_copy:
                    state.file_set[stem][key] = current_fs.get(key)
                    
        self.update_plot()
        messagebox.showinfo("Success", "Settings (Smoothing, Baseline, %T→Abs, etc.) applied to all files!", parent=self)
    
    def apply_manual_baseline(self):
        if len(self.baseline_pts) < 2:
            messagebox.showwarning("Warning", "Please click at least 2 points on the graph first!", parent=self)
            return
        
        fs = state.file_set[self.current_stem]
        fs['manual_baseline_pts'] = self.baseline_pts.copy()
        self.baseline_pts = [] 
        self.var_click_mode.set('none') 
        self.update_plot()
        
    def clear_manual_baseline(self):
        fs = state.file_set[self.current_stem]
        fs['manual_baseline_pts'] = []
        self.baseline_pts = []
        self.update_plot()
    
    def clear_deconv(self):
        fs = state.file_set[self.current_stem]
        fs['deconvs'] = [] 
        self.deconv_start = None 
        self.update_plot() 

    def show_cheat_sheet(self):
        win = tk.Toplevel(self)
        win.title("FT-IR Cheat Sheet")
        win.geometry("450x350")
        win.transient(self) 
        
        cols = ("Frequency (cm⁻¹)", "Functional Group", "Intensity")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=12)
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=140, anchor="center")
            
        bands = [
            ("3200 - 3600", "O-H Stretch (Alcohols)", "Broad, Strong"),
            ("3300 - 3500", "N-H Stretch (Amines)", "Medium"),
            ("2850 - 3000", "C-H Stretch (Alkanes)", "Medium / Strong"),
            ("3000 - 3100", "=C-H Stretch (Alkenes)", "Medium"),
            ("2100 - 2260", "C≡C / C≡N Stretch", "Weak / Medium"),
            ("1650 - 1750", "C=O Stretch (Carbonyl)", "Strong"),
            ("1600 - 1680", "C=C Stretch (Alkenes)", "Weak / Medium"),
            ("1500 - 1600", "N-H Bend (Amines)", "Medium"),
            ("1000 - 1300", "C-O Stretch (Ethers/Esters)", "Strong"),
            ("600 - 900", "C-H Bend (Aromatics)", "Strong")
        ]
        
        for band in bands:
            tree.insert("", tk.END, values=band)
            
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=5)

    def clear_peaks(self):
        state.file_set[self.current_stem]['labels'] = []
        state.file_set[self.current_stem]['areas'] = []
        state.file_set[self.current_stem]['deconvs'] = []
        if hasattr(self, 'update_plot'):
            self.update_plot()

    def save_session_cmd(self):
        try:
            from session import save_session
            save_session(root_window=self, viewer_instance=self, save_as=True)
            
        except ImportError:
            messagebox.showerror("Missing Module", "Could not find 'session.py'. Please ensure the file exists.", parent=self)
        except Exception as e:
            messagebox.showerror("Save Error", f"An error occurred while launching the save sequence:\n{e}", parent=self)

    def sync_annotations_to_state(self):
        """Called by session.save_session() right before writing the JSON
        file. Was a no-op before -- meaning drawn annotations were silently
        never saved. Now actually pulls the live shapes out of
        AnnotationManager into state.global_set['annotations'] (a key the
        session schema already reserved for exactly this)."""
        if hasattr(self, 'annotation_mgr'):
            state.global_set['annotations'] = self.annotation_mgr.get_serialized_data()

    def reset_file_settings(self):
        self.var_offset.set(0.0)
        self.var_smooth.set(15)
        self.var_baseline.set(False)
        self.var_norm.set(False)
        self.var_deriv.set(0)
        self.var_t2a.set(False)
        
        self.clear_manual_baseline()
        self.clear_peaks()
        self.clear_deconv()
        self.save_and_update()
        
    def export_data(self):
        export_win = tk.Toplevel(self)
        export_win.title("Export Options")
        export_win.geometry("400x250")
        export_win.transient(self) 
        export_win.grab_set()      
        
        var_csv = tk.BooleanVar(value=True)
        var_txt = tk.BooleanVar(value=True)
        var_img = tk.BooleanVar(value=True)
        var_fmt = tk.StringVar(value=".png")
        var_dpi = tk.IntVar(value=300)
        
        ttk.Label(export_win, text="Select items to export:", font=("Arial", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        ttk.Checkbutton(export_win, text="1. Processed Data (.csv)", variable=var_csv).pack(anchor="w", padx=25, pady=2)
        ttk.Checkbutton(export_win, text="2. Peaks & Areas Report (.txt)", variable=var_txt).pack(anchor="w", padx=25, pady=2)
        
        img_frame = ttk.Frame(export_win)
        img_frame.pack(fill="x", padx=25, pady=2)
        ttk.Checkbutton(img_frame, text="3. Graph Image", variable=var_img).pack(side="left")
        
        ttk.Label(img_frame, text="  Format:").pack(side="left")
        ttk.Combobox(img_frame, textvariable=var_fmt, values=[".png", ".jpg", ".svg", ".pdf", ".tiff"], width=5, state="readonly").pack(side="left", padx=2)
        
        ttk.Label(img_frame, text="  DPI:").pack(side="left")
        ttk.Combobox(img_frame, textvariable=var_dpi, values=[150, 300, 600, 1200], width=5).pack(side="left", padx=2)
        
        def process_export():
            if not (var_csv.get() or var_txt.get() or var_img.get()):
                messagebox.showwarning("Warning", "Please select at least one item to export!", parent=export_win)
                return
                
            save_dir = filedialog.askdirectory(title="Select Folder to Save Exports", parent=export_win)
            if not save_dir:
                return 
                
            save_dir = Path(save_dir)
            fs = state.file_set[self.current_stem]
            raw_x, raw_y = self.data_dict[self.current_stem]
            
            try:
                x, y = process_spectrum(raw_x, raw_y, self.current_stem)
            except Exception:
                x, y = raw_x, raw_y

            x_arr, y_arr = np.array(x, dtype=float), np.array(y, dtype=float)
            if getattr(state, 'technique', 'FTIR') == 'FTIR' and fs.get('t2a', False):
                y_safe = np.clip(y_arr, 0.0001, None)
                y_arr = 2 - np.log10(y_safe)
            x, y = x_arr, y_arr

            try:
                if var_csv.get():
                    data_path = save_dir / f"{self.current_stem}_processed.csv"
                    tech = getattr(state, 'technique', 'FTIR')
                    csv_header = "Wavenumber,Intensity" if tech == 'FTIR' else ("2-Theta,Intensity" if tech == 'XRD' else "X,Y")
                    np.savetxt(data_path, np.column_stack((x, y)), delimiter=",", header=csv_header, comments="")
                    
                if var_txt.get():
                    report_path = save_dir / f"{self.current_stem}_analysis_report.txt"
                    with open(report_path, 'w') as f:
                        if getattr(state, 'technique', 'FTIR') == 'FTIR':
                            peaks = fs.get('labels', [])
                            areas = fs.get('areas', [])
                            
                            f.write(f"--- FT-IR Analysis Report for {self.current_stem} ---\n\n")
                            if peaks:
                                f.write("PEAKS (Local Minima/Maxima):\n")
                                f.write("X (Wavenumber)\tY (Intensity)\n")
                                for px, py, text in peaks:
                                    f.write(f"{px:.2f}\t\t{py:.4f}\t\t({text})\n")
                                f.write("\n")
                            if areas:
                                f.write("INTEGRATED AREAS:\n")
                                f.write("Start X\t\tEnd X\t\tArea Value\n")
                                for x1, x2, val in areas:
                                    f.write(f"{x1:.2f}\t\t{x2:.2f}\t\t{val:.4f}\n")
                                    
                        elif getattr(state, 'technique', 'FTIR') == 'XRD':
                            xrd_peaks = fs.get('xrd_peaks', [])
                            areas = fs.get('areas', [])
                            
                            f.write(f"--- XRD Analysis Report for {self.current_stem} ---\n\n")
                            if xrd_peaks:
                                f.write("PEAKS & CRYSTALLITE SIZE (Scherrer Equation):\n")
                                f.write("2-Theta\t\tIntensity\tFWHM\t\tSize (nm)\n")
                                for px, py, fwhm, d in xrd_peaks:
                                    f.write(f"{px:.2f}\t\t{py:.4f}\t\t{fwhm:.4f}\t\t{d:.2f}\n")
                                
                                valid_sizes = [p[3] for p in xrd_peaks if p[3] > 0]
                                if valid_sizes:
                                    avg_sz = np.mean(valid_sizes)
                                    std_sz = np.std(valid_sizes) if len(valid_sizes) > 1 else 0.0
                                    f.write(f"\nSTATISTICS: Average Size = {avg_sz:.2f} nm (Std Dev: {std_sz:.2f} nm)\n\n")
                                    
                            if areas:
                                f.write("INTEGRATED AREAS:\n")
                                f.write("Start 2-Theta\tEnd 2-Theta\tArea Value\n")
                                for x1, x2, val in areas:
                                    f.write(f"{x1:.2f}\t\t{x2:.2f}\t\t{val:.4f}\n")

                        else:  # GENERAL
                            points = fs.get('labels', [])
                            areas = fs.get('areas', [])

                            f.write(f"--- Data Analysis Report for {self.current_stem} ---\n\n")
                            if points:
                                f.write("PICKED POINTS:\n")
                                f.write("X\t\tY\n")
                                for px, py, text in points:
                                    f.write(f"{px:.4g}\t\t{py:.4g}\n")
                                f.write("\n")
                            if areas:
                                f.write("INTEGRATED AREAS:\n")
                                f.write("Start X\t\tEnd X\t\tArea Value\n")
                                for x1, x2, val in areas:
                                    f.write(f"{x1:.4g}\t\t{x2:.4g}\t\t{val:.4f}\n")
                
                if var_img.get():
                    fmt = var_fmt.get()
                    dpi = var_dpi.get()
                    img_path = str(save_dir / f"{self.current_stem}_plot{fmt}")
                    self.fig.savefig(img_path, dpi=dpi, bbox_inches='tight')
                    
                messagebox.showinfo("Success", f"Files successfully exported to:\n\n{save_dir}", parent=export_win)
                export_win.destroy() 
                
            except Exception as e:
                messagebox.showerror("Export Error", f"An error occurred while saving:\n{e}", parent=export_win)
                
        ttk.Separator(export_win, orient='horizontal').pack(fill='x', pady=(15, 10))
        btn_frame = ttk.Frame(export_win)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="Cancel", command=export_win.destroy).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="Choose Folder & Save", command=process_export).pack(side="right")

    def auto_find_peaks(self):
        x, y = self.get_processed_data_for_stem(self.current_stem)
        fs = state.file_set[self.current_stem]
        
        # FTIR %Transmittance conventionally shows peaks as downward dips
        # (hence searching -y below); arbitrary GENERAL data has no such
        # convention, so default to the more common upward-peak assumption.
        if getattr(state, 'technique', 'FTIR') == 'GENERAL':
            search_y = y
        elif not fs.get('t2a', False): 
            search_y = -y  
        else:
            search_y = y   
            
        prom = float(self.var_prominence.get())
        
        peaks_idx, _ = find_peaks(search_y, prominence=prom)
        
        for p in peaks_idx:
            px, py = x[p], y[p]
            existing_peaks = fs.get('labels', [])
            if not any(abs(ex[0] - px) < 0.1 for ex in existing_peaks):
                fs.setdefault('labels', []).append((px, py, f"{px:.1f}"))
                
        self.update_plot()

    def sync_peak_listbox(self):
        self.peak_listbox.delete(0, tk.END)
        fs = state.file_set.get(self.current_stem, {})
        
        if getattr(state, 'technique', 'FTIR') == 'FTIR':
            for i, (px, py, text) in enumerate(fs.get('labels', [])):
                self.peak_listbox.insert(tk.END, f"Peak {i+1}: {px:.1f} cm⁻¹ ({text})")
        
        elif getattr(state, 'technique', 'FTIR') == 'XRD':
            for i, (px, py, fwhm, d) in enumerate(fs.get('xrd_peaks', [])):
                if d > 0:
                    self.peak_listbox.insert(tk.END, f"2θ: {px:.2f}° | FWHM: {fwhm:.2f}° | Size: {d:.1f}nm")
                else:
                    self.peak_listbox.insert(tk.END, f"2θ: {px:.2f}° | FWHM: {fwhm:.2f}°")
            
            for i, (x1, x2, area) in enumerate(fs.get('areas', [])):
                self.peak_listbox.insert(tk.END, f"Area: {area:.2f} (from {min(x1,x2):.1f}° to {max(x1,x2):.1f}°)")

        else:  # GENERAL
            for i, (px, py, text) in enumerate(fs.get('labels', [])):
                self.peak_listbox.insert(tk.END, f"Point {i+1}: ({px:.4g}, {py:.4g})")
            for i, (x1, x2, area) in enumerate(fs.get('areas', [])):
                self.peak_listbox.insert(tk.END, f"Area: {area:.4g} (from {min(x1,x2):.4g} to {max(x1,x2):.4g})")

    def delete_selected_peak(self):
        sel = self.peak_listbox.curselection()
        if not sel: return
        idx = sel[0]
        fs = state.file_set[self.current_stem]
        
        if getattr(state, 'technique', 'FTIR') == 'FTIR':
            num_peaks = len(fs.get('labels', []))
            
            if idx < num_peaks:
                fs['labels'].pop(idx)
            else:
                area_idx = idx - num_peaks
                if area_idx < len(fs.get('areas', [])):
                    fs['areas'].pop(area_idx)
                    
        elif getattr(state, 'technique', 'FTIR') == 'XRD':
            if idx < len(fs.get('xrd_peaks', [])):
                fs['xrd_peaks'].pop(idx)

        else:  # GENERAL -- same list layout as FTIR (points then areas)
            num_points = len(fs.get('labels', []))
            if idx < num_points:
                fs['labels'].pop(idx)
            else:
                area_idx = idx - num_points
                if area_idx < len(fs.get('areas', [])):
                    fs['areas'].pop(area_idx)

        self.update_plot()

    def clear_peaks(self):
        fs = state.file_set[self.current_stem]
        
        if 'labels' in fs: fs['labels'] = []
        if 'areas' in fs: fs['areas'] = []
        if 'deconvs' in fs: fs['deconvs'] = []
        if 'xrd_peaks' in fs: fs['xrd_peaks'] = []
        
        self.update_plot()

    def _build_bottom_buttons(self):
        bot_frame = ttk.Frame(self.control_frame)
        bot_frame.pack(side="bottom", fill="x", pady=10)
        self.bottom_action_btn = ttk.Button(bot_frame)
        self.bottom_action_btn.pack(fill="x", ipady=8)
        self._refresh_bottom_button()

    def _refresh_bottom_button(self):
        """(Re)configures the bottom action button's label/command. Split out
        from _build_bottom_buttons() so it can be re-called after the session
        switches mode mid-flight (e.g. via 'Add File(s)' -> Overlay/Stack),
        since that button was previously set once at __init__ and would go
        stale."""
        is_last = False
        if state.settings.get('mode') == 'individual':
            current_idx = next((i for i, d in enumerate(state.all_data) if d[0] == self.stems[0]), 0)
            if current_idx == len(state.all_data) - 1:
                is_last = True

        if state.settings.get('mode') != 'individual' or is_last:
            self.bottom_action_btn.config(text="✅ Finish & Close", command=self.on_close)
        else:
            self.bottom_action_btn.config(text="Next Spectrum ➔", command=self.next_spectrum)

    def _refresh_stack_reorder_visibility(self):
        if state.settings.get('mode') == 'stack':
            if not self.stack_reorder_frame.winfo_ismapped():
                self.stack_reorder_frame.pack(fill="x", pady=(4, 0))
        else:
            if self.stack_reorder_frame.winfo_ismapped():
                self.stack_reorder_frame.pack_forget()

    def move_stem_up(self):
        idx = self.stems.index(self.current_stem)
        if idx == 0:
            return
        self.stems[idx - 1], self.stems[idx] = self.stems[idx], self.stems[idx - 1]
        self.update_plot()

    def move_stem_down(self):
        idx = self.stems.index(self.current_stem)
        if idx >= len(self.stems) - 1:
            return
        self.stems[idx + 1], self.stems[idx] = self.stems[idx], self.stems[idx + 1]
        self.update_plot()

    def _read_new_file(self, filepath):
        """Reads a new file using whichever reader matches the current
        technique -- shared with ir.py/xrd.py/general.py via readers.py."""
        filepath = Path(filepath)
        technique = getattr(state, 'technique', 'FTIR')
        if technique == 'GENERAL':
            from readers import read_generic_configured
            fmt = state.general_format or {'delimiter': ',', 'skip_rows': 0, 'x_col': 0, 'y_col': 1}
            return read_generic_configured(filepath, **fmt)
        else:
            from readers import robust_read_spectrum
            return robust_read_spectrum(filepath)

    def _init_new_file_settings(self, stem):
        """Mirrors config.SessionState.init_file_settings()'s per-file defaults,
        for a single file added after the initial session setup."""
        colors = list(mcolors.TABLEAU_COLORS.values())
        idx = len(state.file_set) % len(colors)
        default_color = colors[idx] if state.settings.get('mode') == 'overlay' else 'black'
        state.file_set[stem] = {
            'custom_name': stem, 'color': default_color, 'offset': 0.0,
            'smooth': state.settings.get('smooth', 15), 'labels': [], 'areas': [],
            'do_baseline': False, 'als_lam': 100000, 'als_p': 0.05
        }

    def add_files(self):
        mode = state.settings.get('mode', 'individual')

        # Individual mode only ever shows one file -- adding another is
        # ambiguous, so ask how it should be handled (replace / switch mode).
        if mode == 'individual' and len(self.stems) > 0:
            dialog = AddDataChoiceDialog(self)
            self.wait_window(dialog)
            if dialog.choice is None:
                return
            if dialog.choice == 'replace':
                self.replace_current_file()
                return
            elif dialog.choice in ('overlay', 'stack'):
                state.settings['mode'] = dialog.choice
                # This window's outer main()-level loop (in ir.py/xrd.py/
                # general.py) is a for-loop over state.all_data, still
                # blocked on this very window via wait_window(). Appending
                # new files below would otherwise get picked up by that
                # loop's next iteration and open a second, stale
                # individual-mode window once this one closes -- this flag
                # tells that loop to stop instead.
                state.mode_switched_mid_session = True
                messagebox.showinfo("Mode Changed",
                                     f"Switched this session to {dialog.choice.capitalize()} mode.\n"
                                     f"Now pick the new file(s) to add.", parent=self)
                self._refresh_stack_reorder_visibility()
                self._refresh_bottom_button()

        filetypes = [("Data files", "*.csv *.txt *.xlsx *.dat *.asr *.raw *.CSV *.TXT")]
        new_paths = filedialog.askopenfilenames(title="Add Data File(s)", filetypes=filetypes)
        if not new_paths:
            return

        added, failed = [], []
        for path in new_paths:
            try:
                x, y = self._read_new_file(path)
                if len(x) > 2:
                    stem = Path(path).stem
                    base_stem, n = stem, 1
                    while stem in self.data_dict:  # avoid clobbering an already-open file with the same name
                        stem = f"{base_stem}_{n}"
                        n += 1
                    self.data_dict[stem] = (x, y)
                    self.stems.append(stem)
                    state.all_data.append((stem, x, y))
                    if stem not in state.file_set:
                        self._init_new_file_settings(stem)
                    added.append(stem)
                else:
                    failed.append(Path(path).name)
            except Exception:
                failed.append(Path(path).name)

        if failed:
            messagebox.showwarning("Some Files Skipped",
                                    f"Could not read {len(failed)} file(s):\n" + "\n".join(failed[:10]),
                                    parent=self)

        if added:
            self.cb_files['values'] = self.stems
            self.current_stem = added[-1]
            self.cb_files.set(self.current_stem)
            self.load_active_settings()
            self._refresh_bottom_button()
            self.update_plot()

    def replace_current_file(self):
        filetypes = [("Data files", "*.csv *.txt *.xlsx *.dat *.asr *.raw")]
        new_path = filedialog.askopenfilename(title="Replace Current File's Data", filetypes=filetypes)
        if not new_path:
            return
        self._do_replace_current(new_path)

    def _do_replace_current(self, new_path):
        try:
            x, y = self._read_new_file(new_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read file:\n{e}", parent=self)
            return
        if len(x) <= 2:
            messagebox.showerror("Error", "That file did not contain enough numeric data.", parent=self)
            return

        stem = self.current_stem
        self.data_dict[stem] = (x, y)
        for i, d in enumerate(state.all_data):
            if d[0] == stem:
                state.all_data[i] = (stem, x, y)
                break

        # Keep display settings (color/offset/etc.) but clear anything that
        # was computed against the OLD data -- peaks/areas/fits would now
        # point at meaningless x/y locations relative to the new dataset.
        fs = state.file_set.get(stem, {})
        fs['labels'] = []
        fs['areas'] = []
        fs['deconvs'] = []
        fs.pop('xrd_peaks', None)
        fs.pop('manual_baseline_pts', None)

        self.update_plot()
        messagebox.showinfo("Replaced", f"'{stem}' now shows data from:\n{Path(new_path).name}", parent=self)

    def remove_current_file(self):
        if len(self.stems) <= 1:
            messagebox.showwarning("Cannot Remove",
                                    "At least one file must remain open. Close the window instead if you're done.",
                                    parent=self)
            return
        if not messagebox.askyesno("Remove File", f"Remove '{self.current_stem}' from this session?", parent=self):
            return

        stem_to_remove = self.current_stem
        self.stems.remove(stem_to_remove)
        del self.data_dict[stem_to_remove]
        state.all_data = [d for d in state.all_data if d[0] != stem_to_remove]
        state.file_set.pop(stem_to_remove, None)

        self.current_stem = self.stems[0]
        self.cb_files['values'] = self.stems
        self.cb_files.set(self.current_stem)
        self.load_active_settings()
        self._refresh_bottom_button()
        self.update_plot()

    def next_spectrum(self):
        self.destroy() 

    def update_plot(self):
        # update_plot() is called on nearly every settings change (offset,
        # color, peak pick, tool switch, etc.) and always does a full
        # self.fig.clear() below, which destroys every matplotlib artist --
        # including any annotations the user has drawn. Snapshot them first
        # so they can be re-attached to the freshly-rebuilt axis afterward.
        ann_snapshot = None
        if hasattr(self, 'annotation_mgr'):
            ann_snapshot = self.annotation_mgr.get_serialized_data()
            if not ann_snapshot and getattr(self, '_pending_annotation_load', None):
                # First call after __init__: nothing drawn yet in this window,
                # but a loaded session may have annotations waiting to be
                # restored onto the axis we're about to create.
                ann_snapshot = self._pending_annotation_load
            self._pending_annotation_load = None

        self.fig.clear()
        self.cursors = [] 
        
        mode = state.settings.get('mode', 'individual')
        is_stack = (mode == 'stack') 
        
        if is_stack:
            axes = self.fig.subplots(len(self.stems), 1, sharex=True)
            if len(self.stems) == 1: axes = [axes]
        else:
            ax = self.fig.add_subplot(111)
            axes = [ax] * len(self.stems)
            
        min_xs, max_xs, min_ys, max_ys = [], [], [], []
        
        for i, stem in enumerate(self.stems):
            ax = axes[i]
            fs = state.file_set[stem]
            raw_x, raw_y = self.data_dict[stem]
            
            try:
                x, y = process_spectrum(raw_x, raw_y, stem)
            except Exception:
                x, y = raw_x, raw_y
            
            x_arr = np.array(x, dtype=float)
            y_arr = np.array(y, dtype=float)
            
            if fs.get('t2a', False):
                y_safe = np.clip(y_arr, 0.0001, None)
                y_arr = 2 - np.log10(y_safe)

            manual_pts = fs.get('manual_baseline_pts', [])
            if len(manual_pts) >= 2:
                pts_x = np.array([p[0] for p in manual_pts])
                pts_y = np.array([p[1] for p in manual_pts])
                sort_idx = np.argsort(pts_x)
                pts_x, pts_y = pts_x[sort_idx], pts_y[sort_idx]
                baseline_curve = np.interp(x_arr, pts_x, pts_y)
                y_arr = y_arr - baseline_curve
            
            if fs.get('normalize', False):
                y_min = np.min(y_arr)
                y_max = np.max(y_arr)
                if y_max != y_min:
                    target_max = 1.0 if fs.get('t2a', False) else 100.0
                    y_arr = ((y_arr - y_min) / (y_max - y_min)) * target_max

            if fs.get('bg_sub', False) and 'bg_data' in fs:
                bg_raw_x, bg_raw_y = fs['bg_data']
                sort_idx = np.argsort(bg_raw_x)
                bg_x_sorted = bg_raw_x[sort_idx]
                bg_y_sorted = bg_raw_y[sort_idx]
                bg_y_interp = np.interp(x, bg_x_sorted, bg_y_sorted)
                y_arr = y_arr - (bg_y_interp * fs.get('bg_mult', 1.0))
            
            y_arr = y_arr + fs.get('offset', 0.0)

            x, y = x_arr, y_arr 

            if len(x) > 0:
                min_xs.append(min(x)); max_xs.append(max(x))
                min_ys.append(min(y)); max_ys.append(max(y))
                
            label_name = fs.get('custom_name', stem)
            color = fs.get('color', 'black')
            
            ax.plot(x, y, label=label_name, color=color, linewidth=1.5)
            
            for px, py, text in fs.get('labels', []):
                ax.plot(px, py, 'v', color=color, markersize=6)
                ax.annotate(text, xy=(px, py), xytext=(0, -20), textcoords="offset points", ha='center', va='bottom', color=color, fontsize=9, bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8, edgecolor='none'), annotation_clip=True)

            for px, py, fwhm, d in fs.get('xrd_peaks', []):
                ax.plot(px, py, 'o', color=color, markersize=5)
                if self.var_show_fwhm.get():
                    text = f"2θ: {px:.1f}°\nFWHM: {fwhm:.2f}°\nD: {d:.1f} nm"
                else:
                    text = f"2θ: {px:.1f}°"
                ax.annotate(text, xy=(px, py), xytext=(0, 10), textcoords="offset points", ha='center', va='bottom', color=color, fontsize=8, bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.9, edgecolor='gray'), annotation_clip=True)

            for x1, x2, area_val in fs.get('areas', []):
                x_arr_area, y_arr_area = np.array(x), np.array(y)
                mask = (x_arr_area >= x1) & (x_arr_area <= x2)
                x_sel, y_sel = x_arr_area[mask], y_arr_area[mask]
                
                if len(x_sel) > 1:
                    sort_idx = np.argsort(x_sel)
                    x_sel, y_sel = x_sel[sort_idx], y_sel[sort_idx]
                    baseline = np.interp(x_sel, [x_sel[0], x_sel[-1]], [y_sel[0], y_sel[-1]])
                    ax.fill_between(x_sel, y_sel, baseline, color=color, alpha=0.4)
                    mid_idx = len(x_sel) // 2
                    ax.text(x_sel[mid_idx], y_sel[mid_idx], f"Area:\n{area_val:.1f}", color='black', ha='center', va='center', bbox=dict(facecolor='white', alpha=0.8, edgecolor='none', pad=2))

            for deconv_data in fs.get('deconvs', []):
                if len(deconv_data) == 6:
                    x1, x2, baseline, popt, num_peaks, is_valley = deconv_data
                else:
                    x1, x2, baseline, popt, num_peaks = deconv_data
                    is_valley = False 
                    
                x_arr_area, y_arr_area = np.array(x), np.array(y)
                mask = (x_arr_area >= x1) & (x_arr_area <= x2)
                x_sel = x_arr_area[mask]
                
                composite_curve = np.zeros_like(x_sel)
                sign = -1 if is_valley else 1
                
                for j in range(0, len(popt), 3):
                    A, mu, sigma = popt[j], popt[j+1], popt[j+2]
                    sub_peak = A * np.exp(-((x_sel - mu)**2) / (2 * sigma**2))
                    composite_curve += sub_peak
                    ax.plot(x_sel, baseline + (sign * sub_peak), linestyle='--', alpha=0.8)
                    ax.fill_between(x_sel, baseline, baseline + (sign * sub_peak), alpha=0.2)
                
                ax.plot(x_sel, baseline + (sign * composite_curve), color='red', linestyle=':', linewidth=2, label=f"Fit ({num_peaks} peaks)")

            if is_stack and len(y) > 0:
                b = (max(y) - min(y)) * 0.05
                ax.set_ylim(bottom=min(y) - b, top=max(y) + b)

        if mode == 'overlay':
            axes[0].legend(loc='best', fontsize=8, framealpha=0.9, edgecolor='none')
        else:
            for ax in set(axes):
                ax.legend(loc='upper right', fontsize=8, framealpha=0.9, edgecolor='none')
            
        for ax in set(axes):
            ax.spines['top'].set_visible(3.5)
            ax.spines['right'].set_visible(3.5)
            ax.spines['left'].set_linewidth(1.5)
            ax.spines['bottom'].set_linewidth(1.5)
            ax.grid(True, linestyle='--', alpha=0.2, color="#d3d3d3")

            apply_global_aesthetics(ax, min_xs, max_xs, min_ys, max_ys, is_stack_mode=is_stack)
            cursor = Cursor(ax, useblit=True, color='red', linewidth=1, linestyle='dotted')
            cursor.visible = self.var_click_mode.get() in ['peak', 'area', 'baseline', 'deconv']
            self.cursors.append(cursor)

        # NEW: self.ax was previously never assigned anywhere in this class,
        # which silently broke the "X: -- | Y: --" cursor readout (it checks
        # hasattr(self, 'ax'), which was always False). Fixed here, and this
        # also gives annotations a stable axis to attach to.
        # In stack mode, annotations attach only to the first (top) subplot --
        # per-subplot annotation tracking in stack mode is a possible future
        # enhancement, not yet supported.
        self.ax = axes[0] if axes else None

        if hasattr(self, 'annotation_mgr') and ann_snapshot:
            self.annotation_mgr.annotations = []
            self.annotation_mgr.selected_artist = None
            if self.ax is not None:
                self.annotation_mgr.load_serialized_data(ann_snapshot, self.ax)

        self.fig.tight_layout() 
        self.canvas.draw_idle()
        self.sync_peak_listbox()
    
    def on_click(self, event):
        if event.inaxes is None or self.var_click_mode.get() == 'none': 
            return
            
        mode = self.var_click_mode.get()
        x_click = event.xdata
        
        x_arr, y_arr = self.get_processed_data_for_stem(self.current_stem)
        fs = state.file_set[self.current_stem]
        
        idx = (np.abs(x_arr - x_click)).argmin()
        closest_x, closest_y = x_arr[idx], y_arr[idx]
        
        if mode == 'peak':
            fs.setdefault('labels', []).append((closest_x, closest_y, f"{closest_x:.1f}"))
            self.update_plot()

        elif mode == 'xrd_peak':
            result = self.calculate_xrd_peak(x_click, x_arr, y_arr)
            if result:
                px, py, fwhm, d = result
                fs.setdefault('xrd_peaks', []).append((px, py, fwhm, d))
                self.update_plot()
            
        elif mode == 'area':
            if getattr(self, 'area_start', None) is None:
                self.area_start = closest_x
                event.inaxes.axvline(closest_x, color='gray', linestyle='--', alpha=0.7)
                event.inaxes.text(closest_x, closest_y, " Start", color='gray', fontweight='bold')
                self.canvas.draw()
            else:
                area_end = closest_x
                x1, x2 = min(self.area_start, area_end), max(self.area_start, area_end)
                try:
                    mask = (x_arr >= x1) & (x_arr <= x2)
                    x_sel, y_sel = x_arr[mask], y_arr[mask]
                    if len(x_sel) > 1:
                        baseline = np.interp(x_sel, [x_sel[0], x_sel[-1]], [y_sel[0], y_sel[-1]])
                        true_peak_y = y_sel - baseline
                        area_val = abs(np.trapezoid(true_peak_y, x_sel))
                        fs.setdefault('areas', []).append((x1, x2, area_val))
                except Exception as e:
                    print(f"🚨 MATH ERROR: {e}")
                self.area_start = None 
                self.update_plot()
                
        elif mode == 'baseline':
            self.baseline_pts.append((closest_x, closest_y))
            event.inaxes.plot(closest_x, closest_y, 'go', markersize=6)
            if len(self.baseline_pts) > 1:
                pts = sorted(self.baseline_pts, key=lambda p: p[0])
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                event.inaxes.plot(xs, ys, 'g--', alpha=0.7)
            self.canvas.draw()
        
        elif mode == 'deconv':
            if getattr(self, 'deconv_start', None) is None:
                self.deconv_start = closest_x
                event.inaxes.axvline(closest_x, color='purple', linestyle='--', alpha=0.7)
                event.inaxes.text(closest_x, closest_y, " Fit Start", color='purple', fontweight='bold')
                self.canvas.draw()
            else:
                deconv_end = closest_x
                x1, x2 = min(self.deconv_start, deconv_end), max(self.deconv_start, deconv_end)
                self.deconv_start = None 
                self.perform_deconvolution(x1, x2, x_arr, y_arr)
    
    def perform_deconvolution(self, x1, x2, x_arr, y_arr):
        num_peaks = simpledialog.askinteger("Deconvolution", "How many sub-peaks do you expect in this region?", parent=self, minvalue=1, maxvalue=5)
        if not num_peaks:
            self.update_plot()
            return

        mask = (x_arr >= x1) & (x_arr <= x2)
        x_sel = x_arr[mask]
        y_sel = y_arr[mask]

        if len(x_sel) < 10:
            messagebox.showwarning("Error", "Not enough data points in this region to run a fit.")
            self.update_plot()
            return

        baseline = np.interp(x_sel, [x_sel[0], x_sel[-1]], [y_sel[0], y_sel[-1]])
        
        mid_idx = len(y_sel) // 2
        is_valley = y_sel[mid_idx] < baseline[mid_idx]
        
        if is_valley:
            y_fit = baseline - y_sel 
        else:
            y_fit = y_sel - baseline
            
        y_fit = np.clip(y_fit, 0, None) 

        def multi_gaussian(x, *params):
            y = np.zeros_like(x)
            for i in range(0, len(params), 3):
                A, mu, sigma = params[i], params[i+1], params[i+2]
                y += A * np.exp(-((x - mu)**2) / (2 * sigma**2))
            return y

        guess, bounds_lower, bounds_upper = [], [], []
        amp_guess = np.max(y_fit)
        width = x2 - x1
        spacing = width / (num_peaks + 1)
        
        for i in range(num_peaks):
            guess.extend([amp_guess, x1 + spacing * (i + 1), width / (num_peaks * 2)])
            bounds_lower.extend([0, x1, 0.01]) 
            bounds_upper.extend([amp_guess * 1.5, x2, width]) 

        try:
            popt, _ = curve_fit(multi_gaussian, x_sel, y_fit, p0=guess, bounds=(bounds_lower, bounds_upper))
            
            fs = state.file_set[self.current_stem]
            fs.setdefault('deconvs', []).append((x1, x2, baseline, popt, num_peaks, is_valley))
            print(f"✅ Deconvolution successful with {num_peaks} curves.")
            
        except Exception as e:
            messagebox.showerror("Fitting Error", f"Could not converge on a fit. Try a narrower region.\n\nError: {e}")
        
        self.var_click_mode.set('none') 
        self.update_plot()
    
    def export_deconv_data(self):
        fs = state.file_set.get(self.current_stem, {})
        deconvs = fs.get('deconvs', [])
        
        if not deconvs:
            messagebox.showwarning("No Data", "No deconvolution fits found for the current file.", parent=self)
            return
            
        folder = filedialog.askdirectory(title="Select Folder to Save Deconvolution Data", parent=self)
        if not folder: return
        
        import csv, os
        base_name = self.current_stem
        
        img_path = os.path.join(folder, f"{base_name}_Deconvolution_Plot.png")
        self.fig.savefig(img_path, dpi=300, bbox_inches='tight')
        
        for idx, (x1, x2, baseline, popt, num_peaks, is_valley) in enumerate(deconvs):
            csv_path = os.path.join(folder, f"{base_name}_Deconv_Region_{idx+1}.csv")
            
            x_fit = np.linspace(min(x1, x2), max(x1, x2), 500)
            
            with open(csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                headers = ["Wavenumber", "Total Fit"] + [f"Peak_{i+1}" for i in range(num_peaks)]
                writer.writerow(headers)
                
                for x_val in x_fit:
                    row = [x_val]
                    total_y = 0
                    peak_ys = []
                    
                    for i in range(num_peaks):
                        A, mu, sigma = popt[i*3], popt[i*3+1], popt[i*3+2]
                        y_peak = A * np.exp(-((x_val - mu)**2) / (2 * sigma**2)) 
                        peak_ys.append(y_peak)
                        total_y += y_peak
                        
                    if is_valley:
                        row.append(baseline - total_y)
                        for py in peak_ys: row.append(baseline - py)
                    else:
                        row.append(baseline + total_y)
                        for py in peak_ys: row.append(baseline + py)
                        
                    writer.writerow(row)
                    
        messagebox.showinfo("Success", f"Exported Plot Image and {len(deconvs)} CSV data file(s) to:\n{folder}", parent=self)

    def on_close(self):
        dialog = CloseDialog(self)
        self.wait_window(dialog) 
        
        if not dialog.choice:
            return 
            
        if "save" in dialog.choice:
            try:
                self.save_session_cmd() 
            except Exception:
                pass 
                
        if "exit" in dialog.choice:
            # Safe here: this window's process was spawned in isolation by
            # launcher.py via multiprocessing, so killing it doesn't touch the
            # dashboard. os._exit() sidesteps a known Tkinter teardown hang when
            # several Toplevels + matplotlib canvases are open, at the cost of
            # skipping atexit/cleanup handlers (harmless -- all file writes in
            # this app already use 'with open(...)', which flush on their own).
            import os
            os._exit(0) 
            
        elif "menu" in dialog.choice:
            # CHANGED: this used to do
            #   os.execl(sys.executable, sys.executable, *sys.argv)
            # which re-executes the *current* interpreter with the *current*
            # sys.argv. That is broken for this app's process model: ir.main()/
            # xrd.main() run inside a child process spawned by launcher.py via
            # multiprocessing.Process. On Windows (and frozen/PyInstaller builds
            # everywhere), that child's sys.argv holds multiprocessing's internal
            # bootstrap flags (e.g. "--multiprocessing-fork <handle>"), not the
            # original script path -- re-exec'ing with those stale handles
            # crashes or hangs instead of relaunching the setup screen.
            #
            # Fix: signal the request via shared state instead of touching the
            # process at all. main()'s loop (in ir.py / xrd.py) checks this flag
            # after each viewer closes and, if set, unwinds back to SetupGUI.
            state.restart_to_menu = True
            self.destroy()
    
    def calculate_xrd_peak(self, x_click, x_arr, y_arr):
        mask = (x_arr >= x_click - 1.0) & (x_arr <= x_click + 1.0)
        if not np.any(mask): return None
        
        x_window = x_arr[mask]
        y_window = y_arr[mask]
        
        max_idx = np.argmax(y_window)
        peak_x = x_window[max_idx]
        peak_y = y_window[max_idx]
        
        half_max = peak_y / 2.0
        
        left_mask = (x_window < peak_x)
        right_mask = (x_window > peak_x)
        
        try:
            left_x = np.interp(half_max, y_window[left_mask], x_window[left_mask])
            right_x = np.interp(half_max, y_window[right_mask][::-1], x_window[right_mask][::-1])
            fwhm = right_x - left_x
        except ValueError:
            fwhm = 0.0 
            
        if fwhm > 0:
            K = 0.9
            lam = 0.15406 
            
            theta_deg = peak_x / 2.0
            theta_rad = np.radians(theta_deg)
            fwhm_rad = np.radians(fwhm)
            
            grain_size_nm = (K * lam) / (fwhm_rad * np.cos(theta_rad))
        else:
            grain_size_nm = 0.0
            
        return (peak_x, peak_y, fwhm, grain_size_nm)
    
    def auto_find_xrd_peaks(self):
        x_data, y_data = self.get_processed_data_for_stem(self.current_stem)
        
        peaks, _ = find_peaks(y_data, 
                               height=float(self.var_xrd_min_height.get()),
                               prominence=float(self.var_prominence.get()))
        
        fs = state.file_set[self.current_stem]
        for p in peaks:
            result = self.calculate_xrd_peak(x_data[p], x_data, y_data)
            if result:
                px, py, fwhm, d = result
                fs.setdefault('xrd_peaks', []).append((px, py, fwhm, d))
                
        self.update_plot()
    
    def show_grain_size_chart(self):
        fs = state.file_set.get(self.current_stem, {})
        peaks = fs.get('xrd_peaks', [])
        
        valid_peaks = [p for p in peaks if p[3] > 0]
        
        if not valid_peaks:
            messagebox.showwarning("No Data", "Please select valid peaks to calculate grain size first!", parent=self)
            return
            
        valid_peaks.sort(key=lambda p: p[0])
        
        labels = [f"{p[0]:.1f}°" for p in valid_peaks]
        sizes = [p[3] for p in valid_peaks]
        
        avg_size = np.mean(sizes)
        std_dev = np.std(sizes) if len(sizes) > 1 else 0.0
        
        chart_win = tk.Toplevel(self)
        chart_win.title(f"Grain Size Analysis - {self.current_stem}")
        chart_win.geometry("1000x550") 
        
        def save_distribution_chart():
            filepath = filedialog.asksaveasfilename(
                title="Save Distribution Chart",
                initialfile=f"{self.current_stem}_grain_size_distribution.png",
                defaultextension=".png",
                filetypes=[("PNG Image", "*.png"), ("PDF Document", "*.pdf"), ("SVG", "*.svg")],
                parent=chart_win
            )
            if filepath:
                fig.savefig(filepath, dpi=300, bbox_inches='tight')
                messagebox.showinfo("Success", f"Chart saved successfully!\n{filepath}", parent=chart_win)

        btn_frame = ttk.Frame(chart_win)
        btn_frame.pack(side="bottom", fill="x", pady=10)
        ttk.Button(btn_frame, text="💾 Export This 2-Panel Chart as Image", command=save_distribution_chart).pack(ipady=5)

        fig = plt.Figure(figsize=(10, 4), dpi=100)
        
        ax1 = fig.add_subplot(121)
        ax1.bar(labels, sizes, color='#89b4fa', edgecolor='black', zorder=3)
        ax1.axhline(avg_size, color='red', linestyle='--', linewidth=2, zorder=4, label=f"Average: {avg_size:.1f} nm")
        if std_dev > 0:
            ax1.fill_between([-0.5, len(labels)-0.5], avg_size - std_dev, avg_size + std_dev, color='red', alpha=0.1, zorder=1, label=f"±1σ ({std_dev:.1f} nm)")
            
        ax1.set_ylabel("Crystallite Size (nm)", fontweight='bold')
        ax1.set_xlabel("Peak Position (2θ)", fontweight='bold')
        ax1.set_title("Size per Diffraction Peak", fontweight='bold')
        ax1.grid(axis='y', linestyle='--', alpha=0.7, zorder=0)
        ax1.legend()
        
        ax2 = fig.add_subplot(122)
        if len(sizes) > 1 and std_dev > 0:
            bins = max(3, len(sizes))
            ax2.hist(sizes, bins=bins, density=True, color='#a6adc8', edgecolor='black', alpha=0.6, label='Data Histogram')
            
            x_curve = np.linspace(min(sizes) - 3*std_dev, max(sizes) + 3*std_dev, 100)
            y_curve = (1 / (std_dev * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_curve - avg_size) / std_dev)**2)
            
            ax2.plot(x_curve, y_curve, color='#1e1e2e', linewidth=2.5, label='Gaussian Fit')
            ax2.axvline(avg_size, color='red', linestyle='--', linewidth=2, label=f"Mean: {avg_size:.1f} nm")
        else:
            ax2.text(0.5, 0.5, "Need at least 2 peaks\nfor a Gaussian fit.", ha='center', va='center', fontsize=12, color='gray')
            ax2.set_xlim(0, 1)
            ax2.set_ylim(0, 1)

        ax2.set_xlabel("Crystallite Size (nm)", fontweight='bold')
        ax2.set_ylabel("Probability Density", fontweight='bold')
        ax2.set_title("Gaussian Size Distribution", fontweight='bold')
        ax2.legend(loc='upper right')
        
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=chart_win)
        canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
        canvas.draw()
