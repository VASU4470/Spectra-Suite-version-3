# SpectraSuite 3.5.0 — Installation Instructions

These instructions are for the public test release **SpectraSuite 3.5.0** (`v3.5.0-rc.1`).

Download installers only from the official release page:

https://github.com/VASU4470/Spectra-Suite-version-3/releases/tag/v3.5.0-rc.1

No Python installation, Git installation, or GitHub sign-in is required to use the packaged application.

## 🍎 macOS

Choose the file that matches your Mac:

| Mac type | First-install file |
| --- | --- |
| Apple Silicon (M1/M2/M3 and newer) | `SpectraSuite-3.5.0-macos-arm64-unsigned.dmg` |
| Intel Mac | `SpectraSuite-3.5.0-macos-x86_64-unsigned.dmg` |

### Install

1. Download the correct `.dmg` file.
2. Double-click the downloaded DMG.
3. Drag **SpectraSuite** into the **Applications** folder.
4. Eject the mounted SpectraSuite disk image.
5. Open **Applications** and launch SpectraSuite.

### If macOS blocks the first launch

The current test build is unsigned and not notarized, so macOS Gatekeeper may display a security warning.

1. Try to open SpectraSuite once.
2. Open **System Settings → Privacy & Security**.
3. Find the message stating that SpectraSuite was blocked.
4. Choose **Open Anyway**.
5. Confirm the prompt and launch SpectraSuite again.

Use these steps only for a copy downloaded from the official SpectraSuite GitHub release.

### About the PKG files

The release also contains:

* `SpectraSuite-3.5.0-macos-arm64-unsigned-update.pkg`
* `SpectraSuite-3.5.0-macos-x86_64-unsigned-update.pkg`

These packages are intended for the application's update workflow. For a normal first installation, use the DMG.

---

## 🪟 Windows x64

Download:

`SpectraSuite-3.5.0-windows-x64-unsigned-setup.exe`

### Install

1. Download the setup file from the official release page.
2. Double-click the installer.
3. Follow the installation prompts.
4. Launch SpectraSuite from the Start menu or installed shortcut.

### If Microsoft Defender SmartScreen appears

Because the current academic test installer is unsigned, Windows may display **Windows protected your PC**.

1. Confirm that you downloaded the installer from the official SpectraSuite GitHub release.
2. Click **More info**.
3. Review the displayed file information.
4. Choose **Run anyway** if you want to continue.
5. Complete the installer normally.

The application can take several seconds to start while its scientific libraries are loaded.

---

## 🐧 Ubuntu / Debian x64

Download:

`SpectraSuite-3.5.0-linux-amd64.deb`

Open a Terminal in the download folder and run:

```bash
sudo apt install ./SpectraSuite-3.5.0-linux-amd64.deb
```

Then launch SpectraSuite from the desktop application menu.

---

## ✅ After Installation

For a basic installation check:

1. Launch SpectraSuite.
2. Confirm that the Home screen opens.
3. Open one of the working workspaces such as FT-IR, XRD, UV-Vis, Raman, General 2D, or General 3D.
4. Import a supported data file.
5. Confirm that plotting and normal interaction work.
6. Test an export if you are participating in the pilot/test program.

XPS, LIBS, and Fluid Dynamics are preview workspaces and should be treated accordingly.

---

## 📝 Usability Survey

After testing SpectraSuite, please share your experience:

**[SpectraSuite Usability Survey](https://forms.gle/9f5SNrWEqNJdh2cy7)**

Thank you for contributing to UNAM/ICAT's educational and scientific-software research.
