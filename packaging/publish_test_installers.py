"""Publish the approved, already-tested 3.2.0 installer artifacts."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

REPO = "VASU4470/Spectra-Suite-version-3"
SOURCE = "e87c935c0b8935cbc376ce25b77c2e973eaa1c72"
TREE = "c640c2157650b9898aecb814ffc7e90951aa00d8"
TAG = "v3.2.0-rc.1"
RUN = "34877842713"
EXPECTED = {
    "windows-x64": "SpectraSuite-3.2.0-windows-x64-unsigned-setup.exe",
    "macos-arm64": "SpectraSuite-3.2.0-macos-arm64-unsigned.dmg",
    "macos-x86_64": "SpectraSuite-3.2.0-macos-x86_64-unsigned.dmg",
    "linux-amd64": "SpectraSuite-3.2.0-linux-amd64.deb",
}


def command(*args):
    subprocess.run(["gh", *args], check=True)


def api(path):
    return json.loads(subprocess.check_output(
        ["gh", "api", f"repos/{REPO}/{path}"], text=True))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    require(os.environ["GITHUB_REPOSITORY"] == REPO, "Unexpected repository")
    for run_id, count in ((RUN, 4), ("34877842623", 6)):
        info = api(f"actions/runs/{run_id}")
        require(info["head_sha"] == SOURCE and info["conclusion"] == "success",
                "Source commit has not passed the required workflow")
        require(info["head_repository"]["full_name"] == REPO, "Unexpected source repository")
        jobs = api(f"actions/runs/{run_id}/jobs?per_page=100")["jobs"]
        require(len(jobs) == count and all(j["conclusion"] == "success" for j in jobs),
                "A required build/test job did not pass")
    require(api(f"git/commits/{SOURCE}")["tree"]["sha"] == TREE, "Source tree mismatch")
    artifacts = api(f"actions/runs/{RUN}/artifacts")["artifacts"]
    required_names = {f"SpectraSuite-candidate-{target}" for target in EXPECTED}
    require({a["name"] for a in artifacts} == required_names, "Unexpected artifact set")
    require(all(not a["expired"] for a in artifacts), "An installer artifact has expired")

    with tempfile.TemporaryDirectory(prefix="spectrasuite-release-") as directory:
        root = Path(directory)
        publish = root / "assets"
        publish.mkdir()
        hashes = {}
        for target, filename in EXPECTED.items():
            folder = root / target
            command("run", "download", RUN, "--repo", REPO, "--name",
                    f"SpectraSuite-candidate-{target}", "--dir", str(folder))
            manifests = list(folder.glob("build-*.json"))
            checksums = list(folder.glob("SHA256SUMS-*.txt"))
            require(len(manifests) == len(checksums) == 1, "Missing build/checksum manifest")
            info = json.loads(manifests[0].read_text())
            require(info["version"] == "3.2.0", "Wrong application version")
            require(api(f"git/commits/{info['commit']}")["tree"]["sha"] == TREE,
                    "Installer was built from a different source tree")
            require((folder / filename).is_file(), "Expected installer is missing")
            verified = set()
            for line in checksums[0].read_text().splitlines():
                digest, name = line.split("  ", 1)
                require(Path(name).name == name and name not in verified, "Invalid checksum filename")
                asset = folder / name
                require(asset.is_file() and not asset.is_symlink(), "Invalid artifact file")
                require(sha256(asset) == digest, f"Checksum mismatch: {name}")
                verified.add(name)
            require(filename in verified and manifests[0].name in verified, "Unverified installer")
            for asset in folder.iterdir():
                require(asset.name in verified or asset == checksums[0], "Unexpected artifact content")
                require(not (publish / asset.name).exists(), "Duplicate release asset")
                shutil.copy2(asset, publish / asset.name)
                hashes[asset.name] = sha256(asset)
        notes = root / "release-notes.md"
        notes.write_text(
            "# SpectraSuite 3.2.0 — public test release\n\n"
            "Download the installer for your computer from **Assets** below. "
            "**No GitHub sign-in, Python, or Git installation is required.**\n\n"
            "| Computer | Installer |\n| --- | --- |\n"
            "| Windows x64 | SpectraSuite-3.2.0-windows-x64-unsigned-setup.exe |\n"
            "| Apple Silicon Mac (M1/M2/M3 and newer) | SpectraSuite-3.2.0-macos-arm64-unsigned.dmg |\n"
            "| Intel Mac | SpectraSuite-3.2.0-macos-x86_64-unsigned.dmg |\n"
            "| Ubuntu/Debian x64 | SpectraSuite-3.2.0-linux-amd64.deb |\n\n"
            "## Installation\n\n"
            "- **Windows:** open the setup EXE, complete the wizard, then launch SpectraSuite from Start.\n"
            "- **Mac:** open the DMG, drag SpectraSuite to Applications, then launch it there.\n"
            "- **Linux:** open the DEB with your system package installer. System runtime packages may be required.\n\n"
            "Windows and Mac installers are **not publisher-signed**; Mac builds are **not notarized**. "
            "OS security checks may warn or block launch. If blocked, report the exact message and OS version. "
            "Do not disable antivirus or system security globally.\n\n"
            "This is a test release, not the final stable distribution. "
            "The application displays version 3.2.0; the release tag v3.2.0-rc.1 identifies this candidate. "
            "The app works offline and requires no account. Optional email signup is available from Account. "
            "These release downloads have no automatic 30-day artifact expiry; the app has no trial expiry.\n\n"
            "## Included\n\n"
            "- FT-IR, XRD, UV-Vis, Raman, general 2D and 3D plotting.\n"
            "- Single-window project, import, plot, full-height data table, and inspector workflow.\n"
            "- Optional update emails, a non-blocking update banner, and privacy/update preferences.\n\n"
            "## Validation and provenance\n\n"
            f"Frozen source: [{SOURCE[:7]}](https://github.com/{REPO}/commit/{SOURCE}).\n\n"
            f"All [six cross-platform test jobs](https://github.com/{REPO}/actions/runs/34877842623) "
            f"and [four installer jobs](https://github.com/{REPO}/actions/runs/{RUN}) passed. "
            "Installer checks started the app from an actual Windows installation, a copy from each "
            "Mac disk image, and an installed Linux package. Real-user visual/OS security checks remain useful.\n\n"
            "Checksums, exact build commits, and dependency manifests are attached. "
            "Choose an EXE, DMG, or DEB to install; the automatic Source code archives are for developers.\n",
            encoding="utf-8")
        releases = api("releases?per_page=100")
        require(not any(r["tag_name"] == TAG for r in releases),
                "Release already exists; refusing to overwrite it")
        command("release", "create", TAG, "--repo", REPO, "--target", SOURCE,
                "--title", "SpectraSuite 3.2.0 — Test release",
                "--notes-file", str(notes), "--draft", "--prerelease", "--latest=false",
                *[str(p) for p in sorted(publish.iterdir())])
        release = next(r for r in api("releases?per_page=100") if r["tag_name"] == TAG)
        require(release["draft"] and release["prerelease"], "Expected draft prerelease")
        assets = api(f"releases/{release['id']}/assets?per_page=100")
        require({a["name"] for a in assets} == set(hashes), "Release asset set mismatch")
        for asset in assets:
            require(asset["state"] == "uploaded", "Asset upload is incomplete")
            require(asset["size"] == (publish / asset["name"]).stat().st_size,
                    "Release upload size mismatch")
            if asset.get("digest"):
                require(asset["digest"] == f"sha256:{hashes[asset['name']]}",
                        "Release upload digest mismatch")
        command("release", "edit", TAG, "--repo", REPO, "--draft=false",
                "--prerelease", "--latest=false")
        # Verify installer access without a token, as a normal public visitor.
        for filename in EXPECTED.values():
            url = f"https://github.com/{REPO}/releases/download/{TAG}/{filename}"
            request = urllib.request.Request(url, headers={"Range": "bytes=0-31"})
            with urllib.request.urlopen(request, timeout=60) as response:
                require(response.status in (200, 206) and bool(response.read(32)),
                        "Anonymous installer download failed")
        print(f"Public installers verified: https://github.com/{REPO}/releases/tag/{TAG}")


if __name__ == "__main__":
    main()
