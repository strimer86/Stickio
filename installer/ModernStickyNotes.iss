; Stickio - Inno Setup Script
; Requires Inno Setup 6.x (https://jrsoftware.org/isinfo.php)
;
; Собирается не вручную, а из build.bat: он передаёт версию через
; /DMyAppVersion=... и путь к компилятору. При сборке вручную версия
; возьмётся из значения по умолчанию ниже.
;
; ВАЖНО: версия должна совпадать с version_info.txt в корне — build.bat
; это проверяет. Иначе инсталлятор и exe будут рассказывать о себе разное.

#ifndef MyAppVersion
  #define MyAppVersion "1.2.0"
#endif

#define MyAppName      "Stickio"
#define MyAppPublisher "Т.Е.А."
#define MyAppExeName   "Stickio.exe"
; Сайт автора. Показывается в мастере установки и в «Установленные приложения».
#define MyAppURL       "https://stickio.tumioai.ru"
; Совпадает с RUN_KEY в services/settings.py
#define RunKey         "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
AppId={{B9A3D3E0-4F5C-4D7A-8E1B-6C2F9A0D3E5C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
; AppVerName — то, что мастер установки показывает в заголовке и в
; «Установленные приложения». Без него там будет только имя.
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright=© {#MyAppPublisher}
; Версия в ресурсе самого Setup.exe. AppVersion её не заполняет: без этой
; строки в свойствах файла установщика «Версия файла» пустая, а в
; VS_FIXEDFILEINFO стоит 0.0.0.0 — при том что продукт заявляет свою версию.
VersionInfoVersion={#MyAppVersion}
; Права администратора по умолчанию: {autopf} тогда указывает на
; C:\Program Files, а не на %LOCALAPPDATA%\Programs. Это важно не только
; ради порядка — программа, живущая в AppData, выглядит для поведенческой
; эвристики антивируса хуже, потому что именно туда предпочитает ставиться
; вредоносное ПО, которому не нужны права администратора. Диалог выбора
; режима оставлен, так что установка без администратора по-прежнему возможна.
DefaultDirName={autopf}\Stickio
DefaultGroupName={#MyAppName}
OutputDir=..\dist
OutputBaseFilename=Stickio_Setup_{#MyAppVersion}
SetupIconFile=..\Noteit.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
; Имя директивы — именно OverridesAllowed (во множественном числе).
; В файле было PrivilegesRequiredOverrideAllowed — такой директивы нет,
; из-за неё компиляция и обрывалась.
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Приложение может висеть в трее с загруженными библиотеками — Setup
; закрывает его через Restart Manager, иначе файлы не перезаписать.
CloseApplications=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Папочная сборка кладёт все зависимости в {app}\_internal. При обновлении
; поверх старой версии там остались бы библиотеки, которых в новой сборке
; уже нет, — и приложение грузило бы их вместо свежих. Поэтому каталог
; зависимостей чистится перед распаковкой новых файлов. Данные пользователя
; здесь не лежат: база и журналы живут в %LOCALAPPDATA%\Stickio.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; Устанавливаем весь каталог сборки: exe, _internal с библиотеками и Qt,
; иконку и переводы. Без recursesubdirs подкаталог _internal не попал бы
; в установку, и приложение не запустилось бы вовсе.
Source: "..\dist\Stickio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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
// Уборка следов, которые не лежат в каталоге установки:
//   - ключ автозапуска HKCU\Run\Stickio: без него Windows при каждом логоне
//     пытается запустить удалённый exe и показывает ошибку;
//   - по желанию пользователя — база заметок и журналы в %LOCALAPPDATA%\Stickio.
//
// ВАЖНО: комментарий здесь именно строчный (//), а не в фигурных скобках.
// В фигурных скобках нельзя писать константы вида {app}: их закрывающая
// скобка обрывает комментарий, и компилятор падает с «'BEGIN' expected».
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
