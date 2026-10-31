# Запуск zapret-simple на Rust + Slint
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$ExePath = Join-Path $ScriptDir "zapret-slint\target\release\zapret-slint.exe"

if (-not (Test-Path $ExePath)) {
    Write-Host "[zapret-simple] Сборка Slint-версии (Rust)..." -ForegroundColor Cyan
    cargo build --release --manifest-path (Join-Path $ScriptDir "zapret-slint\Cargo.toml")
}

if (Test-Path $ExePath) {
    if ($args.Count -gt 0) {
        Start-Process -FilePath $ExePath -ArgumentList $args
    } else {
        Start-Process -FilePath $ExePath
    }
} else {
    Write-Error "Не удалось найти или собрать zapret-slint.exe"
}
