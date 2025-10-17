[Setup]
#define MyAppName "NydusNet"
#define MyAppVersion "0.0.0" ; This is a placeholder; build.py will provide the real version
#define MyPublisher "NydusNet"
#define MyAppURL "https://github.com/nater0000/nydusnet"
#define MyInstallDir "NydusNet"
#define MyOutputDir "Output"
#define RootDir "{src}\..\.."

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
OutputDir={#RootDir}\{#MyOutputDir}
OutputBaseFilename={#MyAppName}_Installer_{#MyAppVersion}
SetupIconFile={#RootDir}\resources\images\nydusnet.ico
ChangesAssociations=yes
PrivilegesRequired=lowest

[Files]
; Main executable built by PyInstaller
Source: "{#RootDir}\dist\NydusNet.exe"; DestDir: "{app}"; Flags: ignoreversion

; Bundled data files and folders 
; Syncthing is now contained in the python app

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\NydusNet.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\NydusNet.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:";

[Run]
; Install OpenSSH Client (if missing) for the tunnel manager
Filename: "DISM.exe"; Parameters: "/Online /Add-Capability /CapabilityName:OpenSSH.Client~~~~0.0.1.0"; \
    Description: "Install OpenSSH Client (if missing)"; Flags: runhidden shellexec
; Launch the application after installation
Filename: "{app}\NydusNet.exe"; Description: "Launch NydusNet"; Flags: nowait postinstall shellexec