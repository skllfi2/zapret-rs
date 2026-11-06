#!/usr/bin/env python3
# [LEGACY] zapret_pyside — десктопный UI на PySide6 (Qt 6) для zapret-simple.
# ПРИМЕЧАНИЕ: Этот модуль переведён в статус LEGACY / DEPRECATED.
# Основной и активно развиваемой версией является нативный клиент на Slint + Rust: zapret-slint!
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
    import shiboken6
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
        QScrollArea,
        QSpinBox,
        QStackedWidget,
        QSystemTrayIcon,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    print("ERROR: PySide6 не установлен. Выполни: pip install PySide6-Essentials")
    sys.exit(1)


def _q_alive(obj: QObject) -> bool:
    """C++-объект Qt ещё не удалён. Диалог мог закрыться, пока шёл фоновый воркер:
    без этой проверки колбэк стучится в удалённые виджеты (краш/порча кучи)."""
    return shiboken6.isValid(obj)

COLORS = {
    "bg_main": "#18181b",         # Windows 11 Fluent dark canvas
    "bg_sidebar": "#131315",      # Dark navigation surface (FileSorter style)
    "bg_card": "#1f1f23",         # Elevated card surface
    "bg_card_hover": "#242429",   # Card hover
    "bg_topbar": "#161619",       # Sub-header bar
    "text_primary": "#f4f4f5",    # High contrast white
    "text_secondary": "#a1a1aa",  # Muted secondary text
    "text_muted": "#71717a",      # Tertiary muted
    "accent": "#0078d4",          # Windows 11 Blue
    "accent_hover": "#1084e3",    # Light accent
    "accent_subtle": "#60cdff",   # Soft accent cyan
    "danger": "#ef4444",          # Red danger
    "danger_hover": "#f87171",    # Soft danger
    "warn": "#f59e0b",            # Amber warning
    "success": "#5ee87f",         # Green success
    "border": "#27272a",          # Subtle border
    "border_card": "#2e2e33",     # Card border
    "border_hover": "#3f3f46",    # Hover border
    "button_bg": "#27272c",       # Button background
    "button_bg_hover": "#323238", # Button hover
    "log_bg": "#0d0d0f",          # Pure terminal dark
}

# Цвета как PrintGreen/PrintYellow/PrintRed в оригинале
LEVEL_COLORS = {"ok": COLORS["success"], "warn": COLORS["warn"], "bad": COLORS["danger"],
                "info": "#c8c8d8"}

