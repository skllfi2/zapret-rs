# paths.py — автоопределение каталога zapret, константы и служебные пути
import os
import sys


# === Автоопределение каталога zapret (без хардкода одной копии) ===
# Порядок: переменная окружения ZAPRET_DIR -> рабочая копия AppWatch -> ~/Pictures.
def _detect_orig_dir() -> str:
    candidates = []
    env = os.environ.get("ZAPRET_DIR")
    if env:
        candidates.append(env)
    candidates.append(os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                   "AppWatch", "Apps", "zapret-discord-youtube"))
    candidates.append(os.path.join(os.path.expanduser("~"), "Pictures", "zapret-discord-youtube"))
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "bin", "winws.exe")):
            return c
    return candidates[-1]  # последний кандидат — для сообщений об ошибке

ORIG_DIR = _detect_orig_dir()
BIN_DIR = os.path.join(ORIG_DIR, "bin")
LISTS_DIR = os.path.join(ORIG_DIR, "lists")
SERVICE_NAME = "zapret"
SERVICE_DISPLAY = "zapret"

def get_bin_path() -> str:
    # Службу ставит оригинальный service.bat (см. install_service: .bat как binPath запрещён)
    return os.path.join(ORIG_DIR, "service.bat")

# Корень проекта; у frozen-exe (PyInstaller) — каталог самой .exe, иначе .strategy
# попадал бы во временный распаковочный каталог _MEIPASS и терялся при перезапуске.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# .strategy в %LOCALAPPDATA%: каталог приложения может быть read-only
# (Program Files, чужая копия), а %LOCALAPPDATA% пишется всегда.
STRATEGY_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "zapret-simple")
STRATEGY_FILE = os.path.join(STRATEGY_DIR, ".strategy")  # последняя применённая стратегия
LEGACY_STRATEGY_FILE = os.path.join(APP_DIR, ".strategy")  # старое расположение (для чтения)
