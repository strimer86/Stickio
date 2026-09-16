; Stickio - Inno Setup Script
; Requires Inno Setup 6.x (https://jrsoftware.org/isinfo.php)

#define MyAppName      "Stickio"
#define MyAppVersion   "1.0.1"
#define MyAppPublisher "Stickio"
#define MyAppExeName   "Stickio.exe"
#define MyAppDescription "Sticky notes for Windows 11"
; Совпадает с RUN_KEY в services/settings.py
#define RunKey         "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
AppId={{B9A3D3E0-4F5C-4D7A-8E1B-6C2F9A0D3E5C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppDescription={#MyAppDescription}
DefaultDirName={autopf}\Stickio
DefaultGroupName={#MyAppName}
LicenseFile=
OutputDir=..\dist
OutputBaseFilename=Stickio_Setup_{#MyAppVersion}
SetupIconFile=..\Noteit.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverrideAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";              Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";         Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[UninstallRun]
; Приложение могло остаться висеть в трее с залоченной базой — снимаем
; процесс до удаления файлов, иначе WAL/SHM-файлы не дадут почистить каталог.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillStickio"

[Code]
{ Уборка следов, которые не лежат в {app}:
  - ключ автозапуска HKCU\Run\Stickio: без него Windows при каждом логоне
    пытается запустить удалённый exe и показывает ошибку;
  - по желанию пользователя — база заметок и журналы в %LOCALAPPDATA%\Stickio. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    if RegValueExists(HKEY_CURRENT_USER, '{#RunKey}', '{#MyAppName}') then
      RegDeleteValue(HKEY_CURRENT_USER, '{#RunKey}', '{#MyAppName}');

    DataDir := ExpandConstant('{localappdata}\{#MyAppName}');
    if DirExists(DataDir) then
    begin
      if MsgBox('Удалить заметки и журналы приложения?' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                'Нажмите «Нет», чтобы сохранить данные для повторной установки.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
