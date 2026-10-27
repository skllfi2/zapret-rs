# updates.py — проверка обновлений zapret (локальная версия vs GitHub)
import os
from i18n import t
from .paths import ORIG_DIR

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
