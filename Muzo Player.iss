#define MyAppName "Muzo Player"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Muzo Player"
#define MyAppExeName "Muzo Player.exe"

[Setup]
AppId={{B7D6A4C2-8E4F-4B3A-9D2C-7A2026D00111}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}

DefaultDirName={autopf}\Muzo Player
DefaultGroupName=Muzo Player

OutputDir=E:\Claude\Muzo Player\installer
OutputBaseFilename=Muzo_Player_Setup_{#MyAppVersion}

SetupIconFile=E:\Claude\Muzo Player\Muzo Player.ico
UninstallDisplayIcon={app}\Muzo Player.exe

Compression=lzma2
SolidCompression=yes

WizardStyle=modern

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

PrivilegesRequired=admin

DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "E:\Claude\Muzo Player\dist\Muzo Player.exe"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; \
    Description: "Create a desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"; \
    Flags: unchecked

[Icons]
Name: "{autoprograms}\Muzo Player"; \
    Filename: "{app}\Muzo Player.exe"

Name: "{autodesktop}\Muzo Player"; \
    Filename: "{app}\Muzo Player.exe"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\Muzo Player.exe"; \
    Description: "Launch Muzo Player"; \
    Flags: nowait postinstall skipifsilent