@echo off
REM wikifier.bat — Wikifier Windows launcher
REM Delegates to PowerShell for the real implementation (zero external deps).

setlocal

set SCRIPT_DIR=%~dp0

echo Wikifier (Windows)
echo.

if exist "%SCRIPT_DIR%wikifier.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%wikifier.ps1" %*
) else (
    echo [WARNING] wikifier.ps1 not found.
    echo Falling back to basic help...
    echo.
    echo Recommended: Use WSL / Git Bash / MSYS2 and run ./wikifier.sh directly.
    echo Full cross-platform support is in wikifier.sh (bash).
    echo.
    echo Available via PowerShell:
    echo   .\wikifier.ps1 help
    echo   .\wikifier.ps1 check-changes
    echo   .\wikifier.ps1 record-change "path\to\file" "reason here"
)

endlocal
