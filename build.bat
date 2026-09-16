@echo off
setlocal
echo ============================================
echo   Modern Sticky Notes - Builder
echo ============================================
echo.

cd /d "%~dp0"

if not exist "resources\icons\icon.ico" (
    echo [1/3] Generating icon...
    python resources\icons\generate_icon.py
) else (
    echo [1/3] Icon exists, skipping.
)

echo [2/3] Building .exe with PyInstaller...
pyinstaller --clean --noconfirm ModernStickyNotes.spec
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