# Changelog

## 3.2.0 — Release candidate

- Added Windows setup, Apple Silicon/Intel macOS disk images, and an
  Ubuntu/Debian package build, with installed-application startup checks and
  SHA-256 manifests. Candidates remain unsigned until signing is configured.

- Replaced the process-launching dashboard with one persistent application
  window containing Home, inline Import, and closable analysis documents.
- Added automatic opening for a single discovered spectrum and kept
  multi-column dataset selection inside the Import document.
- Embedded FT-IR, XRD, UV-Vis, Raman, General 2D, and General 3D workspaces in
  the same application window.
- Preserved independent state when switching between open spectroscopy tabs.
- Moved Results and History from the bottom drawer into a full-height right
  sidebar with vertically arranged Inspector, Results, and History tabs.
- Kept the editable Data Table beside Plot as a full-height centre workspace.
- Saved the technique identifier in new session files while retaining fallback
  support for older session files.
- Reworked Import into a compact two-column workspace with a small drag/drop
  card and vertical file list on the left, settings and dataset selection on
  the right, and an always-visible analysis button in a fixed footer.
- Replaced cross-menu QMenu reuse with stable action groups, preventing deleted
  native-menu objects when opening or closing analyses on macOS.
- Added an Account menu showing the current offline Community-edition status
  and reserving a clear location for optional future sign-in and licensing.
- Connected an optional hosted SpectraSuite email-update form from the
  Home page and Account menu without storing mailing credentials or user data
  in the desktop application.
- Replaced the interrupting new-release prompt in the project shell with a
  dismissible in-window banner and added one privacy/update-preferences dialog
  for automatic checks, manual checks, email signup, and the privacy policy.

## 3.1.0 — 2026-09-11

- Added reversible UV-Vis absorbance/percent-transmittance display transforms.
- Added separate Kubelka-Munk transforms for fraction or percent reflectance.
- Added a collapsible editable X/Y data table to spectroscopy workspaces.
- Added row/column insert, delete, rename, X/Y/Ignore role assignment, and
  plot rebuilding from edited data.
- Added safe calculated columns with arithmetic, normalization, baseline,
  smoothing, optical-conversion, and approved mathematical functions.
- Added calculated columns to the General 2D and General 3D plotters.
- Replaced the spectroscopy analysis dropdown with compact horizontal icons
  and hover descriptions.
- Reduced plot-reordering controls to compact arrow buttons.
- Added standard desktop menus for files, editing, history, views, analysis,
  updates, and application information.
- Expanded the editable legend list to prevent compressed names.
- Added a non-blocking, offline-safe GitHub release notification with a user
  setting to disable automatic checks.
