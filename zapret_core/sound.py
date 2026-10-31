# sound.py — звуковые уведомления для событий zapret-simple (winsound Win32 API)
import json
import os
import sys

from .paths import SETTINGS_DIR, SETTINGS_FILE

try:
    import winsound
except ImportError:
    winsound = None  # type: ignore[assignment]

ROOT_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOUNDS_DIR = os.path.join(ROOT_DIR, "assets", "sounds")


def is_sound_enabled() -> bool:
    """Проверка, включены ли звуковые уведомления в настройках (по умолчанию True)."""
    try:
        if os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                d = json.load(f)
                return bool(d.get("sound_enabled", True))
    except Exception:
        pass
    return True


def set_sound_enabled(enabled: bool) -> bool:
    """Сохранить статус звуковых уведомлений в ui_settings.json."""
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        data = {}
        if os.path.isfile(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["sound_enabled"] = enabled
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def toggle_sound() -> bool:
    """Переключить статус звука и вернуть новое состояние."""
    new_state = not is_sound_enabled()
    set_sound_enabled(new_state)
    return new_state


def play_sound(event: str) -> bool:
    """Асинхронное воспроизведение системного звука (connect, disconnect, alert, done)."""
    if not winsound or not is_sound_enabled():
        return False
    wav_path = os.path.join(SOUNDS_DIR, f"{event}.wav")
    if not os.path.isfile(wav_path):
        return False
    try:
        winsound.PlaySound(wav_path, winsound.SND_ASYNC | winsound.SND_FILENAME | winsound.SND_NODEFAULT)
        return True
    except Exception:
        return False
