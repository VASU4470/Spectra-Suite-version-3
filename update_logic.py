"""Pure helpers shared by the graphical release checker and its tests."""

from __future__ import annotations

import re
import hashlib
import platform
from pathlib import Path

from app_version import RELEASE_TAG, RELEASE_PAGE_URL


def version_tuple(value):
    """Return a comparable three-part numeric version from tags such as v3.1.0."""
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?", str(value))
    if not match:
        raise ValueError(f"Unrecognized version: {value}")
    return tuple(int(part or 0) for part in match.groups())


def version_key(value):
    """SemVer ordering, including numbered release candidates and final releases."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", str(value).strip())
    if not match:
        raise ValueError(f"Unrecognized version: {value}")
    major, minor, patch, suffix = match.groups()
    prerelease = tuple((0, int(part)) if part.isdigit() else (1, part)
                       for part in suffix.split(".")) if suffix else ()
    return (int(major), int(minor), int(patch or 0), suffix is None, prerelease)


def is_newer_release(candidate, current=RELEASE_TAG):
    return version_key(candidate) > version_key(current)


def select_release(payload, *, include_prereleases=False):
    """Choose by version, never list order; drafts and malformed tags are ignored."""
    if not isinstance(payload, list):
        raise ValueError("GitHub returned an invalid release list.")
    candidates = []
    for item in payload:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        try:
            key = version_key(item.get("tag_name", ""))
        except ValueError:
            continue
        if not include_prereleases and (item.get("prerelease") or not key[3]):
            continue
        candidates.append((key, item))
    return release_summary(max(candidates, key=lambda pair: pair[0])[1]) if candidates else None


def release_summary(payload):
    """Validate and normalize the small part of GitHub's release response we use."""
    tag = str(payload.get("tag_name", "")).strip()
    if not tag:
        raise ValueError("The release response did not include a version tag.")
    return {
        "tag": tag,
        "name": str(payload.get("name") or tag),
        "notes": str(payload.get("body") or "No release notes were supplied."),
        "url": str(payload.get("html_url") or RELEASE_PAGE_URL),
        "assets": [
            {
                "name": str(asset.get("name") or ""),
                "url": str(asset.get("browser_download_url") or ""),
                "size": int(asset.get("size") or 0),
            }
            for asset in payload.get("assets", [])
            if isinstance(asset, dict)
        ],
    }


def update_asset_names(system=None, machine=None):
    """Return the release installer/checksum names for this supported platform."""
    system = (system or platform.system()).casefold()
    machine = (machine or platform.machine()).casefold()
    if system == "windows" and machine in {"amd64", "x86_64", "x64"}:
        return "windows-x64", "windows-amd64", "exe"
    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return "macos-arm64", "darwin-arm64", "pkg"
    if system == "darwin" and machine in {"x86_64", "amd64", "x64"}:
        return "macos-x86_64", "darwin-x86_64", "pkg"
    if system == "linux" and machine in {"x86_64", "amd64", "x64"}:
        return "linux-amd64", "linux-x86_64", "deb"
    return None


def select_update_assets(release, *, system=None, machine=None):
    """Choose the matching full installer and checksum manifest from a release."""
    target = update_asset_names(system, machine)
    if target is None:
        return None
    installer_target, checksum_target, extension = target
    version = version_tuple(release.get("tag", ""))
    version_text = ".".join(str(part) for part in version)
    if extension == "exe":
        installer_name = f"SpectraSuite-{version_text}-windows-x64-unsigned-setup.exe"
    elif extension == "pkg":
        installer_name = f"SpectraSuite-{version_text}-{installer_target}-unsigned-update.pkg"
    else:
        installer_name = f"SpectraSuite-{version_text}-linux-amd64.deb"
    checksum_name = f"SHA256SUMS-{checksum_target}.txt"
    assets = {asset.get("name"): asset for asset in release.get("assets", [])}
    installer = assets.get(installer_name)
    checksums = assets.get(checksum_name)
    if not installer or not checksums:
        return None
    for asset in (installer, checksums):
        url = str(asset.get("url", ""))
        if not url.startswith("https://github.com/"):
            return None
    return installer, checksums


def checksum_from_manifest(text, expected_name):
    """Read one exact basename and SHA-256 digest from a release manifest."""
    matches = []
    for line in str(text).splitlines():
        fields = line.strip().split("  ", 1)
        if len(fields) != 2:
            continue
        digest, filename = fields
        if filename == expected_name and re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            matches.append(digest.casefold())
    if len(matches) != 1:
        raise ValueError("The release checksum file does not contain one valid installer checksum.")
    return matches[0]


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
