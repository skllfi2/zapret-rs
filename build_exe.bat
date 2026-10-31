@echo off
REM Zapret Simple - PyInstaller single-exe build
cd /d "%~dp0"
REM Interpreter fallback chain: env var -> pythoncore-3.15-64 -> py -3.15 -> python
if not defined PYTHON set "PYTHON=C:\Users\dexox\AppData\Local\Python\pythoncore-3.15-64\python.exe"
if exist "%PYTHON%" goto :run
where py >nul 2>nul
if not errorlevel 1 (set "PYTHON=py -3.15") else (set "PYTHON=python")
:run
%PYTHON% build_exe.py
pause
