# SpectraSuite 3.5.0 — test release

This release adds in-app update installation and a refreshed SpectraSuite icon.
The application title displays **SpectraSuite 3.5.0** and the immutable release
tag is **v3.5.0-rc.1**. This release requires a manual download and install.
After it is installed, compatible future releases can be downloaded and
installed from the update notice inside SpectraSuite.

Download the installer for your computer from the release Assets; Python, Git,
and GitHub sign-in are not required.

| Computer | First install | In-app update |
| --- | --- | --- |
| Apple Silicon Mac (M1/M2/M3 and newer) | `SpectraSuite-3.5.0-macos-arm64-unsigned.dmg` | `SpectraSuite-3.5.0-macos-arm64-unsigned-update.pkg` |
| Intel Mac | `SpectraSuite-3.5.0-macos-x86_64-unsigned.dmg` | `SpectraSuite-3.5.0-macos-x86_64-unsigned-update.pkg` |
| Windows x64 | `SpectraSuite-3.5.0-windows-x64-unsigned-setup.exe` | Same setup file |
| Ubuntu/Debian x64 | `SpectraSuite-3.5.0-linux-amd64.deb` | System package installer |

The update dialog shows download progress and verifies the published SHA-256
checksum before opening the installer. Windows and macOS keep a recoverable
copy of the previous app. The dialog provides the normal OS security guidance
for these unsigned, unnotarized test installers; do not disable OS security.
On Mac, the in-app update requires the existing app in `/Applications` and
normal download quarantine metadata. Otherwise, use the browser download path.

Spectra teal is the default interface accent and the app icon is refreshed.
Previously selected appearance themes and plot/export colors are preserved.
The app remains usable offline without an account.

This is a public test release. Review the release checklist in
[`RELEASE.md`](RELEASE.md) before publishing it.
