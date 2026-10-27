# scm.py — установка/запуск/остановка службы zapret (SCM, pywin32 + sc)
import os, subprocess
import win32serviceutil, win32service
from i18n import t
from .paths import SERVICE_NAME, SERVICE_DISPLAY, get_bin_path

def install_service(exe_path=None):
    if exe_path is None:
        exe_path = get_bin_path()
    if not os.path.isfile(exe_path):
        return False, f"Binary not found: {exe_path}"
    if exe_path.lower().endswith(".bat"):
        # .bat не может быть binPath службы (SCM вернёт 1053) — честный отказ вместо тихой ошибки
        return False, t("sm.bat_as_bin", exe=exe_path)
    try:
        # sc требует пробел после "binPath=" — значение отдельным токеном с пробелом
        res = subprocess.run(["sc", "create", SERVICE_NAME, "binPath= " + exe_path, "start=", "demand"],
                             capture_output=True, text=True, errors="replace", creationflags=0x08000000)
        return res.returncode == 0, (res.stdout or res.stderr or "SCM create OK").strip()
    except Exception as e:
        return False, str(e)

def uninstall_service():
    try:
        win32serviceutil.RemoveService(SERVICE_NAME)
        return True, "Service removed (SCM)"
    except Exception as e:
        return False, str(e)

def start_service():
    try:
        win32serviceutil.StartService(SERVICE_NAME)
        return True, "Service started"
    except Exception as e:
        return False, str(e)

def stop_service():
    try:
        win32serviceutil.StopService(SERVICE_NAME)
        return True, "Service stopped"
    except Exception as e:
        return False, str(e)

# QueryServiceStatus возвращает (type, state, controls, ...):
# [0] = тип (SERVICE_WIN32_OWN_PROCESS=16), [1] = состояние (RUNNING=4 и т.д.)
SERVICE_STATES = {
    win32service.SERVICE_STOPPED: "Stopped",
    win32service.SERVICE_START_PENDING: "Start pending",
    win32service.SERVICE_STOP_PENDING: "Stop pending",
    win32service.SERVICE_RUNNING: "Running",
    win32service.SERVICE_CONTINUE_PENDING: "Continue pending",
    win32service.SERVICE_PAUSE_PENDING: "Pause pending",
    win32service.SERVICE_PAUSED: "Paused",
}

def query_status():
    try:
        status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        state = status[1]
        return SERVICE_STATES.get(state, f"State={state}")
    except Exception as e:
        return f"Not installed / error: {e}"

def is_running():
    """Единственный источник правды «служба запущена?» — используем везде."""
    return query_status() == "Running"

def set_autostart(enable=True):
    try:
        cmd = ["sc", "config", SERVICE_NAME, "start=", "auto" if enable else "demand"]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", creationflags=0x08000000)
        return res.returncode == 0, res.stdout + res.stderr
    except Exception as e:
        return False, str(e)
