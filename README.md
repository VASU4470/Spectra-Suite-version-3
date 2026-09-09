**SpectraSuite Version 3**

> **Status:** Version 3 includes FT-IR, XRD, UV-Vis, Raman, General 2D, and
> General 3D workspaces. Multi-X/Multi-Y, Fluid Dynamics, and XPS remain visible
> in the final launcher row as disabled “Coming soon” previews for the next version.

Version 3 retains the Version 2 analysis workflow, including file management,
individual/overlay/stacked plots, processing and reference subtraction,
session save/load, annotations, FT-IR peak/area/deconvolution tools, XRD FWHM
and crystallite-size analysis, configurable data/report/graph export, and the
end-of-workflow save prompt.

The UV-Vis workspace adds absorbance/transmittance/reflectance conversion,
wavelength-energy conversion, peak finding, areas, derivatives, baselines,
reference subtraction, Gaussian peak deconvolution, Tauc plots for four
transition models, fitted band-gap estimates, Urbach-energy fitting, and
Kubelka-Munk analysis for diffuse-reflectance data. Tauc and Urbach results are
reported with their selected fit ranges and R² values because they depend on
material assumptions and should be reviewed by the researcher.

The Raman workspace provides fluorescence/background correction through the
shared ALS baseline, smoothing, derivatives, reference subtraction, upward
band detection, Gaussian deconvolution, FWHM and local-area measurements, and
user-selected intensity ratios. It deliberately does not infer a material or
apply material-specific crystallite-size equations without the required model.

The redesigned General 2D Plotter opens as an editable spreadsheet and live
graph workspace. It imports complete CSV, TSV, delimited-text, and Excel
tables; supports manual typing and Excel-style copy/paste; allows rows and
columns to be added, removed, renamed, and edited; maps one X/category column
to one or more Y columns; and switches between line, scatter, grouped bar,
area, step, pie, histogram, and box plots. Series colors, lines, markers,
widths, titles, axis labels, legends, grids, and value labels are editable.
Edited tables, reusable JSON projects, and PNG/PDF/SVG figures can be saved.

The in-development Multi-X/Multi-Y Plotter maps a separate X and Y column for every series,
with bottom/top X axes and left/right Y axes in one figure. The General 3D
Plotter accepts editable or imported XYZ data and renders scatter,
triangulated or structured surfaces, wireframes, contours, projected contours,
and vector fields. The in-development Fluid Dynamics Plotter reads structured ASCII Tecplot
POINT data and provides mesh, filled-contour, line-contour, heatmap, 3D
surface, wireframe, coordinate-profile, field-difference, and grid-comparison
views. The supplied 151 x 151 CFD examples were used to validate its reader.

The plotting usability pass adds visible technique icons and titles, resizable
and hideable side panels, compact Matplotlib toolbars below the graph, and
cross-platform Ctrl/Cmd undo/redo plus Delete/Backspace handling. Annotation
tools include undo, redo, selected-object deletion, and clear-all; the General
2D Plotter now includes the same basic annotation workflow. General Plotter
supports one X/category column with multiple selected Y columns, while the
dedicated Multi-X/Multi-Y workspace handles independent column pairs and axes.
PNG taskbar variants accompany the SVG launcher icons for consistent Windows,
macOS, and Linux window identity.

Spectroscopy imports now discover multiple datasets in one file. Repeated
X/Y column pairs, a shared X column with several Y columns, and every worksheet
in an Excel workbook are listed before plotting. Users can plot selected data
or all discovered data as individual windows, an overlay, a vertical stack, or
a grid. Grid order can be rearranged up/down/left/right from the viewer.

## Test from source

Use Python 3.11 or 3.12 in a virtual environment:

```bash
python -m pip install -r requirements.txt
python launcher.py
```

The GitHub Actions workflow also compiles, lints, opens the Qt workspaces in an
off-screen display, runs the numerical and export regression tests, builds the
application with PyInstaller, and executes the packaged startup check on
Windows, macOS, and Ubuntu.

Version 3 is still in pre-release testing. A signed installer has not yet been
published; use the source workflow above until a verified release is available.
