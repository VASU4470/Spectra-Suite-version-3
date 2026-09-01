**SpectraSuite Version 3 - PySide6 Migration**

> **Migration status:** Version 3 is under active development. The launcher
> and FT-IR/XRD setup workflow are being migrated to PySide6. The existing
> plotting workspace remains temporarily on the legacy interface while its
> Matplotlib Qt canvas is completed. General Plotter is experimental and has
> not yet completed the same testing cycle as FT-IR and XRD.

**SpectraSuite - FT-IR and XRD Analysis (Pilot Study)**

Welcome to the SpectraSuite beta testing program! This software is being developed at UNAM/ICAT to simplify and enhance the pedagogical experience of analyzing FT-IR and XRD spectral data.

As part of our pilot study, we are asking students to download the software, test it using the provided sample spectra, and fill out a short usability survey. Your feedback is crucial and will remain anonymous.

## 📂 What is Included
* **SpectraSuite Application:** (Available for macOS and Windows in the [Releases](#) tab).
* **Sample Data:** 3 FT-IR spectra and 3 XRD spectra to help you test the modules.
* **Usability Survey:** A brief questionnaire to share your experience.

---

## 🚀 Installation Instructions

### 🍎 For macOS Users
1. Download the `SpectraSuite_Mac.dmg` file from the Releases section.
2. Double-click the `.dmg` file to open it.
3. Drag and drop the `SpectraSuite` app into your **Applications** folder.
4. **Bypass Apple Security (One-time step):** Because this is an academic beta version, you must clear Apple's quarantine flag to allow the app to run smoothly. 
   * Open your Mac's **Terminal** app (you can search for it in Spotlight).
   * Copy and paste the following command and press Enter:
     ```bash
     xattr -rc /Applications/SpectraSuite.app
     ```
   * *If you get a "Permission Denied" error, use this command instead:*
     ```bash
     sudo xattr -rc /Applications/SpectraSuite.app
     ```
     *(Note: When you press Enter, the Terminal will ask for your Mac login password. As you type, no characters or stars will appear on the screen. This is a standard macOS security feature; simply type your password blindly and press Enter).*
5. Go to your Applications folder and double-click SpectraSuite to launch it!
---
## 🪟 For Windows Users
1. Download the SpectraSuite_App_Windows.zip file from the Releases section.
2. Right-click the .zip file and select Extract All... to unzip it.
3. Move the extracted SpectraSuite folder to a preferred location on your computer (e.g., your Documents folder).
4. Open the folder and find the main SpectraSuite executable file (.exe).
5. First Launch: Right-click the executable and select Run as administrator.
6. Bypass Windows Defender (One-time step): Because this is an academic beta version without a commercial publisher certificate, Microsoft Defender SmartScreen will likely flag it.
7. When the blue "Windows protected your PC" screen appears, click the More info text right below the warning.
8. Then, click the Run anyway button that appears at the bottom.
9. Create a Shortcut: Right-click the executable and select "Create shortcut" (or "Pin to Start" / "Pin to Taskbar"). Drag the shortcut to your Desktop for easy access.
10. Double-click the shortcut to open the application! (Note: It takes about 10 seconds to load the scientific libraries into memory).
---

## 🧪 Testing Protocol
1. **Install** the software using the steps above.
2. **Download** the sample FT-IR and XRD files provided in this repository.
3. **Explore** the software by loading the sample data, zooming, and testing the available tools.
4. **Evaluate:** Once you have spent a few minutes using both modules, please complete our pilot study survey.

📝 **[Click Here to Take the Usability Survey] https://forms.gle/9f5SNrWEqNJdh2cy7 **

Thank you for contributing to UNAM/ICAT's educational research!
