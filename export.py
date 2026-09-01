import os
import numpy as np
import pandas as pd
from tkinter import messagebox
from config import state
from processing import process_spectrum, assign_peak_group

def export_on_demand(stems, out_dir, options, fig, root_window):
    """Triggered by the GUI Export button. Saves only what the user requested."""
    os.makedirs(out_dir, exist_ok=True)
    
    # 1. EXPORT PLOT IMAGE
    if options.get('img') and fig:
        # Save the current visible matplotlib figure
        mode = state.settings['mode']
        img_name = "Overlay_Plot.png" if mode != 'individual' else f"{stems[0]}_Plot.png"
        fig.savefig(os.path.join(out_dir, img_name), dpi=300, bbox_inches='tight')

    # Loop through the active spectra to save data/tables
    for stem in stems:
        fs = state.file_set[stem]
        safe_name = fs['custom_name'].replace(' ', '_').replace('/', '-')
        x_proc, y_proc = process_spectrum(*next((d[1], d[2]) for d in state.all_data if d[0] == stem), stem)
        
        # 2. EXPORT RAW PROCESSED DATA
        if options.get('data'):
            df_data = pd.DataFrame({'Wavenumber': x_proc, 'Processed Transmittance': y_proc})
            df_data.to_csv(os.path.join(out_dir, f"{safe_name}_Processed_Data.csv"), index=False)

        # 3. EXPORT EXCEL TABLES (Peaks, Areas, & Deconvolutions)
        if options.get('peaks') or options.get('areas') or options.get('deconv'):
            df_peaks = None
            df_areas = None
            df_deconv = None
            
            # --- PEAKS LOGIC ---
            if options.get('peaks') and fs['labels']:
                peak_x = np.array(fs['labels'])
                peak_y = [y_proc[np.argmin(np.abs(x_proc - px))] for px in peak_x]
                assignments = [assign_peak_group(px) for px in peak_x]
                df_peaks = pd.DataFrame({
                    'Wavenumber': np.round(peak_x, 1), 
                    'Transmittance': np.round(peak_y, 1), 
                    'Group': assignments
                }).sort_values(by='Wavenumber', ascending=False)
                
            # --- AREAS LOGIC ---
            if options.get('areas') and fs.get('areas'):
                area_data = []
                for (x_start, x_end, area_val) in fs['areas']:
                    mid_x = np.mean([x_start, x_end])
                    area_data.append({
                        'Start Wave': np.round(x_start, 1),
                        'End Wave': np.round(x_end, 1),
                        'Midpoint': np.round(mid_x, 1),
                        'Area': np.round(area_val, 3),
                        'Group': assign_peak_group(mid_x)
                    })
                df_areas = pd.DataFrame(area_data).sort_values(by='Midpoint', ascending=False)

            # --- DECONVOLUTION LOGIC (The New Part) ---
            if options.get('deconv') and fs.get('deconvs'):
                deconv_data = []
                # (x1, x2, base, popt, n, is_v) comes from your gui.py fitting logic
                for (x1, x2, base, popt, n, is_v) in fs['deconvs']:
                    for i in range(n):
                        deconv_data.append({
                            'Region': f"{x1}-{x2}",
                            'Peak_Num': i+1,
                            'Height': np.round(popt[i*3], 4),
                            'Center': np.round(popt[i*3+1], 2),
                            'Width': np.round(popt[i*3+2], 4)
                        })
                df_deconv = pd.DataFrame(deconv_data)

            # --- EXCEL WRITER LOGIC ---
            # This is where we add the third sheet!
            if df_peaks is not None or df_areas is not None or df_deconv is not None:
                excel_path = os.path.join(out_dir, f"{safe_name}_Results.xlsx")
                try:
                    with pd.ExcelWriter(excel_path) as writer:
                        if df_peaks is not None: 
                            df_peaks.to_excel(writer, sheet_name='Peaks', index=False)
                        if df_areas is not None: 
                            df_areas.to_excel(writer, sheet_name='Areas', index=False)
                        if df_deconv is not None: 
                            df_deconv.to_excel(writer, sheet_name='Deconvolution', index=False)
                except Exception as e:
                    messagebox.showerror("Export Error", f"Failed to save Excel file. Is it currently open?\n{e}", parent=root_window)             

    messagebox.showinfo("Export Complete", f"✅ Successfully exported selected files to:\n\n{out_dir}", parent=root_window)
