@echo off
setlocal
set "PYTHONUTF8=1"
REM Interpreter fallback chain: env var -> pythoncore-3.15-64 -> py -3.15 -> python
if not defined PY set "PY=C:\Users\dexox\AppData\Local\Python\pythoncore-3.15-64\python.exe"
if exist "%PY%" goto :run
where py >nul 2>nul
if not errorlevel 1 (set "PY=py -3.15") else (set "PY=python")
:run
cd /d "%~dp0"
%PY% -X utf8 smoke_live.py %*
endlocal
