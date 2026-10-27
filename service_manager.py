# service_manager.py — полная замена service.bat (SCM + winws.exe управление)
# Без вызова .bat файлов — всё через pywin32 + subprocess (CREATE_NO_WINDOW)
import os, re, shlex, shutil, subprocess, time, threading, sys, winreg, ctypes
import win32serviceutil, win32service, win32con
from i18n import t

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
    # Службу ставит оригинальный service.bat (см. install_service: .bat как binPath запрещён)
    return os.path.join(ORIG_DIR, "service.bat")

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
                "stderr": t("sm.fake_need_choice")}
    active_map = {"1": "ACTIVE_DISCORD_UDP.bin", "2": "ACTIVE_GAME_UDP.bin"}
    active_name = active_map.get(str(fake_type))
    if not active_name:
        return {"ok": False, "stdout": "", "stderr": t("sm.fake_unknown_type", t=fake_type)}
    fakes = [f for f in sorted(os.listdir(BIN_DIR))
             if f.lower().endswith(".bin") and not f.upper().startswith("ACTIVE_")]
    try:
        idx = int(number)
    except (TypeError, ValueError):
        return {"ok": False, "stdout": "", "stderr": t("sm.fake_number_not_int", n=number)}
    if not (1 <= idx <= len(fakes)):
        return {"ok": False, "stdout": "", "stderr": t("sm.fake_number_range", i=idx, n=len(fakes))}
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
            "note": t("sm.fakes_note")}


def game_filter_status():
    """Чтение utils/game_filter.enabled (как :game_switch_status в service.bat)."""
    path = os.path.join(ORIG_DIR, "utils", "game_filter.enabled")
    info = {"mode": "disabled", "tcp": "12", "udp": "12", "enabled": False, "file": path}
    if not os.path.isfile(path):
        info["stdout"] = t("sm.gf_absent")
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
            return {"ok": False, "stdout": "", "stderr": t("sm.ipset_empty")}
        if os.path.isfile(dest):
            import shutil
            shutil.copy2(dest, dest + ".bak")
        with open(dest, "wb") as f:
            f.write(data)
        n_lines = data.count(b"\n")
        return {"ok": True, "stdout": t("sm.ipset_updated", b=len(data), n=n_lines),
                "stderr": ""}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": t("sm.ipset_update_fail", e=e)}

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
        return {"ok": False, "service": t("sm.no_admin"), "msg": ""}
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
        return {"ok": True, "stdout": t("sm.updates_disabled"),
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
        return {"ok": False, "stdout": "", "stderr": t("sm.ver_unreadable")}
    url = ("https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/"
           "main/.service/version.txt")
    try:
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "zapret-simple"})
        with urllib.request.urlopen(req, timeout=8) as r:
            remote = r.read().decode("utf-8", "replace").strip()
    except Exception as e:
        # Как в оригинале: не смогли проверить — это не ошибка работы zapret
        return {"ok": True, "stdout": t("sm.ver_local_only", l=local, e=e),
                "stderr": "", "local": local, "remote": None}
    if remote == local:
        return {"ok": True, "stdout": t("sm.ver_latest", l=local),
                "stderr": "", "local": local, "remote": remote, "update_available": False}
    return {"ok": True, "stdout": t("sm.ver_new", r=remote, l=local),
            "stderr": "", "local": local, "remote": remote, "update_available": True}


def clear_discord():
    """Остановка Discord + удаление кэша (доступно из любого UI)."""
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
    return {"ok": True, "stdout": t("sm.hosts_summary", n=len(content.splitlines()),
                                    y=len(yt)),
            "stderr": "", "youtube_entries": yt[:10],
            "note": t("sm.hosts_note")}

def hidden_cmd(cmd_list, cwd=ORIG_DIR, timeout=30):
    try:
        res = subprocess.run(cmd_list, cwd=cwd, capture_output=True, text=True, errors="replace",
                             timeout=timeout, creationflags=0x08000000, shell=False)
        return {"ok": res.returncode == 0, "stdout": res.stdout[:3000], "stderr": res.stderr[:1000]}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}

