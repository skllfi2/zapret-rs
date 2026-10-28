@echo off
rem Живой e2e-smoke: шаг 1 (применение стратегии) или шаг 2 (реальный test zapret.ps1).
rem Права админа запросит сам скрипт (UAC). Примеры:
rem   smoke_live.bat
rem   smoke_live.bat --tests --yes
setlocal
set "PYTHONUTF8=1"
set "PY=C:\Users\dexox\AppData\Local\Python\pythoncore-3.15-64\python.exe"
if not exist "%PY%" set "PY=python"
cd /d "%~dp0"
"%PY%" -X utf8 smoke_live.py %*
endlocal
