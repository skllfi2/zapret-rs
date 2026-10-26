# service_manager.py — полная замена service.bat (SCM + winws.exe управление)
# Без вызова .bat файлов — всё через pywin32 + subprocess (CREATE_NO_WINDOW)
import os, subprocess, time, threading, sys, winreg, ctypes
import win32serviceutil, win32service, win32con

# === Автоопределение каталога zapret (без хардкода одной копии) ===
# Порядок: переменная окружения ZAPRET_DIR -> рабочая копия AppWatch -> ~/Pictures.
def _detect_orig_dir():
    candidates = []
    env = os.environ.get("ZAPRET_DIR")
    if env:
        candidates.append(env)
    candidates.append(os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                   "AppWatch", "Apps", "zapret-discord-youtube"))
    candidates.append(os.path.join(os.path.expanduser("~"), "Pictures", "zapret-discord-youtube"))
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "bin", "winws.exe")):
            return c
    return candidates[-1]  # последний кандидат — для сообщений об ошибке

ORIG_DIR = _detect_orig_dir()
BIN_DIR = os.path.join(ORIG_DIR, "bin")
LISTS_DIR = os.path.join(ORIG_DIR, "lists")
SERVICE_NAME = "zapret"
SERVICE_DISPLAY = "zapret"

def get_bin_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "start.bat")

def install_service(exe_path=None):
    if exe_path is None:
        exe_path = get_bin_path()
    if not os.path.isfile(exe_path):
        return False, f"Binary not found: {exe_path}"
    if exe_path.lower().endswith(".bat"):
        # .bat не может быть binPath службы (SCM вернёт 1053) — честный отказ вместо тихой ошибки
        return False, (f".bat нельзя указывать как binPath службы: {exe_path}. "
                       "Служба zapret устанавливается оригинальным service.bat и запускает winws.exe.")
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

# === winws.exe управление (заменяет service.bat вызовы) ===

def winws_is_running():
    try:
        # Без text=True: tasklist отдаёт OEM-кодировку (cp866 и т.п.),
        # декодирование в UTF-8 падало — проверяем байты напрямую.
        res = subprocess.run(["tasklist", "/FI", "IMAGENAME eq winws.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, creationflags=0x08000000)
        return b"winws.exe" in res.stdout.lower()
    except Exception:
        return False

def replace_fakes(fake_type=None, number=None):
    """Замена ACTIVE_*.bin на выбранный fake из bin/ (как :replace_active_fakes в service.bat).
    fake_type: 1=Discord UDP, 2=GameFilter UDP; number — позиция в списке fakes (с 1)."""
    import shutil, hashlib
    if fake_type is None or number is None:
        return {"ok": False, "stdout": "",
                "stderr": "Нужен выбор: fake_type (1=Discord, 2=GameFilter) и номер fake-файла. "
                          "Сначала вызови list_fakes."}
    active_map = {"1": "ACTIVE_DISCORD_UDP.bin", "2": "ACTIVE_GAME_UDP.bin"}
    active_name = active_map.get(str(fake_type))
    if not active_name:
        return {"ok": False, "stdout": "", "stderr": f"Неизвестный тип fake: {fake_type} (нужен 1 или 2)"}
    fakes = [f for f in sorted(os.listdir(BIN_DIR))
             if f.lower().endswith(".bin") and not f.upper().startswith("ACTIVE_")]
    try:
        idx = int(number)
    except (TypeError, ValueError):
        return {"ok": False, "stdout": "", "stderr": f"Номер должен быть числом, получено: {number}"}
    if not (1 <= idx <= len(fakes)):
        return {"ok": False, "stdout": "", "stderr": f"Номер {idx} вне диапазона 1..{len(fakes)}"}
    source = os.path.join(BIN_DIR, fakes[idx - 1])
    active = os.path.join(BIN_DIR, active_name)
    try:
        if os.path.isfile(active):
            shutil.copy2(active, active + ".bak")  # откат
        shutil.copy2(source, active)
        h = hashlib.sha256(open(source, "rb").read()).hexdigest()[:16]
        return {"ok": True, "stdout": f"{active_name} <- {fakes[idx-1]} (sha256:{h})",
                "stderr": "", "active": active_name, "source": fakes[idx - 1]}
    except OSError as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}


def list_fakes():
    """Список fake-файлов с хешами + текущие ACTIVE_* (для выбора в replace_fakes)."""
    import hashlib
    items = []
    for f in sorted(os.listdir(BIN_DIR)):
        if not f.lower().endswith(".bin"):
            continue
        p = os.path.join(BIN_DIR, f)
        try:
            h = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
        except OSError:
            h = "?"
        items.append({"name": f, "sha256": h, "active": f.upper().startswith("ACTIVE_")})
    return {"ok": True, "stdout": items,
            "note": "ACTIVE_* — текущие; остальные нумеруются с 1 для replace_fakes"}


def game_filter_status():
    """Чтение utils/game_filter.enabled (как :game_switch_status в service.bat)."""
    path = os.path.join(ORIG_DIR, "utils", "game_filter.enabled")
    info = {"mode": "disabled", "tcp": "12", "udp": "12", "enabled": False, "file": path}
    if not os.path.isfile(path):
        info["stdout"] = "game_filter.enabled отсутствует — игровой фильтр выключен"
        return {"ok": True, **info}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = (x.strip() for x in line.split("=", 1))
                kl = k.lower()
                if kl == "mode" and v:
                    info["mode"] = v
                elif kl == "all":
                    info["mode"] = "all"
                elif kl == "tcp":
                    # как в service.bat: tcp без значения = режим, со значением = диапазон
                    if v: info["tcp"] = v
                    else: info["mode"] = "tcp"
                elif kl == "udp":
                    if v: info["udp"] = v
                    else: info["mode"] = "udp"
        info["enabled"] = info["mode"] != "disabled"
        info["stdout"] = f"mode={info['mode']}, tcp={info['tcp']}, udp={info['udp']}"
        return {"ok": True, **info}
    except OSError as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}


