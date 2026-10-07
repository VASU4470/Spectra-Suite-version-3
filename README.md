# SpectraSuite 3.5.0 — Scientific Data Analysis (Pilot/Test Release)

Welcome to the SpectraSuite testing program! This software is being developed at UNAM/ICAT to simplify and enhance the practical and pedagogical experience of plotting and analysing scientific data.

As part of testing, users are invited to download **SpectraSuite 3.5.0**, try the available workspaces, and share usability feedback. Your feedback is valuable for improving future releases.

> **Current public testing version:** SpectraSuite 3.5.0  
> **Release tag:** `v3.5.0-rc.1`  
> **Status:** Public test release / prerelease

## 📂 What is Included

* **SpectraSuite Application:** Available for macOS, Windows, and Ubuntu/Debian in the [SpectraSuite 3.5.0 release](https://github.com/VASU4470/Spectra-Suite-version-3/releases/tag/v3.5.0-rc.1).
* **Working workspaces:** FT-IR, XRD, UV-Vis, Raman, General 2D, and General 3D.
* **Preview workspaces:** XPS, LIBS, and Fluid Dynamics. These remain experimental and have documented limitations.
* **Image to Data:** Shared graph-image digitization tool.
* **Usability Survey:** A short questionnaire for sharing your experience.

For complete installation steps, see **[INSTALLATION.md](INSTALLATION.md)**.

---

## 🚀 Installation Instructions

### 🍎 For macOS Users

Choose the installer that matches your Mac:

* **Apple Silicon (M1/M2/M3 and newer):** `SpectraSuite-3.5.0-macos-arm64-unsigned.dmg`
* **Intel Mac:** `SpectraSuite-3.5.0-macos-x86_64-unsigned.dmg`

1. Download the correct `.dmg` file from the [SpectraSuite 3.5.0 release](https://github.com/VASU4470/Spectra-Suite-version-3/releases/tag/v3.5.0-rc.1).
2. Double-click the `.dmg` file to open it.
3. Drag **SpectraSuite** into your **Applications** folder.
4. Because this academic test build is currently unsigned and not notarized, macOS may block the first launch.
5. Try opening SpectraSuite from **Applications**. If macOS blocks it, use **System Settings → Privacy & Security → Open Anyway**, then confirm that you want to open the application.
6. Launch SpectraSuite from the Applications folder.

The `*-unsigned-update.pkg` files attached to the release are intended for the application's update workflow. For a first manual installation, use the `.dmg` file.

---

### 🪟 For Windows Users

1. Download `SpectraSuite-3.5.0-windows-x64-unsigned-setup.exe` from the [SpectraSuite 3.5.0 release](https://github.com/VASU4470/Spectra-Suite-version-3/releases/tag/v3.5.0-rc.1).
2. Double-click the installer.
3. Because this academic test build does not yet have a commercial publisher certificate, Microsoft Defender SmartScreen may display a warning.
4. If the warning appears, review the publisher/file information, click **More info**, and then choose **Run anyway** only if you downloaded the installer from the official SpectraSuite GitHub release above.
5. Follow the installer prompts.
6. Launch SpectraSuite from the Start menu or installed shortcut.

The application may take several seconds to load scientific libraries on first launch.

---

### 🐧 For Ubuntu / Debian Linux Users

1. Download `SpectraSuite-3.5.0-linux-amd64.deb` from the [SpectraSuite 3.5.0 release](https://github.com/VASU4470/Spectra-Suite-version-3/releases/tag/v3.5.0-rc.1).
2. Open a Terminal in the folder containing the downloaded file.
3. Install it with:

   ```bash
   sudo apt install ./SpectraSuite-3.5.0-linux-amd64.deb
   ```

4. Launch SpectraSuite from your desktop application menu.

---

## 🧪 Testing Protocol

1. **Install** SpectraSuite using the instructions above.
2. **Open** the application and explore the scientific workspace(s) relevant to you.
3. **Load data** and test common workflows such as plotting, zooming, data inspection, processing, analysis, annotations, and export where applicable.
4. **Check usability:** note anything confusing, difficult to find, visually unclear, or scientifically unexpected.
5. **Evaluate:** after using the application, please complete the pilot-study usability survey.

📝 **[Click Here to Take the Usability Survey](https://forms.gle/9f5SNrWEqNJdh2cy7)**

Thank you for contributing to UNAM/ICAT's educational and scientific-software research!

---

## ⚠️ Test Release Notice

SpectraSuite 3.5.0 is a public test release. Windows and macOS installers are currently unsigned, and the macOS packages are not notarized. Preview workspaces should not be treated as fully validated scientific modules.

Scientific data remains on the user's computer unless the user explicitly saves or exports it.