STYLESHEET = f"""
QWidget {{ background-color: {COLORS['bg_main']}; color: {COLORS['text_primary']};
    font-family: 'Segoe UI Variable Text', 'Segoe UI Variable', 'Segoe UI', sans-serif; font-size: 9pt; }}

QFrame#sidebar {{ background-color: {COLORS['bg_sidebar']}; border-right: 1px solid {COLORS['border']}; }}
QFrame#statusCard {{ background-color: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; }}
QFrame#topBar {{ background-color: {COLORS['bg_topbar']}; border: 1px solid {COLORS['border']}; border-radius: 8px; }}
QFrame#header {{ background-color: {COLORS['bg_topbar']}; border-bottom: 1px solid {COLORS['border']}; }}
QFrame#card {{ background-color: {COLORS['bg_card']}; border: 1px solid {COLORS['border_card']}; border-radius: 8px; }}
QFrame#card:hover {{ background-color: {COLORS['bg_card_hover']}; border-color: {COLORS['border_hover']}; }}

QLabel#appTitle {{ font-size: 13pt; font-weight: bold; color: #f4f4f5; letter-spacing: 0.5px; }}
QLabel#appLogo {{ font-size: 16pt; color: {COLORS['accent_subtle']}; }}
QLabel#version {{ color: {COLORS['text_secondary']}; font-size: 8pt; }}
QLabel#section {{ color: {COLORS['accent_subtle']}; font-size: 8.5pt; font-weight: bold;
    text-transform: uppercase; letter-spacing: 0.5px; padding: 4px 0 2px 0; border-bottom: 1px solid {COLORS['border']}; }}
QLabel#footer {{ color: {COLORS['text_muted']}; font-size: 7.5pt; }}
QLabel#warn {{ color: {COLORS['danger_hover']}; font-weight: bold; font-size: 8.5pt; }}
QLabel#status {{ color: {COLORS['text_primary']}; font-size: 9pt; font-weight: bold; }}
QLabel#flash {{ color: {COLORS['text_secondary']}; font-size: 8pt; }}
QLabel#cardTitle {{ font-size: 9.5pt; font-weight: bold; color: {COLORS['text_primary']}; }}
QLabel#cardDesc {{ font-size: 8pt; color: {COLORS['text_secondary']}; }}
QLabel#iconBadge {{ background-color: rgba(0, 120, 212, 0.15); color: {COLORS['accent_subtle']};
    border: 1px solid rgba(0, 120, 212, 0.3); border-radius: 8px; font-size: 14pt; }}
QLabel#adminBadge {{ background-color: rgba(255, 255, 255, 0.06); color: {COLORS['text_secondary']};
    border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 4px; padding: 2px 6px; font-size: 7.5pt; font-weight: bold; }}

QPushButton {{ background-color: {COLORS['button_bg']}; color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border_card']}; border-radius: 6px; padding: 6px 14px;
    font-weight: 600; font-size: 8.5pt; text-align: left; }}
QPushButton:hover {{ background-color: {COLORS['button_bg_hover']}; border-color: {COLORS['accent']}; }}
QPushButton:pressed {{ background-color: #1a1a1d; }}
QPushButton:focus {{ border-color: {COLORS['accent']}; }}
QPushButton:disabled {{ color: {COLORS['text_muted']}; background-color: #17171a; border-color: {COLORS['border']}; }}

QPushButton#navBtn {{ background-color: transparent; color: {COLORS['text_secondary']}; border: none;
    border-radius: 6px; padding: 8px 12px; font-size: 9pt; font-weight: 500; text-align: left; }}
QPushButton#navBtn:hover {{ background-color: rgba(255, 255, 255, 0.06); color: {COLORS['text_primary']}; }}
QPushButton#navBtn:checked {{ background-color: {COLORS['accent']}; color: #ffffff; font-weight: bold; }}

QPushButton#small {{ padding: 4px 10px; font-size: 8pt; text-align: center; }}
QPushButton#primary {{ background-color: {COLORS['accent']}; color: #ffffff; border: 1px solid {COLORS['accent_hover']}; }}
QPushButton#primary:hover {{ background-color: {COLORS['accent_hover']}; border-color: #3898ec; }}
QPushButton#accent {{ background-color: #164e2e; color: #4ade80; border: 1px solid #237846; }}
QPushButton#accent:hover {{ background-color: #1d633b; border-color: #34d399; color: #ffffff; }}
QPushButton#danger {{ background-color: #3d1a1d; color: {COLORS['danger_hover']}; border: 1px solid #632328; }}
QPushButton#danger:hover {{ background-color: #502024; border-color: {COLORS['danger']}; color: #ffffff; }}

QLabel#statusBadge {{ background-color: rgba(0, 120, 212, 0.12); color: {COLORS['accent_subtle']};
    border: 1px solid rgba(0, 120, 212, 0.25); border-radius: 4px; padding: 4px 8px; font-weight: bold; font-size: 8pt; }}

QComboBox, QSpinBox {{ background-color: #222226; color: {COLORS['text_primary']};
    border: 1px solid #333338; border-radius: 6px; padding: 5px 10px; font-size: 8.5pt; }}
QComboBox:hover, QSpinBox:hover {{ border-color: #4a4a55; }}
QComboBox:focus, QSpinBox:focus {{ border-color: {COLORS['accent']}; }}
QComboBox::drop-down {{ subcontrol-origin: padding; width: 24px; border: none; }}
QComboBox::down-arrow {{ image: none; width: 8px; height: 8px; }}
QComboBox QAbstractItemView {{ background-color: {COLORS['bg_card']}; color: {COLORS['text_primary']};
    selection-background-color: {COLORS['accent']}; selection-color: #ffffff;
    border: 1px solid #333338; border-radius: 6px; padding: 4px; }}

QTextEdit {{ background-color: {COLORS['log_bg']}; color: #dfe3ec;
    border: 1px solid {COLORS['border']}; border-radius: 6px; padding: 8px;
    font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 8.5pt;
    selection-background-color: #264f78; selection-color: {COLORS['text_primary']}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QDialog {{ background-color: {COLORS['bg_card']}; border: 1px solid {COLORS['border_card']}; border-radius: 8px; }}

QMenu {{ background-color: {COLORS['bg_card']}; color: {COLORS['text_primary']};
    border: 1px solid #333338; border-radius: 6px; padding: 4px; }}
QMenu::item {{ border-radius: 4px; padding: 6px 20px 6px 10px; margin: 1px 2px; }}
QMenu::item:selected {{ background-color: {COLORS['accent']}; color: #ffffff; }}
QMenu::separator {{ height: 1px; background-color: {COLORS['border']}; margin: 4px 6px; }}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background-color: #333338; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background-color: #4f4f58; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background-color: #333338; border-radius: 4px; min-width: 24px; }}
QScrollBar::handle:horizontal:hover {{ background-color: #4f4f58; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QToolTip {{ background-color: #222226; color: {COLORS['text_primary']};
    border: 1px solid #333338; border-radius: 4px; padding: 4px 8px; }}
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
        try:
            self.signals.finished.emit(result)
        except RuntimeError:
            pass


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
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
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


class UpdatesDialog(QDialog):
    """Диалог обновлений: две независимые секции — zapret и само приложение.

    Проверка обеих идёт в фоне (win.submit); обновление одного компонента
    не затрагивает другой. Панель вывода показывается для живого хода обновления.
    """

    def __init__(self, win: "MainWindow") -> None:
        super().__init__(win)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._win = win
        self._zapret_new: str | None = None
        self._app_new: str | None = None
        self.setWindowTitle(t("ui.upd_title"))
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # --- zapret (файлы обхода DPI) ---
        zcard = QFrame()
        zcard.setObjectName("card")
        zl = QVBoxLayout(zcard)
        ztitle = QLabel(t("ui.upd_zapret_sec"))
        ztitle.setObjectName("section")
        zl.addWidget(ztitle)
        self.zapret_lbl = QLabel(t("ui.working"))
        self.zapret_lbl.setWordWrap(True)
        zl.addWidget(self.zapret_lbl)
        self.zapret_btn = QPushButton(t("ui.upd_btn_zapret"))
        self.zapret_btn.setEnabled(False)
        self.zapret_btn.clicked.connect(self._update_zapret)
        zl.addWidget(self.zapret_btn)
        lay.addWidget(zcard)

        # --- zapret-simple (приложение) ---
        acard = QFrame()
        acard.setObjectName("card")
        al = QVBoxLayout(acard)
        atitle = QLabel(t("ui.upd_app_sec"))
        atitle.setObjectName("section")
        al.addWidget(atitle)
        self.app_lbl = QLabel(t("ui.working"))
        self.app_lbl.setWordWrap(True)
        al.addWidget(self.app_lbl)
        self.app_btn = QPushButton(t("ui.upd_btn_app"))
        self.app_btn.setEnabled(False)
        self.app_btn.clicked.connect(self._update_app)
        al.addWidget(self.app_btn)
        lay.addWidget(acard)

        # --- кнопки диалога ---
        row = QHBoxLayout()
        again = QPushButton(t("ui.upd_btn_check"))
        again.clicked.connect(self._check)
        row.addWidget(again)
        row.addStretch()
        close = QPushButton(t("ui.dlg_close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

        self._check()

    def _check(self) -> None:
        """Фоновая проверка обеих секций; кнопки обновления — только при доступности."""
        self.zapret_btn.setEnabled(False)
        self.app_btn.setEnabled(False)
        self.zapret_lbl.setText(t("ui.working"))
        self.app_lbl.setText(t("ui.working"))
        self._win.submit(service_manager.check_updates, self._zapret_checked)
        self._win.submit(service_manager.check_app_update, self._app_checked)

    def _zapret_checked(self, r: Any) -> None:
        if not _q_alive(self):   # диалог закрыт, пока проверялись обновления
            return
        r = r if isinstance(r, dict) else {}
        if r.get("enabled") is False:
            self.zapret_lbl.setText(t("ui.upd_disabled"))
        elif r.get("update_available") and r.get("remote"):
            self._zapret_new = str(r["remote"])
            self.zapret_lbl.setText(t("sm.ver_new", r=r["remote"], l=r.get("local", "?")))
            self.zapret_btn.setEnabled(True)
        else:
            self.zapret_lbl.setText(str(r.get("stderr") or r.get("stdout") or t("ui.upd_none")))

    def _app_checked(self, r: Any) -> None:
        if not _q_alive(self):
            return
        r = r if isinstance(r, dict) else {}
        if not r.get("configured", True):
            self.app_lbl.setText(t("sm.app_upd_unconfigured"))
        elif r.get("update_available") and r.get("remote"):
            self._app_new = str(r["remote"])
            self.app_lbl.setText(t("sm.app_upd_new", r=r["remote"], l=r.get("local", "?")))
            self.app_btn.setEnabled(True)
        else:
            self.app_lbl.setText(str(r.get("stdout") or r.get("stderr") or t("ui.upd_none")))

    def _update_zapret(self) -> None:
        if not self._zapret_new:
            return
        ans = QMessageBox.question(self, t("ui.upd_title"),
                                   t("ui.upd_confirm_zapret", v=self._zapret_new))
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.zapret_btn.setEnabled(False)
        self._win._show_output()  # ход обновления — живой вывод в панель
        self._win.submit_action(service_manager.run_service_action, self._updated,
                                "update_zapret", on_line=self._win._emit_line)

    def _updated(self, r: Any) -> None:
        if not _q_alive(self):
            return
        if not isinstance(r, dict):
            # Воркер отдаёт всегда dict; не-dict — мусор от чужого кода (мок,
            # гонка). Модальное окно на такой «ошибке» опасно: диалог к этому
            # моменту мог уже получить deleteLater, и вложенный цикл QMessageBox
            # уничтожит его посреди показа (порча кучи).
            return
        if r.get("ok"):
            self._win.flash_msg(str(r.get("stdout") or ""), "ok")
        else:
            QMessageBox.warning(self, t("ui.upd_title"),
                                str(r.get("stderr") or r.get("error") or "?"))
        self._check()  # перепроверить обе секции

    def _update_app(self) -> None:
        if not self._app_new:
            return
        ans = QMessageBox.question(self, t("ui.upd_title"),
                                   t("ui.upd_confirm_app", v=self._app_new))
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.app_btn.setEnabled(False)
        self._win._show_output()  # ход обновления — живой вывод в панель
        self._win.submit_action(service_manager.run_service_action, self._app_updated,
                                "update_app", on_line=self._win._emit_line)

    def _app_updated(self, r: Any) -> None:
        if not _q_alive(self):
            return
        if not isinstance(r, dict):
            return   # см. комментарий в _updated: мусор не открывает модалку
        if r.get("ok"):
            # Вспомогательный скрипт заменит файлы после нашего завершения — выходим
            self._win._exiting = True
            self._win.close()
        else:
            QMessageBox.warning(self, t("ui.upd_title"),
                                str(r.get("stderr") or r.get("error") or "?"))
            self._check()


class StatusDialog(QDialog):
    """Диалог статуса службы: служба, winws.exe, версия zapret, стратегия."""

    def __init__(self, win: "MainWindow") -> None:
        super().__init__(win)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle(t("ui.status_title"))
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        self._vals: dict[str, QLabel] = {}
        for i, key in enumerate(("service", "winws", "version", "strategy")):
            name = QLabel(t(f"ui.status_{key}"))
            name.setObjectName("version")
            val = QLabel("…")
            val.setWordWrap(True)
            self._vals[key] = val
            grid.addWidget(name, i, 0)
            grid.addWidget(val, i, 1)
        lay.addLayout(grid)
        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton(t("ui.dlg_close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        win.submit(self._load, self._fill)

    @staticmethod
    def _load() -> dict:
        """Служба + winws + версия/стратегия — одним фоновым запросом."""
        try:
            svc = str(service_manager.query_status())
        except Exception as e:  # noqa: BLE001
            svc = f"ERR: {str(e)[:60]}"
        try:
            running = bool(service_manager.is_running())
        except Exception:  # noqa: BLE001
            running = False
        try:
            menu = service_manager.run_service_action("menu_status") or {}
        except Exception:  # noqa: BLE001
            menu = {}
        return {"service": svc, "running": running,
                "version": menu.get("version", "?"), "strategy": menu.get("strategy", "?")}

    def _fill(self, d: Any) -> None:
        if not _q_alive(self):   # диалог закрыт, пока собирался статус
            return
        d = d if isinstance(d, dict) else {}
        self._vals["service"].setText(str(d.get("service", "?")))
        self._vals["winws"].setText(
            t("ui.status_running") if d.get("running") else t("ui.status_stopped"))
        self._vals["version"].setText(str(d.get("version", "?")))
        self._vals["strategy"].setText(str(d.get("strategy", "?")))


class DiagnosticsDialog(QDialog):
    """Диагностика в диалоге: цветной чек-лист + итог (вместо вывода в лог)."""

    def __init__(self, win: "MainWindow") -> None:
        super().__init__(win)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle(t("ui.diag_title"))
        self.setMinimumSize(560, 440)
        lay = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self._checks_lay = QVBoxLayout(body)
        self._checks_lay.addWidget(QLabel(t("ui.working")))
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        self._counts = QLabel("")
        self._counts.setObjectName("section")
        lay.addWidget(self._counts)
        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton(t("ui.dlg_close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        win.submit(service_manager.run_diagnostics, self._fill)

    def _fill(self, r: Any) -> None:
        if not _q_alive(self):   # диалог закрыт, пока шла диагностика
            return
        while self._checks_lay.count():  # убрать плейсхолдер «Проверяю...»
            item = self._checks_lay.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()
        r = r if isinstance(r, dict) else {}
        checks = r.get("checks") or []
        if not checks:
            self._checks_lay.addWidget(QLabel(str(r.get("service") or t("ui.diag_no_checks"))))
        ok = warn = bad = 0
        for ch in checks:
            level = str(ch.get("level", "info"))
            ok += level == "ok"
            warn += level == "warn"
            bad += level == "bad"
            mark = {"ok": "[+]", "warn": "[?]", "bad": "[X]"}.get(level, "   ")
            line = QLabel(f"{mark} {ch.get('name')}: {ch.get('msg')}")
            line.setWordWrap(True)
            line.setStyleSheet(f"color: {LEVEL_COLORS.get(level, LEVEL_COLORS['info'])};")
            self._checks_lay.addWidget(line)
            if ch.get("url"):
                url = QLabel(f"      {ch['url']}")
                url.setStyleSheet(f"color: {COLORS['text_muted']};")
                self._checks_lay.addWidget(url)
        self._counts.setText(t("ui.diag_counts", ok=ok, warn=warn, bad=bad))
        service_manager.play_sound("done")


class DohDialog(QDialog):
    """Диалог настройки DNS over HTTPS (DoH) на уровне Windows."""

    def __init__(self, win: "MainWindow") -> None:
        super().__init__(win)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._win = win
        self.setWindowTitle(t("ui.doh_title"))
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        sec = QLabel(t("ui.doh_sec"))
        sec.setObjectName("section")
        cl.addWidget(sec)

        self.status_lbl = QLabel(t("ui.working"))
        self.status_lbl.setWordWrap(True)
        cl.addWidget(self.status_lbl)

        # Выбор провайдера
        prow = QHBoxLayout()
        plbl = QLabel(t("ui.doh_provider"))
        prow.addWidget(plbl)
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Cloudflare (1.1.1.1 — быстрый DoH)", "cloudflare")
        self.provider_combo.addItem("Google DNS (8.8.8.8 — надёжный)", "google")
        self.provider_combo.addItem("Quad9 (9.9.9.9 — приватный без логов)", "quad9")
        self.provider_combo.addItem("AdGuard (94.140.14.14 — фильтрация рекламы)", "adguard")
        prow.addWidget(self.provider_combo, 1)
        cl.addLayout(prow)

        brow = QHBoxLayout()
        self.apply_btn = QPushButton(t("ui.doh_apply"))
        self.apply_btn.clicked.connect(self._apply_doh)
        brow.addWidget(self.apply_btn)

        self.disable_btn = QPushButton(t("ui.doh_disable"))
        self.disable_btn.clicked.connect(self._disable_doh)
        brow.addWidget(self.disable_btn)
        cl.addLayout(brow)

        lay.addWidget(card)

        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton(t("ui.dlg_close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

        self._refresh()

    def _refresh(self) -> None:
        self._win.submit(service_manager.get_doh_status, self._on_status)

    def _on_status(self, r: Any) -> None:
        if not _q_alive(self):
            return
        r = r if isinstance(r, dict) else {}
        pname = r.get("provider_name", "?")
        srvs = ", ".join(r.get("servers") or [])
        adps = ", ".join(r.get("adapters") or [])
        autodoh_str = " (Auto-DoH активен)" if r.get("autodoh") else ""
        self.status_lbl.setText(f"{t('ui.doh_status')} {pname}{autodoh_str}\nDNS IP: {srvs}\nАдаптеры: {adps}")
        prov = r.get("provider")
        if prov in ("cloudflare", "google", "quad9", "adguard"):
            idx = self.provider_combo.findData(prov)
            if idx >= 0:
                self.provider_combo.setCurrentIndex(idx)

    def _apply_doh(self) -> None:
        provider = self.provider_combo.currentData()
        self._win.submit(lambda: service_manager.set_doh(provider), self._on_action_done)

    def _disable_doh(self) -> None:
        self._win.submit(service_manager.disable_doh, self._on_action_done)

    def _on_action_done(self, r: Any) -> None:
        if not _q_alive(self):
            return
        r = r if isinstance(r, dict) else {}
        msg = r.get("message") or r.get("error") or ""
        if r.get("ok"):
            service_manager.play_sound("done")
            QMessageBox.information(self, t("ui.doh_title"), msg)
        else:
            service_manager.play_sound("alert")
            QMessageBox.warning(self, t("ui.doh_title"), msg)
        self._refresh()
        self._win.refresh_menu_status()


def _get_asset_path(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", service_manager.APP_DIR)
    p = os.path.join(base, "assets", *parts)
    if os.path.exists(p):
        return p
    return os.path.join(service_manager.APP_DIR, "assets", *parts)


class SettingsCard(QFrame):
    """Карточка настроек в стиле WinUI 3 (по аналогии с SettingsCard в FileSorter).
    Содержит иконку в бейдже, заголовок, описание и область для элементов управления."""
    def __init__(
        self,
        icon_text: str,
        title: str,
        description: str = "",
        action_widget: QWidget | QHBoxLayout | QVBoxLayout | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(64)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(12)

        if icon_text:
            badge = QLabel(icon_text)
            badge.setObjectName("iconBadge")
            badge.setFixedSize(36, 36)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            top.addWidget(badge)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        t_lbl = QLabel(title)
        t_lbl.setObjectName("cardTitle")
        t_box.addWidget(t_lbl)
        if description:
            d_lbl = QLabel(description)
            d_lbl.setObjectName("cardDesc")
            d_lbl.setWordWrap(True)
            t_box.addWidget(d_lbl)
        top.addLayout(t_box, 1)

        if action_widget is not None:
            if isinstance(action_widget, QWidget):
                top.addWidget(action_widget)
            else:
                top.addLayout(action_widget)

        lay.addLayout(top)


class ToastWidget(QWidget):
    """Всплывающее неблокирующее уведомление в стиле WinUI 3 Toast (как в FileSorter)."""
    def __init__(self, msg: str, level: str = "info", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(350, 54)

        border_color = LEVEL_COLORS.get(level, COLORS["accent"])
        container = QFrame(self)
        container.setObjectName("toastContainer")
        container.setGeometry(0, 0, 350, 54)
        container.setStyleSheet(f"""
            QFrame#toastContainer {{
                background-color: #202024;
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)

        box = QHBoxLayout(container)
        box.setContentsMargins(14, 8, 14, 8)
        box.setSpacing(10)

        icon_str = {"ok": "✅", "bad": "❌", "warn": "⚠️", "info": "ℹ️"}.get(level, "ℹ️")
        icon_lbl = QLabel(icon_str)
        icon_lbl.setStyleSheet("font-size: 14px; background: transparent;")
        box.addWidget(icon_lbl)

        lbl = QLabel(msg)
        lbl.setStyleSheet("color: #FFFFFF; font-size: 9pt; font-weight: 500; background: transparent;")
        lbl.setWordWrap(True)
        box.addWidget(lbl, 1)

    def show_and_fade(self, duration_ms: int = 3500) -> None:
        if "unittest" in sys.modules or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        scr = QApplication.primaryScreen()
        if scr:
            geom = scr.geometry()
            self.move(geom.right() - self.width() - 24, geom.bottom() - self.height() - 48)
        self.show()
        QTimer.singleShot(duration_ms, self.close)


