# SpectraSuite 3.3.0 — test release

This release includes the export center, image digitizer and plotting updates.
The application title displays **SpectraSuite 3.3.0**. The immutable release tag
is **v3.3.0-rc.2**.

Download an installer from Assets; no Python, Git or GitHub sign-in is required.

| Computer | Installer |
| --- | --- |
| Apple Silicon Mac (M1/M2/M3 and newer) | SpectraSuite-3.3.0-macos-arm64-unsigned.dmg |
| Intel Mac | SpectraSuite-3.3.0-macos-x86_64-unsigned.dmg |
| Windows x64 | SpectraSuite-3.3.0-windows-x64-unsigned-setup.exe |
| Ubuntu/Debian x64 | SpectraSuite-3.3.0-linux-amd64.deb |

Close the old app before installing. On Mac, open the DMG and drag SpectraSuite
to Applications, replacing the earlier copy, then launch it from Applications.
On Windows, run the setup EXE. On Linux, use the system package installer.
Existing saved data and sessions remain in their original locations.

Windows/Mac installers are unsigned and Mac builds are not notarized; OS
security checks may warn or block launch. This is a public test release.

Changes in this second test build:

- Update checks can include test releases, compare release-candidate numbers,
  show progress/results in preferences, and recheck after a build/channel change.
- Compact home cards and document tabs; compact table tools with an overflow menu.
- Resizable panels with visible dividers, collapse icons and restored widths.
- Visible 2D/3D file-drop instructions; regression-tested file drops onto both
  tables and plots inside the main application window.

Earlier 3.2.0 and 3.3.0-rc.1 installations check only stable releases, so install
this build manually once. In Account → Privacy and update preferences, enable
“Include test releases” to receive subsequent test-build notices. Test builds
include this by default. Notifications open the download page; the app does
not replace itself automatically.

Included:

- Fixed PDF export, publication-size/custom presets and a live figure preview.
- Batch export of selected datasets and multi-page PDF reports with figures,
  saved results and processing settings; complete report preview before saving.
- Preserved XRD size summaries and fitted-curve CSVs in batch exports.
- File/folder drops across spectroscopy, General 2D/3D and fluid workspaces.
- Image to data from Home and plotters: open, paste or drop an image, calibrate
  axes, and trace manually or by color. Export CSV or compare extracted curves.
- LIBS ZIP selection and raw previews; XPS/LIBS plotting previews; corrected
  fluid Cartesian grids and Raman ratio band selection.
- Fixed Windows PDF-preview file locking and added a VS Code F5 configuration.

Image-derived data is approximate and requires user calibration. Specialized
XPS quantification and LIBS element identification are not included.
Multi-X/Multi-Y remains Coming soon. Advanced UV-Vis/Raman analysis dialogs
retain separate CSV exports. The app works offline without an account.

For VS Code, update the `main` branch, install `requirements.txt` in your Python
environment, select its interpreter, then press F5 and choose
**SpectraSuite — desktop application**. This launches `launcher.py`.
