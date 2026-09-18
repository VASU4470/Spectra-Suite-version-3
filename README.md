# SpectraSuite 3.2.0

SpectraSuite is a free desktop application for scientific data plotting and
analysis. It includes working FT-IR, XRD, UV-Vis, Raman, General 2D, and General
3D workspaces. This review branch also includes preview XPS, LIBS, and Fluid
Dynamics workspaces. Multi-X/Multi-Y remains disabled. The published 3.2.0
release candidate does not contain these unreleased changes.

The application is designed to work offline. Scientific data stays on the
computer unless the user explicitly saves or exports it.

## Export and new-workspace preview (unreleased)

**Save figure** is available in the spectroscopy File menu and Export inspector,
and through **Export graph** in the general and fluid plotters. Choose PDF/SVG
for vector output or PNG/JPEG/TIFF for raster output. Set width/height in mm,
DPI, transparency, and optional tight cropping. Cropping off preserves the
specified canvas size; cropping on changes the final dimensions. The live
figure size is restored after export. Failed rendering preserves existing files.

**Export data / results bundle** retains the existing current-spectrum CSV,
peak/area text report and optional current-figure export. Its graph can contain
multiple plotted series; its data/report are explicitly for the active spectrum.
**Save workspace session** saves editable spectroscopy data and settings as JSON.
Batch exports, reusable journal presets, live export preview and multi-page PDF
reports are suggested follow-ups, not implemented features.

- **XPS preview:** import text/CSV/Excel binding-energy spectra in eV; decreasing
  binding-energy axis; manual/automatic upward peak selection; overlays, areas,
  generic baseline tools, annotations, figure export and session reopening.
  Smoothing starts off. No VAMAS parser, charge referencing, Shirley/Tougaard
  background, constrained chemical-state fitting or atomic quantification yet.
- **LIBS preview:** wavelength in nm versus intensity; raw signal by default;
  peak selection (three-decimal wavelength labels), manual baseline, reference
  subtraction, overlays/stacking, areas, export and session reopening. It does
  not infer elements, concentrations, electron density or plasma temperature.
  A future line-reference workflow should retain wavelength medium (air/vacuum),
  tolerance, ion stage and data provenance; NIST ASD is a reference candidate:
  https://physics.nist.gov/PhysRefData/ASD/lines_form.html
- **Fluid preview:** opens in the same shell. Supports a single ASCII Tecplot
  POINT zone with X/Y as the first two columns and K=1. Cartesian coordinates
  reconstruct either point ordering; ordered curvilinear data uses I-fast
  ordering. Shifted-grid subtraction requires rectilinear grids. Binary,
  BLOCK-packed, multi-zone and volume files are not supported. Import a 2D
  slice for volume results. Plot rendering is tested with synthetic fields;
  real instrument/solver examples are still needed.
- **Raman:** intensity ratios require two distinct detected bands within a
  configurable tolerance (default 10 cm⁻¹). The reported local FWHM area is
  explicitly not the full integrated band area. Duplicate shift coordinates
  are rejected rather than measured ambiguously.

Frozen builds now export PDF, SVG, PNG, JPEG and TIFF during `--smoke-test`,
including after installation, to catch missing dynamically loaded renderers.

## Single-window workflow

The development interface uses one persistent project window. Home, file
import, plots, editable tables, and analysis documents no longer open as a
sequence of separate application windows. A single detected spectrum opens
immediately. When a file contains several sheets or Y columns, selection stays
inside an Import tab before the chosen series opens.

Import uses a compact left column for drag/drop and the selected-file list,
with plot preparation and dataset selection on the right. A fixed footer keeps
the **Open analysis** action visible even on shorter laptop screens.

Open analyses remain available as document tabs. Closing an analysis returns
to another open document or to Home instead of closing the application. The
spectroscopy workspace uses a left project/data navigator, a full-height centre
Plot/Data Table area, and one collapsible right sidebar containing Inspector,
Results, and History tabs.

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
- Standard File, Edit, History, View, Analysis, Account, and Help menus
- Compact analysis-mode icons with hover descriptions

Version 3.1 added an editable spectroscopy spreadsheet; the development
interface now presents it as a full-height **Data Table** tab beside **Plot**.
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
shows a non-blocking banner inside the project window when a newer version is
available. The check is asynchronous, fails quietly without internet, and can
be disabled from **Help → Automatically check for updates** or the unified
**Account → Privacy & update preferences** dialog. It does not send an
installation identifier or scientific data. A temporary offline failure is
retried quietly while the application remains open. See [PRIVACY.md](PRIVACY.md).

The **Account** menu reports **Community edition · Offline-ready** and offers
an optional **Get update emails** link. That command opens the public
SpectraSuite Brevo subscription form in the system browser; the application
does not receive or store the submitted address. No account or license key is
required and no installation identifier is collected. The menu also provides
a privacy/preferences dialog and a stable interface location for optional
sign-in or signed offline licenses if a commercial edition is introduced later.

## Installer candidates

Version 3.2.0 is feature-frozen and being prepared for distribution. Native
Windows setup, Apple Silicon/Intel Mac disk images, and Ubuntu/Debian packages
are built by the **Installer candidates** workflow. Candidates bundle Python
and application dependencies, include checksums, and are startup-tested after
installation. Windows/Mac candidates are not publisher-signed or notarized.
See [release preparation](packaging/RELEASE.md) for download formats and remaining
release gates. A finished public installer release has not yet been published.

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

SpectraSuite 3.2.0 is distributed under the [MIT License](LICENSE). A signed
installer has not yet been published; the source workflow above remains the
recommended testing path.
