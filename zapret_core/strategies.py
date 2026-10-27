# strategies.py — разбор стратегий (*.bat) и применение их к службе zapret
import os, re, shlex, time
import win32serviceutil, win32service
from i18n import t
from .paths import (ORIG_DIR, BIN_DIR, LISTS_DIR, SERVICE_NAME, SERVICE_DISPLAY,
                    STRATEGY_FILE)
from .settings import game_filter_status
from .scm import query_status, is_running
from .misc import is_admin

# === СТРАТЕГИИ: разбор .bat и применение к службе (как :service_install в service.bat) ===

def list_strategies():
    """Реальные стратегии = .bat файлы каталога zapret (кроме service*)."""
    try:
        return [os.path.splitext(f)[0] for f in sorted(os.listdir(ORIG_DIR))
                if f.lower().endswith(".bat") and not f.lower().startswith("service")]
    except OSError:
        return []

def _game_filter_ranges():
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

def parse_strategy_args(strategy_id):
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

def apply_strategy(strategy_id, restart=True):
    """Применяет стратегию к службе zapret: пересоздаёт binPath (exeName+exeArgs)
    и перезапускает службу. Требует прав администратора."""
    args, err = parse_strategy_args(strategy_id)
    if err:
        return {"ok": False, "service": err, "strategy": strategy_id}
    if not is_admin():
        return {"ok": False, "strategy": strategy_id,
                "service": t("sm.apply_no_admin")}
    exe = os.path.join(BIN_DIR, "winws.exe")
    exe_args = " ".join(f'"{a}"' if (" " in a and not (a.startswith('"') and a.endswith('"'))) else a
                        for a in args)
    try:
        exists = win32serviceutil.QueryServiceStatus(SERVICE_NAME) is not None
    except Exception:
        exists = False
    try:
        if exists:
            try:
                if is_running():
                    win32serviceutil.StopService(SERVICE_NAME)
                    for _ in range(20):  # ждём остановки, до 10 с
                        time.sleep(0.5)
                        if query_status() == "Stopped":
                            break
            except Exception:
                pass  # служба и так остановлена
            win32serviceutil.ChangeServiceConfig(SERVICE_NAME, exeName=exe, exeArgs=exe_args,
                                                 startType=win32service.SERVICE_AUTO_START,
                                                 description=f"zapret ({strategy_id})")
        else:
            win32serviceutil.InstallService(exe, SERVICE_NAME, SERVICE_DISPLAY,
                                            startType=win32service.SERVICE_AUTO_START,
                                            exeArgs=exe_args, description=f"zapret ({strategy_id})")
        started = ""
        if restart:
            win32serviceutil.StartService(SERVICE_NAME)
            started = t("sm.service_started_suffix")
        # Запоминаем выбранную стратегию для отображения в статусе
        try:
            with open(STRATEGY_FILE, "w", encoding="utf-8") as f:
                f.write(strategy_id)
        except OSError:
            pass
        return {"ok": True, "strategy": strategy_id, "args_count": len(args),
                "service": t("sm.strategy_applied", s=strategy_id, n=len(args), started=started)}
    except Exception as e:
        return {"ok": False, "strategy": strategy_id, "service": str(e)}

def current_strategy():
    """Последняя применённая стратегия (файл .strategy рядом с приложением)."""
    p = STRATEGY_FILE
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None