def ipset_update():
    """Скачивание ipset-all.txt с GitHub (как :ipset_update в service.bat), с бэкапом."""
    import urllib.request
    url = ("https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/"
           "refs/heads/main/.service/ipset-service.txt")
    dest = os.path.join(LISTS_DIR, "ipset-all.txt")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "zapret-simple"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        if not data.strip():
            return {"ok": False, "stdout": "", "stderr": "Пустой ответ от сервера — файл не обновлён"}
        if os.path.isfile(dest):
            import shutil
            shutil.copy2(dest, dest + ".bak")
        with open(dest, "wb") as f:
            f.write(data)
        n_lines = data.count(b"\n")
        return {"ok": True, "stdout": f"ipset-all.txt обновлён: {len(data)} байт, {n_lines} строк",
                "stderr": ""}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": f"Не удалось обновить ipset: {e}"}

def load_user_lists():
    try:
        lists_path = LISTS_DIR
        if not os.path.exists(lists_path):
            os.makedirs(lists_path)
        if not os.path.exists(os.path.join(lists_path, "list-general-user.txt")):
            with open(os.path.join(lists_path, "list-general-user.txt"), "w") as f:
                f.write("# Never leave this file empty\ndomain.example.abc\n")
        if not os.path.exists(os.path.join(lists_path, "list-exclude-user.txt")):
            with open(os.path.join(lists_path, "list-exclude-user.txt"), "w") as f:
                f.write("domain.example.abc\n")
        if not os.path.exists(os.path.join(lists_path, "ipset-exclude-user.txt")):
            with open(os.path.join(lists_path, "ipset-exclude-user.txt"), "w") as f:
                f.write("203.0.113.113/32\n")
        return {"ok": True, "stdout": "Lists loaded", "stderr": ""}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}

