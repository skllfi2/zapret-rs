# autostart.py — автозапуск zapret-simple при старте Windows (HKCU Run)
import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "zapret-simple"


def _get_exec_command() -> str:
    """Формирование командной строки запуска приложения в трей."""
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        return f'"{exe_path}" --minimized'
    # Python script mode
    from .paths import APP_DIR
    script = os.path.join(APP_DIR, "zapret_pyside.py")
    python_exe = sys.executable
    # Если запущен python.exe, лучше использовать pythonw.exe если доступен
    pythonw = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
    runner = pythonw if os.path.isfile(pythonw) else python_exe
    return f'"{runner}" "{script}" --minimized'


def is_autostart_enabled() -> bool:
    """Проверка, зарегистрировано ли приложение в автозагрузке текущего пользователя."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(val)
    except OSError:
        return False


def set_autostart_enabled(enabled: bool) -> tuple[bool, str]:
    """Включение или отключение автозагрузки в реестре Windows."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                cmd = _get_exec_command()
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                return True, "Автозагрузка с Windows включена."
            try:
                winreg.DeleteValue(key, APP_NAME)
            except OSError:
                pass
            return True, "Автозагрузка с Windows отключена."
    except OSError as e:
        return False, f"Ошибка реестра автозагрузки: {e}"


def toggle_autostart() -> bool:
    """Инвертировать текущий статус автозагрузки."""
    new_state = not is_autostart_enabled()
    set_autostart_enabled(new_state)
    return is_autostart_enabled()
