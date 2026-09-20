"""Publish a test release only from matching, fully verified CI artifacts."""
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

REPO = "VASU4470/Spectra-Suite-version-3"
ROOT = Path(__file__).resolve().parents[1]
IDENTITY = runpy.run_path(str(ROOT / "app_version.py"))
VERSION = IDENTITY["APP_VERSION"]
TAG = IDENTITY["RELEASE_TAG"]
SOURCE = os.environ.get("RELEASE_SOURCE_SHA", "")
EXPECTED = {
    "windows-x64": f"SpectraSuite-{VERSION}-windows-x64-unsigned-setup.exe",
    "macos-arm64": f"SpectraSuite-{VERSION}-macos-arm64-unsigned.dmg",
    "macos-x86_64": f"SpectraSuite-{VERSION}-macos-x86_64-unsigned.dmg",
    "linux-amd64": f"SpectraSuite-{VERSION}-linux-amd64.deb",
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
    require(len(SOURCE) == 40 and all(c in "0123456789abcdef" for c in SOURCE), "Invalid release source")
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == SOURCE,
            "Checked-out source differs from release source")
    if api("git/ref/heads/main")["object"]["sha"] != SOURCE:
        print("A newer main commit exists; this source will not be published.")
        return
    releases = api("releases?per_page=100")
    existing = next((r for r in releases if r["tag_name"] == TAG), None)
    if existing:
        require(not existing["draft"], "A draft release exists; inspect it before retrying")
        require(api(f"commits/{TAG}")["sha"] == SOURCE, "Existing version belongs to a different commit")
        print(f"{TAG} is already published; preserving its immutable files.")
        return
    runs = api(f"actions/runs?head_sha={SOURCE}&per_page=100")["workflow_runs"]
    selected = {}
    for workflow, count in (("installers.yml", 4), ("tests.yml", 6)):
        candidates = [r for r in runs if r["path"] == f".github/workflows/{workflow}"
                      and r["head_sha"] == SOURCE and r["conclusion"] == "success"
                      and r["head_repository"]["full_name"] == REPO
                      and r["event"] in {"push", "pull_request"}]
        if not candidates:
            print(f"Waiting for all {count} jobs in {workflow} to pass for {SOURCE}.")
            return
        selected[workflow] = str(max(candidates, key=lambda r: r["id"])["id"])
    installer_run = selected["installers.yml"]
    test_run = selected["tests.yml"]
    tree = api(f"git/commits/{SOURCE}")["tree"]["sha"]
    for run_id, count in ((installer_run, 4), (test_run, 6)):
        info = api(f"actions/runs/{run_id}")
        require(info["head_sha"] == SOURCE and info["conclusion"] == "success",
                "Source commit has not passed the required workflow")
        require(info["head_repository"]["full_name"] == REPO, "Unexpected source repository")
        jobs = api(f"actions/runs/{run_id}/jobs?per_page=100")["jobs"]
        require(len(jobs) == count and all(j["conclusion"] == "success" for j in jobs),
                "A required build/test job did not pass")
    artifacts = api(f"actions/runs/{installer_run}/artifacts")["artifacts"]
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
            command("run", "download", installer_run, "--repo", REPO, "--name",
                    f"SpectraSuite-candidate-{target}", "--dir", str(folder))
            manifests = list(folder.glob("build-*.json"))
            checksums = list(folder.glob("SHA256SUMS-*.txt"))
            require(len(manifests) == len(checksums) == 1, "Missing build/checksum manifest")
            info = json.loads(manifests[0].read_text())
            require(info["version"] == VERSION, "Wrong application version")
            require(api(f"git/commits/{info['commit']}")["tree"]["sha"] == tree,
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
            (ROOT / "packaging/release-notes.md").read_text(encoding="utf-8")
            + f"\n\nSource: [{SOURCE[:7]}](https://github.com/{REPO}/commit/{SOURCE}).\n\n"
            + f"All [six cross-platform jobs](https://github.com/{REPO}/actions/runs/{test_run}) "
            + f"and [four installer jobs](https://github.com/{REPO}/actions/runs/{installer_run}) passed. "
            + "Checksums, exact build commits and dependency manifests are attached.\n",
            encoding="utf-8")
        releases = api("releases?per_page=100")
        require(not any(r["tag_name"] == TAG for r in releases),
                "Release already exists; refusing to overwrite it")
        command("release", "create", TAG, "--repo", REPO, "--target", SOURCE,
                "--title", f"SpectraSuite {VERSION} — Test release",
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
