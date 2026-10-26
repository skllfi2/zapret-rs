#!/usr/bin/env python3
# zapret-pyside — десктопный UI на PySide6 (Qt 6) для zapret-simple
# Полная замена .bat: SCM через pywin32 (service_manager.py), без браузера.
# PySide6 6.12.0 (abi3, Python 3.15+) — только Essentials, ~215 МБ.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import service_manager

try:
    from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, Slot, QTimer
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QFrame, QLabel, QPushButton, QComboBox, QPlainTextEdit, QSpinBox,
        QDialog, QFormLayout, QDialogButtonBox,
    )
except ImportError:
    print("ERROR: PySide6 не установлен. Выполни: pip install PySide6-Essentials")
    sys.exit(1)

# ZuiV2 palette: dark elegant, subtle borders (как в tkinter-версии)
COLORS = {
    "bg_main": "#181825",
    "bg_card": "#202030",
    "bg_header": "#141420",
    "text_primary": "#f0f0f5",
    "text_secondary": "#a0a0b0",
    "text_muted": "#707078",
    "accent": "#d4afff",
    "danger": "#e86060",
    "success": "#5ee87f",
    "border": "#2a2a3a",
    "border_hover": "#3a3a4a",
    "button_bg": "#23233a",
    "button_bg_hover": "#2e2e45",
}

STYLESHEET = f"""
QWidget {{ background-color: {COLORS['bg_main']}; color: {COLORS['text_primary']}; font-family: 'Segoe UI'; }}
QFrame#header {{ background-color: {COLORS['bg_header']}; }}
QFrame#card {{ background-color: {COLORS['bg_card']}; border-radius: 10px; }}
QLabel#appTitle {{ font-size: 26px; font-weight: bold; }}
QLabel#section {{ color: {COLORS['text_muted']}; font-size: 9pt; font-weight: bold; }}
QLabel#footer {{ color: {COLORS['text_muted']}; font-size: 7pt; }}
QLabel#warn {{ color: {COLORS['danger']}; font-weight: bold; }}
QPushButton {{ background-color: {COLORS['button_bg']}; color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']}; border-radius: 6px; padding: 10px 14px;
    font-family: 'Segoe UI'; font-weight: bold; font-size: 9pt; }}
QPushButton:hover {{ background-color: {COLORS['button_bg_hover']}; border-color: {COLORS['border_hover']}; }}
QPushButton:pressed {{ background-color: #1c1c30; }}
QComboBox, QSpinBox {{ background-color: {COLORS['button_bg']}; color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']}; border-radius: 6px; padding: 6px 10px; font-size: 9pt; }}
QComboBox:hover, QSpinBox:hover {{ border-color: {COLORS['border_hover']}; }}
QComboBox QAbstractItemView {{ background-color: {COLORS['bg_card']}; color: {COLORS['text_primary']};
    selection-background-color: {COLORS['button_bg_hover']}; border: 1px solid {COLORS['border']}; }}
QPlainTextEdit {{ background-color: #12121a; color: #e8e8e8; border: 1px solid {COLORS['border']};
    border-radius: 6px; font-family: Consolas; font-size: 9pt; selection-background-color: #3a3a5a; }}
QDialog {{ background-color: {COLORS['bg_card']}; }}
"""


class WorkerSignals(QObject):
    """Сигнал результата фоновой операции — доставляется в главный поток Qt."""
    finished = Signal(object)


class Worker(QRunnable):
    """Фоновая операция через QThreadPool: заменяет threading.Thread + root.after()."""
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001 — любая ошибка должна попасть в UI, а не убить поток
            result = {"ok": False, "error": str(e)}
        self.signals.finished.emit(result)


