# diagnostics.py — полный порт :service_diagnostics из service.bat
# Каждая проверка даёт уровень: ok (зелёный) / warn (жёлтый) / bad (красный) —
# ровно как PrintGreen/PrintYellow/PrintRed в оригинале.
import os
import re
import subprocess
import winreg

from i18n import t

from .misc import is_admin
from .paths import BIN_DIR, ORIG_DIR
from .winws import winws_is_running


def tcp_timestamps() -> tuple[bool, str]:
    try:
        res = subprocess.run(["netsh", "int", "tcp", "set", "global", "timestamps=enabled"],
                             capture_output=True, text=True, errors="replace", creationflags=0x08000000)
        return res.returncode == 0, "TCP enabled" if res.returncode == 0 else str(res.stderr)
    except Exception as e:
        return False, str(e)

# === ДИАГНОСТИКА (полный порт :service_diagnostics из service.bat) ===
# Каждая проверка даёт уровень: ok (зелёный) / warn (жёлтый) / bad (красный) —
# ровно как PrintGreen/PrintYellow/PrintRed в оригинале.

def _sc_service_names() -> list[str]:
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

def _tasklist_running(image: str) -> bool:
    try:
        res = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}"],
                             capture_output=True, text=True, errors="replace",
                             creationflags=0x08000000, timeout=20)
        return image.lower() in (res.stdout or "").lower()
    except Exception:
        return False

def _check(name: str, level: str, msg: str, url: str = "") -> dict:
    return {"name": name, "level": level, "msg": msg, "url": url}

def run_diagnostics() -> dict:
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
        ts_line = next((ln for ln in out.splitlines() if "timestamp" in ln), "")
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

def remove_conflicts() -> dict:
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
