# SpectraSuite 3.5.3 — test release

The application title displays **SpectraSuite 3.5.3** and the immutable release
tag is **v3.5.3-rc.1**. This test release restores “+ New analysis” to the far right of the ribbon.
It also retains the Windows and Mac installer/update flow.

After checksum verification, Windows starts the setup automatically. On Mac,
SpectraSuite opens the official release page so the browser can apply macOS's
normal download security check. Download the matching update package there and
open it to finish installation. This Mac update installation remains manual
until signed and notarized distribution is configured.

| Computer | First install | In-app update |
| --- | --- | --- |
| Apple Silicon Mac (M1/M2/M3 and newer) | SpectraSuite-3.5.3-macos-arm64-unsigned.dmg | SpectraSuite-3.5.3-macos-arm64-unsigned-update.pkg |
| Intel Mac | SpectraSuite-3.5.3-macos-x86_64-unsigned.dmg | SpectraSuite-3.5.3-macos-x86_64-unsigned-update.pkg |
| Windows x64 | SpectraSuite-3.5.3-windows-x64-unsigned-setup.exe | Same setup file |

Windows and Mac keep a recoverable copy of the previous app. The packages
remain unsigned and unnotarized test installers; follow the normal OS prompts
and do not disable system security. Python, Git, and GitHub sign-in are not
required. SpectraSuite remains usable offline.

This is a public test release. Review the release checklist in RELEASE.md
before publishing it.
