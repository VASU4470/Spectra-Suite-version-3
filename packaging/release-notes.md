# SpectraSuite 3.5.4 — test release

The application title displays **SpectraSuite 3.5.4** and the immutable release
tag is **v3.5.4-rc.1**. This public test candidate is based on the 3.5 workspace.

- Help → Learning Center opens the illustrated User Manual, searchable learning topics and offline Example Library.
- Eleven examples include measured polystyrene FT-IR and LaB₆ powder XRD with worked steps and provenance.
- Export manifests record figure settings, and XRD export settings record the Scherrer inputs.
- Instrument text imports tolerate preambles and incomplete rows when enough valid X/Y pairs remain. Invalid session files receive clearer errors.

After checksum verification, Windows starts the setup automatically. On Mac,
SpectraSuite opens the official release page so the browser can apply macOS's
normal download security check. Download the matching update package there and
open it to finish installation. This Mac update installation remains manual
until signed and notarized distribution is configured.

| Computer | First install | In-app update |
| --- | --- | --- |
| Apple Silicon Mac (M1/M2/M3 and newer) | SpectraSuite-3.5.4-macos-arm64-unsigned.dmg | SpectraSuite-3.5.4-macos-arm64-unsigned-update.pkg |
| Intel Mac | SpectraSuite-3.5.4-macos-x86_64-unsigned.dmg | SpectraSuite-3.5.4-macos-x86_64-unsigned-update.pkg |
| Windows x64 | SpectraSuite-3.5.4-windows-x64-unsigned-setup.exe | Same setup file |

Windows and Mac keep a recoverable copy of the previous app. The packages
remain unsigned and unnotarized test installers; follow the normal OS prompts
and do not disable system security. Python, Git, and GitHub sign-in are not
required. SpectraSuite remains usable offline.

This is a public test release. Review the release checklist in RELEASE.md
before publishing it.
