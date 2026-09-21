#ifndef MyAppVersion
  #define MyAppVersion "1.0.1"
#endif

[Setup]
AppId={{D80A1191-3131-4C4D-8E4A-2EAF133A6BD4}
AppName=DeepXII Tools
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\DeepXII Tools
DefaultGroupName=DeepXII Tools
OutputDir=release
OutputBaseFilename=DeepXII-Tools-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=DeepXII Tools

[Files]
Source: "dist\DeepXIITools\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DeepXII Tools"; Filename: "{app}\DeepXIITools.exe"
Name: "{autodesktop}\DeepXII Tools"; Filename: "{app}\DeepXIITools.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\DeepXIITools.exe"; Description: "Launch DeepXII Tools"; Flags: nowait postinstall skipifsilent
