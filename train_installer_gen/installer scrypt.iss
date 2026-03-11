#define MyAppName "Sevue"
#define MyAppVersion "1.69"
#define MyAppPublisher "CodeWeevers"
#define MyAppURL "https://github.com/codeweevers/sevue"
#define MyAppExeName "Sevue.exe"

[Setup]
AppId={{A94B0FBA-82BB-45DD-AAFC-A58CC2FF2D21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName}
DisableWelcomePage=no
DisableDirPage=yes
DisableReadyMemo=yes
CloseApplications=yes
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
AllowCancelDuringInstall=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
OutputDir=release
OutputBaseFilename=sevue_installer
SetupIconFile=..\icons\favicon.ico
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\sevue\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\sevue\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "Install_SevueCam.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Uninstall_SevueCam.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "UnityCaptureFilter32.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "UnityCaptureFilter64.dll"; DestDir: "{app}"; Flags: ignoreversion


[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Flags: runmaximized
Name: "{autoprograms}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Flags: runmaximized excludefromshowinnewinstall
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Flags: runmaximized

[Run]
Filename: "{app}\Install_SevueCam.bat"; StatusMsg: "Installing virtual camera driver..."; Flags: runascurrentuser;
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent unchecked
[UninstallRun] 
Filename: "{app}\Uninstall_SevueCam.bat"; StatusMsg: "Uninstalling virtual camera driver..."; Flags: runascurrentuser