def tcp_timestamps():
    try:
        res = subprocess.run(["netsh", "int", "tcp", "set", "global", "timestamps=enabled"],
                             capture_output=True, text=True, errors="replace", creationflags=0x08000000)
        return res.returncode == 0, "TCP enabled" if res.returncode == 0 else str(res.stderr)
    except Exception as e:
        return False, str(e)

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def admin_use():
    """Проверка прав и внешних команд (как :admin в service.bat)."""
    if not is_admin():
        return {"ok": False, "service": "Нет прав администратора — запусти от имени администратора "
                                        "(sc/netsh будут падать)", "msg": ""}
    cmds = ["chcp", "find", "findstr", "netsh"]
    missing = [c for c in cmds if subprocess.run(["where", c], capture_output=True,
                                                 creationflags=0x08000000).returncode != 0]
    if missing:
        return {"ok": False, "service": f"Admin missing commands: {missing}", "msg": ""}
    load_user_lists()
    return {"ok": True, "service": "Admin rights OK, lists loaded", "msg": ""}

def check_updates():
    """Сравнение локальной версии (LOCAL_VERSION из service.bat) с GitHub (как :service_check_updates)."""
    import re, urllib.request
    enabled_path = os.path.join(ORIG_DIR, "utils", "check_updates.enabled")
    if not os.path.exists(enabled_path):
        return {"ok": True, "stdout": "Проверка обновлений отключена (нет utils/check_updates.enabled)",
                "stderr": "", "enabled": False}
    local = None
    try:
        with open(os.path.join(ORIG_DIR, "service.bat"), encoding="utf-8", errors="replace") as f:
            m = re.search(r'set\s+"LOCAL_VERSION=([^"]+)"', f.read())
            if m:
                local = m.group(1).strip()
    except OSError:
        pass
    if not local:
        return {"ok": False, "stdout": "", "stderr": "Не удалось прочитать LOCAL_VERSION из service.bat"}
    url = ("https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/"
           "main/.service/version.txt")
    try:
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "zapret-simple"})
        with urllib.request.urlopen(req, timeout=8) as r:
            remote = r.read().decode("utf-8", "replace").strip()
    except Exception as e:
        # Как в оригинале: не смогли проверить — это не ошибка работы zapret
        return {"ok": True, "stdout": f"Локальная версия {local}; проверить GitHub не удалось ({e})",
                "stderr": "", "local": local, "remote": None}
    if remote == local:
        return {"ok": True, "stdout": f"Установлена последняя версия: {local}",
                "stderr": "", "local": local, "remote": remote, "update_available": False}
    return {"ok": True, "stdout": f"Доступна новая версия: {remote} (локальная: {local}). "
                                  f"https://github.com/Flowseal/zapret-discord-youtube/releases/latest",
            "stderr": "", "local": local, "remote": remote, "update_available": True}


def clear_discord():
    """Остановка Discord + удаление кэша (перенесено из main.py — доступно и Tkinter)."""
    import shutil
    killed = []
    for p in ["Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe"]:
        r = subprocess.run(["taskkill", "/IM", p, "/F"], capture_output=True)
        if r.returncode == 0:
            killed.append(p)
    removed = []
    appdata = os.environ.get("APPDATA", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")
    for base, name in [(appdata, "Discord"), (appdata, "discord"), (localappdata, "Discord")]:
        d = os.path.join(base, name, "Cache")
        if base and os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            removed.append(d)
    return {"ok": True, "stdout": f"killed={killed or 'none'}, cache_removed={len(removed)}",
            "stderr": ""}


def update_hosts():
    """Диагностика hosts-файла (как :hosts_update / :service_diagnostics в оригинале:
    пункт меню 9 в оригинале пуст — сводим к полезной проверке)."""
    hosts = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                         "System32", "drivers", "etc", "hosts")
    if not os.path.isfile(hosts):
        return {"ok": False, "stdout": "", "stderr": f"hosts not found: {hosts}"}
    try:
        with open(hosts, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}
    yt = [ln for ln in content.splitlines()
          if "youtube.com" in ln.lower() or "youtu.be" in ln.lower()]
    return {"ok": True, "stdout": f"hosts: {len(content.splitlines())} строк, "
                                  f"записей youtube/youtu.be: {len(yt)}",
            "stderr": "", "youtube_entries": yt[:10],
            "note": "Записи youtube в hosts могут мешать — при необходимости удали их вручную"}

