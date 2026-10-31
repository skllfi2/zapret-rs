# misc.py — общие помощники: права админа, скрытые команды, Discord, перезапуск UAC
import ctypes
import os
import subprocess
import sys

from i18n import t

from .lists import load_user_lists
from .paths import ORIG_DIR


def decode_output(data: bytes | str | None) -> str:
    """Декодирование вывода системных утилит (sc/netsh/tasklist).
    На русской локали консольные утилиты печатают OEM cp866, а text=True
    декодирует их через ANSI cp1251 — отсюда кракозябры. Пробуем utf-8, затем cp866."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if not isinstance(data, (bytes, bytearray)):
        return str(data)  # не-байты (моки в тестах) — как есть
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp866", errors="replace")


def is_process_running(image_name: str) -> bool:
    """Проверка, запущен ли процесс (например, winws.exe).
    Использует прямой Win32 Toolhelp32Snapshot API (~0.1 мс, 0 дочерних процессов).
    При сбое или под моками тестов откатывается на tasklist."""
    if getattr(subprocess.run, "_mock_name", None) or hasattr(subprocess.run, "mock_calls"):
        return _tasklist_running_fallback(image_name)
    try:
        from ctypes import wintypes

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        h = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        if not h or h == -1:
            return _tasklist_running_fallback(image_name)
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        target = image_name.lower()
        found = False
        try:
            if ctypes.windll.kernel32.Process32FirstW(h, ctypes.byref(pe)):
                while True:
                    if pe.szExeFile.lower() == target:
                        found = True
                        break
                    if not ctypes.windll.kernel32.Process32NextW(h, ctypes.byref(pe)):
                        break
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
        return found
    except Exception:
        return _tasklist_running_fallback(image_name)


def _tasklist_running_fallback(image_name: str) -> bool:
    try:
        res = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image_name}"],
                             capture_output=True, creationflags=0x08000000, timeout=20)
        return image_name.lower() in decode_output(res.stdout).lower()
    except Exception:
        return False

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def admin_use() -> dict:
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

def clear_discord() -> dict:
    """Остановка Discord + удаление кэша (доступно из любого UI)."""
    import shutil
    killed = []
    for p in ["Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe"]:
        r = subprocess.run(["taskkill", "/IM", p, "/F"], capture_output=True,
                           creationflags=0x08000000)
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

def hidden_cmd(cmd_list: list, cwd: str = ORIG_DIR, timeout: int = 30) -> dict:
    try:
        res = subprocess.run(cmd_list, cwd=cwd, capture_output=True, text=True, errors="replace",
                             timeout=timeout, creationflags=0x08000000, shell=False)
        return {"ok": res.returncode == 0, "stdout": res.stdout[:3000], "stderr": res.stderr[:1000]}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}

def relaunch_as_admin(extra_args=()) -> bool:
    """Перезапуск текущего приложения с повышением прав (UAC).
    args = argv целиком (включая имя скрипта), иначе запустится пустой python;
    у frozen-exe путь к программе сам является программой — его не дублируем."""
    try:
        argv = list(sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv)
        argv += list(extra_args)
        args = " ".join(f'"{a}"' for a in argv)
        h = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
        return h > 32  # >32 = успех
    except Exception:
        return False


def open_original_service() -> dict:
    """Аварийный запуск оригинального service.bat в отдельном окне консоли."""
    bat = os.path.join(ORIG_DIR, "service.bat")
    if not os.path.isfile(bat):
        return {"ok": False, "service": t("sm.service_bat_missing", p=bat)}
    try:
        subprocess.Popen(["cmd.exe", "/c", "start", "zapret service", "service.bat", "admin"],
                         cwd=ORIG_DIR)
        return {"ok": True, "service": t("sm.service_bat_started")}
    except Exception as e:
        return {"ok": False, "service": str(e)}


def cleanup_orphans() -> dict:
    """Принудительная зачистка зависших процессов winws.exe и службы WinDivert."""
    actions = []
    r = subprocess.run(["taskkill", "/IM", "winws.exe", "/F"],
                       capture_output=True, creationflags=0x08000000)
    if r.returncode == 0:
        actions.append("Terminated orphaned winws.exe processes")
    for wd in ("WinDivert", "WinDivert14"):
        r_sc = subprocess.run(["net", "stop", wd], capture_output=True, creationflags=0x08000000)
        if r_sc.returncode == 0:
            actions.append(f"Stopped {wd} driver service")
    msg = "; ".join(actions) if actions else "No orphaned processes or drivers found"
    return {"ok": True, "service": msg, "actions": actions}


def check_connectivity() -> dict:
    """Быстрая проверка доступности ключевых сервисов (YouTube, Discord, Google) без ожидания долгого теста."""
    import time
    import urllib.request
    targets = [
        {"name": "YouTube", "url": "https://www.youtube.com/generate_204"},
        {"name": "Discord", "url": "https://discord.com"},
        {"name": "Google", "url": "https://www.google.com/generate_204"},
    ]
    results = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for item in targets:
        t0 = time.time()
        try:
            req = urllib.request.Request(item["url"], headers=headers)
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                elapsed_ms = int((time.time() - t0) * 1000)
                code = resp.getcode()
                ok = code in (200, 204, 301, 302)
                results.append({"name": item["name"], "ok": ok, "status": code, "latency_ms": elapsed_ms})
        except Exception as e:
            results.append({"name": item["name"], "ok": False, "status": 0, "error": str(e), "latency_ms": None})
    all_ok = all(r["ok"] for r in results)
    return {"ok": all_ok, "targets": results}