class MainWindow(QMainWindow):
    # Сигнал живого вывода тестов: рабочий поток -> главный поток Qt
    line_signal = Signal(str)
    # Статус-ячейки меню создаются в _status_cell через setattr — типы объявлены здесь
    lbl_gf: QLabel
    lbl_ipset: QLabel
    lbl_upd: QLabel
    lbl_doh: QLabel
    lbl_autostart: QLabel

    def __init__(self, auto_refresh: bool | None = None) -> None:
        super().__init__()
        self.setWindowTitle("ZAPRET SERVICE MANAGER")
        self.resize(1180, 720)
        self.setMinimumSize(980, 580)
        self._current_tab_index = 0

        icon_path = _get_asset_path("app.ico")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.pool = QThreadPool.globalInstance()
        self._workers: set[Worker] = set()
        self._busy = False
        self._tests_running = False
        self._best_pending = False  # apply_best -> apply_strategy: флаг для ui.best_fail (D4)

        # Панель вывода скрыта по умолчанию (показ по клику/при тестах); состояние
        # переживает переключение языка (UI пересобирается в _build_ui)
        self._out_visible = False
        # Краткий флеш-статус в шапке — вместо служебных строк в логе вывода
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(5000)
        self._flash_timer.timeout.connect(lambda: self.flash.setText(""))

        self._build_ui()
        self._load_strategies()

        # Трей: создаётся после сборки окна; None — системного трея нет (offscreen)
        self.tray: QSystemTrayIcon | None = None
        self._exiting = False
        self._init_tray()

        # Живой вывод тестов: сигнал рабочего потока -> слот главного потока
        self.line_signal.connect(self._on_line_signal)

        # Таймер статуса службы: один на окно, опрос в фоне через QThreadPool
        if auto_refresh is None:
            auto_refresh = "unittest" not in sys.modules
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        if auto_refresh:
            self.timer.start(3000)
            self.refresh()
        self.refresh_menu_status()

    # ---------- UI (FileSorter / WinUI 3 Navigation Layout) ----------
    def _build_ui(self) -> None:
        self._menu_buttons: list[QPushButton] = []
        root = QWidget()
        root_lay = QHBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # =====================================================================
        # 1. Левый сайдбар навигации (как в FileSorter)
        # =====================================================================
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        s_lay = QVBoxLayout(sidebar)
        s_lay.setContentsMargins(12, 14, 12, 12)
        s_lay.setSpacing(8)

        # Заголовок бренда
        brand_row = QHBoxLayout()
        logo_lbl = QLabel("⚡")
        logo_lbl.setObjectName("appLogo")
        title_lbl = QLabel("ZAPRET SIMPLE")
        title_lbl.setObjectName("appTitle")
        brand_row.addWidget(logo_lbl)
        brand_row.addWidget(title_lbl)
        brand_row.addStretch()
        s_lay.addLayout(brand_row)

        # Бейджи версии и прав Администратора
        badge_row = QHBoxLayout()
        self.version_lbl = QLabel("v?")
        self.version_lbl.setObjectName("version")
        badge_row.addWidget(self.version_lbl)
        badge_row.addStretch()
        admin_lbl = QLabel("🛡️ Admin" if service_manager.is_admin() else "User")
        admin_lbl.setObjectName("adminBadge")
        badge_row.addWidget(admin_lbl)
        s_lay.addLayout(badge_row)
        s_lay.addSpacing(4)

        # Глобальная карточка статуса службы (всегда видна в сайдбаре)
        status_card = QFrame()
        status_card.setObjectName("statusCard")
        sc_lay = QVBoxLayout(status_card)
        sc_lay.setContentsMargins(10, 8, 10, 8)
        sc_lay.setSpacing(6)

        sc_top = QHBoxLayout()
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        self.dot.setStyleSheet(f"background-color: {COLORS['text_muted']}; border-radius: 5px;")
        sc_top.addWidget(self.dot)
        self.status_text = QLabel(t("ui.status_unknown"))
        self.status_text.setObjectName("status")
        sc_top.addWidget(self.status_text, 1)
        sc_lay.addLayout(sc_top)

        self.payload_warn = ClickableLabel("")
        self.payload_warn.setObjectName("warn")
        self.payload_warn.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.payload_warn.set_on_click(lambda: self.run_action("restore_payloads"))
        sc_lay.addWidget(self.payload_warn)

        sc_btns = QHBoxLayout()
        sc_btns.setSpacing(4)
        btn_q_start = self._menu_btn(t("ui.start_service"), lambda: self.run_action("start"), role="accent")
        btn_q_start.setFixedHeight(26)
        btn_q_stop = self._menu_btn(t("ui.stop_service"), lambda: self.run_action("stop"), role="danger")
        btn_q_stop.setFixedHeight(26)
        sc_btns.addWidget(btn_q_start)
        sc_btns.addWidget(btn_q_stop)
        sc_lay.addLayout(sc_btns)
        s_lay.addWidget(status_card)
        s_lay.addSpacing(6)

        # Заголовок навигации
        nav_hdr = QLabel("НАВИГАЦИЯ" if i18n.LANG == "ru" else "NAVIGATION")
        nav_hdr.setStyleSheet("color: #71717a; font-size: 7.5pt; font-weight: bold; padding-left: 4px;")
        s_lay.addWidget(nav_hdr)

        # Кнопки навигации по разделам
        self.nav_buttons: list[QPushButton] = []
        nav_tabs = [
            ("🛡️  " + t("ui.sec_service"), 0),
            ("⚙️  " + t("ui.sec_settings"), 1),
            ("🔄  " + t("ui.sec_updates"), 2),
            ("🛠️  " + t("ui.sec_tools"), 3),
            ("📋  " + t("ui.output"), 4),
        ]
        for name, idx in nav_tabs:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedHeight(38)
            btn.setObjectName("navBtn")
            btn.clicked.connect(lambda checked=False, i=idx: self._switch_tab(i))
            self.nav_buttons.append(btn)
            s_lay.addWidget(btn)

        s_lay.addStretch(1)

        # Подвал сайдбара: язык, звук, тумблер панели вывода
        foot_row = QHBoxLayout()
        foot_row.setSpacing(6)

        self.lang_btn = QPushButton(i18n.LANG.upper())
        self.lang_btn.setObjectName("small")
        self.lang_btn.setFixedSize(46, 28)
        self.lang_btn.setToolTip(t("ui.lang"))
        self.lang_btn.clicked.connect(self._switch_lang)
        foot_row.addWidget(self.lang_btn)

        sound_enabled = service_manager.is_sound_enabled()
        self.sound_btn = QPushButton("🔊" if sound_enabled else "🔇")
        self.sound_btn.setObjectName("small")
        self.sound_btn.setFixedSize(38, 28)
        self.sound_btn.setToolTip(t("ui.sound_on") if sound_enabled else t("ui.sound_off"))
        self.sound_btn.clicked.connect(self._toggle_sound)
        foot_row.addWidget(self.sound_btn)

        self.out_toggle = QPushButton(t("ui.out_show"))
        self.out_toggle.setObjectName("small")
        self.out_toggle.setFixedHeight(28)
        self.out_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.out_toggle.clicked.connect(self._toggle_output)
        foot_row.addWidget(self.out_toggle, 1)
        s_lay.addLayout(foot_row)

        root_lay.addWidget(sidebar)

        # =====================================================================
        # 2. Основная рабочая область (Main Content Area)
        # =====================================================================
        main_area = QWidget()
        m_lay = QVBoxLayout(main_area)
        m_lay.setContentsMargins(16, 12, 16, 12)
        m_lay.setSpacing(10)

        # Верхняя плашка действий (Top Bar: стратегия, флеш, права)
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(54)
        tb_lay = QHBoxLayout(top_bar)
        tb_lay.setContentsMargins(14, 8, 14, 8)
        tb_lay.setSpacing(10)

        strat_lbl = QLabel(t("ui.strategy"))
        strat_lbl.setObjectName("version")
        tb_lay.addWidget(strat_lbl)

        self.strat_box = QComboBox()
        self.strat_box.setFixedWidth(230)
        self.strat_box.currentTextChanged.connect(lambda _: self.apply_strategy())
        tb_lay.addWidget(self.strat_box)

        self.apply_btn = QPushButton(t("ui.apply"))
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setFixedWidth(90)
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.clicked.connect(self.apply_strategy)
        tb_lay.addWidget(self.apply_btn)

        tb_lay.addSpacing(8)
        self.flash = QLabel("")
        self.flash.setObjectName("flash")
        tb_lay.addWidget(self.flash, 1)

        btn_top_admin = self._menu_btn(t("ui.admin_rights"), self._relaunch_admin, role="small")
        btn_top_admin.setFixedHeight(28)
        tb_lay.addWidget(btn_top_admin)

        m_lay.addWidget(top_bar)

        # Стек страниц (QStackedWidget)
        self.stack = QStackedWidget()

        # ----- Страница 0: Служба (Service) -----
        page0 = QWidget()
        p0_lay = QVBoxLayout(page0)
        p0_lay.setContentsMargins(0, 0, 0, 0)
        p0_lay.setSpacing(10)

        sec0_lbl = QLabel(t("ui.sec_service"))
        sec0_lbl.setObjectName("section")
        p0_lay.addWidget(sec0_lbl)

        sc1_actions = QHBoxLayout()
        sc1_actions.setSpacing(6)
        sc1_actions.addWidget(self._menu_btn(t("ui.start_service"), lambda: self.run_action("start"), role="accent"))
        sc1_actions.addWidget(self._menu_btn(t("ui.stop_service"), lambda: self.run_action("stop"), role="danger"))
        sc1_actions.addWidget(self._menu_btn(t("ui.check_status"), self._open_status))
        p0_lay.addWidget(SettingsCard(
            "🛡️",
            t("ui.sec_service"),
            "Мониторинг процесса winws.exe и оперативное управление состоянием службы Windows",
            sc1_actions,
        ))

        sc2_actions = QHBoxLayout()
        sc2_actions.setSpacing(6)
        sc2_actions.addWidget(self._menu_btn(t("ui.apply_best"), self.apply_best_strategy, role="primary"))
        sc2_actions.addWidget(self._menu_btn(t("ui.quick_check"), self._quick_check))
        p0_lay.addWidget(SettingsCard(
            "⭐",
            t("ui.strategy"),
            "Применение наборов параметров winws для обхода DPI или автоматический выбор лучшей по тестам",
            sc2_actions,
        ))

        sc3_actions = QHBoxLayout()
        sc3_actions.setSpacing(6)
        sc3_actions.addWidget(self._menu_btn(t("ui.install_service"), lambda: self.run_action("service_install"), role="primary"))
        sc3_actions.addWidget(self._menu_btn(t("ui.remove_services"), lambda: self.run_action("service_remove"), role="danger"))
        sc3_actions.addWidget(self._menu_btn(t("ui.admin_rights"), self._relaunch_admin, role="accent"))
        p0_lay.addWidget(SettingsCard(
            "⚙️",
            t("ui.install_service"),
            "Создание постоянной системной службы Windows (services.msc) с автозапуском или её удаление",
            sc3_actions,
        ))
        p0_lay.addStretch(1)

        scroll0 = QScrollArea()
        scroll0.setWidgetResizable(True)
        scroll0.setWidget(page0)
        self.stack.addWidget(scroll0)

        # ----- Страница 1: Параметры и сеть (Settings) -----
        page1 = QWidget()
        p1_lay = QVBoxLayout(page1)
        p1_lay.setContentsMargins(0, 0, 0, 0)
        p1_lay.setSpacing(10)

        sec1_lbl = QLabel(t("ui.sec_settings"))
        sec1_lbl.setObjectName("section")
        p1_lay.addWidget(sec1_lbl)

        self.lbl_doh = QLabel("[?]")
        self.lbl_doh.setObjectName("statusBadge")
        doh_act = QHBoxLayout()
        doh_act.setSpacing(8)
        doh_act.addWidget(self.lbl_doh)
        doh_act.addWidget(self._menu_btn(t("ui.doh_sec"), self._open_doh))
        p1_lay.addWidget(SettingsCard(
            "🔒",
            t("ui.doh_sec"),
            "Безопасное шифрование DNS over HTTPS (Cloudflare, Google, AdGuard, Quad9) для IPv4 и IPv6 без утечек",
            doh_act,
        ))

        self.lbl_gf = QLabel("[?]")
        self.lbl_gf.setObjectName("statusBadge")
        gf_act = QHBoxLayout()
        gf_act.setSpacing(8)
        gf_act.addWidget(self.lbl_gf)
        gf_act.addWidget(self._menu_btn(t("ui.game_filter"), self._game_filter_menu))
        p1_lay.addWidget(SettingsCard(
            "🎮",
            t("ui.game_filter"),
            "Исключение портов сетевых игр из обработки winws (снижает пинг и исключает ложные блокировки)",
            gf_act,
        ))

        self.lbl_ipset = QLabel("[?]")
        self.lbl_ipset.setObjectName("statusBadge")
        ipset_act = QHBoxLayout()
        ipset_act.setSpacing(8)
        ipset_act.addWidget(self.lbl_ipset)
        ipset_act.addWidget(self._menu_btn(t("ui.ipset_filter"), lambda: self.run_action("toggle_ipset")))
        p1_lay.addWidget(SettingsCard(
            "🌐",
            t("ui.ipset_filter"),
            "Фильтрация трафика только по заблокированным диапазонам IP-адресов (разгружает процессор)",
            ipset_act,
        ))

        self.lbl_autostart = QLabel("[?]")
        self.lbl_autostart.setObjectName("statusBadge")
        auto_act = QHBoxLayout()
        auto_act.setSpacing(8)
        auto_act.addWidget(self.lbl_autostart)
        auto_act.addWidget(self._menu_btn(t("ui.autostart"), self._toggle_autostart))
        p1_lay.addWidget(SettingsCard(
            "🚀",
            t("ui.autostart"),
            "Автоматический запуск zapret-simple при старте Windows в свернутом в системный трей виде",
            auto_act,
        ))

        self.lbl_upd = QLabel("[?]")
        self.lbl_upd.setObjectName("statusBadge")
        upd_act = QHBoxLayout()
        upd_act.setSpacing(8)
        upd_act.addWidget(self.lbl_upd)
        upd_act.addWidget(self._menu_btn(t("ui.autoupdate_check"), lambda: self.run_action("toggle_check_updates")))
        p1_lay.addWidget(SettingsCard(
            "🔔",
            t("ui.autoupdate_check"),
            "Автоматическая проверка новых релизов ядра zapret на GitHub при каждом запуске",
            upd_act,
        ))

        p1_lay.addWidget(SettingsCard(
            "🎭",
            t("ui.replace_fakes"),
            "Генерация и подмена активных фейковых HTTP/TLS/QUIC пакетов для обхода глубокого DPI анализа",
            self._menu_btn(t("ui.replace_fakes"), self.show_fakes),
        ))
        p1_lay.addStretch(1)

        scroll1 = QScrollArea()
        scroll1.setWidgetResizable(True)
        scroll1.setWidget(page1)
        self.stack.addWidget(scroll1)

        # ----- Страница 2: Обновления и списки (Updates) -----
        page2 = QWidget()
        p2_lay = QVBoxLayout(page2)
        p2_lay.setContentsMargins(0, 0, 0, 0)
        p2_lay.setSpacing(10)

        sec2_lbl = QLabel(t("ui.sec_updates"))
        sec2_lbl.setObjectName("section")
        p2_lay.addWidget(sec2_lbl)

        p2_lay.addWidget(SettingsCard(
            "☁️",
            t("ui.check_updates"),
            "Проверка наличия и загрузка свежей версии zapret из официального репозитория GitHub",
            self._menu_btn(t("ui.check_updates"), self._open_updates),
        ))
        p2_lay.addWidget(SettingsCard(
            "📥",
            t("ui.update_ipset"),
            "Загрузка актуальных списков заблокированных IP-подсетей для точечной фильтрации",
            self._menu_btn(t("ui.update_ipset"), lambda: self.run_action("ipset_update")),
        ))
        p2_lay.addWidget(SettingsCard(
            "📝",
            t("ui.update_hosts"),
            "Обновление локального списка доменных имен zapret-hosts.txt",
            self._menu_btn(t("ui.update_hosts"), lambda: self.run_action("update_hosts")),
        ))
        p2_lay.addWidget(SettingsCard(
            "🔄",
            t("ui.restore_payload"),
            "Восстановление стандартных бинарных шаблонов фейков при их повреждении или отсутствии",
            self._menu_btn(t("ui.restore_payload"), lambda: self.run_action("restore_payloads")),
        ))
        p2_lay.addStretch(1)

        scroll2 = QScrollArea()
        scroll2.setWidgetResizable(True)
        scroll2.setWidget(page2)
        self.stack.addWidget(scroll2)

        # ----- Страница 3: Инструменты и тесты (Tools) -----
        page3 = QWidget()
        p3_lay = QVBoxLayout(page3)
        p3_lay.setContentsMargins(0, 0, 0, 0)
        p3_lay.setSpacing(10)

        sec3_lbl = QLabel(t("ui.sec_tools"))
        sec3_lbl.setObjectName("section")
        p3_lay.addWidget(sec3_lbl)

        p3_lay.addWidget(SettingsCard(
            "⚡",
            t("ui.quick_check"),
            "Мгновенный экспресс-тест YouTube 204, Discord и Google с замером задержки ping за 1 секунду",
            self._menu_btn(t("ui.quick_check"), self._quick_check, role="primary"),
        ))
        p3_lay.addWidget(SettingsCard(
            "🧪",
            t("ui.run_tests"),
            "Комплексное автоматическое тестирование всех доступных стратегий blockcheck",
            self._menu_btn(t("ui.run_tests"), self.run_tests, role="accent"),
        ))
        p3_lay.addWidget(SettingsCard(
            "🩺",
            t("ui.run_diagnostics"),
            "Анализ сетевых адаптеров, конфликтующих программ, антивирусов и других служб WinDivert",
            self._menu_btn(t("ui.run_diagnostics"), self.run_diagnostics),
        ))
        p3_lay.addWidget(SettingsCard(
            "🧹",
            t("ui.remove_conflicts"),
            "Принудительное завершение зависших winws.exe и выгрузка застрявшего драйвера WinDivert14",
            self._menu_btn(t("ui.remove_conflicts"), lambda: self.run_action("remove_conflicts"), role="danger"),
        ))
        p3_lay.addWidget(SettingsCard(
            "💬",
            t("ui.clear_discord"),
            "Очистка локального кэша Discord для сброса заблокированных сессий голосовых каналов",
            self._menu_btn(t("ui.clear_discord"), lambda: self.run_action("clear_discord")),
        ))

        folder_actions = QHBoxLayout()
        folder_actions.setSpacing(6)
        folder_actions.addWidget(self._menu_btn(t("ui.select_folder"), self._choose_zapret_folder))
        folder_actions.addWidget(self._menu_btn(t("ui.unpack_zip"), self._unpack_zapret_zip))
        folder_actions.addWidget(self._menu_btn(t("ui.open_original_service"), lambda: self.run_action("open_original_service")))
        p3_lay.addWidget(SettingsCard(
            "📁",
            "Управление каталогом zapret",
            "Выбор сторонней папки zapret, распаковка скачанного архива zip или запуск оригинального service.bat",
            folder_actions,
        ))
        p3_lay.addStretch(1)

        scroll3 = QScrollArea()
        scroll3.setWidgetResizable(True)
        scroll3.setWidget(page3)
        self.stack.addWidget(scroll3)

        # ----- Страница 4: Журнал событий (Logs) -----
        page4 = QWidget()
        p4_lay = QVBoxLayout(page4)
        p4_lay.setContentsMargins(0, 0, 0, 0)
        p4_lay.setSpacing(10)
        p4_lbl = QLabel(t("ui.output"))
        p4_lbl.setObjectName("section")
        p4_lay.addWidget(p4_lbl)
        p4_hint = QLabel("Журнал вывода диагностических команд, тестов доступности и системных логов.")
        p4_hint.setStyleSheet("color: #a1a1aa; font-size: 8.5pt;")
        p4_lay.addWidget(p4_hint)
        p4_lay.addStretch(1)
        self.stack.addWidget(page4)

        m_lay.addWidget(self.stack, 1)

        # Синхронизируем активный таб в сайдбаре
        idx = min(max(0, self._current_tab_index), len(self.nav_buttons) - 1)
        self.nav_buttons[idx].setChecked(True)
        self.stack.setCurrentIndex(min(idx, 3))

        # =====================================================================
        # 3. Нижняя выдвижная панель вывода (Collapsible Output Drawer)
        # =====================================================================
        self.out_panel = QFrame()
        self.out_panel.setObjectName("card")
        self.out_panel.setFixedHeight(180)
        o = QVBoxLayout(self.out_panel)
        o.setContentsMargins(12, 8, 12, 8)
        o.setSpacing(6)

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

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.document().setMaximumBlockCount(2000)
        o.addWidget(self.output, 1)

        foot_lbl = QLabel(t("ui.footer"))
        foot_lbl.setObjectName("footer")
        o.addWidget(foot_lbl)

        m_lay.addWidget(self.out_panel)
        self.out_panel.setVisible(self._out_visible)
        self._sync_out_toggle()

        root_lay.addWidget(main_area, 1)

        self.setCentralWidget(root)
        self.add_out(t("ui.ready_msg"), "info")

    # ---------- Переключение вкладок сайдбара ----------
    def _switch_tab(self, idx: int) -> None:
        self._current_tab_index = idx
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == idx)
        if idx == 4:
            self._show_output()
        else:
            self.stack.setCurrentIndex(idx)

    # ---------- Панель вывода: показ/скрытие ----------
    def _toggle_output(self) -> None:
        self._out_visible = not self._out_visible
        self.out_panel.setVisible(self._out_visible)
        self._sync_out_toggle()

    def _show_output(self) -> None:
        """Показать панель вывода (живой вывод тестов, списки результата)."""
        if not self._out_visible:
            self._out_visible = True
            self.out_panel.setVisible(True)
            self._sync_out_toggle()

    def _sync_out_toggle(self) -> None:
        self.out_toggle.setText(t("ui.out_hide") if self._out_visible else t("ui.out_show"))

    def flash_msg(self, text: str, level: str = "info") -> None:
        """Краткий статус действия в шапке — вместо служебных строк в логе."""
        if not text:
            return
        color = LEVEL_COLORS.get(level, LEVEL_COLORS["info"])
        self.flash.setStyleSheet(f"color: {color};")
        self.flash.setText(str(text)[:200])
        self._flash_timer.start()
        self.show_toast(str(text)[:120], level)

    def show_toast(self, text: str, level: str = "info") -> None:
        """Показывает ToastWidget в правом нижнем углу экрана (стиль FileSorter)."""
        if "unittest" in sys.modules or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        try:
            toast = ToastWidget(text, level, self)
            toast.show_and_fade(3500)
        except Exception:
            pass

    def _menu_btn(
        self,
        text_or_grid: Any,
        slot_or_row: Any = None,
        role: str = "",
        text_legacy: str = "",
        cmd_legacy: Any = None,
        role_legacy: str = "",
        **kwargs: Any,
    ) -> QPushButton:
        """Создает и регистрирует кнопку действия (гасится при submit_action).
        Поддерживает как сигнатуру (text, slot, role), так и legacy (grid, row, col, text, cmd, role)."""
        if isinstance(text_or_grid, str):
            text = text_or_grid
            cmd = slot_or_row
            r = role or str(kwargs.get("role_or_col") or "")
            btn = QPushButton(text)
            if r:
                btn.setObjectName(r)
            btn.setMinimumHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if callable(cmd):
                btn.clicked.connect(cmd)
            self._menu_buttons.append(btn)
            return btn
        else:
            grid = text_or_grid
            row = slot_or_row
            col = role
            text = text_legacy
            cmd = cmd_legacy
            r = role_legacy or str(kwargs.get("role") or "")
            btn = QPushButton(text)
            if r:
                btn.setObjectName(r)
            btn.setMinimumHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if callable(cmd):
                btn.clicked.connect(cmd)
            if grid is not None and hasattr(grid, "addWidget"):
                grid.addWidget(btn, row, col)
            self._menu_buttons.append(btn)
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

    def _toggle_sound(self) -> None:
        """Переключатель звука: инвертирует статус, сохраняет в настройки и обновляет кнопку."""
        enabled = service_manager.toggle_sound()
        self.sound_btn.setText("🔊" if enabled else "🔇")
        self.sound_btn.setToolTip(t("ui.sound_on") if enabled else t("ui.sound_off"))
        if enabled:
            service_manager.play_sound("connect")

    def _open_doh(self) -> None:
        """Открытие диалога настройки DoH."""
        DohDialog(self).exec()

    def _toggle_autostart(self) -> None:
        """Включение / отключение запуска zapret-simple вместе с Windows."""
        enabled = service_manager.toggle_autostart()
        if hasattr(self, "lbl_autostart"):
            self.lbl_autostart.setText(f"[{t('ui.autostart_on') if enabled else t('ui.autostart_off')}]")
        status_txt = t("ui.autostart_on") if enabled else t("ui.autostart_off")
        self.flash_msg(f"{t('ui.autostart')} {status_txt}", "ok")
        service_manager.play_sound("done")

    def _choose_zapret_folder(self) -> None:
        """Выбор пользователем каталога zapret вручную."""
        folder = QFileDialog.getExistingDirectory(self, t("ui.choose_zapret_folder"),
                                                 service_manager.ORIG_DIR)
        if not folder:
            return
        ok, msg = service_manager.set_custom_zapret_dir(folder)
        if ok:
            service_manager.play_sound("done")
            self.flash_msg(msg, "ok")
            self._load_strategies()
            self.update_status()
            self.refresh_menu_status()
        else:
            service_manager.play_sound("alert")
            self.flash_msg(msg, "bad")

    def _unpack_zapret_zip(self) -> None:
        """Распаковка скачанного архива zapret."""
        zip_path, _ = QFileDialog.getOpenFileName(self, t("ui.choose_zapret_zip"),
                                                  "", t("ui.zip_filter"))
        if not zip_path:
            return
        self.flash_msg("Распаковка архива zapret...", "info")
        self.submit_action(service_manager.unpack_zapret_archive, self._unpack_done, zip_path)

    def _unpack_done(self, r: Any) -> None:
        if not _q_alive(self):
            return
        if isinstance(r, tuple):
            ok, msg = r
        elif isinstance(r, dict):
            ok, msg = r.get("ok", False), r.get("service", "")
        else:
            ok, msg = False, str(r)
        if ok:
            service_manager.play_sound("done")
            self.flash_msg(str(msg), "ok")
            self._load_strategies()
            self.update_status()
            self.refresh_menu_status()
        else:
            service_manager.play_sound("alert")
            self.flash_msg(str(msg), "bad")

    def _quick_check(self) -> None:
        """Быстрая проверка доступности сервисов (YouTube, Discord, Google)."""
        self.flash_msg(t("ui.working"), "info")
        self.submit(service_manager.check_connectivity, self._quick_check_done)

    def _quick_check_done(self, r: Any) -> None:
        if not _q_alive(self):
            return
        r = r if isinstance(r, dict) else {}
        targets = r.get("targets", [])
        lines = []
        for tg in targets:
            name = tg.get("name")
            ok = tg.get("ok")
            lat = tg.get("latency_ms")
            lat_str = f" ({lat} ms)" if lat is not None else ""
            status = "OK" if ok else "FAIL"
            lines.append(f"{name}: {status}{lat_str}")
        summary = " | ".join(lines) if lines else "Нет данных"
        all_ok = bool(r.get("ok", False))
        self.flash_msg(summary, "ok" if all_ok else "bad")
        self.add_out(f"[Check] {summary}", "ok" if all_ok else "bad")
        service_manager.play_sound("done" if all_ok else "alert")

    # ---------- Трей ----------
    def _init_tray(self) -> None:
        """Трей: кружок статуса службы, клик — показать окно, меню — Показать/Выход.
        Повторный вызов (смена языка) только обновляет подписи и подсказку (D3):
        QAction переиспользуются, иконка не сбрасывается в серый."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        if self.tray is None:
            self.tray = QSystemTrayIcon(self)
            self.tray.activated.connect(self._on_tray_activated)
            self._tray_menu = QMenu(self)
            self._tray_act_show = QAction(t("ui.tray_show"), self._tray_menu)
            self._tray_act_show.triggered.connect(self._show_from_tray)
            self._tray_act_exit = QAction(t("ui.tray_exit"), self._tray_menu)
            self._tray_act_exit.triggered.connect(self._exit_from_tray)
            self._tray_menu.addAction(self._tray_act_show)
            self._tray_menu.addAction(self._tray_act_exit)
            self.tray.setContextMenu(self._tray_menu)
            self.tray.setIcon(self._status_icon(COLORS["text_muted"]))
            self.tray.setToolTip(t("ui.tray_tooltip", s="…"))
        else:
            self._tray_act_show.setText(t("ui.tray_show"))
            self._tray_act_exit.setText(t("ui.tray_exit"))
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

    def _status_cell(self, grid: Any, row: int = 0, col: int = 0, attr: str = "") -> None:
        if isinstance(grid, str):
            attr = grid
            lbl = QLabel("—")
            lbl.setObjectName("statusBadge")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            setattr(self, attr, lbl)
            return
        lbl = QLabel("—")
        lbl.setObjectName("statusBadge")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        setattr(self, attr, lbl)
        if grid is not None and hasattr(grid, "addWidget"):
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
        self.flash_msg(t("ui.out_copy_done"), "ok")

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
            self.flash_msg(t("ui.out_saved", p=path), "ok")
        except OSError as e:
            self.flash_msg(t("ui.out_save_fail", e=e), "bad")

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

    def submit_action(self, fn: Callable[..., Any], on_done: Callable[[Any], None],
                      *args: Any, **kwargs: Any) -> Worker:
        """submit + гашение кнопок действий на время операции (B1): двойной клик
        не должен порождать параллельные SCM-вызовы/тесты. Статус-опросы
        (refresh/refresh_menu_status) идут через submit и кнопки не трогают."""
        for b in self._menu_buttons:
            b.setEnabled(False)

        def _done(result: Any) -> None:
            for b in self._menu_buttons:
                b.setEnabled(True)
            on_done(result)

        return self.submit(fn, _done, *args, **kwargs)

    # ---------- Повышение прав (A3) ----------
    def _relaunch_admin(self) -> None:
        """Кнопка «Повысить права»: отпускаем мьютекс, зовём UAC-перезапуск.
        При успехе закрываем текущий экземпляр (иначе ребёнок упирается в
        ERROR_ALREADY_EXISTS); при отказе UAC — возвращаем мьютекс."""
        _release_mutex()
        self.submit_action(service_manager.run_service_action, self._relaunch_done, "relaunch_admin")

    def _relaunch_done(self, r: Any) -> None:
        self._action_done(r)
        if isinstance(r, dict) and r.get("ok"):
            self._exiting = True  # elevated-копия уже запущена — выходим без мьютекса
            self.close()
        else:
            _acquire_single_instance()  # UAC отклонён — возвращаем мьютекс

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
            self._best_pending = False  # ранний отказ — _apply_done не выстрелит
            self.flash_msg(t("ui.err_no_strategy"), "bad")
            return
        if not service_manager.is_admin():
            self._best_pending = False
            self.flash_msg(t("ui.apply_need_admin"), "bad")
            return
        self.flash_msg(t("ui.applying_strategy", s=sid), "info")
        # На время применения гасим комбобокс и кнопку (B1): две быстрые смены
        # не должны перетирать binPath друг другу
        self.strat_box.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.submit_action(service_manager.apply_strategy, self._apply_done, sid)

    def _apply_done(self, r: Any) -> None:
        if not _q_alive(self):
            return
        self.strat_box.setEnabled(True)
        self.apply_btn.setEnabled(True)
        r = r if isinstance(r, dict) else {}
        msg = r.get("service", r.get("error"))
        if self._best_pending:
            self._best_pending = False
            if not r.get("ok"):
                # apply_best_strategy -> apply_strategy не удалась: честный итог (D4)
                service_manager.play_sound("alert")
                self.flash_msg(t("ui.best_fail", e=msg), "bad")
                self.update_status()
                self.refresh_menu_status()
                return
        if r.get("ok"):
            service_manager.play_sound("connect")
        else:
            service_manager.play_sound("alert")
        self.flash_msg(str(msg or ""), "ok" if r.get("ok") else "bad")
        self.update_status()
        self.refresh_menu_status()

    # ---------- Действия ----------
    def run_action(self, action: str) -> None:
        self.submit_action(service_manager.run_service_action, self._action_done, action)

    def _action_done(self, r: Any) -> None:
        if not _q_alive(self):
            return
        level = "ok" if isinstance(r, dict) and r.get("ok") else "bad"
        lines: list[str] = []
        if isinstance(r, tuple):
            ok, msg = r
            level = "ok" if ok else "bad"
            msg = str(msg)
        elif isinstance(r, dict):
            msg = r.get("service", r.get("stdout", r.get("stderr", r.get("error", ""))))
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", errors="replace")
            # Списочные результаты (удалённые конфликты, обновлённые списки) —
            # это живой вывод действия: печатаем в панель и показываем её
            src = r.get("stdout")
            src_lines = src if isinstance(src, list) else []
            lines = [str(x) for x in list(r.get("actions") or []) + src_lines[:50]]
        else:
            msg = str(r)
        if lines:
            self._show_output()
            for line in lines:
                self.add_out(line, "info")
        if level == "ok":
            msg_str = str(msg).lower()
            if any(k in msg_str for k in ("запущен", "started", "active", "применена", "applied", "running")):
                service_manager.play_sound("connect")
            elif any(k in msg_str for k in ("остановлен", "stopped", "удален", "removed")):
                service_manager.play_sound("disconnect")
            else:
                service_manager.play_sound("done")
        else:
            service_manager.play_sound("alert")
        self.flash_msg(str(msg)[:200], level)
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
        self.submit_action(service_manager.run_service_action, self._action_done,
                           "set_game_filter", mode=mode)

    # ---------- Диагностика (17 проверок оригинала) — в диалоговом окне ----------
    def run_diagnostics(self) -> None:
        DiagnosticsDialog(self).exec()

    def _open_updates(self) -> None:
        """Диалог обновлений: проверка и применение — zapret и приложение."""
        UpdatesDialog(self).exec()

    def _open_status(self) -> None:
        """Диалог статуса службы (вместо текста в логе вывода)."""
        StatusDialog(self).exec()

    # ---------- Тесты (оригинальный test zapret.ps1) ----------
    def run_tests(self) -> None:
        if self._tests_running:
            self.flash_msg(t("ui.games_running"), "warn")
            return
        # Guard ставим ДО prereq-воркера (B1): второй клик не должен пройти,
        # даже пока первый prereq ещё в очереди; снимается при отказе prereq,
        # отмене диалога и в _tests_done
        self._tests_running = True
        self.submit_action(service_manager.run_service_action, self._tests_prereq_done,
                           "tests_prereq")

    def _tests_prereq_done(self, r: Any) -> None:
        if not r.get("ok"):
            self._tests_running = False
            problems = "\n".join(str(p) for p in r.get("problems", []))
            text = f"{problems}\n\n{t('ui.fix_errors')}" if problems else t("ui.fix_errors")
            QMessageBox.warning(self, t("ui.run_tests"), text)
            return
        if not self._tests_running:
            return  # воркер уже завершился (закрытие окна) — не открываем диалог
        dlg = TestDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self._tests_running = False
            return
        kind, mode, sel = dlg.values()
        self._show_output()  # живой вывод тестов — панель показывается сама
        self.add_out(t("ui.running_tests", t=kind, m=mode), "info")
        # Живой вывод: колбэк вызывается из рабочего потока, в UI — только через сигнал;
        # should_stop (B2): закрытие окна останавливает ps1, а не оставляет сироту
        w = Worker(service_manager.run_tests, test_type=kind, mode=mode, selection=sel,
                   on_line=self._emit_line, should_stop=lambda: self._exiting)
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
        self.flash_msg(str(r.get("service", r.get("error")) or ""),
                       "ok" if r.get("ok") else "bad")

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
        if not _q_alive(self):
            return
        d = d if isinstance(d, dict) else {}
        running = d.get("running", False)
        status_raw = str(d.get("status", t("ui.status_unknown")))
        self.status_text.setText(status_raw)
        if running:
            color = COLORS["success"]
        elif "stopped" in status_raw.lower() or "остановл" in status_raw.lower():
            color = COLORS["warn"]
        else:
            color = COLORS["danger"]
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
        self.submit(service_manager.get_doh_status, self._doh_done)

    def _doh_done(self, doh: Any) -> None:
        if not _q_alive(self):
            return
        if isinstance(doh, dict) and hasattr(self, "lbl_doh"):
            self.lbl_doh.setText(f"[{doh.get('provider_name', '?')}]")

    def _menu_done(self, r: Any) -> None:
        if not _q_alive(self) or not isinstance(r, dict):
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
        if hasattr(self, "lbl_autostart"):
            on = service_manager.is_autostart_enabled()
            self.lbl_autostart.setText(f"[{t('ui.autostart_on') if on else t('ui.autostart_off')}]")
        if not r.get("admin"):
            # Тонкое напоминание — в оригинале права тоже нужны для части пунктов
            pass

    # ---------- Лучшая стратегия из результатов тестов ----------
    def apply_best_strategy(self) -> None:
        """Читает 'Best strategy' из последнего test_results_*.txt и применяет её
        тем же путём, что и кнопка Apply (проверка прав, фон, перезапуск службы)."""
        self.submit_action(service_manager.best_strategy, self._best_done)

    def _best_done(self, r: Any) -> None:
        r = r if isinstance(r, dict) else {}
        if not r.get("ok"):
            self.flash_msg(r.get("reason") or t("tests.best_none"), "warn")
            return
        sid = r["strategy"]
        self.strat_box.blockSignals(True)
        self.strat_box.setCurrentText(sid)
        self.strat_box.blockSignals(False)
        # Подтверждение: применение перезапускает службу — решает пользователь
        ans = QMessageBox.question(self, t("ui.best_confirm_title"),
                                   t("ui.best_confirm_text", s=sid))
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._best_pending = True  # если apply_strategy не выстрелит — _apply_done отчитается (D4)
        self.apply_strategy()

    # ---------- Fakes ----------
    def show_fakes(self) -> None:
        self.submit_action(service_manager.run_service_action, self._fakes_listed, "list_fakes")

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
        self.submit_action(service_manager.run_service_action, self._fakes_replaced,
                           "replace_active_fakes", fake_type=kind, number=number)

    def _fakes_replaced(self, r: Any) -> None:
        r = r if isinstance(r, dict) else {}
        ok = r.get("ok", False)
        self.flash_msg(str(r.get("stdout") or r.get("stderr") or ""),
                       "ok" if ok else "bad")

    def closeEvent(self, ev: QCloseEvent) -> None:
        if self.tray is not None and not self._exiting:
            # Есть трей — закрытие прячет окно; настоящий выход только из меню трея
            ev.ignore()
            self.hide()
            return
        self._exiting = True  # should_stop воркера тестов увидит отказ и убьёт ps1
        self.timer.stop()
        self._flash_timer.stop()
        if not self.pool.waitForDone(3000):
            # Воркеры не завершились: их колбэки уже не выполнятся, процесс может
            # задержаться — фиксируем в лог (B2)
            applog.log("waitForDone timeout on exit: some workers still running")
        super().closeEvent(ev)


def main() -> int:
    # 1. Лог и перехват крашей — до создания окна, чтобы падало уже «под наблюдением»
    applog.install_excepthook()
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    icon_path = _get_asset_path("app.ico")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 2. Один экземпляр: именованный мьютекс ядра Windows
    mutex, already_running = _acquire_single_instance()
    if already_running:
        QMessageBox.warning(None, "zapret-simple", t("ui.already_running"))
        return 1

    # 3. Автоповышение прав: один UAC-вопрос при старте; при отказе работаем без прав
    if not service_manager.is_admin() and "--no-elevate" not in sys.argv:
        # Мьютекс отпускаем ДО ShellExecuteW (A3): иначе ребёнок может успеть
        # стартовать раньше ReleaseHandle и упереться в ERROR_ALREADY_EXISTS
        _release_mutex(mutex)
        if service_manager.relaunch_as_admin(extra_args=["--no-elevate"]):
            applog.log("relaunched elevated")
            return 0
        applog.log("elevation declined — running without admin rights")
        mutex, _ = _acquire_single_instance()  # UAC отклонён — возвращаем мьютекс

    w = MainWindow()
    ag = app.primaryScreen().availableGeometry()
    w.move(ag.center() - w.rect().center())
    if ("--minimized" in sys.argv or "--tray" in sys.argv) and w.tray is not None:
        w.hide()
    else:
        w.show()
    code = app.exec()
    _release_mutex(mutex)
    return code


# Глобальный хэндл мьютекса: кнопка «Повысить права» отпускает его перед
# запуском elevated-копии и возвращает, если UAC отклонён (A3).
_MUTEX_HANDLE: int | None = None


def _acquire_single_instance() -> tuple[int | None, bool]:
    """(хэндл_мьютекса, уже_запущен?). Хэндл держим живым весь срок процесса."""
    global _MUTEX_HANDLE
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_wchar_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, "Local\\zapret-simple-ui")
        if not handle:
            return None, False
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS — уже запущен
            _close_handle(handle)
            return None, True
        _MUTEX_HANDLE = handle
        return handle, False
    except Exception:
        return None, False  # не смогли проверить — не мешаем запуску


def _release_mutex(handle: int | None = None) -> None:
    """Закрывает хэндл (по аргументу или последний сохранённый) и обнуляет глобальный."""
    global _MUTEX_HANDLE
    h = handle if handle is not None else _MUTEX_HANDLE
    _MUTEX_HANDLE = None
    _close_handle(h)


def _close_handle(handle: int | None) -> None:
    if handle:
        try:
            import ctypes
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
