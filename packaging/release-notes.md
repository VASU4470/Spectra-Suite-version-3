# SpectraSuite 3.6.0 — test release

The application title displays **SpectraSuite 3.6.0** and the immutable release
tag is **v3.6.0-rc.1**.

This test release introduces the redesigned scientific workspace and integrates
the Learning Center / in-app user manual and scientific guidance into the
single-window SpectraSuite workflow. Shared UI-v2 presentation and property
components are used across the affected workspaces while preserving existing
scientific calculations, processing defaults, import/export behavior, saved
sessions, update behavior, and preview/Coming Soon maturity labels.

The release also includes regression coverage for the redesigned interface and
a hardened CI GUI smoke-test harness so a completed successful PySide6 test run
is distinguished from a later Qt/Matplotlib teardown failure.

After checksum verification, Windows starts the setup automatically. On Mac,
SpectraSuite opens the official release page so the browser can apply macOS's
normal download security check. Download the matching update package there and
open it to finish installation. This Mac update installation remains manual
until signed and notarized distribution is configured.

| Computer | First install | In-app update |
| --- | --- | --- |
| Apple Silicon Mac (M1/M2/M3 and newer) | SpectraSuite-3.6.0-macos-arm64-unsigned.dmg | SpectraSuite-3.6.0-macos-arm64-unsigned-update.pkg |
| Intel Mac | SpectraSuite-3.6.0-macos-x86_64-unsigned.dmg | SpectraSuite-3.6.0-macos-x86_64-unsigned-update.pkg |
| Windows x64 | SpectraSuite-3.6.0-windows-x64-unsigned-setup.exe | Same setup file |

Windows and Mac keep a recoverable copy of the previous app. The packages
remain unsigned and unnotarized test installers; follow normal OS prompts and
do not disable system security. Python, Git, and GitHub sign-in are not
required. SpectraSuite remains usable offline.

This is a public test release, not a signed stable distribution. Review the
release checklist in RELEASE.md before publication.
