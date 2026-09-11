"""Pure helpers shared by the graphical release checker and its tests."""

from __future__ import annotations

import re

from app_version import APP_VERSION, RELEASE_PAGE_URL


def version_tuple(value):
    """Return a comparable three-part numeric version from tags such as v3.1.0."""
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?", str(value))
    if not match:
        raise ValueError(f"Unrecognized version: {value}")
    return tuple(int(part or 0) for part in match.groups())


def is_newer_release(candidate, current=APP_VERSION):
    return version_tuple(candidate) > version_tuple(current)


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

