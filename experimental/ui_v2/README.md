# SpectraSuite UI v2 — Experimental Workspace

Status: **design/prototype only**

This directory is an isolated workspace for redesigning the SpectraSuite desktop UI/UX. It is intentionally **not wired into the launcher, updater, packaging, or release metadata**.

## Isolation rules

- Development happens on `feature/ui-workspace-redesign`.
- `main` remains unchanged until a later integration decision.
- Do not change `APP_VERSION`, `RELEASE_TAG`, installer metadata, updater behavior, or release notes during ordinary UI development.
- Do not expose this prototype as completed functionality.
- Preserve current scientific calculations, defaults, file compatibility, session compatibility, exports, and axis conventions.
- Reuse existing shared scientific and plotting components rather than duplicating algorithms.

## Current source baseline

The redesign branch was created from current `main`, whose head at branch creation was the 3.5.3 test-release preparation line. The older project-context snapshot describing 3.4.0 is therefore not the current Git source of truth.

The existing spectroscopy UI currently uses:

- a persistent single-window shell;
- a left project/data navigator;
- central `Plot` and `Data table` peer tabs;
- a right `Inspector / Results / History` sidebar.

The redesign specifically reconsiders that presentation layer while preserving working scientific behavior.

## Design direction

The target architecture is:

1. **Top ribbon / contextual command system** as the primary command surface.
2. **Narrow collapsible Project Explorer** on the left.
3. **Large central multi-document scientific workspace**.
4. **No permanent right Inspector**.
5. Data tables, plots, results, and reports become first-class workspace documents.
6. Documents may coexist, tile, maximize, restore, and switch independently.
7. Detailed plot configuration moves into object-specific property dialogs.
8. Scientific operations use a common analysis-dialog framework.
9. Processing and analysis outputs should be represented as linked derived objects where practical while preserving raw data.
10. Technique-specific workspaces register commands into shared UI infrastructure rather than building parallel interfaces.

## Reference study

The design direction is informed by a targeted OriginPro 8.5 UI/UX study plus REA static PE-resource inspection. The goal is to learn interaction architecture, not to copy Origin visually or reproduce proprietary algorithms.

See:

- `ORIGIN_REA_FINDINGS.md`
- `ARCHITECTURE.md`
- `MIGRATION_PLAN.md`

## Release status

This folder does **not** define a future SpectraSuite release number. The next release identity will be chosen only after accepted features are integrated and fully validated.
