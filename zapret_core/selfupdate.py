# selfupdate.py — самообновление zapret-simple (GitHub Releases)
#
# Репозиторий проекта ещё не создан: SELF_UPDATE_REPO = "" -> функции вежливо
# сообщают «источник не настроен» и включаются одной правкой константы.
# Логика: источник отдельный от zapret (Flowseal) — обновление приложения никогда
# не трогает файлы zapret, и наоборот (см. updates.apply_zapret_update).
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from i18n import t

from .paths import APP_DIR
from .updates import _download, _github_latest

APP_VERSION = "0.4.0"
SELF_UPDATE_REPO = ""  # "owner/repo" — заполнить, когда репозиторий появится
APP_EXE_NAME = "zapret-simple.exe"  # имя ассета-исполняемого файла в Release


def _find_app_root(extract_dir: str) -> str | None:
    """Каталог распакованного архива, в котором лежит zapret_pyside.py.
    У GitHub zip это owner-repo-tag/ внутри; ищем глубиной до 2 уровней."""
    for base, _dirs, files in os.walk(extract_dir):
        if "zapret_pyside.py" in files:
            return base
        # не спускаемся глубже 2 уровней — архив чужой структуры не разбираем
        depth = base[len(extract_dir):].count(os.sep)
        if depth >= 2:
            _dirs[:] = []
    return None


def check_app_update() -> dict:
    """Локальная версия приложения vs GitHub Releases (если репозиторий настроен)."""
    if not SELF_UPDATE_REPO:
        return {"ok": True, "configured": False, "local": APP_VERSION, "remote": None,
                "update_available": False, "stdout": t("sm.app_upd_unconfigured")}
    try:
        rel = _github_latest(SELF_UPDATE_REPO)
    except Exception:
        return {"ok": True, "configured": True, "local": APP_VERSION, "remote": None,
                "update_available": False, "stdout": t("sm.app_upd_check_failed")}
    tag = str(rel.get("tag_name") or "").lstrip("v")
    available = bool(tag) and tag != APP_VERSION
    return {"ok": True, "configured": True, "local": APP_VERSION,
            "remote": tag or None, "update_available": available,
            "stdout": (t("sm.app_upd_new", r=tag, l=APP_VERSION) if available
                       else t("sm.app_upd_latest", l=APP_VERSION))}


def update_app(on_line=None) -> dict:
    """Скачивание и применение обновления самого приложения.

    Source-режим: распаковка релизного zip поверх каталога приложения.
    Frozen-exe: качаем exe-ассет + вспомогательный .bat ждёт завершения процесса,
    заменяет exe и перезапускает (замена запущенного exe Windows запрещает).
    """
    def log(msg: str) -> None:
        if on_line:
            try:
                on_line(msg)
            except Exception:
                pass

    if not SELF_UPDATE_REPO:
        return {"ok": False, "stdout": "", "stderr": t("sm.app_upd_unconfigured")}
    try:
        rel = _github_latest(SELF_UPDATE_REPO)
    except Exception:
        return {"ok": False, "stdout": "", "stderr": t("sm.app_upd_check_failed")}
    assets = rel.get("assets") or []
    frozen = bool(getattr(sys, "frozen", False))
    tmp = tempfile.mkdtemp(prefix="zapret-simple-upd-")
    try:
        if frozen:
            exe_url = next((a["browser_download_url"] for a in assets
                            if str(a.get("name") or "") == APP_EXE_NAME), None)
            if not exe_url:
                return {"ok": False, "stdout": "", "stderr": t("sm.app_upd_no_exe", e=APP_EXE_NAME)}
            log(t("sm.app_upd_downloading"))
            # staging вне tmp: вспомогательный .bat скопирует exe уже ПОСЛЕ нашего
            # завершения, а tmp в finally удаляется немедленно
            staged = os.path.join(tempfile.gettempdir(), APP_EXE_NAME + ".new")
            _download(exe_url, staged)
            log(t("sm.app_upd_applying"))
            _spawn_replace_helper(staged, os.path.abspath(sys.executable))
            return {"ok": True, "restart": True, "stdout": t("sm.app_upd_done")}
        # Source-режим: zip с исходниками поверх каталога приложения
        zip_url = next((a["browser_download_url"] for a in assets
                        if str(a.get("name") or "").endswith(".zip")), None)
        if not zip_url:
            return {"ok": False, "stdout": "", "stderr": t("sm.app_upd_no_zip")}
        log(t("sm.app_upd_downloading"))
        zip_path = os.path.join(tmp, "update.zip")
        _download(zip_url, zip_path)
        extract_dir = os.path.join(tmp, "x")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
        root = _find_app_root(extract_dir)
        if not root:
            return {"ok": False, "stdout": "", "stderr": t("sm.app_upd_bad_archive")}
        log(t("sm.app_upd_applying"))
        # .strategy и ui_settings лежат в %LOCALAPPDATA% — копирование не трогает их
        shutil.copytree(root, APP_DIR, dirs_exist_ok=True)
        return {"ok": True, "restart": True, "stdout": t("sm.app_upd_done")}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": t("sm.app_upd_failed", e=e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _spawn_replace_helper(new_exe: str, cur_exe: str) -> None:
    """Вспомогательный .bat: дождаться гибели нашего PID, заменить exe, запустить."""
    helper = os.path.join(tempfile.gettempdir(), "zapret-simple-selfupd.bat")
    pid = os.getpid()
    content = (
        "@echo off\r\n"
        f":wait\r\n"
        f'tasklist /FI "PID eq {pid}" | find "{pid}" >nul\r\n'
        f"if not errorlevel 1 (timeout /t 2 /nobreak >nul & goto wait)\r\n"
        f'copy /y "{new_exe}" "{cur_exe}" >nul\r\n'
        f'del "{new_exe}" >nul 2>&1\r\n'
        f'start "" "{cur_exe}"\r\n'
        f'del "%~f0"\r\n'
    )
    with open(helper, "w", encoding="utf-8") as f:
        f.write(content)
    subprocess.Popen(["cmd", "/c", helper],
                     creationflags=0x08000000 | 0x00000008)  # NO_WINDOW | DETACHED


# ZAPRET_REPO используется здесь только для переэкспорта полной картины обновлений;
# самообновление zapret живёт в updates.apply_zapret_update.
__all__ = ["APP_VERSION", "SELF_UPDATE_REPO", "check_app_update", "update_app"]
