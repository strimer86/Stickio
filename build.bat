@echo off
setlocal
echo ============================================
echo   Modern Sticky Notes - Builder
echo ============================================
echo.

cd /d "%~dp0"

rem Иконку берут и сборщик (.spec), и инсталлятор (.iss) — ровно один файл
rem Noteit.ico в корне. Раньше здесь проверялся resources\icons\icon.ico:
rem он генерировался скриптом, но в сборку не попадал вообще, поэтому
rem сборка «с новой иконкой» ничего не меняла.
if not exist "Noteit.ico" (
    echo [1/3] [ERROR] Не найден Noteit.ico в корне проекта.
    echo        Это единственный источник иконки для .spec и .iss.
    pause
    exit /b 1
) else (
    echo [1/3] Icon found: Noteit.ico
)

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
