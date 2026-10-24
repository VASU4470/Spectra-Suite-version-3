# OriginPro 8.5 UI / REA Findings

## Scope

This study examined OriginPro 8.5 as a UI/UX reference for SpectraSuite.

Methods:
- manual UI observation on Windows;
- screenshots of worksheet, graph, axis properties, plot details, and analysis workflows;
- REA static PE-resource inspection of Origin executable/components.

The study did **not** attempt to reproduce Origin algorithms or proprietary scientific implementations.

## Observed UI behaviors

### Independent scientific documents

Origin treats worksheet and graph as separate workspace objects.

Observed behavior:
- worksheet and graph can coexist;
- either can be maximized/restored;
- switching one active object does not destroy the other;
- Project Explorer retains both objects.

Design lesson:
SpectraSuite Data Table and Plot should not have to replace each other as mutually exclusive central tabs.

### Context-dependent commands

The visible top-level command environment changes depending on the active scientific object.

Worksheet-active commands differ from graph-active commands.

Design lesson:
SpectraSuite's ribbon/command groups should respond to document type and technique context.

### Project Explorer

Origin uses a compact left-side project navigator to expose worksheet/graph objects.

Design lesson:
Keep a narrow collapsible Project Explorer, but do not use it as an analysis-parameter panel.

### Axis properties

Detailed axis settings are presented in a dedicated object-specific dialog over the graph.

Observed categories include:
- scale;
- title/format;
- grid lines;
- breaks;
- tick labels;
- minor/custom tick labels.

Design lesson:
Detailed formatting belongs in explicit property dialogs rather than a permanent right Inspector.

### Plot details

Origin's Plot Details dialog uses an object hierarchy such as:

- Graph
  - Layer
    - Dataset/series

The property surface changes with the selected object.

Design lesson:
SpectraSuite should use one scalable shared plot-properties architecture rather than separate ad hoc formatting panels per technique.

### Analysis workflow

Origin organizes analysis into categories and opens focused operation dialogs.

Observed operation structure commonly separates:
- input;
- options/parameters;
- output;
- recalculation behavior.

Design lesson:
SpectraSuite can standardize scientific operation dialogs while keeping technique-specific scientific code unchanged.

### Derived scientific data

Observed analysis can create derived data/columns instead of replacing the original source.

Design lesson:
Where compatible with existing SpectraSuite behavior, processed/analysis outputs should become explicit linked objects or derived data products rather than being hidden only in a transient results panel.

## REA evidence

REA static PE-resource inspection successfully analyzed:
- `Origin85.exe`
- `ogrid.dll`
- `OCntrls.dll`
- `OTreeEditor.dll`
- `ODlg8.dll`

The scans showed substantial modular UI-resource inventories.

### `ogrid.dll`

Contains many cursor, bitmap, icon, dialog, and string-table resources.

Interpretation:
consistent with a specialized grid/worksheet UI subsystem.

### `OCntrls.dll`

Contains reusable bitmap, menu, dialog, string and icon resources.

Interpretation:
consistent with a reusable controls component.

### `OTreeEditor.dll`

Contains menu/dialog resources plus multiple icon groups.

Interpretation:
consistent with a specialized tree/navigation UI component.

### `ODlg8.dll`

Contains a particularly large resource inventory with many dialogs and menus.

Interpretation:
strong evidence that Origin modularizes complex dialog/menu presentation rather than embedding all UI into the main executable.

## Limitations

REA's PE-resource parser observes static resource structure but does not decode the semantic meaning of every menu/dialog payload.

The Windows ARM environment prevented several deeper native-analysis providers from being useful.

Therefore the study supports interaction/design architecture, but it does **not** establish Origin's exact internal class design or scientific algorithms.

## Final design lessons carried into SpectraSuite

1. Use reusable shared UI subsystems.
2. Make tables, plots, and results first-class workspace documents.
3. Let documents coexist and maximize independently.
4. Use contextual top commands.
5. Keep a compact Project Explorer.
6. Remove the need for a permanent right Inspector.
7. Use object-specific property dialogs.
8. Standardize scientific analysis-dialog structure.
9. Prefer explicit derived results/data where compatible.
10. Preserve SpectraSuite's own scientific calculations and identity.
