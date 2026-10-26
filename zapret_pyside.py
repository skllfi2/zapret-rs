#!/usr/bin/env python3
# zapret_pyside — десктопный UI на PySide6 (Qt 6) для zapret-simple
# Структура меню — как в оригинальном service.bat (ZAPRET SERVICE MANAGER v<LOCAL_VERSION>):
# секции :: SERVICE / :: SETTINGS / :: UPDATES / :: TOOLS, статусы в квадратных скобках.
# Тёмная тема ZuiV2, вывод с цветами PrintGreen/PrintYellow/PrintRed.
# PySide6 6.12.0 (abi3, Python 3.15+) — только Essentials.
import sys, os, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import service_manager

try:
    from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, Slot, QTimer
    from PySide6.QtGui import QFont, QAction
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QFrame, QLabel, QPushButton, QComboBox, QTextEdit, QSpinBox, QMenu,
        QDialog, QFormLayout, QDialogButtonBox, QMessageBox,
    )
except ImportError:
    print("ERROR: PySide6 не установлен. Выполни: pip install PySide6-Essentials")
    sys.exit(1)

COLORS = {
    "bg_main": "#181825",
    "bg_card": "#202030",
    "bg_header": "#141420",
    "text_primary": "#f0f0f5",
    "text_secondary": "#a0a0b0",
    "text_muted": "#707078",
    "accent": "#d4afff",
    "danger": "#e86060",
    "warn": "#e8c860",
    "success": "#5ee87f",
    "border": "#2a2a3a",
    "border_hover": "#3a3a4a",
    "button_bg": "#23233a",
    "button_bg_hover": "#2e2e45",
}

# Цвета как PrintGreen/PrintYellow/PrintRed в оригинале
LEVEL_COLORS = {"ok": COLORS["success"], "warn": COLORS["warn"], "bad": COLORS["danger"],
                "info": "#c8c8d8"}

STYLESHEET = f"""
QWidget {{ background-color: {COLORS['bg_main']}; color: {COLORS['text_primary']}; font-family: 'Segoe UI'; }}
QFrame#header {{ background-color: {COLORS['bg_header']}; }}
QLabel#appTitle {{ font-size: 20px; font-weight: bold; }}
QLabel#version {{ color: {COLORS['text_secondary']}; font-size: 13px; }}
QLabel#section {{ color: {COLORS['accent']}; font-size: 10pt; font-weight: bold;
    padding-top: 6px; }}
QLabel#footer {{ color: {COLORS['text_muted']}; font-size: 7pt; }}
QLabel#warn {{ color: {COLORS['danger']}; font-weight: bold; }}
QLabel#status {{ color: {COLORS['text_secondary']}; font-size: 9pt; font-weight: bold; }}
QPushButton {{ background-color: {COLORS['button_bg']}; color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']}; border-radius: 6px; padding: 8px 12px;
    font-family: 'Segoe UI'; font-weight: bold; font-size: 9pt; text-align: left; }}
QPushButton:hover {{ background-color: {COLORS['button_bg_hover']}; border-color: {COLORS['border_hover']}; }}
QPushButton:pressed {{ background-color: #1c1c30; }}
QPushButton#small {{ padding: 6px 10px; font-size: 8pt; text-align: center; }}
QComboBox, QSpinBox {{ background-color: {COLORS['button_bg']}; color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']}; border-radius: 6px; padding: 6px 10px; font-size: 9pt; }}
QComboBox:hover, QSpinBox:hover {{ border-color: {COLORS['border_hover']}; }}
QComboBox QAbstractItemView {{ background-color: {COLORS['bg_card']}; color: {COLORS['text_primary']};
    selection-background-color: {COLORS['button_bg_hover']}; border: 1px solid {COLORS['border']}; }}
QTextEdit {{ background-color: #12121a; color: #e8e8e8; border: 1px solid {COLORS['border']};
    border-radius: 6px; font-family: Consolas; font-size: 9pt; selection-background-color: #3a3a5a; }}
QDialog {{ background-color: {COLORS['bg_card']}; }}
QMenu {{ background-color: {COLORS['bg_card']}; color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']}; }}
QMenu::item:selected {{ background-color: {COLORS['button_bg_hover']}; }}
"""


class WorkerSignals(QObject):
    finished = Signal(object)
    line = Signal(str)  # живой вывод (тесты)


class Worker(QRunnable):
    """Фоновая операция: результат — сигнал finished, потоковый вывод — сигнал line."""
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "error": str(e)}
        self.signals.finished.emit(result)


