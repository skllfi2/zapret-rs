@echo off
REM Обновление из вне — командой, без интерфейса
REM Вызывает оригинальный service.bat check_updates
cd /d "C:\Users\dexox\Pictures\zapret-discord-youtube"
call service.bat check_updates
echo Обновление запущено. Проверьте вывод.
pause