class ClickableLabel(QLabel):
    """Метка, реагирующая на клик (используется для предупреждения о payload)."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._on_click = None

    def set_on_click(self, fn):
        self._on_click = fn

    def mousePressEvent(self, ev):
        if self._on_click and ev.button() == Qt.LeftButton:
            self._on_click()
        else:
            super().mousePressEvent(ev)


class FakeDialog(QDialog):
    """Диалог выбора fake-файла (аналог :replace_active_fakes в service.bat)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Replace Active Fake")
        form = QFormLayout(self)
        self.kind = QComboBox()
        self.kind.addItem("1 — Discord UDP", "1")
        self.kind.addItem("2 — GameFilter UDP", "2")
        self.number = QSpinBox()
        self.number.setRange(1, 99)
        form.addRow("Тип fake:", self.kind)
        form.addRow("Номер файла:", self.number)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self):
        return self.kind.currentData(), str(self.number.value())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zapret — DPI Bypass")
        self.resize(760, 620)
        self.setMinimumSize(600, 480)

        # Пул потоков живёт всё время окна; busy-флаг не даёт накопить опросы статуса
        self.pool = QThreadPool.globalInstance()
        self._workers = set()
        self._busy = False

        self._build_ui()
        self._load_strategies()

        # Автообновление статуса службы (ровно один таймер, как в tkinter-версии)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.refresh()

    # ---------- UI ----------
    def _build_ui(self):
        root = QWidget()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(72)
        h = QHBoxLayout(header)
        h.setContentsMargins(20, 0, 20, 0)
        title = QLabel("Zapret")
        title.setObjectName("appTitle")
        h.addWidget(title)
        h.addStretch()
        self.dot = QLabel()
        self.dot.setFixedSize(14, 14)
        self.dot.setStyleSheet(f"background-color: {COLORS['text_muted']}; border-radius: 7px;")
        h.addWidget(self.dot)
        h.addSpacing(8)
        self.status_text = QLabel("Неизвестно")
        self.status_text.setStyleSheet(f"color: {COLORS['text_secondary']}; font-weight: bold;")
        h.addWidget(self.status_text)
        self.payload_warn = ClickableLabel("")
        self.payload_warn.setObjectName("warn")
        self.payload_warn.set_on_click(lambda: self.run_action("restore_payloads"))
        h.addSpacing(10)
        h.addWidget(self.payload_warn)
        lay.addWidget(header)

        # Content card
        card = QFrame()
        card.setObjectName("card")
        c = QVBoxLayout(card)
        c.setContentsMargins(16, 14, 16, 14)
        c.setSpacing(8)
        lay.addWidget(card, 1)
        lay.setContentsMargins(16, 14, 16, 14)

        # Секция управления
        c.addWidget(QLabel("УПРАВЛЕНИЕ СЕРВИСОМ (SCM — без .bat)", objectName="section"))

        # Стратегии: реальные .bat из каталога zapret (как в вебе и в tkinter)
        row = QHBoxLayout()
        row.addWidget(QLabel("Стратегия:", font=QFont("Segoe UI", 9, QFont.Bold)))
        self.strat_box = QComboBox()
        self.strat_box.currentTextChanged.connect(lambda: self.apply_strategy())
        row.addWidget(self.strat_box, 1)
        apply_btn = QPushButton("Применить")
        apply_btn.clicked.connect(self.apply_strategy)
        row.addWidget(apply_btn)
        c.addLayout(row)

        # Кнопки действий (сетка 2 колонки)
        btn_defs = [
            ("Status", lambda: self.run_action("service_status")),
            ("Admin (права)", lambda: self.run_action("relaunch_admin")),
            ("Install Svc", lambda: self.run_action("service_install")),
            ("Uninstall", lambda: self.run_action("service_remove")),
            ("Start", lambda: self.run_action("start")),
            ("Stop", lambda: self.run_action("stop")),
            ("Diag", lambda: self.run_action("service_diagnostics")),
            ("Test", lambda: self.run_action("test")),
            ("Update", lambda: self.run_action("check_updates")),
            ("GameFilter", lambda: self.run_action("load_game_filter")),
            ("Clear Discord", lambda: self.run_action("clear_discord")),
            ("List Fakes", self.show_fakes),
            ("Restore Payload", lambda: self.run_action("restore_payloads")),
            ("IPSet Update", lambda: self.run_action("ipset_update")),
        ]
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (label, cmd) in enumerate(btn_defs):
            btn = QPushButton(label)
            btn.setMinimumHeight(40)
            btn.clicked.connect(cmd)
            grid.addWidget(btn, i // 2, i % 2)
        c.addLayout(grid)

        # Вывод
        c.addWidget(QLabel("ВЫВОД", objectName="section"))
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(140)
        c.addWidget(self.output, 1)

        c.addWidget(QLabel("zapret-simple — native SCM (pywin32) | без service.bat | "
                           "PySide6 6.12 | Python 3.15+", objectName="footer"))

        self.setCentralWidget(root)
        self.append_output("Готово. Нажми любую кнопку.\nВсе функции работают через service_manager (без .bat).")

    # ---------- Фоновые операции ----------
    def submit(self, fn, on_done, *args, **kwargs):
        """Запуск функции в фоне; on_done вызывается в главном потоке с результатом."""
        w = Worker(fn, *args, **kwargs)
        self._workers.add(w)

        def _done(result):
            self._workers.discard(w)
            on_done(result)

        w.signals.finished.connect(_done)
        self.pool.start(w)

    def append_output(self, text):
        self.output.appendPlainText(text)

    # ---------- Стратегии ----------
    def _load_strategies(self):
        try:
            strats = service_manager.list_strategies()
        except Exception:
            strats = []
        # Блокируем сигналы: иначе setCurrentText вызвал бы apply_strategy при старте
        self.strat_box.blockSignals(True)
        self.strat_box.addItems(strats)
        cur = service_manager.current_strategy()
        if cur and cur in strats:
            self.strat_box.setCurrentText(cur)
        elif strats and "general" in strats:
            self.strat_box.setCurrentText("general")
        self.strat_box.blockSignals(False)

    def apply_strategy(self):
        """Применение выбранной стратегии в фоне (перезапуск службы — долго)."""
        sid = self.strat_box.currentText()
        if not sid:
            self.append_output("[ERR] Стратегия не выбрана")
            return
        if not service_manager.is_admin():
            self.append_output("[ERR] Применение стратегии требует прав администратора — "
                               "нажми «Admin (права)» и повтори")
            return
        self.append_output(f">>> Применение стратегии: {sid} (служба будет перезапущена)...")
        self.submit(service_manager.apply_strategy, self._apply_done, sid)

    def _apply_done(self, r):
        r = r if isinstance(r, dict) else {}
        self.append_output(f"[{'OK' if r.get('ok') else 'ERR'}] {r.get('service', r.get('error'))}")
        self.update_status()

    # ---------- Действия ----------
    def run_action(self, action):
        self.append_output(f">>> Выполняется: {action}")
        # sc/netsh/ipset могут занимать секунды — не блокируем UI
        self.submit(service_manager.run_service_action, self._action_done, action)

    def _action_done(self, r):
        if isinstance(r, tuple):
            ok, msg = r
            result = f"[{'OK' if ok else 'ERR'}] {msg}"
        elif isinstance(r, dict):
            ok = r.get("ok", False)
            msg = r.get("service", r.get("stdout", r.get("stderr", r.get("error", ""))))
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", errors="replace")
            result = f"[{'OK' if ok else 'ERR'}] {str(msg)[:200]}"
        else:
            result = str(r)[:200]
        self.append_output(result)
        self.update_status()

    def show_fakes(self):
        """Список fake-файлов + выбор для замены."""
        self.submit(service_manager.run_service_action, self._fakes_listed, "list_fakes")

    def _fakes_listed(self, r):
        r = r if isinstance(r, dict) else {}
        items = r.get("stdout") or []
        if not items:
            self.append_output("[ERR] Нет .bin файлов в bin/")
            return
        lines, num = [], 0
        for f in items:
            if f.get("active"):
                lines.append(f"  *  {f['name']}  {f['sha256']}[ACTIVE]")
            else:
                num += 1
                lines.append(f"  {num}. {f['name']}  {f['sha256']}")
        self.append_output("Fake-файлы:\n" + "\n".join(lines))
        dlg = FakeDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        kind, number = dlg.values()
        self.submit(service_manager.run_service_action, self._fakes_replaced,
                    "replace_active_fakes", fake_type=kind, number=number)

    def _fakes_replaced(self, r):
        r = r if isinstance(r, dict) else {}
        self.append_output(f"[{'OK' if r.get('ok') else 'ERR'}] {r.get('stdout') or r.get('stderr')}")

    # ---------- Статус ----------
    def refresh(self):
        if self._busy:
            return  # предыдущий опрос ещё летит — не плодим потоки
        self._busy = True
        self.submit(self._read_status, self._status_done)

    def update_status(self):
        self.refresh()

    @staticmethod
    def _read_status():
        try:
            s = service_manager.query_status()
            running = service_manager.is_running()
        except Exception as e:  # noqa: BLE001
            return {"status": f"ERR: {str(e)[:30]}", "running": False}
        try:
            pl = service_manager.payloads_status()
        except Exception:
            pl = {"ok": True, "missing": []}
        return {"status": s, "running": running, "payloads": pl}

    def _status_done(self, d):
        self._busy = False
        d = d if isinstance(d, dict) else {}
        running = d.get("running", False)
        self.status_text.setText(d.get("status", "Неизвестно"))
        self.status_text.setStyleSheet(
            f"color: {COLORS['success'] if running else COLORS['danger']}; font-weight: bold;")
        self.dot.setStyleSheet(
            f"background-color: {COLORS['success'] if running else COLORS['danger']}; border-radius: 7px;")
        pl = d.get("payloads", {"ok": True, "missing": []})
        if pl.get("ok", True):
            self.payload_warn.setText("")
        else:
            self.payload_warn.setText(f"⚠ нет .bin: {len(pl['missing'])} — клик для восстановления")

    def closeEvent(self, ev):
        # Дожидаемся фоновых операций, чтобы не оборвать служебные вызовы на середине
        self.pool.waitForDone(2000)
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    w = MainWindow()
    # Центрируем окно на экране
    ag = app.primaryScreen().availableGeometry()
    w.move(ag.center() - w.rect().center())
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
