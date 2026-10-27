# winws.py — winws.exe: процессы, fake-payload файлы (*.bin), их восстановление
import os
import subprocess

from i18n import t

from .paths import BIN_DIR

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
    import hashlib
    import shutil
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
                try:
                    return os.path.getmtime(p)
                except OSError:
                    return 0
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
