@echo off
REM Launch the Rust wikifier binary.
setlocal
set "HERE=%~dp0"
if not "%WIKIFIER_BIN%"=="" ("%WIKIFIER_BIN%" %* & exit /b %ERRORLEVEL%)
if exist "%HERE%target\release\wikifier.exe" ("%HERE%target\release\wikifier.exe" %* & exit /b %ERRORLEVEL%)
if exist "%HERE%target\debug\wikifier.exe" ("%HERE%target\debug\wikifier.exe" %* & exit /b %ERRORLEVEL%)
cargo run --quiet --manifest-path "%HERE%Cargo.toml" -- %*
exit /b %ERRORLEVEL%
