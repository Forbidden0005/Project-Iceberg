@echo off
title Project Iceberg - Dependency Check
cd /d "%~dp0"

echo.
echo  ==========================================
echo   PROJECT ICEBERG  --  local-first AI
echo  ==========================================
echo.

:: ── Python check ─────────────────────────────────────────────
echo [checking] Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [error] Python not found. Install Python 3.10+ and add it to PATH.
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo.

:: ── Node.js/npx check (for MCP servers) ──────────────────────
:: Skipped - npx check can hang in batch files on some systems
:: MCP servers are optional and will auto-connect if npx is available
echo [skip] Node.js / npx check (optional - MCP servers will try to connect on startup)
echo.

:: ── Python package dependency check ──────────────────────────
echo [checking] Python packages from requirements.txt...
echo.

setlocal enabledelayedexpansion
set MISSING_PACKAGES=
set MISSING_COUNT=0

:: Check each core package
call :check_package "requests" "requests"
call :check_package "flask" "flask"
call :check_package "mcp" "mcp"

:: Optional packages (don't block on these)
echo [checking] Optional packages (voice mode)...
python -c "import speech_recognition" >nul 2>&1
if errorlevel 1 (
    echo [skip] SpeechRecognition not installed (optional - for voice mode^)
) else (
    echo [ok] SpeechRecognition installed
)

python -c "import pyttsx3" >nul 2>&1
if errorlevel 1 (
    echo [skip] pyttsx3 not installed (optional - for voice mode^)
) else (
    echo [ok] pyttsx3 installed
)

python -c "import pyaudio" >nul 2>&1
if errorlevel 1 (
    echo [skip] pyaudio not installed (optional - for voice mode^)
) else (
    echo [ok] pyaudio installed
)

echo.

:: ── Install missing packages if needed ───────────────────────
if !MISSING_COUNT! gtr 0 (
    echo [error] Missing %MISSING_COUNT% required package(s^):
    echo !MISSING_PACKAGES!
    echo.
    choice /C YN /M "Install missing packages now"
    if errorlevel 2 (
        echo.
        echo [abort] Cannot start without required packages.
        echo         Run: pip install -r requirements.txt
        pause
        exit /b 1
    )
    
    echo.
    echo [installing] Running: pip install -r requirements.txt
    echo.
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [error] Package installation failed.
        echo         Try manually: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo.
    echo [ok] All packages installed successfully!
    echo.
)

endlocal

:: ── All checks passed - starting server ──────────────────────
echo [ok] All dependencies satisfied!
echo.

:: Open browser after server warms up
start /B cmd /C "timeout /t 5 /nobreak >nul && start http://localhost:5000"

echo  Server  : http://localhost:5000
echo  Ctrl+C  : stop
echo.

:: Start server
python server.py

echo.
echo  Project Iceberg stopped.
pause
exit /b 0

:: ── Helper function to check a package ───────────────────────
:check_package
set PKG_NAME=%~1
set PKG_IMPORT=%~2

python -c "import %PKG_IMPORT%" >nul 2>&1
if errorlevel 1 (
    echo [missing] %PKG_NAME%
    set MISSING_PACKAGES=!MISSING_PACKAGES! %PKG_NAME%
    set /a MISSING_COUNT+=1
) else (
    echo [ok] %PKG_NAME%
)
goto :eof