def find_payload_source():
    """Ищем каталог с *.bin payload-файлами для восстановления.
    Порядок: ZAPRET_PAYLOADS_DIR -> самый свежий AppWatch/Versions/<app>/*/bin."""
    candidates = []
    env = os.environ.get("ZAPRET_PAYLOADS_DIR")
    if env:
        candidates.append(env)
    versions_root = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AppWatch", "Versions")
    if os.path.isdir(versions_root):
        for app in os.listdir(versions_root):  # например zapretdiscordyoutube
            app_root = os.path.join(versions_root, app)
            if not os.path.isdir(app_root):
                continue
            subs = [os.path.join(app_root, s) for s in os.listdir(app_root)]
            # ближайшую к настоящему версию — первой (1102, 1103, ...)
            def _mtime(p):
                try: return os.path.getmtime(p)
                except OSError: return 0
            for sub in sorted(subs, key=_mtime, reverse=True):
                b = os.path.join(sub, "bin")
                try:
                    has_bin = os.path.isdir(b) and any(f.lower().endswith(".bin") for f in os.listdir(b))
                except OSError:
                    has_bin = False
                if has_bin:
                    candidates.append(b)
                    break
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


def restore_payloads(dest_dir=None, source_dir=None):
    """Восстановление *.bin в bin/ рабочей копии (не перезаписывает существующие).
    Нужно, если развёртывание скопировало bin не полностью: без .bin fake-стратегии
    winws молча не работают."""
    import shutil
    dest = dest_dir or BIN_DIR
    src = source_dir or find_payload_source()
    if not src:
        return {"ok": False, "stdout": "", "stderr": t("sm.payload_src_missing")}
    if os.path.abspath(src) == os.path.abspath(dest):
        return {"ok": False, "stdout": "", "stderr": t("sm.payload_src_eq_dest")}
    try:
        os.makedirs(dest, exist_ok=True)
        copied, skipped = [], []
        for f in sorted(os.listdir(src)):
            if not f.lower().endswith(".bin"):
                continue
            target = os.path.join(dest, f)
            if os.path.exists(target):
                skipped.append(f)      # никогда не перезаписываем: ACTIVE_* могли заменить вручную
                continue
            shutil.copy2(os.path.join(src, f), target)
            copied.append(f)
    except OSError as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}
    pl = payloads_status(dest)
    return {"ok": pl["ok"], "source": src, "dest": dest,
            "copied": copied, "skipped": skipped,
            "stdout": t("sm.payload_copied", c=len(copied), s=len(skipped), status=pl['stdout']),
            "stderr": pl.get("stderr", ""), "payloads": pl}


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
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".strategy"), "w",
                      encoding="utf-8") as f:
                f.write(strategy_id)
        except OSError:
            pass
        return {"ok": True, "strategy": strategy_id, "args_count": len(args),
                "service": t("sm.strategy_applied", s=strategy_id, n=len(args), started=started)}
    except Exception as e:
        return {"ok": False, "strategy": strategy_id, "service": str(e)}


# === МЕНЮ: версия и тумблеры (порт :menu/:ipset_switch/:check_updates_switch) ===

def local_version():
    """LOCAL_VERSION из service.bat (как в шапке оригинального меню)."""
    try:
        with open(os.path.join(ORIG_DIR, "service.bat"), encoding="utf-8", errors="replace") as f:
            m = re.search(r'set\s+"LOCAL_VERSION=([^"]+)"', f.read())
            return m.group(1).strip() if m else None
    except OSError:
        return None

def ipset_status():
    """Как :ipset_switch_status — any / none / loaded по содержимому ipset-all.txt."""
    path = os.path.join(LISTS_DIR, "ipset-all.txt")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = f.read()
    except OSError:
        return "none"  # файла нет — как в оригинале при нечитаемом файле
    lines = [l for l in data.splitlines() if l.strip()]
    if not lines:
        return "any"
    return "none" if any("203.0.113.113/32" in l for l in lines) else "loaded"

def check_updates_flag():
    """Как :check_updates_switch_status — enabled/disabled по файлу-флагу."""
    return "enabled" if os.path.exists(os.path.join(ORIG_DIR, "utils", "check_updates.enabled")) \
        else "disabled"

def game_filter_label():
    """Человекочитаемый статус игрового фильтра (как :game_switch_status в шапке меню)."""
    gf = game_filter_status()
    mode = gf.get("mode", "disabled")
    return {"all": "enabled (TCP and UDP)", "tcp": "enabled (TCP)",
            "udp": "enabled (UDP)"}.get(mode, "disabled")

def menu_status():
    """Все статусы шапки оригинального меню одним запросом."""
    return {"ok": True, "version": local_version(), "strategy": current_strategy(),
            "game_filter": game_filter_label(), "ipset": ipset_status(),
            "check_updates": check_updates_flag(), "admin": is_admin()}

