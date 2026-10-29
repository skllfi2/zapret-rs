# strategies.py — разбор стратегий (*.bat) и применение их к службе zapret
import os
import re
import shlex
import time

import win32service
import win32serviceutil

from i18n import t

from .misc import is_admin
from .paths import (
    BIN_DIR,
    LEGACY_STRATEGY_FILE,
    LISTS_DIR,
    ORIG_DIR,
    SERVICE_DISPLAY,
    SERVICE_NAME,
    STRATEGY_FILE,
)
from .scm import is_running, query_status
from .settings import game_filter_status

# === СТРАТЕГИИ: разбор .bat и применение к службе (как :service_install в service.bat) ===

def list_strategies() -> list[str]:
    """Реальные стратегии = .bat файлы каталога zapret (кроме service*)."""
    try:
        return [os.path.splitext(f)[0] for f in sorted(os.listdir(ORIG_DIR))
                if f.lower().endswith(".bat") and not f.lower().startswith("service")]
    except OSError:
        return []

def default_strategy() -> str | None:
    """Стратегия по умолчанию: general, иначе первая из списка."""
    all_strats = list_strategies()
    if "general" in all_strats:
        return "general"
    return all_strats[0] if all_strats else None

def _game_filter_ranges() -> tuple[str, str]:
    """Эффективные диапазоны как в :game_switch_status: для выключенного направления — 12
    (заглушка: winws получает порт, на котором трафика нет)."""
    gf = game_filter_status()
    mode, tcp, udp = gf.get("mode", "disabled"), gf.get("tcp", "1024-65535"), gf.get("udp", "1024-65535")
    if mode == "all":
        return tcp, udp
    if mode == "tcp":
        return tcp, "12"
    if mode == "udp":
        return "12", udp
    return "12", "12"

def parse_strategy_args(strategy_id: str) -> tuple[list[str] | None, str | None]:
    """Разбирает выбранный .bat и возвращает список аргументов winws.exe.
    Понимает продолжения строк через ^, кавычки и переменные %BIN%/%LISTS%/%GameFilter*%."""
    bat = os.path.join(ORIG_DIR, strategy_id + ".bat")
    if not os.path.isfile(bat):
        return None, t("sm.strategy_not_found", p=bat)
    try:
        with open(bat, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return None, str(e)
    # Склеиваем продолжения строк (caret) и вырезаем служебные строки
    logical = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("::") or line.startswith("@") or line.startswith("REM"):
            continue
        if line.endswith("^"):
            logical.append(line[:-1].rstrip())
            continue
        if logical:
            logical.append(line)
            logical_text = " ".join(logical)
            logical = []
        else:
            logical_text = line
        if "winws.exe" not in logical_text:
            continue
        # Нашли строку запуска — отрезаем всё до winws.exe"
        m = re.search(r'winws\.exe"\s*(.*)$', logical_text, re.IGNORECASE)
        if not m:
            continue
        args_str = m.group(1)
        tcp, udp = _game_filter_ranges()
        bin_dir = BIN_DIR.rstrip("\\") + "\\"
        lists_dir = LISTS_DIR.rstrip("\\") + "\\"
        for var, val in [("%BIN%", bin_dir), ("%LISTS%", lists_dir),
                         ("%GameFilterTCP%", tcp), ("%GameFilterUDP%", udp),
                         ("%~dp0", ORIG_DIR.rstrip("\\") + "\\")]:
            args_str = args_str.replace(var, val)
        return shlex.split(args_str, posix=False), None
    return None, t("sm.strategy_no_winws", s=strategy_id)

def format_exe_args(args: list[str]) -> str:
    """Строка аргументов winws.exe для binPath службы: аргументы с пробелами — в кавычках."""
    return " ".join(f'"{a}"' if (" " in a and not (a.startswith('"') and a.endswith('"'))) else a
                    for a in args)

def _win32_error_code(e: Exception) -> int | None:
    """Код Win32 у pywintypes.error (например 1056 = служба уже запущена)."""
    code = getattr(e, "winerror", None)
    return code if isinstance(code, int) else None

def apply_strategy(strategy_id: str, restart: bool = True) -> dict:
    """Применяет стратегию к службе zapret: пересоздаёт binPath (exeName+exeArgs)
    и перезапускает службу. Требует прав администратора."""
    args, err = parse_strategy_args(strategy_id)
    if err is not None or args is None:
        return {"ok": False, "service": err, "strategy": strategy_id}
    if not is_admin():
        return {"ok": False, "strategy": strategy_id,
                "service": t("sm.apply_no_admin")}
    exe = os.path.join(BIN_DIR, "winws.exe")
    exe_args = format_exe_args(args)
    try:
        exists = win32serviceutil.QueryServiceStatus(SERVICE_NAME) is not None
    except Exception:
        exists = False
    try:
        if exists and is_running():
            # Службу нельзя менять на лету — сначала честная остановка с ожиданием
            # (отказ до ChangeServiceConfig: конфигурация не меняется при проблемах)
            try:
                win32serviceutil.StopService(SERVICE_NAME)
            except Exception as e:
                if _win32_error_code(e) != 1062:  # 1062 = уже остановлена
                    return {"ok": False, "strategy": strategy_id,
                            "service": t("sm.stop_failed", e=str(e))}
            for _ in range(20):  # ждём остановки, до 10 с
                time.sleep(0.5)
                if query_status() == "Stopped":
                    break
            else:
                return {"ok": False, "strategy": strategy_id,
                        "service": t("sm.stop_failed", e=query_status())}
        if exists:
            # pythonClassString=None: pywin32 по умолчанию пропускает InstallPythonClassString
            win32serviceutil.ChangeServiceConfig(None, SERVICE_NAME, exeName=exe, exeArgs=exe_args,
                                                 startType=win32service.SERVICE_AUTO_START,
                                                 description=f"zapret ({strategy_id})")
        else:
            win32serviceutil.InstallService(None, SERVICE_NAME, SERVICE_DISPLAY,
                                            startType=win32service.SERVICE_AUTO_START,
                                            exeName=exe, exeArgs=exe_args,
                                            description=f"zapret ({strategy_id})")
        started = ""
        if restart:
            try:
                win32serviceutil.StartService(SERVICE_NAME)
                started = t("sm.service_started_suffix")
            except Exception as e:
                # 1056 = уже запущена: конфигурация применена — это успех, а не ошибка
                if _win32_error_code(e) != 1056:
                    raise
                started = t("sm.service_started_suffix")
        # Запоминаем выбранную стратегию для отображения в статусе
        try:
            os.makedirs(os.path.dirname(STRATEGY_FILE), exist_ok=True)
            with open(STRATEGY_FILE, "w", encoding="utf-8") as f:
                f.write(strategy_id)
        except OSError as e:
            return {"ok": False, "strategy": strategy_id,
                    "service": t("sm.strategy_write_failed", e=str(e))}
        return {"ok": True, "strategy": strategy_id, "args_count": len(args),
                "service": t("sm.strategy_applied", s=strategy_id, n=len(args), started=started)}
    except Exception as e:
        return {"ok": False, "strategy": strategy_id, "service": str(e)}

def current_strategy() -> str | None:
    """Последняя применённая стратегия: .strategy в %LOCALAPPDATA%\\zapret-simple,
    для старых версий — fallback на файл рядом с приложением."""
    for p in (STRATEGY_FILE, LEGACY_STRATEGY_FILE):
        try:
            with open(p, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return None
