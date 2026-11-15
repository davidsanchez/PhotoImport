; Installateur Windows (Inno Setup). Compilé par .github/workflows/release.yml
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{8E1B6C0E-5C0B-4C55-9D0A-7B6B6F4E2A11}
AppName=PhotoImport
AppVersion={#Version}
DefaultDirName={autopf}\PhotoImport
DefaultGroupName=PhotoImport
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=PhotoImport-{#Version}-windows-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\dist\PhotoImport\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\PhotoImport"; Filename: "{app}\PhotoImport.exe"
Name: "{autodesktop}\PhotoImport"; Filename: "{app}\PhotoImport.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PhotoImport.exe"; Description: "{cm:LaunchProgram,PhotoImport}"; Flags: nowait postinstall skipifsilent
