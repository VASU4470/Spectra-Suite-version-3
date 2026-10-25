# SpectraSuite 3.6.0 test release preparation

Version 3.6.0 integrates the redesigned scientific workspace and the Learning
Center / in-app user manual and scientific guidance. Publish it as
`v3.6.0-rc.1`; earlier release tags remain immutable.

The release must preserve existing scientific calculations, processing defaults,
axis conventions, import/export behavior, saved-session compatibility, updater
behavior, and preview/Coming Soon maturity labels unless a separate validated
scientific change explicitly approves otherwise.

The publication workflow on main requires successful Windows and Mac test jobs
and successful installer jobs for the same source commit. It checks the built
source tree, complete artifact set, SHA-256 manifests and uploaded release
assets. Matching successful PR runs may be reused only when they correspond to
the exact source commit promoted to main. Workflow-completion events may retry
publication if a build is still running.

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

## Release gates

1. All required Windows and Mac test jobs and Installer candidates jobs pass for
   the exact release source. Record the commit SHA and run links.
2. Verify packaged startup and the redesigned workspace/Learning Center on a real
   machine before promoting beyond prerelease status.
3. Verify important import, plot, analysis, session, export, and update paths.
4. Configure publisher signing for Windows and Developer ID signing plus
   notarization for Mac before promising seamless stable installation. Signing
   credentials belong in release-service secret storage, never in source.
5. Preserve the exact tested source in the release tag and attach verified
   installer files, checksums, provenance, and release notes.
6. Publish the completed GitHub Release as a prerelease. App notifications
   discover published newer releases; a source commit alone does not trigger an
   update banner.

Until these gates pass, the test release must not be advertised as a signed,
finished stable installer release.
