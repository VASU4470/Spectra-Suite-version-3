import matplotlib.colors as mcolors

# Ordered from most specific/narrow bands to broadest overlapping bands 
# so the auto-assigner doesn't mask specific peaks with broad ones!
IR_TABLE = [
    # --- TRIPLE BONDS & CUMULENES ---
    (2240, 2260, 'Nitriles (C≡N) stretch'),
    (2100, 2250, 'Alkyne (C≡C) stretch'),
    
    # --- SULFUR & SPECIFIC SHARP STRETCHES ---
    (2500, 2600, 'Thiols/Mercaptans (S–H) stretch'),
    
    # --- CARBONYLS (C=O) ---
    (1750, 1820, 'Anhydride (C=O) stretch'),
    (1730, 1750, 'Ester (C=O) stretch'),
    (1720, 1740, 'Aldehyde (C=O) stretch'),
    (1705, 1725, 'Ketone (C=O) stretch'),
    (1700, 1725, 'Carboxylic acid (C=O) stretch'),
    (1630, 1680, 'Amide (C=O) stretch'),

    # --- DOUBLE BONDS (C=C, C=N) & N-H BENDING ---
    (1640, 1690, 'Imines/oximes (C=N) stretch'),
    (1600, 1680, 'Alkene (C=C) stretch'),
    (1550, 1640, 'Amines/amides (N–H) bend'),
    (1450, 1600, 'Aromatic (C=C) stretch'),
    (1540, 1560, 'Nitro (R–NO2) asym stretch'),

    # --- C-H STRETCHES ---
    (3050, 3150, 'Aromatic (C–H) stretch'),
    (3000, 3100, 'Alkene (C–H) stretch'),
    (2850, 3000, 'Alkane (C–H) stretch'),
    (2700, 2900, 'Aldehyde (C–H) stretch'),
    (3250, 3350, 'Alkyne (C–H) stretch'),

    # --- O-H and N-H STRETCHES ---
    (3600, 3650, 'Free Alcohols/phenols (O–H) stretch'),
    (3200, 3400, 'H-bonded Alcohols/phenols (O–H) stretch'),
    (3100, 3500, 'Amines/amides (N–H) stretch'),
    (2400, 3400, 'Carboxylic acids (O–H) stretch'), # Broadest stretch, placed last

    # --- SINGLE BONDS (C-O, C-N, C-X) ---
    (1000, 1400, 'Fluoride (C–F) stretch'),
    (1000, 1350, 'Amines (C–N) stretch'),
    (1000, 1300, 'C–O stretch (Alcohols/esters/ethers)'),
    (1340, 1360, 'Nitro (R–NO2) sym stretch'),
    
    # --- C-H BENDING ---
    (1455, 1475, 'Methylene (–CH2–) bend'),
    (1440, 1460, 'Methyl (–CH3) asym bend'),
    (1365, 1385, 'Methyl (–CH3) sym bend'),
    (650, 1000, 'Alkene (C–H) out-of-plane bend'),
    (600, 900, 'Aromatic (C–H) out-of-plane bend'),

    # --- HEAVY HALIDES (< 800) ---
    (540, 785, 'Chloride (C–Cl) stretch'),
    (400, 650, 'Bromide/Iodide (C–Br, C–I) stretch'),

    # --- INORGANIC IONS ---
    (3030, 3300, 'Ammonium ion'),
    (1390, 1430, 'Ammonium ion'),
    (1410, 1490, 'Carbonate ion'),
    (860, 880, 'Carbonate ion'),
    (1080, 1130, 'Sulfate ion'),
    (610, 680, 'Sulfate ion'),
    (1350, 1380, 'Nitrate ion'),
    (815, 840, 'Nitrate ion'),
    (1000, 1100, 'Phosphate ion'),
    (900, 1100, 'Silicate ion')
]

class SessionState:
    """Manages the global and file-specific state for the current session."""
    def __init__(self):
        self.settings = {'is_all': True, 'files': [], 'mode': 'individual', 'smooth': 15}
        self.all_data = []
        self.technique = 'FTIR'  # Defaults to FTIR, but xrd.py will change this!
        self.master_folder = None
        self.file_set = {}
        self.current_session_file = None # NEW: Tracks the active JSON file
        self.restart_to_menu = False # NEW: Signals main() to loop back to SetupGUI instead of re-exec'ing the process
        self.general_format = None # NEW: {'delimiter','skip_rows','x_col','y_col'} chosen for the GENERAL plotter, reused when adding more files mid-session
        self.mode_switched_mid_session = False # NEW: set when 'Add File(s)' switches Individual -> Overlay/Stack inside an open PlotViewer; tells main()'s per-file loop to stop (state.all_data now holds files that loop never expected, and they're already shown together in the window that's about to close)
        
        self.global_set = {
            'xlim': None, 'ylim': None,
            'title': '',
            'xlabel': 'Wavenumber (cm⁻¹)', 'ylabel': 'Transmittance (%)',
            'xstep': '', 'ystep': '',
            'grid': False, 'bg': '#ffffff', 'title_color': 'black', 
            'show_minor': False, 'show_tick_lbls': True,
            'vlines': [], 
            'borders': {'top': False, 'bottom': True, 'left': True, 'right': False},
            'annotations': [] # NEW: Holds shapes for Overlay/Stack modes
        }

    def init_file_settings(self):
        """Initializes default plotting parameters for each loaded file."""
        colors = list(mcolors.TABLEAU_COLORS.values())
        for i, (stem, _, _) in enumerate(self.all_data):
            default_color = colors[i % len(colors)] if self.settings['mode'] == 'overlay' else 'black'
            self.file_set[stem] = {
                'custom_name': stem,   # <--- ADD THIS LINE!
                'color': default_color, 
                'offset': 0.0, 
                'smooth': self.settings['smooth'], 
                'labels': [], 
                'areas': [], 
                'do_baseline': False, 
                'als_lam': 100000, 
                'als_p': 0.05
            }
state = SessionState()
