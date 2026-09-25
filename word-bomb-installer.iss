[Setup]
AppName=Word Bomb Tool
AppVersion=4.0.3
AppPublisher=mPhpMaster
AppPublisherURL=https://github.com/mPhpMaster/word-bomb-tool
AppSupportURL=https://github.com/mPhpMaster/word-bomb-tool
AppCopyright=Copyright © 2026 mPhpMaster
DefaultDirName={pf}\Word Bomb Tool
DefaultGroupName=Word Bomb Tool
DisableProgramGroupPage=no
AllowNoIcons=yes
LicenseFile=LICENSE
OutputBaseFilename=WordBombTool-Setup
OutputDir=dist
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\WordBombGUI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\WordBombCLI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ocr_config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "run.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "run-cli.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Word Bomb Tool"; Filename: "{app}\WordBombGUI.exe"
Name: "{userdesktop}\Word Bomb Tool"; Filename: "{app}\WordBombGUI.exe"
Name: "{group}\WordBomb CLI"; Filename: "{app}\WordBombCLI.exe"

[Run]
Filename: "{app}\WordBombGUI.exe"; Description: "Launch Word Bomb Tool"; Flags: nowait postinstall skipifsilent
