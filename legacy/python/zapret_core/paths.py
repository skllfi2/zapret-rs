# paths.py — автоопределение каталога zapret, константы и служебные пути
import os
import sys

# Корень проекта; у frozen-exe (PyInstaller) — каталог самой .exe
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Служебный каталог %LOCALAPPDATA%\zapret-simple для настроек и .strategy
SETTINGS_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "zapret-simple")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "ui_settings.json")
STRATEGY_DIR = SETTINGS_DIR
STRATEGY_FILE = os.path.join(STRATEGY_DIR, ".strategy")  # последняя применённая стратегия
LEGACY_STRATEGY_FILE = os.path.join(APP_DIR, ".strategy")  # старое расположение (для чтения)


def _saved_zapret_dir() -> str | None:
    """Каталог, ранее выбранный пользователем в настройках."""
    try:
        import json
        if os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                d = json.load(f)
                p = d.get("zapret_dir")
                if p and isinstance(p, str) and os.path.isdir(p):
                    return p
    except Exception:
        pass
    return None


def set_zapret_dir(path: str) -> bool:
    """Сохранить пользовательский каталог zapret в ui_settings.json."""
    if not path or not os.path.isdir(path):
        return False
    try:
        import json
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        data = {}
        if os.path.isfile(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["zapret_dir"] = path
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


# === Автоопределение каталога zapret (каскадный поиск) ===
# 1. ZAPRET_DIR (переменная окружения)
# 2. zapret_dir из ui_settings.json (сохранённый выбор пользователя)
# 3. Портативный режим: ./zapret/ или корень приложения
# 4. %LOCALAPPDATA%\zapret-simple\zapret (папка автозагрузки)
# 5. Legacy-пути (AppWatch / Pictures)
def _detect_orig_dir() -> str:
    candidates: list[str] = []
    env = os.environ.get("ZAPRET_DIR")
    if env:
        candidates.append(env)

    saved = _saved_zapret_dir()
    if saved:
        candidates.append(saved)

    candidates.append(os.path.join(APP_DIR, "zapret"))
    candidates.append(APP_DIR)
    candidates.append(os.path.join(SETTINGS_DIR, "zapret"))
    candidates.append(os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                   "AppWatch", "Apps", "zapret-discord-youtube"))
    candidates.append(os.path.join(os.path.expanduser("~"), "Pictures", "zapret-discord-youtube"))

    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "bin", "winws.exe")):
            return os.path.abspath(c)

    # Если нигде не найден — возвращаем локальный ./zapret для понятного сообщения
    return os.path.join(APP_DIR, "zapret")


ORIG_DIR = _detect_orig_dir()
BIN_DIR = os.path.join(ORIG_DIR, "bin")
LISTS_DIR = os.path.join(ORIG_DIR, "lists")
SERVICE_NAME = "zapret"
SERVICE_DISPLAY = "zapret"


def get_bin_path() -> str:
    return os.path.join(ORIG_DIR, "service.bat")


def reload_paths(new_dir: str) -> None:
    """Обновить глобальные пути в paths и зависимых модулях."""
    global ORIG_DIR, BIN_DIR, LISTS_DIR
    ORIG_DIR = os.path.abspath(new_dir)
    BIN_DIR = os.path.join(ORIG_DIR, "bin")
    LISTS_DIR = os.path.join(ORIG_DIR, "lists")
    for mod_name in ("zapret_core.strategies", "zapret_core.settings",
                     "zapret_core.diagnostics", "zapret_core.misc",
                     "zapret_core.tests_runner", "zapret_core.updates",
                     "service_manager"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            setattr(mod, "ORIG_DIR", ORIG_DIR)  # noqa: B010
            setattr(mod, "BIN_DIR", BIN_DIR)  # noqa: B010
            setattr(mod, "LISTS_DIR", LISTS_DIR)  # noqa: B010


def set_custom_zapret_dir(dir_path: str) -> tuple[bool, str]:
    """Установка и сохранение пользовательского каталога zapret."""
    if not dir_path or not os.path.isdir(dir_path):
        return False, f"Каталог не существует: {dir_path}"
    winws = os.path.join(dir_path, "bin", "winws.exe")
    if not os.path.isfile(winws):
        return False, f"В каталоге не найден исполняемый файл bin/winws.exe: {dir_path}"
    if set_zapret_dir(dir_path):
        reload_paths(dir_path)
        return True, f"Каталог zapret успешно установлен: {dir_path}"
    return False, "Не удалось сохранить настройки каталога."


def unpack_zapret_archive(zip_path: str, target_dir: str | None = None) -> tuple[bool, str]:
    """Распаковка zip-архива zapret с автоопределением структуры."""
    import shutil
    import zipfile
    if not os.path.isfile(zip_path):
        return False, f"Файл архива не найден: {zip_path}"
    if not zipfile.is_zipfile(zip_path):
        return False, f"Файл не является корректным ZIP-архивом: {zip_path}"

    try:
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            marker = next((n for n in names if n.replace("\\", "/").endswith("bin/winws.exe")), None)
            if marker is None:
                return False, "В архиве не найден исполняемый файл bin/winws.exe."
            prefix = marker.split("bin/winws.exe", 1)[0]

            if target_dir is None:
                target_dir = os.path.join(APP_DIR, "zapret")
                try:
                    os.makedirs(target_dir, exist_ok=True)
                except OSError:
                    target_dir = os.path.join(SETTINGS_DIR, "zapret")
                    os.makedirs(target_dir, exist_ok=True)

            os.makedirs(target_dir, exist_ok=True)
            abs_target = os.path.abspath(target_dir)
            for n in names:
                if not n.startswith(prefix) or n.endswith("/"):
                    continue
                rel = n[len(prefix):].replace("/", os.sep)
                dest = os.path.abspath(os.path.join(target_dir, rel))
                if not dest.startswith(abs_target):
                    continue  # Защита от Zip Slip
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(n) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)

        set_custom_zapret_dir(target_dir)
        return True, f"Zapret успешно распакован в: {target_dir}"
    except Exception as e:
        return False, f"Ошибка распаковки архива: {e}"
