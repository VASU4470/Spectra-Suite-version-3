# SpectraSuite 3.5.1 — test release

The application title displays **SpectraSuite 3.5.1** and the immutable release
tag is **v3.5.1-rc.1**. This test release verifies whether an installed 3.5.0
app can discover and start installing a newer prerelease from its update notice.

This release adds a changing Live accent that picks a different interface color
on each launch while avoiding immediate repeats. It is the default for users
who have not chosen a theme; manually selected themes remain fixed. Fluid
dynamics now reads headered and headerless TXT/CSV grids, including Tecplot
POINT files with changed metadata labels. The New analysis action is now a plus
button beside Home in the document tabs.

Download the installer for your computer from the release Assets; Python, Git,
and GitHub sign-in are not required.

| Computer | First install | In-app update |
| --- | --- | --- |
| Apple Silicon Mac (M1/M2/M3 and newer) | SpectraSuite-3.5.1-macos-arm64-unsigned.dmg | SpectraSuite-3.5.1-macos-arm64-unsigned-update.pkg |
| Intel Mac | SpectraSuite-3.5.1-macos-x86_64-unsigned.dmg | SpectraSuite-3.5.1-macos-x86_64-unsigned-update.pkg |
| Windows x64 | SpectraSuite-3.5.1-windows-x64-unsigned-setup.exe | Same setup file |
| Ubuntu/Debian x64 | SpectraSuite-3.5.1-linux-amd64.deb | System package installer |

The update dialog shows download progress and verifies the published SHA-256
checksum before opening the installer. Windows and macOS keep a recoverable
copy of the previous app. The dialog provides the normal OS security guidance
for these unsigned, unnotarized test installers; do not disable OS security.
On Mac, the in-app update requires the existing app in /Applications and
normal download quarantine metadata. Otherwise, use the browser download path.

Plot/export colors are unchanged. The app remains usable offline without an
account. Update installation opens the normal operating-system installer; the
user confirms installation there.

This is a public test release. Review the release checklist in RELEASE.md
before publishing it.
