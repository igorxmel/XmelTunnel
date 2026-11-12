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
; Silent install = an update started by the app itself: start it again (with its window state).
Filename: "{app}\XmelTunnel.exe"; Parameters: "--restarted {param:XTARGS|}"; Flags: nowait skipifnotsilent

[UninstallRun]
; Undo everything the app changed on this PC: Windows PAC, Claude Code proxy, autostart, settings.
Filename: "{app}\XmelTunnel.exe"; Parameters: "--uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "XmelTunnelCleanup"

[CustomMessages]
en.UpdateCaption=Update — XmelTunnel {#AppVersion}
ru.UpdateCaption=Обновление — XmelTunnel {#AppVersion}
en.UpdateTitle=Update XmelTunnel
ru.UpdateTitle=Обновление XmelTunnel
en.UpdateText=XmelTunnel will be updated to version {#AppVersion}. Your settings, profiles and lists stay as they are.
ru.UpdateText=XmelTunnel обновится до версии {#AppVersion}. Настройки, профили и списки останутся как есть.
en.UpdateButton=Update
ru.UpdateButton=Обновить
en.UpdateDone=XmelTunnel is updated
ru.UpdateDone=XmelTunnel обновлён

[Code]
function IsUpgrade: Boolean;
begin
  Result := RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F1C2A7E-3B9D-4C55-9E21-58A4D0C7B3E1}_is1');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { an update: the license was accepted at install time, the folder and shortcuts are already chosen }
  Result := IsUpgrade and ((PageID = wpLicense) or (PageID = wpSelectDir) or (PageID = wpSelectTasks));
end;

procedure InitializeWizard;
begin
  if IsUpgrade then
    WizardForm.Caption := CustomMessage('UpdateCaption');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if not IsUpgrade then
    Exit;
  if CurPageID = wpReady then
  begin
    WizardForm.PageNameLabel.Caption := CustomMessage('UpdateTitle');
    WizardForm.PageDescriptionLabel.Caption := CustomMessage('UpdateText');
    WizardForm.NextButton.Caption := CustomMessage('UpdateButton');
  end;
  if CurPageID = wpFinished then
    WizardForm.FinishedHeadingLabel.Caption := CustomMessage('UpdateDone');
end;

