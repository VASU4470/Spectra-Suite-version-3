# SpectraSuite 3.5.1 test release preparation

Version 3.5.1 adds a Live accent, more flexible fluid TXT/CSV parsing, and a
plus action beside Home. Publish it as the labeled test release
`v3.5.1-rc.1`; earlier release tags remain immutable. The release is also used
to test discovery and installation from an already-installed 3.5.0 app.

The publication workflow on main requires six successful cross-platform test
jobs and four successful installer jobs for the same source commit. It checks
the actual built source tree, complete artifact set, SHA-256 manifests and
uploaded release assets before publishing. Matching successful PR runs may be
reused after fast-forwarding their exact source commit to main. If builds are
still running, workflow-completion events retry the publication check.

Installers remain unsigned/unnotarized and must be described as test builds.
Set APP_VERSION and RELEASE_TAG together for each release; never replace an
existing version tag. A draft left by a failed upload requires inspection.

## Candidate downloads

The **Installer candidates** GitHub Actions run stores one artifact per target:

| Target | File | User action |
| --- | --- | --- |
| Windows x64 | unsigned setup .exe | First install manually; later, download and start setup from the in-app update flow |
| Apple Silicon Mac | unsigned arm64 .dmg | First install: open image and drag SpectraSuite to Applications |
| Apple Silicon Mac | unsigned arm64 update .pkg | In-app update: open in macOS Installer; the package reopens SpectraSuite after installation |
| Intel Mac | unsigned x86_64 .dmg | First install: open image and drag SpectraSuite to Applications |
| Intel Mac | unsigned x86_64 update .pkg | In-app update: open in macOS Installer; the package reopens SpectraSuite after installation |
| Ubuntu/Debian x64 | .deb | Open with the system package installer |

Python, Git, and pip are not needed by end users. Linux may need system runtime
packages installed by its package manager. These are candidate builds, not a
claim of signed or notarized distribution. Do not disable OS security settings.
The update dialog verifies the package checksum. On macOS, it opens the in-app
download only when the operating system's quarantine marker is present; otherwise
it directs the user to the browser download so Gatekeeper receives normal
download provenance.

Each artifact includes SHA-256 checksums, the tested source commit, architecture,
and installed Python dependency versions. CI runs the source tests and starts the
app installed from the Windows setup, copied from the Mac image, or installed
from the Linux package. This does not test Gatekeeper/SmartScreen or replace an
interactive clean-machine installation test.

## Stable distribution gates

1. All six existing Cross-platform tests jobs and all four Installer candidates
   jobs pass for the exact release source. Record the commit SHA and run links.
2. Verify the Mac menus, imports, plots, export, offline launch, and update
   preferences on a real Mac; verify Windows installation/uninstallation and
   Linux desktop launching.
3. Configure publisher signing for Windows and Developer ID signing plus
   notarization for Mac before promising a seamless public installer. Signing
   credentials belong in the release service's secret storage, never in source.
   Current candidate builders do not perform publisher signing.
4. Verify Brevo consent, double opt-in, privacy policy, unsubscribe, and a test
   email. No mailing credentials are needed in the app.
5. Promote the exact tested source to the release branch, preserve an immutable
   version tag, and attach verified signed files, checksums, and release notes.
   Do not replace the existing v3.1.0 tag or files.
6. Publish the completed GitHub Release. App notifications discover published
   newer releases; a source commit alone does not trigger an update banner.

Until these gates pass, the test release must not be advertised as a signed,
finished stable installer release. The main publication workflow includes
verified installer assets and marks the current release as a prerelease.
