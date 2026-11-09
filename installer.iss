; XmelTunnel per-user installer (Inno Setup 6 or 7). Built by build.py, which passes the defines below.
; No admin rights: installs into %LOCALAPPDATA%\Programs\XmelTunnel.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "igorxmel"
#endif
#ifndef AppURL
  #define AppURL "https://github.com/igorxmel/XmelTunnel"
#endif

[Setup]
AppId={{6F1C2A7E-3B9D-4C55-9E21-58A4D0C7B3E1}
AppName=XmelTunnel
AppVersion={#AppVersion}
AppVerName=XmelTunnel {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
AppCopyright=Copyright (C) 2026 {#AppPublisher}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=XmelTunnel installer
VersionInfoProductName=XmelTunnel
DefaultDirName={localappdata}\Programs\XmelTunnel
DefaultGroupName=XmelTunnel
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=XmelTunnel-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\XmelTunnel.exe
UninstallDisplayName=XmelTunnel
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; The app holds this mutex while running: setup and uninstall ask to close it first.
AppMutex=XmelTunnelAppMutex
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\XmelTunnel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\XmelTunnel"; Filename: "{app}\XmelTunnel.exe"
Name: "{autodesktop}\XmelTunnel"; Filename: "{app}\XmelTunnel.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\XmelTunnel.exe"; Description: "{cm:LaunchProgram,XmelTunnel}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Undo everything the app changed on this PC: Windows PAC, Claude Code proxy, autostart, settings.
Filename: "{app}\XmelTunnel.exe"; Parameters: "--uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "XmelTunnelCleanup"
