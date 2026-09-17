@echo off
rem Русский текст ниже в UTF-8. Без этой строки cmd читает .bat в OEM-кодировке
rem и выводит вместо букв мусор, поэтому переключаем консоль на UTF-8.
chcp 65001 >nul
setlocal
echo ============================================
echo   Stickio - сборка приложения и инсталлятора
echo ============================================
echo.

cd /d "%~dp0"

rem Версия приложения. ЕДИНСТВЕННОЕ место, где она задаётся для сборки:
rem отсюда уходит и в метаданные exe (сверяется с version_info.txt), и в
rem инсталлятор.
set "APP_VERSION=1.1.0"

rem Иконка — нарисованный вручную Noteit.ico в корне, его берут и сборщик
rem (.spec), и инсталлятор (.iss), и widgets\sticky_note.py. Это
rem единственный источник: раньше рядом жил генерируемый черновик
rem (resources\icons), который в сборку не попадал вообще, только путал.
if not exist "Noteit.ico" (
    echo [1/4] [ERROR] Не найден Noteit.ico в корне проекта.
    echo        Это единственный источник иконки для .spec и .iss.
    pause
    exit /b 1
)

rem Размер — грубая, но полезная страховка. Рабочая иконка занимает ~240 КБ:
rem это изображение со всеми девятью размерами. Файл в единицы килобайт
rem означает, что её подменили — так уже было, иконку потом восстанавливали
rem из истории git. Лучше остановить сборку, чем выпустить exe с чужой иконкой.
for %%A in ("Noteit.ico") do set ICON_SIZE=%%~zA
if %ICON_SIZE% LSS 50000 (
    echo [1/4] [ERROR] Noteit.ico подозрительно мал: %ICON_SIZE% байт.
    echo        Ожидается около 240 КБ — файл со всеми размерами от 16 до 256.
    echo        Похоже, иконку подменили. Восстановите её:
    echo            git checkout HEAD -- Noteit.ico
    pause
    exit /b 1
)
echo [1/4] Иконка на месте: Noteit.ico (%ICON_SIZE% байт)

rem Версия живёт в трёх местах: APP_VERSION здесь, version_info.txt
rem (метаданные exe) и services\app_info.py (VERSION_FALLBACK — для запуска
rem из исходников). Расходятся они молча: инсталлятор показал бы одну
rem версию, свойства файла другую, а окно «О программе» третью. Поэтому
rem сверяем то, что проверяется здесь, и останавливаемся при расхождении;
rem пару version_info.txt <-> app_info.py проверяет tests\test_app_info.py.
findstr /c:"%APP_VERSION%.0" version_info.txt >nul
if errorlevel 1 (
    echo [2/4] [ERROR] Версия в version_info.txt не совпадает с APP_VERSION=%APP_VERSION%.
    echo        Поправьте в version_info.txt поля filevers, FileVersion и ProductVersion
    echo        или значение APP_VERSION в этом файле — они обязаны совпадать.
    pause
    exit /b 1
)
echo [2/4] Версия %APP_VERSION% — совпадает с version_info.txt

echo [3/4] Сборка приложения (PyInstaller, папочный режим)...
rem --clean здесь не используем: в этой среде PyInstaller падает на
rem удалении base_library.zip (файл уходит в корзину и не удаляется).
where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Не найден pyinstaller в PATH.
    echo        Установите его: pip install pyinstaller
    pause
    exit /b 1
)
pyinstaller --noconfirm ModernStickyNotes.spec
if errorlevel 1 (
    echo.
    echo [ERROR] Сборка PyInstaller не удалась.
    pause
    exit /b 1
)
echo        Готово: dist\Stickio\Stickio.exe

echo [4/4] Сборка инсталлятора (Inno Setup)...
rem Ищем компилятор Inno Setup: сначала 6, затем 7. ProgramFiles(x86)
rem вынесен в переменную — скобки в имени при подстановке прямо в команду
rem ломают разбор строки.
set "PF86=%ProgramFiles(x86)%"
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%PF86%\Inno Setup 6\ISCC.exe" set "ISCC=%PF86%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%PF86%\Inno Setup 7\ISCC.exe" set "ISCC=%PF86%\Inno Setup 7\ISCC.exe"

if not defined ISCC (
    echo.
    echo [ERROR] Не найден ISCC.exe — компилятор Inno Setup.
    echo        Установите Inno Setup 6 или 7: https://jrsoftware.org/isinfo.php
    echo        Приложение уже собрано, инсталлятор можно сделать вручную:
    echo            откройте installer\ModernStickyNotes.iss
    pause
    exit /b 1
)

"%ISCC%" /DMyAppVersion=%APP_VERSION% installer\ModernStickyNotes.iss
if errorlevel 1 (
    echo.
    echo [ERROR] Сборка инсталлятора не удалась.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Готово
echo ============================================
echo   Приложение:  dist\Stickio\Stickio.exe
echo   Инсталлятор: dist\Stickio_Setup_%APP_VERSION%.exe
echo.
pause
