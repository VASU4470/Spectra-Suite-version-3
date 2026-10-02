# macOS Monterey Intel compatibility test

The regular Intel installer currently contains a Qt runtime that requires
macOS 13 or later. This separate candidate pins PySide6/Qt 6.7.0 and sets
`MACOSX_DEPLOYMENT_TARGET=12.0` so it can be evaluated on Monterey 12 without
changing the standard Intel, Apple Silicon, Windows, or Linux installer builds.

## Build and test prerelease

The dedicated **Monterey Intel compatibility test release** workflow builds on
an Intel macOS runner, runs the source tests, smoke-tests the packaged app, and
publishes an unsigned prerelease containing the Monterey DMG, build manifest,
dependency list, and SHA-256 checksums. The separate artifact is not included in
the regular four-platform release publisher.

The DMG is named
`SpectraSuite-3.4.0-macos-x86_64-monterey-unsigned.dmg` (the version comes
from `app_version.py`). The test release uses a non-version tag, which the
SpectraSuite in-app version checker ignores.

## Required real-Mac acceptance

The CI runner is Intel macOS 15. It does not emulate Monterey, so a successful
workflow run alone does not establish Monterey compatibility. Install the
prerelease on the Intel Mac running Monterey 12.0.1 and verify:

1. Copy SpectraSuite to Applications and launch it successfully.
2. Open Home, import a small CSV, plot it, and close/reopen an analysis.
3. Export a plot to PNG and PDF.
4. Quit and relaunch the app; confirm it does not close during startup.

This is a test prerelease for the specified Monterey machine. It is unsigned and
not notarized; macOS may show the standard developer-verification prompt. Do
not describe Monterey as supported until the real-Mac checks pass. If they pass,
keep this Monterey-specific prerelease available and document the tested model
and macOS version. If they fail, use the captured error to revise the packaging
before issuing a replacement candidate.