class ClickableLabel(QLabel):
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
    """Замена fake-файла (аналог :replace_active_fakes_prompt)."""
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


class TestDialog(QDialog):
    """Выбор типа/режима тестов — как два Read-Host в оригинальном test zapret.ps1."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Run Tests")
        form = QFormLayout(self)
        self.kind = QComboBox()
        self.kind.addItem("Standard tests (HTTP/ping)", 1)
        self.kind.addItem("DPI checkers (TCP 16-20 freeze)", 2)
        self.mode = QComboBox()
        self.mode.addItem("All configs", 1)
        self.mode.addItem("Selected configs", 2)
        self.selection = QSpinBox()
        self.selection.setRange(1, 99)
        self.selection.setEnabled(False)
        self.mode.currentIndexChanged.connect(
            lambda i: self.selection.setEnabled(self.mode.currentData() == 2))
        form.addRow("Тип теста:", self.kind)
        form.addRow("Режим:", self.mode)
        form.addRow("Конфиг (при Selected):", self.selection)
        note = QLabel("Тесты требуют прав администратора и УДАЛЁННОЙ службы zapret "
                      "(как в оригинале). Идут несколько минут.")
        note.setWordWrap(True)
        note.setObjectName("footer")
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self):
        sel = self.selection.value() if self.mode.currentData() == 2 else None
        return self.kind.currentData(), self.mode.currentData(), sel


class MainWindow(QMainWindow):
    # Сигнал живого вывода тестов: рабочий поток -> главный поток Qt
    line_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZAPRET SERVICE MANAGER")
        self.resize(780, 660)
        self.setMinimumSize(640, 520)

        self.pool = QThreadPool.globalInstance()
        self._workers = set()
        self._busy = False
        self._tests_running = False

        self._build_ui()
        self._load_strategies()

        # Живой вывод тестов: сигнал рабочего потока -> слот главного потока
        self.line_signal.connect(self._on_line_signal)

        # Таймер статуса службы (один, как в tkinter-версии)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.refresh()
        self.refresh_menu_status()

    # ---------- UI ----------
    def _build_ui(self):
        root = QWidget()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ===== Шапка: как заголовок меню service.bat =====
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(76)
        h = QHBoxLayout(header)
        h.setContentsMargins(18, 6, 18, 6)
        left = QVBoxLayout()
        trow = QHBoxLayout()
        title = QLabel("ZAPRET SERVICE MANAGER")
        title.setObjectName("appTitle")
        trow.addWidget(title)
        self.version_lbl = QLabel("v?")
        self.version_lbl.setObjectName("version")
        trow.addWidget(self.version_lbl)
        trow.addStretch()
        left.addLayout(trow)
        # Strategy + выбор (в оригинале строка "Strategy: X" под заголовком)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Strategy:", objectName="version"))
        self.strat_box = QComboBox()
        self.strat_box.setFixedWidth(230)
        self.strat_box.currentTextChanged.connect(lambda _: self.apply_strategy())
        srow.addWidget(self.strat_box)
        apply_btn = QPushButton("Применить", objectName="small")
        apply_btn.setFixedWidth(100)
        apply_btn.clicked.connect(self.apply_strategy)
        srow.addWidget(apply_btn)
        srow.addStretch()
        left.addLayout(srow)
        h.addLayout(left, 1)

        # Статус службы + payload справа
        right = QVBoxLayout()
        srow2 = QHBoxLayout()
        srow2.addStretch()
        self.dot = QLabel()
        self.dot.setFixedSize(12, 12)
        self.dot.setStyleSheet(f"background-color: {COLORS['text_muted']}; border-radius: 6px;")
        srow2.addWidget(self.dot)
        srow2.addSpacing(6)
        self.status_text = QLabel("Неизвестно")
        self.status_text.setObjectName("status")
        srow2.addWidget(self.status_text)
        right.addLayout(srow2)
        self.payload_warn = ClickableLabel("")
        self.payload_warn.setObjectName("warn")
        self.payload_warn.setAlignment(Qt.AlignRight)
        self.payload_warn.set_on_click(lambda: self.run_action("restore_payloads"))
        right.addWidget(self.payload_warn)
        h.addLayout(right)
        lay.addWidget(header)

        # ===== Меню-секции =====
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(f"QFrame#card {{ background-color: {COLORS['bg_card']}; border-radius: 10px; }}")
        c = QVBoxLayout(card)
        c.setContentsMargins(16, 10, 16, 10)
        c.setSpacing(6)
        lay.addWidget(card, 0)
        lay.setContentsMargins(14, 12, 14, 12)

        # --- :: SERVICE (пункты 1-3 как в оригинале + Start/Stop) ---
        c.addWidget(QLabel(":: SERVICE", objectName="section"))
        g = QGridLayout()
        g.setSpacing(6)
        self._menu_btn(g, 0, 0, "1.  Install Service", lambda: self.run_action("service_install"))
        self._menu_btn(g, 0, 1, "2.  Remove Services", lambda: self.run_action("service_remove"))
        self._menu_btn(g, 1, 0, "3.  Check Status", lambda: self.run_action("service_status"))
        self._menu_btn(g, 1, 1, "Start Service", lambda: self.run_action("start"))
        self._menu_btn(g, 1, 2, "Stop Service", lambda: self.run_action("stop"))
        self._menu_btn(g, 0, 2, "Admin (права)", lambda: self.run_action("relaunch_admin"))
        g.setColumnStretch(0, 3)
        g.setColumnStretch(1, 3)
        g.setColumnStretch(2, 2)
        c.addLayout(g)

        # --- :: SETTINGS (4-7, статусы в []) ---
        c.addWidget(QLabel(":: SETTINGS", objectName="section"))
        g = QGridLayout()
        g.setSpacing(6)
        gf_btn = self._menu_btn(g, 0, 0, "4.  Game Filter", self._game_filter_menu)
        self._status_cell(g, 0, 1, "lbl_gf")
        self._menu_btn(g, 1, 0, "5.  IPSet Filter", lambda: self.run_action("toggle_ipset"))
        self._status_cell(g, 1, 1, "lbl_ipset")
        self._menu_btn(g, 2, 0, "6.  Auto-Update Check", lambda: self.run_action("toggle_check_updates"))
        self._status_cell(g, 2, 1, "lbl_upd")
        self._menu_btn(g, 3, 0, "7.  Replace active fakes", self.show_fakes)
        g.setColumnStretch(0, 2)
        g.setColumnStretch(1, 3)
        c.addLayout(g)

        # --- :: UPDATES (8-10) ---
        c.addWidget(QLabel(":: UPDATES", objectName="section"))
        g = QGridLayout()
        g.setSpacing(6)
        self._menu_btn(g, 0, 0, "8.  Update IPSet List", lambda: self.run_action("ipset_update"))
        self._menu_btn(g, 0, 1, "9.  Update Hosts File", lambda: self.run_action("update_hosts"))
        self._menu_btn(g, 1, 0, "10. Check for Updates", lambda: self.run_action("check_updates"))
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        c.addLayout(g)

        # --- :: TOOLS (11-12 + доп. действия) ---
        c.addWidget(QLabel(":: TOOLS", objectName="section"))
        g = QGridLayout()
        g.setSpacing(6)
        self._menu_btn(g, 0, 0, "11. Run Diagnostics", self.run_diagnostics)
        tests_btn = self._menu_btn(g, 0, 1, "12. Run Tests", self.run_tests)
        self._menu_btn(g, 1, 0, "Remove conflicts", lambda: self.run_action("remove_conflicts"))
        self._menu_btn(g, 1, 1, "Clear Discord cache", lambda: self.run_action("clear_discord"))
        self._menu_btn(g, 2, 0, "Restore payload (.bin)", lambda: self.run_action("restore_payloads"))
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        c.addLayout(g)

        # --- ВЫВОД (цветной, как PrintGreen/Red/Yellow) ---
        c.addWidget(QLabel("ВЫВОД", objectName="section"))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(130)
        c.addWidget(self.output, 1)

        c.addWidget(QLabel("zapret-simple — native SCM (pywin32) | без service.bat | "
                           "PySide6 6.12 | Python 3.15+", objectName="footer"))

        self.setCentralWidget(root)
        self.add_out("Готово. Меню как в оригинальном service.bat — все действия работают "
                     "через service_manager.", "info")

    def _menu_btn(self, grid, row, col, text, cmd):
        btn = QPushButton(text)
        btn.setMinimumHeight(34)
        btn.clicked.connect(cmd)
        grid.addWidget(btn, row, col)
        return btn

    def _status_cell(self, grid, row, col, attr):
        lbl = QLabel("—")
        lbl.setObjectName("status")
        lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        setattr(self, attr, lbl)
        grid.addWidget(lbl, row, col)

    # ---------- Вывод ----------
    def add_out(self, text, level="info"):
        color = LEVEL_COLORS.get(level, LEVEL_COLORS["info"])
        self.output.append(
            f'<span style="color:{color}">{html.escape(str(text))}</span>')
        sb = self.output.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ---------- Фоновые операции ----------
    def submit(self, fn, on_done, *args, **kwargs):
        w = Worker(fn, *args, **kwargs)
        self._workers.add(w)

        def _done(result):
            self._workers.discard(w)
            on_done(result)

        w.signals.finished.connect(_done)
        self.pool.start(w)
        return w

    # ---------- Стратегии ----------
    def _load_strategies(self):
        try:
            strats = service_manager.list_strategies()
        except Exception:
            strats = []
        self.strat_box.blockSignals(True)
        self.strat_box.addItems(strats)
        cur = service_manager.current_strategy()
        if cur and cur in strats:
            self.strat_box.setCurrentText(cur)
        elif strats and "general" in strats:
            self.strat_box.setCurrentText("general")
        self.strat_box.blockSignals(False)

    def apply_strategy(self):
        sid = self.strat_box.currentText()
        if not sid:
            self.add_out("[ERR] Стратегия не выбрана", "bad")
            return
        if not service_manager.is_admin():
            self.add_out("[X] Применение стратегии требует прав администратора — "
                         "нажми «Admin (права)» и повтори", "bad")
            return
        self.add_out(f">>> Применение стратегии: {sid} (служба будет перезапущена)...", "info")
        self.submit(service_manager.apply_strategy, self._apply_done, sid)

    def _apply_done(self, r):
        r = r if isinstance(r, dict) else {}
        self.add_out(f"[{'OK' if r.get('ok') else 'X'}] {r.get('service', r.get('error'))}",
                     "ok" if r.get("ok") else "bad")
        self.update_status()
        self.refresh_menu_status()

    # ---------- Действия ----------
    def run_action(self, action):
        self.add_out(f">>> {action}", "info")
        self.submit(service_manager.run_service_action, self._action_done, action)

    def _action_done(self, r):
        level = "ok" if isinstance(r, dict) and r.get("ok") else "bad"
        if isinstance(r, tuple):
            ok, msg = r
            level = "ok" if ok else "bad"
            msg = str(msg)
        elif isinstance(r, dict):
            msg = r.get("service", r.get("stdout", r.get("stderr", r.get("error", ""))))
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", errors="replace")
            # Частные случаи диагностики-действий с списками
            for line in (r.get("actions") or []) + (r.get("stdout") or [])[:50] \
                    if isinstance(r.get("stdout"), list) else (r.get("actions") or []):
                self.add_out(str(line), "info")
        else:
            msg = str(r)
        self.add_out(f"[{'OK' if level == 'ok' else 'X'}] {str(msg)[:400]}", level)
        self.update_status()
        self.refresh_menu_status()

    # ---------- Game Filter: подменю режимов (как :game_switch) ----------
    def _game_filter_menu(self):
        menu = QMenu(self)
        for name, mode in [("disabled", "disabled"), ("All (TCP and UDP)", "all"),
                           ("TCP", "tcp"), ("UDP", "udp")]:
            act = QAction(name, menu)
            act.triggered.connect(lambda _, m=mode: self._set_game_filter(m))
            menu.addAction(act)
        menu.exec(self.mapToGlobal(self.rect().topLeft()))

    def _set_game_filter(self, mode):
        self.add_out(f">>> Game Filter -> {mode}", "info")
        self.submit(service_manager.run_service_action, self._action_done,
                    "set_game_filter", mode=mode)

    # ---------- Диагностика (17 проверок оригинала) ----------
    def run_diagnostics(self):
        self.add_out(">>> Run Diagnostics (все проверки из service.bat)...", "info")
        self.submit(service_manager.run_diagnostics, self._diag_done)

    def _diag_done(self, r):
        if not isinstance(r, dict):
            self.add_out(f"[X] {r}", "bad")
            return
        # Цветная печать чек-листа — как PrintGreen/PrintYellow/PrintRed
        for ch in r.get("checks", []):
            level = ch.get("level", "info")
            mark = {"ok": "[+]", "warn": "[?]", "bad": "[X]"}.get(level, "   ")
            line = f"{mark} {ch.get('name')}: {ch.get('msg')}"
            self.add_out(line, level)
            if ch.get("url"):
                self.add_out(f"      {ch['url']}", "info")
        self.add_out(r.get("service", ""), "ok" if r.get("ok") else "warn")

    # ---------- Тесты (оригинальный test zapret.ps1) ----------
    def run_tests(self):
        if self._tests_running:
            self.add_out("[?] Тесты уже выполняются", "warn")
            return
        self.submit(service_manager.run_service_action, self._tests_prereq_done,
                    "tests_prereq")

    def _tests_prereq_done(self, r):
        if not r.get("ok"):
            for p in r.get("problems", []):
                self.add_out(f"[X] {p}", "bad")
            self.add_out("Fix the errors above and rerun.", "warn")
            return
        dlg = TestDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        kind, mode, sel = dlg.values()
        self._tests_running = True
        self.add_out(f">>> Run Tests: type={kind}, mode={mode} (идёт несколько минут)...", "info")
        # Живой вывод: колбэк вызывается из рабочего потока, в UI — только через сигнал
        w = Worker(service_manager.run_tests, test_type=kind, mode=mode, selection=sel,
                   on_line=self._emit_line)
        self._workers.add(w)
        w.signals.finished.connect(self._tests_done)
        self.pool.start(w)

    @Slot(str)
    def _on_line_signal(self, line):
        # Цвет по префиксам test zapret.ps1 — как PrintGreen/PrintYellow/PrintRed
        if line.startswith("[OK]") or line.startswith("[INFO]"):
            level = "ok"
        elif line.startswith("[ERROR]") or line.startswith("[X]"):
            level = "bad"
        elif line.startswith("[WARN") or line.startswith("[WARNING]"):
            level = "warn"
        else:
            level = "info"
        self.add_out(line, level)

    def _emit_line(self, line):
        # Вызывается из фонового потока — пушим в главный поток через сигнал Qt
        self.line_signal.emit(line)

    def _tests_done(self, r):
        self._tests_running = False
        r = r if isinstance(r, dict) else {}
        for line in (r.get("stdout") or []):
            self.add_out(line, "info")
        level = "ok" if r.get("ok") else "bad"
        self.add_out(f"[{'OK' if r.get('ok') else 'X'}] {r.get('service', r.get('error'))}", level)

    # ---------- Статус ----------
    def refresh(self):
        if self._busy:
            return
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
        color = COLORS["success"] if running else COLORS["danger"]
        self.status_text.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
        pl = d.get("payloads", {"ok": True, "missing": []})
        if pl.get("ok", True):
            self.payload_warn.setText("")
        else:
            self.payload_warn.setText(f"⚠ нет .bin: {len(pl['missing'])} — восстановить")

    def refresh_menu_status(self):
        """Статусы в квадратных скобках + версия (как шапка меню service.bat)."""
        self.submit(service_manager.run_service_action, self._menu_done, "menu_status")

    def _menu_done(self, r):
        if not isinstance(r, dict):
            return
        if r.get("version"):
            self.version_lbl.setText(f"v{r['version']}")
        if r.get("strategy"):
            self.strat_box.blockSignals(True)
            self.strat_box.setCurrentText(r["strategy"])
            self.strat_box.blockSignals(False)
        self.lbl_gf.setText(f"[{r.get('game_filter', '?')}]")
        self.lbl_ipset.setText(f"[{r.get('ipset', '?')}]")
        self.lbl_upd.setText(f"[{r.get('check_updates', '?')}]")
        if not r.get("admin"):
            # Тонкое напоминание — в оригинале права тоже нужны для части пунктов
            pass

    # ---------- Fakes ----------
    def show_fakes(self):
        self.submit(service_manager.run_service_action, self._fakes_listed, "list_fakes")

    def _fakes_listed(self, r):
        r = r if isinstance(r, dict) else {}
        items = r.get("stdout") or []
        if not items:
            self.add_out("[X] Нет .bin файлов в bin/", "bad")
            return
        lines, num = [], 0
        for f in items:
            if f.get("active"):
                lines.append(f"  *  {f['name']}  {f['sha256']}[ACTIVE]")
            else:
                num += 1
                lines.append(f"  {num}. {f['name']}  {f['sha256']}")
        self.add_out("Fake-файлы:", "info")
        for l in lines:
            self.add_out(l, "info")
        dlg = FakeDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        kind, number = dlg.values()
        self.submit(service_manager.run_service_action, self._fakes_replaced,
                    "replace_active_fakes", fake_type=kind, number=number)

    def _fakes_replaced(self, r):
        r = r if isinstance(r, dict) else {}
        ok = r.get("ok", False)
        self.add_out(f"[{'OK' if ok else 'X'}] {r.get('stdout') or r.get('stderr')}",
                     "ok" if ok else "bad")

    def closeEvent(self, ev):
        self.pool.waitForDone(2000)
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    w = MainWindow()
    ag = app.primaryScreen().availableGeometry()
    w.move(ag.center() - w.rect().center())
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
