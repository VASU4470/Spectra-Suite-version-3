"""Build a separately labeled Intel installer candidate for macOS Monterey."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "release-dist"


def main() -> None:
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise RuntimeError("The Monterey candidate must be built on an Intel macOS runner")
    if os.environ.get("MACOSX_DEPLOYMENT_TARGET") != "12.0":
        raise RuntimeError("Set MACOSX_DEPLOYMENT_TARGET=12.0 for this build")

    from PySide6 import QtCore

    if not QtCore.qVersion().startswith("6.7."):
        raise RuntimeError(f"Expected Qt 6.7.x, found Qt {QtCore.qVersion()}")

    sys.path.insert(0, str(ROOT / "packaging"))
    import build_installers

    build_installers.main()

    version = __import__("runpy").run_path(str(ROOT / "app_version.py"))["APP_VERSION"]
    names = {
        f"SpectraSuite-{version}-macos-x86_64-unsigned.dmg":
            f"SpectraSuite-{version}-macos-x86_64-monterey-unsigned.dmg",
        "build-macos-x86_64.json": "build-macos-x86_64-monterey.json",
        "dependencies-macos-x86_64.txt": "dependencies-macos-x86_64-monterey.txt",
        "SHA256SUMS-macos-x86_64.txt": "SHA256SUMS-macos-x86_64-monterey.txt",
    }
    for source_name, target_name in names.items():
        source = OUTPUT / source_name
        if not source.is_file():
            raise RuntimeError(f"Expected build output is missing: {source_name}")
        source.rename(OUTPUT / target_name)

    manifest_path = OUTPUT / "build-macos-x86_64-monterey.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({
        "minimum_macos": "12.0",
        "build_flavor": "monterey-intel-compatibility-candidate",
        "qt_version": QtCore.qVersion(),
        "distribution_status": "installer-candidate",
    })
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    checksum_path = OUTPUT / "SHA256SUMS-macos-x86_64-monterey.txt"
    entries = []
    for artifact in sorted(OUTPUT.iterdir()):
        if artifact.is_file() and artifact != checksum_path:
            digest = hashlib.file_digest(artifact.open("rb"), "sha256").hexdigest()
            entries.append(f"{digest}  {artifact.name}")
    checksum_path.write_text("\n".join(entries) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