def set_game_filter(mode, tcp="1024-65535", udp="1024-65535"):
    """Запись game_filter.enabled (как :save_game_filter_settings). mode ∈ all/tcp/udp/disabled."""
    if mode not in ("all", "tcp", "udp", "disabled"):
        return {"ok": False, "service": t("sm.bad_game_filter_mode", m=mode)}
    path = os.path.join(ORIG_DIR, "utils", "game_filter.enabled")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"mode={mode}\ntcp={tcp}\nudp={udp}\n")
        return {"ok": True, "service": f"GameFilter = {game_filter_label()}",
                "game_filter": game_filter_label()}
    except OSError as e:
        return {"ok": False, "service": str(e)}

def toggle_check_updates(enable=None):
    """Вкл/выкл автопроверку обновлений (как :check_updates_switch — создать/удалить файл-флаг)."""
    path = os.path.join(ORIG_DIR, "utils", "check_updates.enabled")
    try:
        if enable is None:
            enable = not os.path.exists(path)
        if enable:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("ENABLED\n")
        elif os.path.exists(path):
            os.remove(path)
        return {"ok": True, "service": f"Auto-Update Check = {check_updates_flag()}",
                "check_updates": check_updates_flag()}
    except OSError as e:
        return {"ok": False, "service": str(e)}

def toggle_ipset(mode=None):
    """Переключение ipset (как :ipset_switch): loaded→none→any→loaded с backup-файлом."""
    path = os.path.join(LISTS_DIR, "ipset-all.txt")
    backup = path + ".backup"
    cur = ipset_status()
    target = mode or {"loaded": "none", "none": "any", "any": "loaded"}.get(cur, "none")
    try:
        os.makedirs(LISTS_DIR, exist_ok=True)
        if target == "none":
            if os.path.isfile(path):
                # В оригинале: бэкап имеющегося списка, затем заглушка-маркер
                if os.path.isfile(backup):
                    os.remove(backup)
                os.replace(path, backup)
            with open(path, "w", encoding="utf-8") as f:
                f.write("203.0.113.113/32\n")
        elif target == "any":
            with open(path, "w", encoding="utf-8") as f:
                f.write("")
        else:  # loaded — вернуть из бэкапа
            if not os.path.isfile(backup):
                return {"ok": False, "service": t("sm.ipset_no_backup")}
            if os.path.isfile(path):
                os.remove(path)
            os.replace(backup, path)
        return {"ok": True, "service": f"IPSet Filter = {ipset_status()}", "ipset": ipset_status()}
    except OSError as e:
        return {"ok": False, "service": str(e)}

