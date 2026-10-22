#define MyAppName "NOVAURA Launcher"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "NOVAURA"
#define MyAppExeName "NOVAURA.exe"

[Setup]
AppId={{E1A7906A-7EC7-4D3B-8E1C-7F1A7D6C921B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\NOVAURA Launcher
DefaultGroupName=NOVAURA Launcher
OutputDir=..\dist
OutputBaseFilename=NOVAURA-Setup
SetupIconFile=..\src\novaura\assets\novaura.ico
UninstallDisplayIcon={app}\NOVAURA.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные ярлыки:"; Flags: unchecked

[Files]
Source: "..\dist\NOVAURA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\NOVAURA Launcher"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\NOVAURA Launcher"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить NOVAURA Launcher"; Flags: postinstall nowait skipifsilent
