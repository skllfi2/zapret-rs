# settings.py — тумблеры и статусы как в шапке меню service.bat:
# game_filter.enabled, check_updates.enabled, LOCAL_VERSION
import os, re
from i18n import t
from .paths import ORIG_DIR

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

# === МЕНЮ: версия и тумблеры (порт :menu/:ipset_switch/:check_updates_switch) ===

def local_version():
    """LOCAL_VERSION из service.bat (как в шапке оригинального меню)."""
    try:
        with open(os.path.join(ORIG_DIR, "service.bat"), encoding="utf-8", errors="replace") as f:
            m = re.search(r'set\s+"LOCAL_VERSION=([^"]+)"', f.read())
            return m.group(1).strip() if m else None
    except OSError:
        return None

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
