@echo off
REM Launch the Rust wikifier binary. Prefers WIKIFIER_BIN, then a local build, then cargo run.
REM No parenthesized blocks: %ERRORLEVEL% inside one expands before the command runs,
REM which used to turn every failure into exit code 0.
setlocal
set "HERE=%~dp0"
set "BIN=%WIKIFIER_BIN%"
if not defined BIN if exist "%HERE%target\release\wikifier.exe" set "BIN=%HERE%target\release\wikifier.exe"
if not defined BIN if exist "%HERE%target\debug\wikifier.exe" set "BIN=%HERE%target\debug\wikifier.exe"
if not defined BIN goto cargo
"%BIN%" %*
exit /b %ERRORLEVEL%
:cargo
cargo run --quiet --manifest-path "%HERE%Cargo.toml" -- %*
exit /b %ERRORLEVEL%
