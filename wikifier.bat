@echo off
REM wikifier.bat — thin Windows launcher: python -m wikifier <command> [args]
setlocal
set "HERE=%~dp0"
if exist "%HERE%wikifier\__init__.py" set "PYTHONPATH=%HERE%;%PYTHONPATH%"
if exist "%HERE%..\..\wikifier\__init__.py" set "PYTHONPATH=%HERE%..\..;%PYTHONPATH%"
if "%WIKIFIER_PYTHON%"=="" (set "PY=python") else (set "PY=%WIKIFIER_PYTHON%")
"%PY%" -m wikifier %*
exit /b %ERRORLEVEL%
