# SpectraSuite UI/UX Architecture v2

## Purpose

Define the presentation architecture for a more scalable scientific desktop workspace without changing SpectraSuite's scientific calculations or established data compatibility.

## 1. Application shell

Keep the persistent single-window PySide6 application model.

The shell owns:

- application title and global menu/ribbon;
- Project Explorer visibility;
- central document workspace;
- status bar;
- document lifecycle;
- active-document context;
- global command routing.

The shell must not contain technique-specific scientific algorithms.

## 2. Ribbon / command system

Primary top-level tabs are expected to include:

- File
- Home
- Data
- Plot
- Process
- Analyze
- Annotate
- View
- Export
- Help

Technique-specific contextual groups/tabs may appear for FT-IR, XRD, UV-Vis, Raman, XPS, LIBS, and other accepted modules.

The active document controls command availability. A data-table document should expose data/table commands; a graph document should expose graph/annotation commands; technique context adds relevant scientific analysis commands.

Grouped commands may use split buttons/dropdowns where a family of related operations exists.

The ribbon is a command surface, not a permanent parameter editor.

## 3. Project Explorer

A narrow collapsible left-side Project Explorer replaces the current broad "project/data control" role.

The tree represents scientific objects, for example:

- Dataset
  - Raw data
  - Derived data
  - Plot
  - Peak analysis
  - Fit/deconvolution result
- Comparison plot
- Report/result table

The Explorer is for navigation, organization, visibility, naming, and selection. It should not become a second Inspector.

## 4. Central document workspace

The center becomes the dominant scientific workspace.

First-class document types should include at minimum:

- Data table
- Plot
- Result table/report
- Analysis result view

Documents must be independently openable and able to:

- coexist;
- tile;
- maximize;
- restore;
- switch focus;
- close without destroying source data.

The current Plot/Data Table mutually exclusive tab model is not the target for v2.

## 5. Data–plot relationship

A graph is a view of one or more scientific data objects, not a replacement for the worksheet/data table.

Editing or processing rules must preserve existing scientific behavior and session compatibility.

Where practical, processing should produce explicit derived data objects rather than silently overwriting raw source data.

Example:

- Sample A / Raw
- Sample A / Baseline corrected
- Sample A / Smoothed
- Sample A / FT-IR plot
- Sample A / Peak results

## 6. Property dialogs

There is no permanent right Inspector.

Detailed configuration is opened explicitly from:

- double-click;
- context menu;
- ribbon Properties command;
- keyboard shortcut where appropriate.

Shared property dialogs should include:

### Axis Properties
Possible sections:
- Scale
- Appearance
- Tick labels
- Grid
- Breaks (only if supported)

### Plot Properties
Hierarchical object selector:
- Plot/page
- Layer/axes
- Series/dataset
- Annotation
- Legend

Relevant controls change with the selected object.

### Annotation / Legend properties
Can be separate lightweight dialogs or pages routed through shared plot properties depending on implementation feasibility.

Dialogs should support Apply / Cancel / OK and should not alter scientific defaults implicitly.

## 7. Scientific analysis dialog framework

Scientific operations should share a common interaction structure:

1. Input
2. Parameters
3. Output
4. Recalculation / provenance where applicable

Technique-specific controls plug into this framework.

Examples include:
- baseline correction;
- smoothing;
- peak finding;
- area calculation;
- deconvolution/fitting;
- XRD FWHM / Scherrer;
- UV-Vis Tauc / Urbach;
- Raman band analysis.

Existing equations, defaults, parameter ranges, and behavior remain authoritative unless a separate scientific-change task explicitly approves changes.

## 8. Results and history

Results should no longer require a permanent right sidebar.

Preferred surfaces:
- result documents;
- derived tables;
- plot annotations where appropriate;
- status messages;
- explicit History/Provenance document or dialog.

Undo/redo and existing internal history mechanisms should remain functional during migration.

## 9. Status bar

Use a compact bottom status bar for immediate context, such as:

- active technique;
- active dataset/document;
- cursor X/Y;
- point count;
- zoom/view status;
- selected peak/value;
- transient operation status.

The status bar must remain compact and should not become a result panel.

## 10. Shared-component principle

The v2 UI must be shared infrastructure.

Preferred conceptual modules:

- `RibbonController`
- `ProjectExplorer`
- `ScientificWorkspace`
- `DocumentManager`
- `DataTableDocument`
- `PlotDocument`
- `ResultsDocument`
- `AxisPropertiesDialog`
- `PlotPropertiesDialog`
- `AnalysisDialogBase`
- command registry/context router

Names are provisional; current source architecture should determine final class/module boundaries.

FT-IR, XRD, UV-Vis, Raman, etc. should register commands and document/result types rather than duplicate the shell.

## 11. Compatibility constraints

The redesign must not silently change:

- baseline algorithms or defaults;
- smoothing algorithms or defaults;
- fitting/deconvolution equations or defaults;
- peak detection behavior;
- XRD axis/scientific conventions;
- UV-Vis transformations or fit assumptions;
- saved-session compatibility;
- import/export formats;
- updater/release behavior;
- scientific plot colors due to application appearance themes.

## 12. Design character

Use Origin's scientific workspace ideas and Office-style command organization as references, but do not visually clone either product.

Target character:

- scientific;
- dense but organized;
- discoverable;
- icon-assisted;
- keyboard accessible;
- publication-focused;
- consistent across techniques;
- efficient on Windows and macOS.
