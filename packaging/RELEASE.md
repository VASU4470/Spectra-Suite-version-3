# SpectraSuite 3.5.2 test release preparation

Version 3.5.2 fixes the in-app update handoff after package verification,
cleans up Markdown release notes, and limits new CI test/build jobs to Windows
and Mac. Publish it as `v3.5.2-rc.1`; earlier release tags remain immutable.

The publication workflow on main requires four successful Windows and Mac test
jobs and three successful installer jobs for the same source commit. It checks
the built source tree, complete artifact set, SHA-256 manifests and uploaded
release assets. Matching successful PR runs may be reused after fast-forwarding
their exact source commit to main. Workflow-completion events retry publication
if a build is still running.

Installers remain unsigned and unnotarized and must be described as test builds.
Set `APP_VERSION` and `RELEASE_TAG` together for each release; never replace an
existing version tag. A draft left by a failed upload requires inspection.

## Candidate downloads

The **Installer candidates** GitHub Actions run stores one artifact per target:

| Target | File | User action |
| --- | --- | --- |
| Windows x64 | unsigned setup .exe | First install manually; in-app update starts the verified setup |
| Apple Silicon Mac | unsigned arm64 .dmg | First install: open image and drag SpectraSuite to Applications |
| Apple Silicon Mac | unsigned arm64 update .pkg | Download from the browser and open in macOS Installer |
| Intel Mac | unsigned x86_64 .dmg | First install: open image and drag SpectraSuite to Applications |
| Intel Mac | unsigned x86_64 update .pkg | Download from the browser and open in macOS Installer |

Python, Git, and pip are not needed by end users. These are candidate builds,
not signed or notarized distribution. Do not disable OS security settings. The
update dialog verifies the installer checksum. On Windows it starts the verified
setup automatically. On Mac it opens the official release page so the browser
can apply macOS's normal download security check; the user then downloads and
opens the matching update package. This Mac step remains manual while these
packages are unsigned and unnotarized.

Each artifact includes SHA-256 checksums, the tested source commit, architecture,
and installed Python dependency versions. CI runs source tests and starts the app
installed from the Windows setup or copied from a Mac image. This does not test
Gatekeeper/SmartScreen or replace an interactive clean-machine installation test.

## Stable distribution gates

1. All four Windows and Mac test jobs and all three Installer candidates jobs
   pass for the exact release source. Record the commit SHA and run links.
2. Verify the Mac menus, imports, plots, export, offline launch, and update
   preferences on a real Mac; verify Windows installation and uninstallation.
3. Configure publisher signing for Windows and Developer ID signing plus
   notarization for Mac before promising seamless public installation. Signing
   credentials belong in release-service secret storage, never in source.
4. Verify Brevo consent, double opt-in, privacy policy, unsubscribe, and a test
   email. No mailing credentials are needed in the app.
5. Promote the exact tested source to the release branch, preserve an immutable
   version tag, and attach verified signed files, checksums, and release notes.
6. Publish the completed GitHub Release. App notifications discover published
   newer releases; a source commit alone does not trigger an update banner.

Until these gates pass, the test release must not be advertised as a signed,
finished stable installer release. The main publication workflow verifies the
installer assets and marks the current release as a prerelease.
