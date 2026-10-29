@echo off
rem Живой e2e-smoke: шаг 1 (применение стратегии) или шаг 2 (реальный test zapret.ps1).
rem Права админа запросит сам скрипт (UAC). Примеры:
rem   smoke_live.bat
rem   smoke_live.bat --tests --yes
setlocal
set "PYTHONUTF8=1"
REM C1: цепочка интерпретаторов — захардкоженный -> py -3.15 -> python.
REM %PY% вызывается без кавычек: путь без пробелов, а "py -3.15" — это две команды.
set "PY=C:\Users\dexox\AppData\Local\Python\pythoncore-3.15-64\python.exe"
if exist "%PY%" goto :run
where py >nul 2>nul
if not errorlevel 1 (set "PY=py -3.15") else (set "PY=python")
:run
cd /d "%~dp0"
%PY% -X utf8 smoke_live.py %*
endlocal
