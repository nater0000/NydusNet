[Setup]
#define MyAppName "NydusNet"
#define MyAppVersion "1.0.0" ; This will be replaced by the build script
#define MyPublisher "NydusNet"
#define MyAppURL "https://github.com/nater0000/nydusnet"
#define MyInstallDir "NydusNet"
#define MyOutputDir "Output"
#define RootDir ""

SourceDir=..
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyInstallDir}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\NydusNet.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyAppName}_Installer_{#MyAppVersion}
SetupIconFile={#RootDir}\resources\images\nydusnet.ico
ChangesAssociations=yes
PrivilegesRequired=lowest

[Files]
; Main executable built by PyInstaller
Source: "{#RootDir}\dist\NydusNet.exe"; DestDir: "{app}"; Flags: ignoreversion

; Bundled data files and folders
Source: "{#RootDir}\dist\ansible\*"; DestDir: "{app}\ansible"; Flags: recursesubdirs createallsubdirs
Source: "{#RootDir}\dist\resources\syncthing\*"; DestDir: "{app}\resources\syncthing"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\NydusNet.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\NydusNet.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:";

[Run]
; Install OpenSSH Client (if missing) for the tunnel manager
Filename: "DISM.exe"; Parameters: "/Online /Add-Capability /CapabilityName:OpenSSH.Client~~~~0.0.1.0"; \
    Description: "Install OpenSSH Client (if missing)"; Flags: runhidden shellexec
Filename: "{app}\NydusNet.exe"; Description: "Launch NydusNet"; Flags: nowait postinstall shellexec