def current_strategy():
    """Последняя применённая стратегия (файл .strategy рядом с приложением)."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".strategy")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def relaunch_as_admin():
    """Перезапуск текущего приложения с повышением прав (UAC).
    args = argv целиком (включая имя скрипта), иначе запустится пустой python."""
    try:
        args = " ".join(f'"{a}"' for a in sys.argv)
        h = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
        return h > 32  # >32 = успех
    except Exception:
        return False


def payloads_status(bin_dir=None):
    """Проверка fake-payload файлов (*.bin), на которые ссылается winws.exe.
    В рабочей копии их может не быть (лежат в архиве версий) — тогда fake-стратегии не работают."""
    bin_dir = bin_dir or BIN_DIR
    if not os.path.isdir(bin_dir):
        return {"ok": False, "missing": [bin_dir], "total": 0,
                "stderr": t("sm.bin_dir_missing", d=bin_dir)}
    try:
        files = [f for f in os.listdir(bin_dir) if f.lower().endswith(".bin")]
    except OSError as e:
        return {"ok": False, "missing": [], "total": 0, "stderr": str(e)}
    # Обязательные для работы десинхронизации (как в строке winws сервиса)
    required = ["ACTIVE_DISCORD_UDP.bin", "ACTIVE_GAME_UDP.bin",
                "quic_initial_www_google_com.bin", "tls_clienthello_www_google_com.bin"]
    missing = [r for r in required if r not in files]
    return {"ok": not missing, "total": len(files), "missing": missing,
            "stdout": t("sm.payloads_summary", n=len(files), m=len(missing)),
            "stderr": (t("sm.payloads_missing", list=", ".join(missing))) if missing else ""}

# === ДИАГНОСТИКА (полный порт :service_diagnostics из service.bat) ===
# Каждая проверка даёт уровень: ok (зелёный) / warn (жёлтый) / bad (красный) —
# ровно как PrintGreen/PrintYellow/PrintRed в оригинале.

def _sc_service_names():
    """Список имён установленных служб (sc query) — как `sc query | findstr` в оригинале."""
    try:
        res = subprocess.run(["sc", "query"], capture_output=True, text=True,
                             errors="replace", creationflags=0x08000000, timeout=30)
        names = []
        for line in (res.stdout or "").splitlines():
            line = line.strip()
            if line.upper().startswith("SERVICE_NAME:"):
                names.append(line.split(":", 1)[1].strip())
        return names
    except Exception:
        return []

def _tasklist_running(image):
    try:
        res = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}"],
                             capture_output=True, text=True, errors="replace",
                             creationflags=0x08000000, timeout=20)
        return image.lower() in (res.stdout or "").lower()
    except Exception:
        return False

def _check(name, level, msg, url=""):
    return {"name": name, "level": level, "msg": msg, "url": url}

def run_diagnostics():
    """Все проверки из :service_diagnostics. Как в оригинале: выключенные TCP
    timestamps диагностика включает сама (при правах админа); разрушающие фиксы
    (удаление WinDivert и конфликтных служб) — отдельное действие remove_conflicts,
    чтобы диагностика ничего не удаляла без спроса."""
    checks = []
    d = ORIG_DIR
    checks.append(_check("Path", "ok", f"Zapret is installed in: '{d}'"))

    # Base Filtering Engine
    try:
        r = subprocess.run(["sc", "query", "BFE"], capture_output=True, text=True,
                           errors="replace", creationflags=0x08000000, timeout=20)
        if "RUNNING" in (r.stdout or "").upper():
            checks.append(_check("BFE", "ok", t("diag.bfe_ok")))
        else:
            checks.append(_check("BFE", "bad", t("diag.bfe_bad")))
    except Exception as e:
        checks.append(_check("BFE", "warn", f"BFE check failed: {e}"))

    # Proxy (HKCU\...\Internet Settings)
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        try:
            proxy_on, _ = winreg.QueryValueEx(k, "ProxyEnable")
        except OSError:
            proxy_on = 0
        proxy_server = ""
        if proxy_on == 1:
            try:
                proxy_server, _ = winreg.QueryValueEx(k, "ProxyServer")
            except OSError:
                proxy_server = "?"
        winreg.CloseKey(k)
        if proxy_on == 1:
            checks.append(_check("Proxy", "warn", t("diag.proxy_warn", p=proxy_server)))
        else:
            checks.append(_check("Proxy", "ok", t("diag.proxy_ok")))
    except OSError:
        checks.append(_check("Proxy", "ok", t("diag.proxy_ok")))

    # TCP timestamps — в оригинале: выключены -> авто-включение прямо в диагностике
    try:
        r = subprocess.run(["netsh", "interface", "tcp", "show", "global"],
                           capture_output=True, text=True, errors="replace",
                           creationflags=0x08000000, timeout=20)
        out = (r.stdout or "").lower()
        ts_line = next((l for l in out.splitlines() if "timestamp" in l), "")
        if "enabled" in ts_line and "dis" not in ts_line:
            checks.append(_check("TCP timestamps", "ok", t("diag.ts_ok")))
        else:
            if is_admin():
                checks.append(_check("TCP timestamps", "warn", t("diag.ts_enabling")))
                ok, msg = tcp_timestamps()
                if ok:
                    checks[-1] = _check("TCP timestamps", "ok", t("diag.ts_enabled"))
                else:
                    checks[-1] = _check("TCP timestamps", "bad", t("diag.ts_failed", e=msg))
            else:
                checks.append(_check("TCP timestamps", "warn", t("diag.ts_no_admin")))
    except Exception as e:
        checks.append(_check("TCP timestamps", "warn", t("diag.ts_check_failed", e=e)))

    # Adguard
    if _tasklist_running("AdguardSvc.exe"):
        checks.append(_check("Adguard", "bad", t("diag.adguard_bad"),
                             "https://github.com/Flowseal/zapret-discord-youtube/issues/417"))
    else:
        checks.append(_check("Adguard", "ok", t("diag.adguard_ok")))

    # Службы-конфликты: одним запросом sc query, как findstr в оригинале
    names = _sc_service_names()
    lower_names = [n.lower() for n in names]

    if any("killer" in n for n in lower_names):
        checks.append(_check("Killer", "bad", t("diag.killer_bad"),
                             "https://github.com/Flowseal/zapret-discord-youtube/issues/2512#issuecomment-2821119513"))
    else:
        checks.append(_check("Killer", "ok", t("diag.killer_ok")))

    if any("intel" in n and "connectivity" in n for n in lower_names):
        checks.append(_check("Intel Connectivity", "bad", t("diag.intel_bad"),
                             "https://github.com/ValdikSS/GoodbyeDPI/issues/541#issuecomment-2661670982"))
    else:
        checks.append(_check("Intel Connectivity", "ok", t("diag.intel_ok")))

    if any(n in ("tracsrvwrapper", "epwd") for n in lower_names):
        checks.append(_check("Check Point", "bad", t("diag.checkpoint_bad")))
    else:
        checks.append(_check("Check Point", "ok", t("diag.checkpoint_ok")))

    if any("smartbyte" in n for n in lower_names):
        checks.append(_check("SmartByte", "bad", t("diag.smartbyte_bad")))
    else:
        checks.append(_check("SmartByte", "ok", t("diag.smartbyte_ok")))

    # Кириллица в пути
    if re.search(r"[\u0430-\u044f\u0410-\u042f\u0451\u0401]", d):
        checks.append(_check("Cyrillic path", "warn", t("diag.cyrillic_warn")))
    else:
        checks.append(_check("Cyrillic path", "ok", t("diag.cyrillic_ok")))

    # OneDrive
    onedrive = os.environ.get("OneDrive", "")
    if onedrive and (d + "\\").lower().startswith((onedrive + "\\").lower()):
        checks.append(_check("OneDrive", "bad", t("diag.onedrive_bad")))
    else:
        checks.append(_check("OneDrive", "ok", t("diag.onedrive_ok")))

    # WinDivert64.sys
    try:
        sys_files = [f for f in os.listdir(BIN_DIR) if f.lower().endswith(".sys")]
        if sys_files:
            checks.append(_check("WinDivert", "ok", t("diag.windivert_ok", f=sys_files[0])))
        else:
            checks.append(_check("WinDivert", "bad", t("diag.windivert_bad")))
    except OSError:
        checks.append(_check("WinDivert", "bad", t("diag.windivert_bin_bad")))

    # VPN
    vpn = [n for n in names if "vpn" in n.lower() or n.lower().startswith("happ")]
    if vpn:
        checks.append(_check("VPN", "warn", t("diag.vpn_warn", v=", ".join(vpn))))
    else:
        checks.append(_check("VPN", "ok", t("diag.vpn_ok")))

    # Secure DNS (DoH) — реестр Dnscache\InterfaceSpecificParameters
    doh = 0
    try:
        base = r"SYSTEM\CurrentControlSet\Services\Dnscache\InterfaceSpecificParameters"
        stack = [base]
        seen = 0
        while stack and seen < 5000:
            path = stack.pop()
            seen += 1
            try:
                hk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
            except OSError:
                continue
            try:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(hk, i)
                    except OSError:
                        break
                    i += 1
                    stack.append(path + "\\" + sub)
                    if i > 200:
                        break
            finally:
                winreg.CloseKey(hk)
            # значения DohFlags текущего ключа
            try:
                hk2 = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
                try:
                    val, _ = winreg.QueryValueEx(hk2, "DohFlags")
                    if isinstance(val, int) and val > 0:
                        doh += 1
                except OSError:
                    pass
                finally:
                    winreg.CloseKey(hk2)
            except OSError:
                pass
    except Exception:
        doh = 0
    if doh:
        checks.append(_check("Secure DNS", "ok", t("diag.dns_ok")))
    else:
        checks.append(_check("Secure DNS", "warn", t("diag.dns_warn")))

    # Hosts file — youtube
    hosts = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                         "System32", "drivers", "etc", "hosts")
    try:
        with open(hosts, encoding="utf-8", errors="replace") as f:
            hdata = f.read().lower()
        if "youtube.com" in hdata or "youtu.be" in hdata:
            checks.append(_check("Hosts file", "warn", t("diag.hosts_bad")))
        else:
            checks.append(_check("Hosts file", "ok", t("diag.hosts_ok")))
    except OSError:
        checks.append(_check("Hosts file", "ok", t("diag.hosts_ok")))

    # WinDivert конфликт: winws не запущен, но служба WinDivert активна
    windivert = [n for n in lower_names if n == "windivert"]
    if windivert and not winws_is_running():
        checks.append(_check("WinDivert conflict", "bad", t("diag.wd_conflict_bad")))
    else:
        checks.append(_check("WinDivert conflict", "ok", t("diag.wd_conflict_ok")))

    # Конфликтные обходы
    conflicting = ["goodbyedpi", "discordfix_zapret", "winws1", "winws2"]
    found = [n for n in conflicting if n in lower_names]
    if found:
        checks.append(_check("Conflicting bypasses", "bad",
                             t("diag.conflicts_bad", c=" ".join(found))))
    else:
        checks.append(_check("Conflicting bypasses", "ok", t("diag.conflicts_ok")))

    # Discord installations (в оригинале — вопрос про очистку кэша)
    ad = os.environ.get("APPDATA", "")
    discs = [n for n in ("discord", "discordptb", "discordcanary", "discorddevelopment")
             if ad and os.path.isdir(os.path.join(ad, n))]
    if discs:
        checks.append(_check("Discord", "warn", t("diag.discord_warn", d=", ".join(discs))))
    else:
        checks.append(_check("Discord", "ok", t("diag.discord_ok")))

    bad = [c for c in checks if c["level"] == "bad"]
    warns = [c for c in checks if c["level"] == "warn"]
    summary = t("diag.summary", n=len(checks), b=len(bad), w=len(warns))
    return {"ok": not bad, "checks": checks, "service": summary,
            "counts": {"ok": len([c for c in checks if c["level"] == "ok"]),
                       "warn": len(warns), "bad": len(bad)}}

def remove_conflicts():
    """Авто-фиксы из оригинала: TCP timestamps + удаление WinDivert и конфликтных
    обходов (GoodbyeDPI/discordfix_zapret/winws1/winws2). В оригинале — после
    подтверждения Y/N, здесь это отдельное действие."""
    if not is_admin():
        return {"ok": False, "service": t("sm.conflicts_no_admin")}
    actions = []
    ok_all = True

    # TCP timestamps
    ok, msg = tcp_timestamps()
    actions.append(f"TCP timestamps: {t('sm.timestamps_enabled') if ok else t('sm.timestamps_failed', e=msg)}")
    ok_all &= ok

    # WinDivert + конфликтные обходы
    names = _sc_service_names()
    targets = [n for n in names
               if n.lower() in ("windivert", "windivert14", "goodbyedpi",
                                "discordfix_zapret", "winws1", "winws2")]
    for svc in targets:
        subprocess.run(["net", "stop", svc], capture_output=True, creationflags=0x08000000, timeout=30)
        r = subprocess.run(["sc", "delete", svc], capture_output=True, text=True,
                           errors="replace", creationflags=0x08000000, timeout=30)
        if r.returncode == 0:
            actions.append(f"Removed service: {svc}")
        else:
            actions.append(f"[X] Failed to remove: {svc}")
            ok_all = False
    if not targets:
        actions.append(t("sm.no_conflicts"))
    return {"ok": ok_all, "service": " | ".join(actions), "actions": actions}

# === ТЕСТЫ (порт :run_tests -> utils\test zapret.ps1) ===
# Оригинал просто открывает PowerShell-окно. Здесь: пре-чеки те же, что в ps1,
# запуск того же скрипта, ответы на его Read-Host (тип теста, режим) пишутся в stdin,
# строки вывода отдаются колбэку on_line для живого показа в UI.

def tests_prerequisites():
    """Пре-чеки test zapret.ps1 — те же условия, но заранее."""
    problems = []
    if not is_admin():
        problems.append(t("tests.need_admin"))
    if not shutil.which("curl"):
        problems.append(t("tests.need_curl"))
    try:
        win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        problems.append(t("tests.service_installed"))
    except Exception:
        pass  # службы нет — это и есть требуемое состояние
    ps1 = os.path.join(ORIG_DIR, "utils", "test zapret.ps1")
    if not os.path.isfile(ps1):
        problems.append(t("tests.script_missing", p=ps1))
    return problems

def _latest_test_result():
    """Последний файл utils/test results/test_results_*.txt (там итог и Best strategy)."""
    d = os.path.join(ORIG_DIR, "utils", "test results")
    try:
        files = [os.path.join(d, f) for f in os.listdir(d)
                 if f.startswith("test_results_") and f.endswith(".txt")]
        return max(files, key=os.path.getmtime) if files else None
    except OSError:
        return None

def run_tests(on_line=None, test_type=1, mode=1, selection=None, timeout=1800):
    """Запуск оригинального utils\test zapret.ps1.
    test_type: 1=Standard (HTTP/ping), 2=DPI checkers; mode: 1=All configs, 2=Selected;
    selection — номер конфига при mode=2 (третий Read-Host в оригинале).
    on_line(str) — колбэк на каждую строку вывода (живой прогресс в UI)."""
    problems = tests_prerequisites()
    if problems:
        return {"ok": False, "service": t("tests.not_started", p=" | ".join(problems)),
                "problems": problems}
    ps1 = os.path.join(ORIG_DIR, "utils", "test zapret.ps1")
    started = time.time()
    lines = []
    try:
        p = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1],
            cwd=ORIG_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, errors="replace",
            creationflags=0x08000000)
    except Exception as e:
        return {"ok": False, "service": t("tests.ps_fail", e=e)}
    # Ответы на Read-Host скрипта: тип теста, режим; при Selected — ещё и номер конфига.
    # Пишем сразу — буфер stdin сохранится до чтения скриптом.
    answers = f"{test_type}\n{mode}\n"
    if mode == 2:
        answers += f"{selection or 1}\n"
    try:
        p.stdin.write(answers)
        p.stdin.flush()
    except (BrokenPipeError, OSError):
        pass
    deadline = started + timeout
    try:
        for raw in p.stdout:
            if time.time() > deadline:
                p.kill()
                lines.append(t("tests.timeout"))
                break
            line = raw.rstrip("\r\n")
            lines.append(line)
            if on_line:
                try:
                    on_line(line)
                except Exception:
                    pass
    finally:
        try:
            p.stdin.close()
        except Exception:
            pass
        try:
            p.wait(timeout=15)
        except Exception:
            p.kill()
    # Итог из последнего файла результатов (Best strategy и аналитика)
    tail = ""
    res_file = _latest_test_result()
    if res_file and os.path.getmtime(res_file) >= started - 5:
        try:
            with open(res_file, encoding="utf-8", errors="replace") as f:
                rdata = f.read()
            best = next((l.strip() for l in rdata.splitlines()
                         if l.strip().startswith("Best strategy:")), "")
            tail = f" | {best or t('tests.results_saved')} ({os.path.basename(res_file)})"
        except OSError:
            pass
    joined = "\n".join(lines)
    has_error = "[ERROR]" in joined
    summary = (t("tests.done", t=int(time.time() - started), tail=tail)
               if not has_error else t("tests.aborted"))
    return {"ok": not has_error, "service": summary, "stdout": lines[-60:],
            "results_file": res_file}

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
    if action == "service_diagnostics" or action == "diagnostics":
        return run_diagnostics()
    if action == "remove_conflicts":
        return remove_conflicts()
    if action == "tests_prereq" or action == "tests_precheck":
        probs = tests_prerequisites()
        return {"ok": not probs, "problems": probs,
                "service": t("tests.prereq_ok") if not probs
                else t("tests.wont_start", p=" | ".join(probs))}
    if action == "run_tests" or action == "test":
        return run_tests(on_line=kwargs.get("on_line"),
                         test_type=kwargs.get("test_type", 1),
                         mode=kwargs.get("mode", 1),
                         selection=kwargs.get("selection"))
    if action == "payloads_status":
        return payloads_status()
    if action == "restore_payloads":
        return restore_payloads(**kwargs)
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
    if action in ("admin", "admin_use"):
        return admin_use()
    if action == "menu_status":
        return menu_status()
    if action == "set_game_filter":
        return set_game_filter(kwargs.get("mode", "disabled"),
                               kwargs.get("tcp", "1024-65535"),
                               kwargs.get("udp", "1024-65535"))
    if action == "toggle_check_updates":
        return toggle_check_updates(kwargs.get("enable"))
    if action == "toggle_ipset":
        return toggle_ipset(kwargs.get("mode"))
    if action == "apply_strategy":
        return apply_strategy(kwargs.get("strategy") or arg)
    if action == "relaunch_admin":
        ok = relaunch_as_admin()
        return {"ok": ok, "service": t("sm.relaunch_ok") if ok
                else t("sm.relaunch_fail")}
    return {"ok": False, "service": f"Unknown action: {action}"}
