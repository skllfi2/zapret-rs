@echo off
REM Обновление zapret: проверка версии через наш Python-модуль (оригинальные .bat не вызываются)
cd /d "%~dp0"
REM C1: цепочка интерпретаторов — захардкоженный -> py -3.15 -> python.
REM %PYTHON% вызывается без кавычек: путь без пробелов, а "py -3.15" — это две команды.
set "PYTHON=C:\Users\dexox\AppData\Local\Python\pythoncore-3.15-64\python.exe"
if exist "%PYTHON%" goto :run
where py >nul 2>nul
if not errorlevel 1 (set "PYTHON=py -3.15") else (set "PYTHON=python")
:run
%PYTHON% -c "import json, service_manager; print(json.dumps(service_manager.check_updates(), ensure_ascii=False, indent=2))"
pause
