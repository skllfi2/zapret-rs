# misc.py — общие помощники: права админа, скрытые команды, Discord, перезапуск UAC
import os, subprocess, sys, ctypes
from i18n import t
from .paths import ORIG_DIR
from .lists import load_user_lists

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

def hidden_cmd(cmd_list, cwd=ORIG_DIR, timeout=30):
    try:
        res = subprocess.run(cmd_list, cwd=cwd, capture_output=True, text=True, errors="replace",
                             timeout=timeout, creationflags=0x08000000, shell=False)
        return {"ok": res.returncode == 0, "stdout": res.stdout[:3000], "stderr": res.stderr[:1000]}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}

def relaunch_as_admin(extra_args=()):
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
