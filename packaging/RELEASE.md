# SpectraSuite 3.4.0 release preparation

Version 3.4.0 improves appearance, image-digitizer guidance, connected-curve
tracing and export-control clarity. It is published as the clearly labeled test
release `v3.4.0-rc.1`. Earlier release tags remain immutable. This release is
also the end-to-end update-notification target for installed 3.3.0-rc.2 builds.

The publication workflow on main requires six successful cross-platform test
jobs and four successful installer jobs for the same source commit. It checks
the actual built source tree, complete artifact set, SHA-256 manifests and
uploaded release assets before publishing. Matching successful PR runs may be
reused after fast-forwarding their exact source commit to main. If builds are
still running, workflow-completion events retry the publication check.

Installers remain unsigned/unnotarized and must be described as test builds.
Set a new APP_VERSION and RELEASE_TAG for the next release; never replace an
existing version tag. A draft left by a failed upload requires inspection.

## Candidate downloads

The **Installer candidates** GitHub Actions run stores one artifact per target:

| Target | File | User action |
| --- | --- | --- |
| Windows x64 | unsigned setup .exe | Open setup; installs for the current user and adds a Start menu entry |
| Apple Silicon Mac | unsigned arm64 .dmg | Open image and drag SpectraSuite to Applications |
| Intel Mac | unsigned x86_64 .dmg | Open image and drag SpectraSuite to Applications |
| Ubuntu/Debian x64 | .deb | Open with the system package installer |

Python, Git, and pip are not needed by end users. Linux may need system runtime
packages installed by its package manager. These are candidate builds, not a
claim of signed or notarized distribution. Do not disable OS security settings.

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
