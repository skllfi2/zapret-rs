@echo off
REM Сборка zapret-simple в один exe (PyInstaller): dist\zapret-simple.exe
cd /d "%~dp0"
set PYTHON="C:\Users\dexox\AppData\Local\Python\pythoncore-3.15-64\python.exe"
%PYTHON% build_exe.py
pause
