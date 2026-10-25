# SpectraSuite UI v2 Migration Plan

## Goal

Move from the current Project–Canvas–Inspector spectroscopy layout to the UI v2 architecture without breaking scientific behavior, session compatibility, or release/update behavior.

## Phase 0 — Design only

Status at branch creation.

Tasks:
- freeze architecture decisions;
- define ribbon information architecture;
- define document types and object relationships;
- define Project Explorer tree model;
- define property-dialog behavior;
- define analysis-dialog framework;
- create mockups/prototypes that are not wired into the production launcher.

No scientific or release code changes.

## Phase 1 — Shared shell prototype

Create isolated prototype components under the experimental UI area.

Prototype:
- ribbon shell;
- collapsible Project Explorer;
- central multi-document workspace;
- document focus/context routing;
- status bar.

Use dummy/sample documents first.

Acceptance:
- no changes to production launcher;
- no impact on existing tests outside prototype-specific tests;
- works on supported PySide6 platforms in source mode.

## Phase 2 — Data and Plot documents

Prototype shared:
- DataTableDocument;
- PlotDocument;
- tile/maximize/restore behavior;
- active-document switching;
- shared command routing.

Reuse current table/plot components where practical rather than rewriting scientific plotting code.

Acceptance:
- plot and table can coexist;
- one can maximize and restore without destroying the other;
- document state remains independent.

## Phase 3 — Project Explorer object model

Introduce a shared project/document object representation for prototype use.

Objects may include:
- raw dataset;
- derived dataset;
- plot;
- result table;
- analysis result.

Do not alter saved-session format until compatibility design and migration tests are approved.

## Phase 4 — Property dialogs

Build shared prototype dialogs:
- Axis Properties;
- Plot Properties;
- Legend/Annotation properties as needed.

These should operate against existing Matplotlib-backed objects through adapters where possible.

Acceptance:
- no permanent right Inspector required for prototype formatting tasks;
- cancel/apply semantics are predictable;
- scientific plot colors remain independent of application theme.

## Phase 5 — Analysis-dialog framework

Build a shared dialog container supporting:
- Input;
- Parameters;
- Output;
- Recalculation/provenance.

Migrate only one low-risk existing operation as a proof of concept.

Do not change algorithms/defaults.

## Phase 6 — Technique pilot

Choose one spectroscopy workspace as the pilot integration target after the shared shell is stable.

Recommended order:
1. FT-IR or Raman for general spectroscopy workflow;
2. XRD;
3. UV-Vis;
4. remaining techniques.

The pilot must reuse existing scientific functions and state rather than reimplement them.

## Phase 7 — Compatibility and regression validation

Before replacing the production UI:
- run relevant automated tests;
- update tests that intentionally encode the old UI structure;
- preserve session loading;
- test old saved projects;
- test import/export;
- test undo/redo/history;
- test startup;
- test light themes;
- test Windows and macOS;
- verify no release/updater changes.

## Phase 8 — Integration decision

Only after prototype acceptance:
- decide whether to merge into the normal development line;
- remove or retire old presentation components carefully;
- run complete combined validation.

The next SpectraSuite release number is **not** determined by this branch.

## Explicit non-goals

This migration is not permission to:
- change scientific equations;
- change baseline/smoothing/fitting defaults;
- redesign data formats;
- change updater/release channels;
- remove working capabilities;
- mark experimental functionality as complete.
