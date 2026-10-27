#!/usr/bin/env python3
# zapret_pyside — десктопный UI на PySide6 (Qt 6) для zapret-simple
# Структура меню — как в оригинальном service.bat (ZAPRET SERVICE MANAGER v<LOCAL_VERSION>):
# секции :: SERVICE / :: SETTINGS / :: UPDATES / :: TOOLS, статусы в квадратных скобках.
# Тёмная тема ZuiV2, вывод с цветами PrintGreen/PrintYellow/PrintRed.
# PySide6 6.12.0 (abi3, Python 3.15+) — только Essentials.
import datetime
import html
import os
import sys
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import i18n
import service_manager
import zapret_core.applog as applog
from i18n import t

try:
    from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
    from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon, QMouseEvent, QPainter, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QSystemTrayIcon,
        QTextEdit,
        QVBoxLayout,
        QWidget,
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
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "error": str(e)}
        self.signals.finished.emit(result)


class ClickableLabel(QLabel):
    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self._on_click: Callable[[], None] | None = None

    def set_on_click(self, fn: Callable[[], None]) -> None:
        self._on_click = fn

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if self._on_click and ev.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        else:
            super().mousePressEvent(ev)


class FakeDialog(QDialog):
    """Замена fake-файла (аналог :replace_active_fakes_prompt)."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("ui.fake_dialog_title"))
        form = QFormLayout(self)
        self.kind = QComboBox()
        self.kind.addItem(t("ui.fake_kind_1"), "1")
        self.kind.addItem(t("ui.fake_kind_2"), "2")
        self.number = QSpinBox()
        self.number.setRange(1, 99)
        form.addRow(t("ui.fake_kind"), self.kind)
        form.addRow(t("ui.fake_number"), self.number)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[str, str]:
        return self.kind.currentData(), str(self.number.value())


class TestDialog(QDialog):
    """Выбор типа/режима тестов — как два Read-Host в оригинальном test zapret.ps1."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("ui.tests_dialog_title"))
        form = QFormLayout(self)
        self.kind = QComboBox()
        self.kind.addItem(t("ui.tests_kind_std"), 1)
        self.kind.addItem(t("ui.tests_kind_dpi"), 2)
        self.mode = QComboBox()
        self.mode.addItem(t("ui.tests_mode_all"), 1)
        self.mode.addItem(t("ui.tests_mode_sel"), 2)
        self.selection = QSpinBox()
        self.selection.setRange(1, 99)
        self.selection.setEnabled(False)
        self.mode.currentIndexChanged.connect(
            lambda i: self.selection.setEnabled(self.mode.currentData() == 2))
        form.addRow(t("ui.tests_kind"), self.kind)
        form.addRow(t("ui.tests_mode"), self.mode)
        form.addRow(t("ui.tests_sel_config"), self.selection)
        note = QLabel(t("ui.tests_note"))
        note.setWordWrap(True)
        note.setObjectName("footer")
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[int, int, int | None]:
        sel = self.selection.value() if self.mode.currentData() == 2 else None
        return self.kind.currentData(), self.mode.currentData(), sel


