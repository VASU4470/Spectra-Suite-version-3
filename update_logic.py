"""Pure helpers shared by the graphical release checker and its tests."""

from __future__ import annotations

import re

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
    }
