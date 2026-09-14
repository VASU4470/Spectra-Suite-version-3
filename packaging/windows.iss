#ifndef AppVersion
  #error AppVersion must be supplied by the build
#endif
#ifndef ProjectRoot
  #error ProjectRoot must be supplied by the build
#endif
[Setup]
AppId={{8D5D8406-9D57-4F26-A53C-5473C5F35F72}
AppName=SpectraSuite
AppVersion={#AppVersion}
AppPublisher=SpectraSuite
AppPublisherURL=https://github.com/VASU4470/Spectra-Suite-version-3
DefaultDirName={localappdata}\Programs\SpectraSuite
DefaultGroupName=SpectraSuite
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
LicenseFile={#ProjectRoot}\LICENSE
OutputDir={#ProjectRoot}\release-dist
OutputBaseFilename=SpectraSuite-{#AppVersion}-windows-x64-unsigned-setup
SetupIconFile={#ProjectRoot}\build\installer.ico
UninstallDisplayIcon={app}\SpectraSuite.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
[Files]
Source: "{#ProjectRoot}\dist\SpectraSuite\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\SpectraSuite"; Filename: "{app}\SpectraSuite.exe"
Name: "{group}\Uninstall SpectraSuite"; Filename: "{uninstallexe}"
[Run]
Filename: "{app}\SpectraSuite.exe"; Description: "Open SpectraSuite"; Flags: nowait postinstall skipifsilent