class MainWindow(QMainWindow):
    # Сигнал живого вывода тестов: рабочий поток -> главный поток Qt
    line_signal = Signal(str)
    # Статус-ячейки меню создаются в _status_cell через setattr — типы объявлены здесь
    lbl_gf: QLabel
    lbl_ipset: QLabel
    lbl_upd: QLabel

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ZAPRET SERVICE MANAGER")
        self.resize(1120, 680)
        self.setMinimumSize(960, 520)

        self.pool = QThreadPool.globalInstance()
        self._workers: set[Worker] = set()
        self._busy = False
        self._tests_running = False

        self._build_ui()
        self._load_strategies()

        # Трей: создаётся после сборки окна; None — системного трея нет (offscreen)
        self.tray: QSystemTrayIcon | None = None
        self._exiting = False
        self._init_tray()

        # Живой вывод тестов: сигнал рабочего потока -> слот главного потока
        self.line_signal.connect(self._on_line_signal)

        # Таймер статуса службы: один на окно, опрос в фоне через QThreadPool
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.refresh()
        self.refresh_menu_status()

    # ---------- UI ----------
    def _build_ui(self) -> None:
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
        strat_lbl = QLabel(t("ui.strategy"))
        strat_lbl.setObjectName("version")
        srow.addWidget(strat_lbl)
        self.strat_box = QComboBox()
        self.strat_box.setFixedWidth(230)
        self.strat_box.currentTextChanged.connect(lambda _: self.apply_strategy())
        srow.addWidget(self.strat_box)
        apply_btn = QPushButton(t("ui.apply"))
        apply_btn.setObjectName("small")
        apply_btn.setFixedWidth(100)
        apply_btn.clicked.connect(self.apply_strategy)
        srow.addWidget(apply_btn)
        srow.addStretch()
        # Переключатель языка ru/en — выбор сохраняется и переживает перезапуск
        self.lang_btn = QPushButton(i18n.LANG.upper())
        self.lang_btn.setObjectName("small")
        self.lang_btn.setFixedSize(46, 26)
        self.lang_btn.setToolTip(t("ui.lang"))
        self.lang_btn.clicked.connect(self._switch_lang)
        srow.addWidget(self.lang_btn)
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
        self.status_text = QLabel(t("ui.status_unknown"))
        self.status_text.setObjectName("status")
        srow2.addWidget(self.status_text)
        right.addLayout(srow2)
        self.payload_warn = ClickableLabel("")
        self.payload_warn.setObjectName("warn")
        self.payload_warn.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.payload_warn.set_on_click(lambda: self.run_action("restore_payloads"))
        right.addWidget(self.payload_warn)
        h.addLayout(right)
        lay.addWidget(header)

        # ===== Тело: меню слева, вывод справа — читается одновременно =====
        body = QHBoxLayout()
        body.setSpacing(12)
        lay.addLayout(body, 1)
        lay.setContentsMargins(14, 12, 14, 12)

        # ===== Меню-секции =====
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(f"QFrame#card {{ background-color: {COLORS['bg_card']}; border-radius: 10px; }}")
        c = QVBoxLayout(card)
        c.setContentsMargins(16, 10, 16, 10)
        c.setSpacing(6)
        body.addWidget(card, 3)

        # --- :: SERVICE (пункты 1-3 как в оригинале + Start/Stop) ---
        sec_lbl = QLabel(t("ui.sec_service"))
        sec_lbl.setObjectName("section")
        c.addWidget(sec_lbl)
        g = QGridLayout()
        g.setSpacing(6)
        self._menu_btn(g, 0, 0, t("ui.install_service"), lambda: self.run_action("service_install"))
        self._menu_btn(g, 0, 1, t("ui.remove_services"), lambda: self.run_action("service_remove"))
        self._menu_btn(g, 1, 0, t("ui.check_status"), lambda: self.run_action("service_status"))
        self._menu_btn(g, 1, 1, t("ui.start_service"), lambda: self.run_action("start"))
        self._menu_btn(g, 1, 2, t("ui.stop_service"), lambda: self.run_action("stop"))
        self._menu_btn(g, 0, 2, t("ui.admin_rights"), lambda: self.run_action("relaunch_admin"))
        g.setColumnStretch(0, 3)
        g.setColumnStretch(1, 3)
        g.setColumnStretch(2, 2)
        c.addLayout(g)

        # --- :: SETTINGS (4-7, статусы в []) ---
        sec_lbl = QLabel(t("ui.sec_settings"))
        sec_lbl.setObjectName("section")
        c.addWidget(sec_lbl)
        g = QGridLayout()
        g.setSpacing(6)
        self._menu_btn(g, 0, 0, t("ui.game_filter"), self._game_filter_menu)
        self._status_cell(g, 0, 1, "lbl_gf")
        self._menu_btn(g, 1, 0, t("ui.ipset_filter"), lambda: self.run_action("toggle_ipset"))
        self._status_cell(g, 1, 1, "lbl_ipset")
        self._menu_btn(g, 2, 0, t("ui.autoupdate_check"), lambda: self.run_action("toggle_check_updates"))
        self._status_cell(g, 2, 1, "lbl_upd")
        self._menu_btn(g, 3, 0, t("ui.replace_fakes"), self.show_fakes)
        g.setColumnStretch(0, 2)
        g.setColumnStretch(1, 3)
        c.addLayout(g)

        # --- :: UPDATES (8-10) ---
        sec_lbl = QLabel(t("ui.sec_updates"))
        sec_lbl.setObjectName("section")
        c.addWidget(sec_lbl)
        g = QGridLayout()
        g.setSpacing(6)
        self._menu_btn(g, 0, 0, t("ui.update_ipset"), lambda: self.run_action("ipset_update"))
        self._menu_btn(g, 0, 1, t("ui.update_hosts"), lambda: self.run_action("update_hosts"))
        self._menu_btn(g, 1, 0, t("ui.check_updates"), lambda: self.run_action("check_updates"))
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        c.addLayout(g)

        # --- :: TOOLS (11-12 + доп. действия) ---
        sec_lbl = QLabel(t("ui.sec_tools"))
        sec_lbl.setObjectName("section")
        c.addWidget(sec_lbl)
        g = QGridLayout()
        g.setSpacing(6)
        self._menu_btn(g, 0, 0, t("ui.run_diagnostics"), self.run_diagnostics)
        self._menu_btn(g, 0, 1, t("ui.run_tests"), self.run_tests)
        self._menu_btn(g, 1, 0, t("ui.remove_conflicts"), lambda: self.run_action("remove_conflicts"))
        self._menu_btn(g, 1, 1, t("ui.clear_discord"), lambda: self.run_action("clear_discord"))
        self._menu_btn(g, 2, 0, t("ui.restore_payload"), lambda: self.run_action("restore_payloads"))
        self._menu_btn(g, 2, 1, t("ui.apply_best"), self.apply_best_strategy)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        c.addLayout(g)
        c.addStretch(1)  # пункты меню прижаты вверх, не слипаются с выводом

        # ===== Правая панель: ВЫВОД (цветной, как PrintGreen/Red/Yellow) =====
        out_panel = QFrame()
        out_panel.setObjectName("card")
        out_panel.setStyleSheet(f"QFrame#card {{ background-color: {COLORS['bg_card']}; border-radius: 10px; }}")
        o = QVBoxLayout(out_panel)
        o.setContentsMargins(14, 10, 14, 10)
        o.setSpacing(6)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumWidth(360)
        # Заголовок панели + копирование/сохранение/очистка вывода
        out_head = QHBoxLayout()
        out_lbl = QLabel(t("ui.output"))
        out_lbl.setObjectName("section")
        out_head.addWidget(out_lbl)
        out_head.addStretch()
        for label, slot in ((t("ui.out_copy"), self._copy_output),
                            (t("ui.out_save"), self._save_output),
                            (t("ui.out_clear"), self._clear_output)):
            b = QPushButton(label)
            b.setObjectName("small")
            b.setFixedHeight(26)
            b.clicked.connect(slot)
            out_head.addWidget(b)
        o.addLayout(out_head)
        o.addWidget(self.output, 1)
        foot_lbl = QLabel(t("ui.footer"))
        foot_lbl.setObjectName("footer")
        o.addWidget(foot_lbl)
        body.addWidget(out_panel, 2)

        self.setCentralWidget(root)
        self.add_out(t("ui.ready_msg"), "info")

    def _menu_btn(self, grid: QGridLayout, row: int, col: int, text: str,
                  cmd: Callable[..., None]) -> QPushButton:
        btn = QPushButton(text)
        btn.setMinimumHeight(34)
        btn.clicked.connect(cmd)
        grid.addWidget(btn, row, col)
        return btn

    def _switch_lang(self) -> None:
        """Переключатель ru/en: сохраняет выбор и перестраивает окно на месте."""
        i18n.save("en" if i18n.LANG == "ru" else "ru")
        old = self.takeCentralWidget()
        if old is not None:
            old.deleteLater()
        self._build_ui()
        self._load_strategies()
        self._init_tray()  # подписи меню трея тоже локализованы
        self.refresh()
        self.refresh_menu_status()

    # ---------- Трей ----------
    def _init_tray(self) -> None:
        """Трей: кружок статуса службы, клик — показать окно, меню — Показать/Выход.
        Повторный вызов (смена языка) пересобирает меню на текущем языке."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        if self.tray is None:
            self.tray = QSystemTrayIcon(self)
            self.tray.activated.connect(self._on_tray_activated)
        menu = QMenu(self)
        act_show = QAction(t("ui.tray_show"), menu)
        act_show.triggered.connect(self._show_from_tray)
        act_exit = QAction(t("ui.tray_exit"), menu)
        act_exit.triggered.connect(self._exit_from_tray)
        menu.addAction(act_show)
        menu.addAction(act_exit)
        self.tray.setContextMenu(menu)
        self.tray.setIcon(self._status_icon(COLORS["text_muted"]))
        self.tray.setToolTip(t("ui.tray_tooltip", s="…"))
        self.tray.show()

    @staticmethod
    def _status_icon(color: str) -> QIcon:
        """Кружок-иконка нужного цвета — без внешних файлов ресурсов."""
        pm = QPixmap(64, 64)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(0, 0, 64, 64)
        p.end()
        return QIcon(pm)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _exit_from_tray(self) -> None:
        self._exiting = True
        self.close()

    def _status_cell(self, grid: QGridLayout, row: int, col: int, attr: str) -> None:
        lbl = QLabel("—")
        lbl.setObjectName("status")
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        setattr(self, attr, lbl)
        grid.addWidget(lbl, row, col)

    # ---------- Вывод ----------
    def add_out(self, text: str, level: str = "info") -> None:
        color = LEVEL_COLORS.get(level, LEVEL_COLORS["info"])
        self.output.append(
            f'<span style="color:{color}">{html.escape(str(text))}</span>')
        sb = self.output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _copy_output(self) -> None:
        QApplication.clipboard().setText(self.output.toPlainText())
        self.add_out(t("ui.out_copy_done"), "ok")

    def _clear_output(self) -> None:
        self.output.clear()

    def _save_output(self) -> None:
        default = f"zapret-output_{datetime.datetime.now():%Y-%m-%d_%H-%M-%S}.txt"
        path, _ = QFileDialog.getSaveFileName(self, t("ui.out_save"), default,
                                              "Text (*.txt);;All files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.output.toPlainText())
            self.add_out(t("ui.out_saved", p=path), "ok")
        except OSError as e:
            self.add_out(t("ui.out_save_fail", e=e), "bad")

    # ---------- Фоновые операции ----------
    def submit(self, fn: Callable[..., Any], on_done: Callable[[Any], None],
               *args: Any, **kwargs: Any) -> Worker:
        w = Worker(fn, *args, **kwargs)
        self._workers.add(w)

        def _done(result: Any) -> None:
            self._workers.discard(w)
            on_done(result)

        w.signals.finished.connect(_done)
        self.pool.start(w)
        return w

    # ---------- Стратегии ----------
    def _load_strategies(self) -> None:
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

    def apply_strategy(self) -> None:
        sid = self.strat_box.currentText()
        if not sid:
            self.add_out(t("ui.err_no_strategy"), "bad")
            return
        if not service_manager.is_admin():
            self.add_out(t("ui.apply_need_admin"), "bad")
            return
        self.add_out(t("ui.applying_strategy", s=sid), "info")
        self.submit(service_manager.apply_strategy, self._apply_done, sid)

    def _apply_done(self, r: Any) -> None:
        r = r if isinstance(r, dict) else {}
        self.add_out(f"[{'OK' if r.get('ok') else 'X'}] {r.get('service', r.get('error'))}",
                     "ok" if r.get("ok") else "bad")
        self.update_status()
        self.refresh_menu_status()

    # ---------- Действия ----------
    def run_action(self, action: str) -> None:
        self.add_out(f">>> {action}", "info")
        self.submit(service_manager.run_service_action, self._action_done, action)

    def _action_done(self, r: Any) -> None:
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
    def _game_filter_menu(self) -> None:
        menu = QMenu(self)
        for name, mode in [(t("ui.gf_disabled"), "disabled"), (t("ui.gf_all"), "all"),
                           (t("ui.gf_tcp"), "tcp"), (t("ui.gf_udp"), "udp")]:
            act = QAction(name, menu)
            act.triggered.connect(lambda _, m=mode: self._set_game_filter(m))
            menu.addAction(act)
        menu.exec(self.mapToGlobal(self.rect().topLeft()))

    def _set_game_filter(self, mode: str) -> None:
        self.add_out(f">>> Game Filter -> {mode}", "info")
        self.submit(service_manager.run_service_action, self._action_done,
                    "set_game_filter", mode=mode)

    # ---------- Диагностика (17 проверок оригинала) ----------
    def run_diagnostics(self) -> None:
        self.add_out(f">>> {t('ui.run_diagnostics')}...", "info")
        self.submit(service_manager.run_diagnostics, self._diag_done)

    def _diag_done(self, r: Any) -> None:
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
    def run_tests(self) -> None:
        if self._tests_running:
            self.add_out(t("ui.games_running"), "warn")
            return
        self.submit(service_manager.run_service_action, self._tests_prereq_done,
                    "tests_prereq")

    def _tests_prereq_done(self, r: Any) -> None:
        if not r.get("ok"):
            for p in r.get("problems", []):
                self.add_out(f"[X] {p}", "bad")
            self.add_out(t("ui.fix_errors"), "warn")
            return
        dlg = TestDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        kind, mode, sel = dlg.values()
        self._tests_running = True
        self.add_out(t("ui.running_tests", t=kind, m=mode), "info")
        # Живой вывод: колбэк вызывается из рабочего потока, в UI — только через сигнал
        w = Worker(service_manager.run_tests, test_type=kind, mode=mode, selection=sel,
                   on_line=self._emit_line)
        self._workers.add(w)
        w.signals.finished.connect(self._tests_done)
        self.pool.start(w)

    @Slot(str)
    def _on_line_signal(self, line: str) -> None:
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

    def _emit_line(self, line: str) -> None:
        # Вызывается из фонового потока — пушим в главный поток через сигнал Qt
        self.line_signal.emit(line)

    def _tests_done(self, r: Any) -> None:
        self._tests_running = False
        r = r if isinstance(r, dict) else {}
        for line in (r.get("stdout") or []):
            self.add_out(line, "info")
        level = "ok" if r.get("ok") else "bad"
        self.add_out(f"[{'OK' if r.get('ok') else 'X'}] {r.get('service', r.get('error'))}", level)

    # ---------- Статус ----------
    def refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.submit(self._read_status, self._status_done)

    def update_status(self) -> None:
        self.refresh()

    @staticmethod
    def _read_status() -> dict:
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

    def _status_done(self, d: Any) -> None:
        self._busy = False
        d = d if isinstance(d, dict) else {}
        running = d.get("running", False)
        self.status_text.setText(d.get("status", t("ui.status_unknown")))
        color = COLORS["success"] if running else COLORS["danger"]
        self.status_text.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
        pl = d.get("payloads", {"ok": True, "missing": []})
        if pl.get("ok", True):
            self.payload_warn.setText("")
        else:
            self.payload_warn.setText(t("ui.payload_warn", n=len(pl['missing'])))
        # Трей: цвет кружка и подсказка = статус службы
        if self.tray is not None:
            self.tray.setIcon(self._status_icon(color))
            self.tray.setToolTip(t("ui.tray_tooltip", s=d.get("status", "?")))

    def refresh_menu_status(self) -> None:
        """Статусы в квадратных скобках + версия (как шапка меню service.bat)."""
        self.submit(service_manager.run_service_action, self._menu_done, "menu_status")

    def _menu_done(self, r: Any) -> None:
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

    # ---------- Лучшая стратегия из результатов тестов ----------
    def apply_best_strategy(self) -> None:
        """Читает 'Best strategy' из последнего test_results_*.txt и применяет её
        тем же путём, что и кнопка Apply (проверка прав, фон, перезапуск службы)."""
        self.add_out(f">>> {t('ui.apply_best')}...", "info")
        self.submit(service_manager.best_strategy, self._best_done)

    def _best_done(self, r: Any) -> None:
        r = r if isinstance(r, dict) else {}
        if not r.get("ok"):
            self.add_out(f"[?] {r.get('reason') or t('tests.best_none')}", "warn")
            return
        sid = r["strategy"]
        self.add_out(t("ui.best_found", s=sid), "ok")
        self.strat_box.blockSignals(True)
        self.strat_box.setCurrentText(sid)
        self.strat_box.blockSignals(False)
        self.apply_strategy()

    # ---------- Fakes ----------
    def show_fakes(self) -> None:
        self.submit(service_manager.run_service_action, self._fakes_listed, "list_fakes")

    def _fakes_listed(self, r: Any) -> None:
        r = r if isinstance(r, dict) else {}
        items = r.get("stdout") or []
        if not items:
            self.add_out(t("ui.no_bins"), "bad")
            return
        lines, num = [], 0
        for f in items:
            if f.get("active"):
                lines.append(f"  *  {f['name']}  {f['sha256']}[ACTIVE]")
            else:
                num += 1
                lines.append(f"  {num}. {f['name']}  {f['sha256']}")
        self.add_out(t("ui.fakes_list"), "info")
        for ln in lines:
            self.add_out(ln, "info")
        dlg = FakeDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        kind, number = dlg.values()
        self.submit(service_manager.run_service_action, self._fakes_replaced,
                    "replace_active_fakes", fake_type=kind, number=number)

    def _fakes_replaced(self, r: Any) -> None:
        r = r if isinstance(r, dict) else {}
        ok = r.get("ok", False)
        self.add_out(f"[{'OK' if ok else 'X'}] {r.get('stdout') or r.get('stderr')}",
                     "ok" if ok else "bad")

    def closeEvent(self, ev: QCloseEvent) -> None:
        if self.tray is not None and not self._exiting:
            # Есть трей — закрытие прячет окно; настоящий выход только из меню трея
            ev.ignore()
            self.hide()
            return
        self.pool.waitForDone(2000)
        super().closeEvent(ev)


def main() -> int:
    # 1. Лог и перехват крашей — до создания окна, чтобы падало уже «под наблюдением»
    applog.install_excepthook()
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    # 2. Один экземпляр: именованный мьютекс ядра Windows
    mutex, already_running = _acquire_single_instance()
    if already_running:
        QMessageBox.warning(None, "zapret-simple", t("ui.already_running"))
        return 1

    # 3. Автоповышение прав: один UAC-вопрос при старте; при отказе работаем без прав
    if not service_manager.is_admin() and "--no-elevate" not in sys.argv:
        if service_manager.relaunch_as_admin(extra_args=["--no-elevate"]):
            _release_mutex(mutex)  # отпускаем до выхода — иначе ребёнок упрётся в мьютекс
            applog.log("relaunched elevated")
            return 0
        applog.log("elevation declined — running without admin rights")

    w = MainWindow()
    ag = app.primaryScreen().availableGeometry()
    w.move(ag.center() - w.rect().center())
    w.show()
    code = app.exec()
    _release_mutex(mutex)
    return code


def _acquire_single_instance() -> tuple[int | None, bool]:
    """(хэндл_мьютекса, уже_запущен?). Хэндл держим живым весь срок процесса."""
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_wchar_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, "Local\\zapret-simple-ui")
        if not handle:
            return None, False
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS — уже запущен
            _release_mutex(handle)
            return None, True
        return handle, False
    except Exception:
        return None, False  # не смогли проверить — не мешаем запуску


def _release_mutex(handle: int | None) -> None:
    if handle:
        try:
            import ctypes
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
