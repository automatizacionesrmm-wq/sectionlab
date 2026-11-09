; Inno Setup script for the SectionLab Windows installer (spec S20).
;
; Installs the frozen runtime once and updates it in place, so a new version is installed
; by running the new setup over the old one: no folder to unzip and preferences survive.
; Built by tools/build_windows.ps1 and by .github/workflows/windows-build.yml with
;   ISCC.exe /DAppVersion=<version> packaging\sectionlab.iss
; The bundle must already exist in dist\SectionLab (PyInstaller plus tools/assemble_app.py).

#define AppName "SectionLab"
#define AppExeName "SectionLab.exe"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppSourceDir "..\dist\SectionLab"

[Setup]
; A stable AppId is what makes an install upgrade the previous version instead of
; appearing as a second product.
AppId={{7C4B2F19-38E5-4A62-9F0B-2D6E8A1C55B3}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=SectionLab
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=SectionLab-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Everything lands under the user profile, so installing and upgrading need no admin rights.
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#AppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
