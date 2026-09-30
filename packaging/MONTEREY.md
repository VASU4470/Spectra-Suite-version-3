# macOS Monterey Intel compatibility candidate

The regular Intel installer currently contains a Qt runtime that requires
macOS 13 or later. This separate candidate pins PySide6/Qt 6.7.0 and sets
`MACOSX_DEPLOYMENT_TARGET=12.0` so it can be evaluated on Monterey 12 without
changing the standard Intel, Apple Silicon, Windows, or Linux installer builds.

## Build

Run **Monterey Intel compatibility candidate** manually from GitHub Actions.
It runs the source test suite on an Intel macOS runner and uploads a separate
candidate artifact. The regular release publisher does not consume this
artifact, and the workflow does not create or replace a GitHub Release or tag.

The DMG is named
`SpectraSuite-3.4.0-macos-x86_64-monterey-unsigned.dmg` (the version comes
from `app_version.py`). The artifact also includes a build manifest,
dependency list, and SHA-256 checksums.

## Required real-Mac acceptance

Before publishing a special Monterey release, install the DMG on the Intel Mac
running Monterey 12.0.1 and verify:

1. Copy SpectraSuite to Applications and launch it successfully.
2. Open Home, import a small CSV, plot it, and close/reopen an analysis.
3. Export a plot to PNG and PDF.
4. Quit and relaunch the app; confirm it does not close during startup.

This runner builds and smoke-tests the packaged app on Intel macOS 15. It does
not emulate Monterey. A successful GitHub Actions run alone is not proof of
Monterey runtime compatibility. Keep this artifact labeled as a candidate
until the real-Mac checks pass. It remains unsigned and not notarized.
