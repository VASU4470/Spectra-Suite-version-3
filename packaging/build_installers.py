"""Build and smoke-test native installer candidates on their target OS."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = runpy.run_path(str(ROOT / "app_version.py"))["APP_VERSION"]
OUTPUT = ROOT / "release-dist"
ENV = dict(os.environ, QT_QPA_PLATFORM="offscreen", MPLBACKEND="QtAgg",
           SPECTRASUITE_DISABLE_UPDATE_CHECK="1")


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT, **kwargs)


def smoke(executable):
    run([executable, "--smoke-test"], env=ENV, timeout=120)


def build_bundle():
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--onedir", "--name", "SpectraSuite"]
    if sys.platform in {"win32", "darwin"}:
        args.append("--windowed")
    if sys.platform == "darwin":
        args += ["--icon", "app_icon.icns", "--osx-bundle-identifier",
                 "org.spectrasuite.desktop"]
    elif sys.platform == "win32":
        from PIL import Image
        (ROOT / "build").mkdir(exist_ok=True)
        with Image.open(ROOT / "icon.png") as icon:
            icon.save(ROOT / "build/installer.ico", format="ICO",
                      sizes=[(16, 16), (32, 32), (48, 48), (128, 128), (256, 256)])
        args += ["--icon", "build/installer.ico"]
    assets = [ROOT / "icon.png", ROOT / "LICENSE", ROOT / "PRIVACY.md"]
    assets += sorted(ROOT.glob("*_icon.svg"))
    assets += sorted(ROOT.glob("*_icon_taskbar.png"))
    for asset in assets:
        args += ["--add-data", f"{asset.name}:."]
    for package in ("PySide6", "shiboken6", "numpy", "scipy", "pandas", "matplotlib",
                    "openpyxl", "xlrd", "Pillow"):
        args += ["--copy-metadata", package]
    run(args + ["launcher.py"])


def windows():
    compiler = shutil.which("ISCC.exe")
    if not compiler:
        candidate = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        candidate = candidate / "Inno Setup 6/ISCC.exe"
        if candidate.is_file():
            compiler = str(candidate)
    if not compiler:
        raise RuntimeError("Inno Setup compiler was not found on the Windows runner")
    smoke(ROOT / "dist/SpectraSuite/SpectraSuite.exe")
    run([compiler, f"/DAppVersion={VERSION}", f"/DProjectRoot={ROOT}",
         ROOT / "packaging/windows.iss"])
    installer = OUTPUT / f"SpectraSuite-{VERSION}-windows-x64-unsigned-setup.exe"
    installed = ROOT / "build/Installed SpectraSuite"
    run([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
         f"/DIR={installed}"], timeout=180)
    try:
        smoke(installed / "SpectraSuite.exe")
    finally:
        run([installed / "unins000.exe", "/VERYSILENT", "/SUPPRESSMSGBOXES",
             "/NORESTART"], timeout=120)


def macos():
    arch = platform.machine()
    app = ROOT / "dist/SpectraSuite.app"
    smoke(app / "Contents/MacOS/SpectraSuite")
    stage = ROOT / "build/dmg-stage"
    stage.mkdir(parents=True, exist_ok=True)
    run(["ditto", app, stage / app.name])
    (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
    disk = OUTPUT / f"SpectraSuite-{VERSION}-macos-{arch}-unsigned.dmg"
    run(["hdiutil", "create", "-volname", f"SpectraSuite {VERSION}",
         "-srcfolder", stage, "-ov", "-format", "UDZO", disk])
    run(["hdiutil", "verify", disk])
    mount = ROOT / "build/dmg-mounted"
    mount.mkdir(exist_ok=True)
    run(["hdiutil", "attach", disk, "-readonly", "-nobrowse", "-mountpoint", mount])
    try:
        installed = ROOT / "build/Installed SpectraSuite.app"
        run(["ditto", mount / "SpectraSuite.app", installed])
        smoke(installed / "Contents/MacOS/SpectraSuite")
    finally:
        run(["hdiutil", "detach", mount])


def linux():
    smoke(ROOT / "dist/SpectraSuite/SpectraSuite")
    package = ROOT / "build/debian"
    target = package / "opt/spectrasuite"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "dist/SpectraSuite", target, dirs_exist_ok=True)
    control = package / "DEBIAN"
    control.mkdir(exist_ok=True)
    (control / "control").write_text(
        f"Package: spectrasuite\nVersion: {VERSION}\nArchitecture: amd64\n"
        "Maintainer: SpectraSuite <95100431+VASU4470@users.noreply.github.com>\n"
        "Section: science\nPriority: optional\n"
        "Depends: libc6 (>= 2.35), libstdc++6, libgl1, libegl1, libfontconfig1, "
        "libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-keysyms1, "
        "libxcb-image0, libxcb-render-util0, libxcb-xinerama0, libdbus-1-3\n"
        "Homepage: https://github.com/VASU4470/Spectra-Suite-version-3\n"
        "Description: Offline spectroscopy analysis and scientific plotting\n"
        " FT-IR, XRD, UV-Vis, Raman, and general 2D/3D plotting.\n",
        encoding="utf-8")
    desktop = package / "usr/share/applications/spectrasuite.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(
        "[Desktop Entry]\nType=Application\nName=SpectraSuite\n"
        "Comment=Spectroscopy analysis and scientific plotting\n"
        "Exec=/opt/spectrasuite/SpectraSuite\nIcon=spectrasuite\n"
        "Terminal=false\nCategories=Education;Science;\n",
        encoding="utf-8")
    icon = package / "usr/share/pixmaps/spectrasuite.png"
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "icon.png", icon)
    executable = package / "usr/bin/spectrasuite"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.symlink_to("/opt/spectrasuite/SpectraSuite")
    archive = OUTPUT / f"SpectraSuite-{VERSION}-linux-amd64.deb"
    run(["dpkg-deb", "--root-owner-group", "--build", package, archive])
    run(["dpkg-deb", "--info", archive])
    run(["sudo", "apt-get", "install", "--yes", str(archive)])
    smoke("/opt/spectrasuite/SpectraSuite")


def main():
    OUTPUT.mkdir(exist_ok=True)
    build_bundle()
    if sys.platform == "win32":
        windows()
    elif sys.platform == "darwin":
        macos()
    elif sys.platform.startswith("linux"):
        linux()
    else:
        raise RuntimeError(f"Unsupported packaging platform: {sys.platform}")
    suffix = f"{platform.system().lower()}-{platform.machine().lower()}"
    manifest = {
        "version": VERSION, "commit": os.environ.get("BUILD_COMMIT", ""),
        "platform": platform.platform(), "architecture": platform.machine(),
        "python": sys.version, "distribution_status": "installer-candidate",
        "publisher_signed": False, "apple_notarized": False,
    }
    (OUTPUT / f"build-{suffix}.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    dependencies = subprocess.check_output(
        [sys.executable, "-m", "pip", "freeze"], text=True)
    (OUTPUT / f"dependencies-{suffix}.txt").write_text(dependencies, encoding="utf-8")
    entries = []
    for artifact in sorted(OUTPUT.iterdir()):
        if artifact.is_file():
            with artifact.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            entries.append(f"{digest}  {artifact.name}")
    (OUTPUT / f"SHA256SUMS-{suffix}.txt").write_text(
        "\n".join(entries) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
