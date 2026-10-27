# applog.py — лог-файл приложения и перехват непредвиденных ошибок.
# Любой необработанный exception (главный поток или фоновые потоки) попадает в
# %LOCALAPPDATA%\zapret-simple\zapret.log, а в UI показывается диалог с путём к логу.
# Всё здесь обязано работать даже при сломанном состоянии — поэтому без исключений.
import os
import sys
import threading
import traceback
from datetime import datetime

LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "zapret-simple")
LOG_FILE = os.path.join(LOG_DIR, "zapret.log")


def log_path():
    return LOG_FILE


def log(msg):
    """Аппенд в лог с меткой времени. Никогда не бросает исключений."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {msg}\n")
    except Exception:
        pass


def _short_error(exc_type, exc):
    name = getattr(exc_type, "__name__", str(exc_type))
    return f"{name}: {exc}"


def _show_dialog(exc_type, exc, tb_text):
    """Диалог с путём к логу — только если Qt уже жив и мы в главном потоке."""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        from i18n import t
        app = QApplication.instance()
        if app is None or threading.current_thread() is not threading.main_thread():
            return
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle(t("ui.crash_title"))
        box.setText(f"{_short_error(exc_type, exc)}\n\n"
                    f"{t('ui.crash_msg', p=LOG_FILE)}")
        box.setDetailedText(tb_text)
        box.exec()
    except Exception:
        pass


def _handle(exc_type, exc, tb):
    tb_text = "".join(traceback.format_exception(exc_type, exc, tb))
    log(f"UNHANDLED {_short_error(exc_type, exc)}\n{tb_text.rstrip()}")
    if not getattr(sys, "frozen", False):
        sys.__excepthook__(exc_type, exc, tb)  # traceback и в консоль при разработке
    _show_dialog(exc_type, exc, tb_text)


def install_excepthook():
    """sys.excepthook + threading.excepthook -> zapret.log. Безопасно вызывать дважды."""
    sys.excepthook = _handle

    def _thread_hook(args):
        exc = (args.exc_type, args.exc_value, args.exc_traceback)
        tb_text = "".join(traceback.format_exception(*exc))
        log(f"UNHANDLED (thread {getattr(args, 'thread', '?')})\n{tb_text.rstrip()}")

    threading.excepthook = _thread_hook
    log(f"start: argv={sys.argv}, frozen={bool(getattr(sys, 'frozen', False))}")
