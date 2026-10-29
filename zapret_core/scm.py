# scm.py — установка/запуск/остановка службы zapret (SCM, pywin32 + sc)
import os
import subprocess
import time

import win32service
import win32serviceutil

from i18n import t

from .misc import decode_output
from .paths import BIN_DIR, SERVICE_NAME


def install_service(exe_path: str | None = None, exe_args: str | None = None) -> tuple[bool, str]:
    """Установка службы как в оригинальном :service_install: binPath = winws.exe + ARGS
    (последняя применённая/дефолтная стратегия), start=auto. Сам запуск — отдельно
    (кнопка «Запустить»), как и в оригинале (sc create ...; sc start отдельно)."""
    from .strategies import current_strategy, default_strategy  # локально: цикл импортов
    if exe_path is None:
        exe_path = os.path.join(BIN_DIR, "winws.exe")
        if exe_args is None:
            sid = current_strategy() or default_strategy()
            if sid:
                from .strategies import parse_strategy_args
                args, _ = parse_strategy_args(sid)
                if args:
                    from .strategies import format_exe_args
                    exe_args = format_exe_args(args)
    if not os.path.isfile(exe_path):
        return False, f"Binary not found: {exe_path}"
    if exe_path.lower().endswith(".bat"):
        # .bat не может быть binPath службы (SCM вернёт 1053) — честный отказ вместо тихой ошибки
        return False, t("sm.bat_as_bin", exe=exe_path)
    binpath = f'"{exe_path}"' + (f" {exe_args}" if exe_args else "")
    try:
        # sc требует пробел после "binPath=" — значение отдельным токеном с пробелом
        res = subprocess.run(["sc", "create", SERVICE_NAME, "binPath= " + binpath,
                              "start=", "auto"],
                             capture_output=True, creationflags=0x08000000)
        out = decode_output(res.stdout or res.stderr or b"SCM create OK").strip()
        return res.returncode == 0, out
    except Exception as e:
        return False, str(e)

def uninstall_service() -> tuple[bool, str]:
    """Удаление службы: сначала остановка с ожиданием (RemoveService сама по себе
    не останавливает — служба осталась бы запущена без binPath), затем RemoveService
    с реальной проверкой, что служба исчезла из SCM."""
    SERVICE_STOPPED = win32service.SERVICE_STOPPED
    try:
        status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)
    except Exception:
        status = None  # службы нет — просто удаляем (RemoveService сообщит сама)
    if status is not None and status[1] != SERVICE_STOPPED:
        try:
            win32serviceutil.StopService(SERVICE_NAME)
        except Exception:
            pass  # могла остановиться сама — решит проверка ниже
        for _ in range(20):  # ждём остановки, до 10 с
            time.sleep(0.5)
            try:
                if win32serviceutil.QueryServiceStatus(SERVICE_NAME)[1] == SERVICE_STOPPED:
                    break
            except Exception:
                break  # исчезла из SCM раньше времени — это успех
        else:
            return False, t("sm.remove_stop_failed")
    try:
        win32serviceutil.RemoveService(SERVICE_NAME)
    except Exception as e:
        return False, str(e)
    try:
        win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        return False, "Service still registered after RemoveService"
    except Exception:
        return True, "Service removed (SCM)"

def start_service() -> tuple[bool, str]:
    try:
        win32serviceutil.StartService(SERVICE_NAME)
        return True, "Service started"
    except Exception as e:
        return False, str(e)

def stop_service() -> tuple[bool, str]:
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

def query_status() -> str:
    try:
        status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        state = status[1]
        return SERVICE_STATES.get(state, f"State={state}")
    except Exception as e:
        return f"Not installed / error: {e}"

def is_running() -> bool:
    """Единственный источник правды «служба запущена?» — используем везде."""
    return query_status() == "Running"

def set_autostart(enable: bool = True) -> tuple[bool, str]:
    try:
        cmd = ["sc", "config", SERVICE_NAME, "start=", "auto" if enable else "demand"]
        res = subprocess.run(cmd, capture_output=True, creationflags=0x08000000)
        out = decode_output(res.stdout) + decode_output(res.stderr)
        return res.returncode == 0, out
    except Exception as e:
        return False, str(e)
