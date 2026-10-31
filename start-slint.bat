@echo off
setlocal
cd /d "%~dp0"

set "EXE=zapret-slint\target\release\zapret-slint.exe"

if exist "%EXE%" goto :run

echo [zapret-simple] Building Slint release binary...
cargo build --release --manifest-path zapret-slint\Cargo.toml
if not exist "%EXE%" (
    echo [ERROR] Failed to build zapret-slint.exe.
    pause
    exit /b 1
)

:run
start "" "%EXE%" %*
endlocal
