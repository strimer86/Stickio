@echo off
setlocal
echo ============================================
echo   Modern Sticky Notes - Builder
echo ============================================
echo.

cd /d "%~dp0"

rem Иконка — нарисованный вручную Noteit.ico в корне, его берут и сборщик
rem (.spec), и инсталлятор (.iss), и widgets\sticky_note.py. Это
rem единственный источник: раньше рядом жил генерируемый черновик
rem (resources\icons), который в сборку не попадал вообще, только путал.
if not exist "Noteit.ico" (
    echo [1/3] [ERROR] Не найден Noteit.ico в корне проекта.
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
    echo [1/3] [ERROR] Noteit.ico подозрительно мал: %ICON_SIZE% байт.
    echo        Ожидается около 240 КБ — файл со всеми размерами от 16 до 256.
    echo        Похоже, иконку подменили. Восстановите её:
    echo            git checkout HEAD -- Noteit.ico
    pause
    exit /b 1
)
echo [1/3] Icon found: Noteit.ico (%ICON_SIZE% bytes)

echo [2/3] Building .exe with PyInstaller...
rem --clean здесь не используем: в этой среде PyInstaller падает на
rem удалении base_library.zip (файл уходит в корзину и не удаляется).
pyinstaller --noconfirm ModernStickyNotes.spec
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Build complete.
echo Output: dist\Stickio.exe
echo.
echo To create installer, open installer\ModernStickyNotes.iss in Inno Setup.
echo.
pause
