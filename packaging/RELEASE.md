# SpectraSuite 3.2.0 release preparation

Feature scope is frozen for 3.2.0: the single-window interface, existing scientific
tools, optional email signup, update banner, and privacy preferences. Accept only
release-blocking fixes until this version ships.

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

## Release gates

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

Until these gates pass, v3.2.0 must not be advertised as a finished installer
release. The existing release workflow creates source-only releases on main;
change that workflow to require installer assets before merging this candidate.
