@echo off
REM Обновление zapret: проверка версии через наш Python-модуль (оригинальные .bat не вызываются)
cd /d "%~dp0"
set PYTHON="C:\Users\dexox\AppData\Local\Python\pythoncore-3.15-64\python.exe"
%PYTHON% -c "import json, service_manager; print(json.dumps(service_manager.check_updates(), ensure_ascii=False, indent=2))"
pause