def hidden_cmd(cmd_list, cwd=ORIG_DIR, timeout=30):
    try:
        res = subprocess.run(cmd_list, cwd=cwd, capture_output=True, text=True, errors="replace",
                             timeout=timeout, creationflags=0x08000000, shell=False)
        return {"ok": res.returncode == 0, "stdout": res.stdout[:3000], "stderr": res.stderr[:1000]}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}

def payloads_status():
    """Проверка fake-payload файлов (*.bin), на которые ссылается winws.exe.
    В рабочей копии их может не быть (лежат в архиве версий) — тогда fake-стратегии не работают."""
    if not os.path.isdir(BIN_DIR):
        return {"ok": False, "missing": [BIN_DIR], "total": 0,
                "stderr": f"Каталог bin не найден: {BIN_DIR}"}
    try:
        files = [f for f in os.listdir(BIN_DIR) if f.lower().endswith(".bin")]
    except OSError as e:
        return {"ok": False, "missing": [], "total": 0, "stderr": str(e)}
    # Обязательные для работы десинхронизации (как в строке winws сервиса)
    required = ["ACTIVE_DISCORD_UDP.bin", "ACTIVE_GAME_UDP.bin",
                "quic_initial_www_google_com.bin", "tls_clienthello_www_google_com.bin"]
    missing = [r for r in required if r not in files]
    return {"ok": not missing, "total": len(files), "missing": missing,
            "stdout": f"payload-файлов в bin: {len(files)}; отсутствует обязательных: {len(missing)}",
            "stderr": ("Отсутствуют: " + ", ".join(missing)) if missing else ""}

def run_service_action(action="status_zapret", arg="", **kwargs):
    """Основной маршрутизатор — заменяет service.bat полностью.
    kwargs пробрасываются в функцию (например, fake_type/number для replace_active_fakes)."""
    if action == "service_install":
        r = install_service(); return {"ok": r[0], "service": r[1]}
    if action == "service_remove":
        r = uninstall_service(); return {"ok": r[0], "service": r[1]}
    if action == "service_status":
        return {"ok": True, "service": query_status()}
    if action == "start":
        r = start_service(); return {"ok": r[0], "service": r[1]}
    if action == "stop":
        r = stop_service(); return {"ok": r[0], "service": r[1]}
    if action == "load_game_filter":
        return game_filter_status()
    if action == "load_user_lists":
        return load_user_lists()
    if action == "service_diagnostics":
        try:
            pl = payloads_status()
            return {"ok": True,
                    "service": f"zapret_service={query_status()}, winws_running={winws_is_running()}, "
                               f"admin={is_admin()}, dir={ORIG_DIR}, "
                               f"payloads={pl['total']} (missing_required={len(pl['missing'])})",
                    "payloads": pl}
        except Exception as e:
            return {"ok": True, "service": f"diag error: {e}"}
    if action == "payloads_status":
        return payloads_status()
    if action == "status_zapret":
        return {"ok": True, "service": f"winws.exe running={winws_is_running()}, service={query_status()}"}
    if action == "replace_active_fakes":
        return replace_fakes(**kwargs)
    if action == "list_fakes":
        return list_fakes()
    if action == "check_updates":
        return check_updates()
    if action in ("ipset_update", "update_ipset", "8"):
        return ipset_update()
    if action in ("update_hosts", "hosts_update", "9"):
        return update_hosts()
    if action == "clear_discord":
        return clear_discord()
    if action == "admin":
        return admin_use()
    if action == "test":
        try:
            return {"ok": True, "service": f"service={query_status()}, winws_running={winws_is_running()}"}
        except Exception as e:
            return {"ok": True, "service": f"test error: {e}"}
    return {"ok": False, "service": f"Unknown action: {action}"}
