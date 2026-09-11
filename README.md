# SpectraSuite 3.1.0

SpectraSuite is a free desktop application for scientific data plotting and
analysis. It includes working FT-IR, XRD, UV-Vis, Raman, General 2D, and General
3D workspaces. Multi-X/Multi-Y, Fluid Dynamics, and XPS remain visible in the
last launcher row as disabled previews for a future release.

The application is designed to work offline. Scientific data stays on the
computer unless the user explicitly saves or exports it.

## Spectroscopy workspaces

FT-IR, XRD, UV-Vis, and Raman share a consistent plotting workspace with:

- Individual, overlay, vertical-stack, and grid layouts
- Multi-file and multi-column CSV/Excel dataset discovery
- Noise-adaptive automatic peak detection and manual peak selection
- Smoothing, normalization, derivatives, reference subtraction, and baselines
- Editable legends, line styles, axes, annotations, and plot order
- PNG, JPEG, TIFF, SVG, and PDF graph export
- Processed-data and analysis-report export
- Saved JSON sessions
- Standard File, Edit, History, View, Analysis, and Help menus
- Compact analysis-mode icons with hover descriptions

Version 3.1 adds a collapsible spreadsheet below every spectroscopy graph.
Columns are visibly assigned as `[X]`, `[Y]`, or `[Ignore]`. Users can edit
cells, copy/paste from a spreadsheet, insert or delete rows and columns, rename
columns, change column roles, and rebuild the plot from the edited table.
Shared-X/multiple-Y data can be plotted as an overlay, stack, or grid.

### Calculated columns

The calculated-column tool uses a restricted formula language and never runs
arbitrary Python. Columns are referenced as `C1`, `C2`, and so on. Examples:

```text
C2 + C3
C2 - C3
C2 * 5
normalize(C2)
baseline(C2)
smooth(C2, 11)
```

Supported functions include `abs`, `sqrt`, `log`, `log10`, `exp`, `clip`,
`normalize`, `zscore`, `smooth`, and `baseline`. UV-Vis formulas also include
`transmittance(C2)`, `absorbance(C2)`, and `km(C2)`. `km` expects reflectance as
a fraction; use `km(C2 / 100)` when the source column is percent reflectance.

## UV-Vis calculations

The main UV-Vis workspace provides explicit, reversible display transforms:

- Absorbance → percent transmittance: `%T = 100 × 10⁻ᴬ`
- Percent transmittance → absorbance: `A = −log₁₀(%T / 100)`

Kubelka-Munk is presented separately because it is a diffuse-reflectance
transformation, not an absorbance/transmittance conversion:

- Reflectance fraction or percent → `F(R) = (1 − R)² / (2R)`

Every transform starts from the imported raw values, so returning to
**Original / as imported** restores the original signal.

The advanced UV-Vis dialog supports wavelength/energy conversion, four Tauc
transition models, explicit fit ranges, band-gap intercepts and uncertainty,
Urbach-energy fitting, optional pre-edge baseline correction, and Kubelka-Munk
analysis for reflectance. Fit ranges and R² values are shown because these
models depend on the material and measurement assumptions and require
researcher review.

## General plotting

The General 2D Plotter imports or creates editable tables, maps one X/category
column to multiple Y columns, and produces line, scatter, grouped bar, area,
step, pie, histogram, and box plots. The General 3D Plotter supports scattered
XYZ data, structured surfaces, wireframes, contours, vector fields, multiple
layers, and ASCII Tecplot POINT (`.plt`) grids. Both workspaces also support the
restricted calculated-column formulas described above.

## Updates and privacy

SpectraSuite checks the public GitHub Releases API at most once per 24 hours and
shows a message when a newer version is available. The check is asynchronous,
fails quietly without internet, and can be disabled from **Help → Automatically
check for updates**. It does not send an installation identifier or scientific
data. See [PRIVACY.md](PRIVACY.md).

## Run from source

Use Python 3.11 or 3.12 in a virtual environment:

```bash
python -m pip install -r requirements.txt
python launcher.py
```

Update an existing Git clone with:

```bash
git pull
python -m pip install -r requirements.txt
python launcher.py
```

The GitHub Actions workflow compiles and lints the project, runs numerical and
off-screen PySide6 tests, validates image/PDF export, builds the PyInstaller
application, and starts the packaged result on Windows, macOS, and Ubuntu with
Python 3.11 and 3.12.

## License

SpectraSuite 3.1.0 is distributed under the [MIT License](LICENSE). A signed
installer has not yet been published; the source workflow above remains the
recommended testing path.
