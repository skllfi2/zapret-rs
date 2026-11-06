# lists.py — списки lists/*.txt: ipset (тумблер loaded/none/any), user-списки, hosts
import os

from i18n import t

from .paths import LISTS_DIR


def ipset_update() -> dict:
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

def load_user_lists() -> dict:
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

def update_hosts() -> dict:
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

def ipset_status() -> str:
    """Как :ipset_switch_status — any / none / loaded по содержимому ipset-all.txt."""
    path = os.path.join(LISTS_DIR, "ipset-all.txt")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = f.read()
    except OSError:
        return "none"  # файла нет — как в оригинале при нечитаемом файле
    lines = [ln for ln in data.splitlines() if ln.strip()]
    if not lines:
        return "any"
    return "none" if any("203.0.113.113/32" in ln for ln in lines) else "loaded"

def toggle_ipset(mode: str | None = None) -> dict:
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
