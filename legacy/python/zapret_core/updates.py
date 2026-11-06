# updates.py — обновления zapret: проверка версии (как :service_check_updates)
# и применение релиза GitHub (бэкап -> замена файлов -> пере-применение стратегии).
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile

from i18n import t

from .paths import ORIG_DIR, STRATEGY_DIR

ZAPRET_REPO = "Flowseal/zapret-discord-youtube"
_USER_AGENT = "zapret-simple"


def _github_latest(repo: str) -> dict:
    """GitHub API: latest release (tag_name, assets). Ошибки сети/API — исключение."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT,
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def _download(url: str, dest: str) -> None:
    """Скачивание файла по URL (для релизов GitHub — через browser_download_url)."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def _local_zapret_version() -> str | None:
    """LOCAL_VERSION из service.bat оригинальной копии."""
    try:
        with open(os.path.join(ORIG_DIR, "service.bat"), encoding="utf-8", errors="replace") as f:
            m = re.search(r'set\s+"LOCAL_VERSION=([^"]+)"', f.read())
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return None


def check_updates() -> dict:
    """Сравнение локальной версии (LOCAL_VERSION из service.bat) с GitHub (как :service_check_updates)."""
    enabled_path = os.path.join(ORIG_DIR, "utils", "check_updates.enabled")
    if not os.path.exists(enabled_path):
        return {"ok": True, "stdout": t("sm.updates_disabled"),
                "stderr": "", "enabled": False}
    local = _local_zapret_version()
    if not local:
        return {"ok": False, "stdout": "", "stderr": t("sm.ver_unreadable")}
    try:
        rel = _github_latest(ZAPRET_REPO)
    except Exception as e:
        # Как в оригинале: не смогли проверить — это не ошибка работы zapret
        return {"ok": True, "stdout": t("sm.ver_local_only", l=local, e=e),
                "stderr": "", "local": local, "remote": None}
    remote = str(rel.get("tag_name") or "").strip()
    if remote == local:
        return {"ok": True, "stdout": t("sm.ver_latest", l=local),
                "stderr": "", "local": local, "remote": remote, "update_available": False}
    return {"ok": True, "stdout": t("sm.ver_new", r=remote, l=local),
            "stderr": "", "local": local, "remote": remote, "update_available": True}


def apply_zapret_update(on_line=None) -> dict:
    """Применение обновления zapret из GitHub Releases.

    Шаги: скачать zip релиза -> бэкап текущей копии -> остановить службу ->
    распаковать поверх ORIG_DIR -> пере-применить текущую стратегию (файлы
    стратегий могли измениться) с перезапуском службы. Настройки (utils/*.enabled)
    и .strategy (%LOCALAPPDATA%) не затрагиваются — они не входят в релизный zip.
    """
    def log(msg: str) -> None:
        if on_line:
            try:
                on_line(msg)
            except Exception:
                pass

    from .misc import is_admin
    if not is_admin():
        return {"ok": False, "stdout": "", "stderr": t("sm.upd_need_admin")}
    try:
        rel = _github_latest(ZAPRET_REPO)
    except Exception:
        return {"ok": False, "stdout": "", "stderr": t("sm.upd_check_failed")}
    tag = str(rel.get("tag_name") or "").strip()
    zip_url = next((a["browser_download_url"] for a in (rel.get("assets") or [])
                    if str(a.get("name") or "").endswith(".zip")), None)
    if not tag or not zip_url:
        return {"ok": False, "stdout": "", "stderr": t("sm.upd_no_zip")}
    tmp = tempfile.mkdtemp(prefix="zapret-upd-")
    try:
        log(t("sm.upd_downloading", v=tag))
        zip_path = os.path.join(tmp, "update.zip")
        _download(zip_url, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            # релизный zip содержит распакованную копию zapret (bin/winws.exe внутри)
            marker = next((n for n in names if n.replace("\\", "/").endswith("bin/winws.exe")), None)
            if marker is None:
                return {"ok": False, "stdout": "", "stderr": t("sm.upd_bad_archive")}
            # общий префикс верхнего уровня (zapret-discord-youtube-1.10.4/...) убираем
            prefix = marker.split("bin/winws.exe", 1)[0]
            # winws.exe занят работающей службой — снимаем её ДО бэкапа и замены
            # файлов (закрытый файл ломает и make_archive, и распаковку)
            from .scm import query_status, stop_service
            if "Running" in (query_status() or ""):
                stop_service()
            backup = os.path.join(STRATEGY_DIR, "backups")
            os.makedirs(backup, exist_ok=True)
            log(t("sm.upd_backuping"))
            shutil.make_archive(os.path.join(backup, f"zapret-{_local_zapret_version() or 'unknown'}"),
                                "zip", ORIG_DIR)
            for n in names:
                if not n.startswith(prefix) or n.endswith("/"):
                    continue
                rel_path = n[len(prefix):].replace("/", os.sep)
                dest = os.path.join(ORIG_DIR, rel_path)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(n) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
        log(t("sm.upd_reapplying"))
        from .strategies import apply_strategy, current_strategy, default_strategy
        sid = current_strategy() or default_strategy()
        if sid:
            r = apply_strategy(sid, restart=True)
            if not r.get("ok"):
                return {"ok": True, "stdout": t("sm.upd_done", v=tag),
                        "stderr": t("sm.upd_reapply_failed", e=r.get("service", "")),
                        "version": tag}
        return {"ok": True, "stdout": t("sm.upd_done", v=tag), "stderr": "", "version": tag}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": t("sm.upd_failed", e=e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
