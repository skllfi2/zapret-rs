# tests/test_pyside_ui.py — десктопный UI на PySide6: кнопки, стратегии, потоки
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Qt не должен требовать реального дисплея — рисуем в offscreen
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import PySide6  # noqa: F401
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "zapret_pyside.py")


def _read_src():
    with open(_SRC, "r", encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(HAS_PYSIDE, "PySide6 не установлен")
class TestPySideUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Импорт внутри setUpClass: QApplication создаётся один раз на процесс
        from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton

        import i18n
        import zapret_pyside as z
        cls.z = z
        cls.i18n = i18n
        # Детерминированный язык: пункты меню сверяются с en-паритетом service.bat
        i18n.set_lang("en")
        cls.QPushButton = QPushButton
        cls.QComboBox = QComboBox
        cls.QLabel = QLabel
        cls.app = QApplication.instance() or QApplication([])
        cls.win = z.MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        cls.i18n.set_lang("ru")  # не тащим тестовый язык в остальные тесты

    def _btn_texts(self):
        return [b.text() for b in self.win.findChildren(self.QPushButton)]

    def test_all_buttons_present(self):
        # Пункты меню — 12 как в оригинальном service.bat + доп. действия
        texts = self._btn_texts()
        for key in ["ui.install_service", "ui.remove_services", "ui.check_status",
                    "ui.game_filter", "ui.ipset_filter", "ui.autoupdate_check",
                    "ui.replace_fakes", "ui.update_ipset", "ui.update_hosts",
                    "ui.check_updates", "ui.run_diagnostics", "ui.run_tests",
                    "ui.start_service", "ui.stop_service", "ui.admin_rights",
                    "ui.remove_conflicts", "ui.clear_discord", "ui.restore_payload"]:
            a = self.i18n.t(key)
            self.assertIn(a, texts, f"Пункт {a} отсутствует")

    def test_menu_sections_like_original(self):
        # Секции меню — как в service.bat: :: SERVICE/SETTINGS/UPDATES/TOOLS
        secs = [lb.text() for lb in self.win.findChildren(self.QLabel)
                if lb.objectName() == "section"]
        for key in ["ui.sec_service", "ui.sec_settings", "ui.sec_updates", "ui.sec_tools"]:
            s = self.i18n.t(key)
            self.assertIn(s, secs, f"Секция {s} отсутствует")

    def test_lang_switcher_present(self):
        # Переключатель ru/en в шапке — общий с ядром, выбор в ui_settings.json
        self.assertTrue(any(b.text() in ("RU", "EN") for b in self.win.findChildren(self.QPushButton)),
                        "Нет кнопки переключения языка")

    def test_strategy_selector_populated(self):
        # Комбобокс стратегий реально заполнен из list_strategies() (реальные .bat)
        boxes = self.win.findChildren(self.QComboBox)
        self.assertTrue(boxes, "Нет селектора стратегий")
        self.assertGreater(boxes[0].count(), 0, "Список стратегий пуст")
        self.assertTrue(boxes[0].currentText(), "Стратегия не выбрана")

    def test_output_populated(self):
        self.assertTrue(self.win.output.toPlainText().strip(), "Область вывода пуста")

    def test_output_panel_buttons_present(self):
        # Копировать/Сохранить/Очистить + лучшая стратегия из тестов
        texts = self._btn_texts()
        for key in ("ui.out_copy", "ui.out_save", "ui.out_clear", "ui.apply_best"):
            self.assertIn(self.i18n.t(key), texts, f"Кнопка {key} отсутствует")

    def test_copy_output_to_clipboard(self):
        self.win.output.setPlainText("copy-test-body")
        self.win._copy_output()
        self.assertEqual(self.app.clipboard().text(), "copy-test-body")

    def test_best_strategy_applies_to_selector(self):
        # Мок best_strategy(ok) -> имя попадает в селектор и в вывод.
        # is_admin=False: Apply останавливается на воротах прав — реальной установки
        # службы в тестах не происходит.
        import time
        import unittest.mock as mock
        self.win.output.clear()
        with mock.patch("service_manager.best_strategy",
                        return_value={"ok": True, "strategy": "general", "file": "r.txt"}), \
             mock.patch("service_manager.is_admin", return_value=False):
            self.win.apply_best_strategy()
        expect = self.i18n.t("ui.best_found", s="general")
        for _ in range(50):
            self.app.processEvents()
            time.sleep(0.02)
            if expect in self.win.output.toPlainText():
                break
        self.assertIn(expect, self.win.output.toPlainText())
        self.assertIn("general", self.win.strat_box.currentText())

    def test_best_strategy_without_results_warns(self):
        import time
        import unittest.mock as mock
        self.win.output.clear()
        with mock.patch("service_manager.best_strategy",
                        return_value={"ok": False, "strategy": None, "reason": "no-results"}):
            self.win.apply_best_strategy()
        for _ in range(50):
            self.app.processEvents()
            time.sleep(0.02)
            if "no-results" in self.win.output.toPlainText():
                break
        self.assertIn("no-results", self.win.output.toPlainText())

    def test_status_updates_via_threadpool(self):
        # Статус читается в фоне через QThreadPool и доставляется сигналом
        import time
        for _ in range(40):
            self.app.processEvents()
            time.sleep(0.02)
            if self.win.status_text.text() not in (self.i18n.t("ui.status_unknown"), ""):
                break
        self.assertNotEqual(self.win.status_text.text(), "")

    def test_no_widget_access_from_worker_threads(self):
        # Стратегия Qt: работа в потоке, результат — через сигнал в главный поток
        src = _read_src()
        self.assertIn("QThreadPool", src)
        self.assertIn("Signal(", src)
        self.assertNotIn("root.after(0", src)  # остаток tkinter-подхода


@unittest.skipUnless(HAS_PYSIDE, "PySide6 не установлен")
class TestPySideActions(unittest.TestCase):
    """Краевые ветки обработчиков: диалоги, _action_done, тесты, статусы, fakes."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        import i18n
        import zapret_pyside as z
        cls.z, cls.i18n = z, i18n
        cls.app = QApplication.instance() or QApplication([])
        cls.win = z.MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls.win._exiting = True
        cls.win.close()

    def _wait(self, pred, tries=60):
        for _ in range(tries):
            self.app.processEvents()
            time.sleep(0.02)
            if pred():
                return True
        return False

    # ---------- Сохранение/очистка вывода ----------
    def test_save_output_cancel_keeps_quiet(self):
        import unittest.mock as mock
        self.win.output.clear()
        with mock.patch.object(self.z.QFileDialog, "getSaveFileName",
                               return_value=("", "")):
            self.win._save_output()
        self.assertEqual(self.win.output.toPlainText().strip(), "")

    def test_save_output_writes_file(self):
        import tempfile
        import unittest.mock as mock
        self.win.output.clear()
        self.win.output.setPlainText("тело-вывода")
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.txt")
            with mock.patch.object(self.z.QFileDialog, "getSaveFileName",
                                   return_value=(path, "Text (*.txt)")):
                self.win._save_output()
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "тело-вывода")
        self.assertIn(self.i18n.t("ui.out_saved", p=path),
                      self.win.output.toPlainText())

    def test_save_output_reports_failure(self):
        import tempfile
        import unittest.mock as mock
        self.win.output.clear()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "no-dir", "out.txt")   # каталога нет -> OSError
            with mock.patch.object(self.z.QFileDialog, "getSaveFileName",
                                   return_value=(path, "")):
                self.win._save_output()
            txt = self.win.output.toPlainText()
            self.assertIn("[X]", txt)                       # вывод bad-уровня
            self.assertIn("out.txt", txt)                   # путь в тексте ошибки

    def test_clear_output(self):
        self.win.output.setPlainText("x")
        self.win._clear_output()
        self.assertEqual(self.win.output.toPlainText(), "")

    # ---------- Ворота прав на применение стратегии ----------
    def test_apply_strategy_requires_admin(self):
        import unittest.mock as mock
        self.win.output.clear()
        with mock.patch("service_manager.is_admin", return_value=False), \
             mock.patch("service_manager.apply_strategy") as apply_m:
            self.win.apply_strategy()
        self.assertIn(self.i18n.t("ui.apply_need_admin"),
                      self.win.output.toPlainText())
        apply_m.assert_not_called()

    def test_apply_strategy_empty_selection(self):
        import unittest.mock as mock
        self.win.output.clear()
        with mock.patch.object(self.win.strat_box, "currentText", return_value=""):
            self.win.apply_strategy()
        self.assertIn(self.i18n.t("ui.err_no_strategy"),
                      self.win.output.toPlainText())

    def test_apply_strategy_success_flow(self):
        import unittest.mock as mock
        self.win.output.clear()
        with mock.patch("service_manager.is_admin", return_value=True), \
             mock.patch("service_manager.apply_strategy",
                        return_value={"ok": True, "service": "применено"}):
            self.win.apply_strategy()
        ok = self._wait(lambda: "применено" in self.win.output.toPlainText())
        self.assertTrue(ok, self.win.output.toPlainText())
        self.assertIn("[OK] применено", self.win.output.toPlainText())

    # ---------- Действия и ветки _action_done ----------
    def test_run_action_dispatch_and_done(self):
        import unittest.mock as mock
        self.win.output.clear()
        with mock.patch("service_manager.run_service_action",
                        return_value={"ok": True, "service": "статус-ок"}):
            self.win.run_action("service_status")
        self._wait(lambda: "статус-ок" in self.win.output.toPlainText())
        txt = self.win.output.toPlainText()
        self.assertIn(">>> service_status", txt)
        self.assertIn("[OK] статус-ок", txt)

    def test_action_done_branches(self):
        self.win.output.clear()
        self.win._action_done((True, "кортеж"))                       # кортеж
        self.win._action_done({"ok": False, "stderr": b"bytes-error"})  # bytes
        self.win._action_done({"ok": True, "actions": ["act-1"],
                               "stdout": ["line-1", "line-2"]})        # списки
        self.win._action_done({"ok": True, "actions": ["act-2"],
                               "stdout": "строка-вывода"})             # строка не-список
        self.win._action_done("просто строка")                         # не dict
        txt = self.win.output.toPlainText()
        self.assertIn("[OK] кортеж", txt)
        self.assertIn("bytes-error", txt)
        self.assertIn("act-1", txt)
        self.assertIn("line-1", txt)
        self.assertIn("line-2", txt)
        self.assertIn("act-2", txt)
        self.assertIn("строка-вывода", txt)
        self.assertIn("[X] просто строка", txt)

    def test_set_game_filter_menu_action(self):
        import unittest.mock as mock
        self.win.output.clear()
        with mock.patch("service_manager.run_service_action",
                        return_value={"ok": True, "service": "gf-ok"}) as m:
            self.win._set_game_filter("tcp")
        self._wait(lambda: "gf-ok" in self.win.output.toPlainText())
        self.assertIn("Game Filter -> tcp", self.win.output.toPlainText())
        self.assertTrue(m.called)

    # ---------- Тесты (test zapret.ps1) из UI ----------
    def test_run_tests_guard_when_running(self):
        self.win.output.clear()
        self.win._tests_running = True
        try:
            self.win.run_tests()
            self.assertIn(self.i18n.t("ui.games_running"),
                          self.win.output.toPlainText())
        finally:
            self.win._tests_running = False

    def test_run_tests_prereq_fail(self):
        import unittest.mock as mock
        self.win.output.clear()
        with mock.patch("service_manager.run_service_action",
                        return_value={"ok": False, "problems": ["проблема-1"]}):
            self.win.run_tests()
        self._wait(lambda: "проблема-1" in self.win.output.toPlainText())
        txt = self.win.output.toPlainText()
        self.assertIn("[X] проблема-1", txt)
        self.assertIn(self.i18n.t("ui.fix_errors"), txt)

    def test_run_tests_dialog_reject(self):
        import unittest.mock as mock

        dialogs = []

        class _Reject:
            def __init__(self, parent=None):
                dialogs.append(self)

            def exec(self):
                return 0   # QDialog.Rejected

        self.win.output.clear()
        with mock.patch("service_manager.run_service_action",
                        return_value={"ok": True, "problems": []}), \
             mock.patch.object(self.z, "TestDialog", _Reject):
            self.win.run_tests()
            # Ждём ПОЛНОЙ доставки результата воркера: диалог создаётся и закрывается
            # внутри колбэка. Без этого запоздавший finished-сигнал выстрелит уже в
            # чужом тесте, где TestDialog снова настоящий и exec() заблокирует навсегда.
            self.assertTrue(self._wait(lambda: dialogs),
                            "диалог предпроверки не был показан")
        self.assertFalse(self.win._tests_running)   # отказ — тесты не запущены

    def test_run_tests_dialog_accept_runs_worker(self):
        import unittest.mock as mock

        class _Accept:
            def __init__(self, parent=None):
                pass

            def exec(self):
                return 1   # QDialog.Accepted

            def values(self):
                return (1, 1, None)

        self.win.output.clear()
        with mock.patch("service_manager.run_service_action",
                        return_value={"ok": True, "problems": []}), \
             mock.patch.object(self.z, "TestDialog", _Accept), \
             mock.patch("service_manager.run_tests",
                        return_value={"ok": True, "service": "тесты-готово",
                                      "stdout": ["строка-теста"]}):
            self.win.run_tests()
            ok = self._wait(lambda: "тесты-готово" in self.win.output.toPlainText())
        self.assertTrue(ok, self.win.output.toPlainText())
        self.assertIn("строка-теста", self.win.output.toPlainText())
        self.assertFalse(self.win._tests_running)

    def test_on_line_signal_levels(self):
        self.win.output.clear()
        for line in ("[OK] хорошо", "[INFO] инфо", "[ERROR] ошибка",
                     "[WARN] предупреждение", "просто текст"):
            self.win._on_line_signal(line)
        txt = self.win.output.toPlainText()
        for line in ("хорошо", "инфо", "ошибка", "предупреждение", "просто текст"):
            self.assertIn(line, txt)

    def test_emit_line_crosses_to_ui(self):
        self.win.output.clear()
        self.win._emit_line("[OK] из-потока")
        self.assertTrue(self._wait(lambda: "из-потока" in self.win.output.toPlainText()))

    def test_tests_done_prints_summary(self):
        self.win.output.clear()
        self.win._tests_running = True
        self.win._tests_done({"ok": False, "service": "тесты упали",
                              "stdout": ["ошибка-теста"]})
        self.assertFalse(self.win._tests_running)
        txt = self.win.output.toPlainText()
        self.assertIn("ошибка-теста", txt)
        self.assertIn("[X] тесты упали", txt)
        self.win._tests_done("не-словарь")   # не должен падать

    # ---------- Диагностика ----------
    def test_run_diagnostics_and_done(self):
        import unittest.mock as mock
        checks = [{"name": "c1", "level": "ok", "msg": "норм"},
                  {"name": "c2", "level": "bad", "msg": "плохо",
                   "url": "http://example.com"},
                  {"name": "c3", "level": "warn", "msg": "внимание"}]
        self.win.output.clear()
        with mock.patch("service_manager.run_diagnostics",
                        return_value={"ok": False, "checks": checks, "service": "итог"}):
            self.win.run_diagnostics()
        self.assertTrue(self._wait(lambda: "итог" in self.win.output.toPlainText()))
        txt = self.win.output.toPlainText()
        self.assertIn("[+] c1: норм", txt)
        self.assertIn("[X] c2: плохо", txt)
        self.assertIn("http://example.com", txt)
        self.assertIn("[?] c3: внимание", txt)

    def test_diag_done_non_dict(self):
        self.win.output.clear()
        self.win._diag_done("не-словарь")
        self.assertIn("[X] не-словарь", self.win.output.toPlainText())

    # ---------- Статусы ----------
    def test_read_status_error_branch(self):
        import unittest.mock as mock
        with mock.patch("service_manager.query_status",
                        side_effect=RuntimeError("err")):
            d = self.win._read_status()
        self.assertTrue(d["status"].startswith("ERR:"))
        self.assertFalse(d["running"])

    def test_refresh_busy_guard_and_status_done(self):
        self.win._busy = False
        self.win.refresh()
        self.assertTrue(self.win._busy)          # первый вызов ставит флаг
        self.win.refresh()                        # второй — без очереди в пул
        self.assertTrue(self._wait(lambda: not self.win._busy))
        self.win._status_done({"status": "Running", "running": True,
                               "payloads": {"ok": False, "missing": ["a.bin", "b.bin"]}})
        self.assertEqual(self.win.status_text.text(), "Running")
        self.assertIn("2", self.win.payload_warn.text())
        self.win._status_done({})                 # пусто -> статус неизвестен
        self.assertEqual(self.win.status_text.text(), self.i18n.t("ui.status_unknown"))

    def test_menu_status_done(self):
        import unittest.mock as mock
        menu = {"version": "9.9.9", "strategy": "general", "game_filter": "all",
                "ipset": "any", "check_updates": "on", "admin": True}
        with mock.patch("service_manager.run_service_action", return_value=menu):
            self.win.refresh_menu_status()
        self.assertTrue(self._wait(lambda: self.win.lbl_gf.text() == "[all]"))
        self.assertEqual(self.win.version_lbl.text(), "v9.9.9")
        self.assertEqual(self.win.lbl_ipset.text(), "[any]")
        self.assertEqual(self.win.lbl_upd.text(), "[on]")
        self.win._menu_done("мусор")   # не-dict — ранний выход без падения

    # ---------- Fakes ----------
    def test_show_fakes_reject_and_accept(self):
        import unittest.mock as mock

        class _Reject:
            def __init__(self, parent=None):
                pass

            def exec(self):
                return 0

        class _Accept:
            def __init__(self, parent=None):
                pass

            def exec(self):
                return 1

            def values(self):
                return (2, 1)

        items = [{"name": "A.bin", "sha256": "aaa", "active": True},
                 {"name": "B.bin", "sha256": "bbb", "active": False}]
        self.win.output.clear()
        with mock.patch("service_manager.run_service_action",
                        return_value={"ok": True, "stdout": items}), \
             mock.patch.object(self.z, "FakeDialog", _Reject):
            self.win.show_fakes()
            self.assertTrue(self._wait(lambda: "B.bin" in self.win.output.toPlainText()))
        txt = self.win.output.toPlainText()
        self.assertIn("* A.bin", txt)      # активный помечен
        self.assertIn("1. B.bin", txt)     # остальные пронумерованы

        with mock.patch("service_manager.run_service_action",
                        return_value={"ok": True, "stdout": items}) as m, \
             mock.patch.object(self.z, "FakeDialog", _Accept):
            self.win.show_fakes()

            def repl():
                return any(c.args and c.args[0] == "replace_active_fakes"
                           for c in m.call_args_list)

            self.assertTrue(self._wait(repl))
        call = next(c for c in m.call_args_list
                    if c.args and c.args[0] == "replace_active_fakes")
        self.assertEqual(call.kwargs, {"fake_type": 2, "number": 1})

    def test_fakes_empty_and_replaced(self):
        import unittest.mock as mock
        self.win.output.clear()
        with mock.patch("service_manager.run_service_action",
                        return_value={"ok": True, "stdout": []}):
            self.win.show_fakes()
        self.assertTrue(self._wait(
            lambda: self.i18n.t("ui.no_bins") in self.win.output.toPlainText()))
        self.win.output.clear()
        self.win._fakes_replaced({"ok": False, "stderr": "нет такого fake"})
        self.win._fakes_replaced({"ok": True, "stdout": "заменено"})
        txt = self.win.output.toPlainText()
        self.assertIn("[X] нет такого fake", txt)
        self.assertIn("[OK] заменено", txt)

    # ---------- Фоновые операции ----------
    def test_worker_exception_becomes_error_result(self):
        results = []
        self.win.submit(lambda: 1 / 0, results.append)
        self.assertTrue(self._wait(lambda: results))
        self.assertFalse(results[0]["ok"])
        self.assertIn("division by zero", results[0]["error"])

    # ---------- Диалоги строятся без модального exec() ----------
    def test_dialogs_build_without_exec(self):
        dlg = self.z.FakeDialog(None)
        self.assertEqual(dlg.kind.count(), 2)
        kind, number = dlg.values()
        self.assertIn(kind, ("1", "2"))
        self.assertEqual(number, "1")           # SpinBox по умолчанию
        dlg.deleteLater()

        td = self.z.TestDialog(None)
        self.assertEqual(td.kind.count(), 2)
        self.assertEqual(td.mode.count(), 2)
        self.assertEqual(td.values(), (1, 1, None))   # Standard + All -> без номера
        td.mode.setCurrentIndex(1)                     # Selected -> номер включается
        self.assertTrue(td.selection.isEnabled())
        self.assertEqual(td.values(), (1, 2, 1))       # kind не менялся, mode=Selected
        td.deleteLater()

    def test_load_strategies_fallback_branches(self):
        import unittest.mock as mock
        # list_strategies упал -> пусто, без исключения наружу
        with mock.patch("service_manager.list_strategies", side_effect=OSError("x")):
            self.win._load_strategies()
        # Текущая стратегия неизвестна -> fallback на general
        with mock.patch("service_manager.list_strategies",
                        return_value=["general", "other"]), \
             mock.patch("service_manager.current_strategy", return_value="ghost"):
            self.win._load_strategies()
        self.assertEqual(self.win.strat_box.currentText(), "general")
        # Текущая известна -> она и выбирается
        with mock.patch("service_manager.list_strategies",
                        return_value=["general", "other"]), \
             mock.patch("service_manager.current_strategy", return_value="other"):
            self.win._load_strategies()
        self.assertEqual(self.win.strat_box.currentText(), "other")

    def test_read_status_payload_error_defaults_ok(self):
        import unittest.mock as mock
        with mock.patch("service_manager.query_status", return_value="Running"), \
             mock.patch("service_manager.is_running", return_value=True), \
             mock.patch("service_manager.payloads_status", side_effect=OSError("x")):
            d = self.win._read_status()
        self.assertEqual(d, {"status": "Running", "running": True,
                             "payloads": {"ok": True, "missing": []}})

    def test_switch_lang_rebuilds_ui_on_new_lang(self):
        old = self.i18n.LANG
        try:
            self.win._switch_lang()
            self.assertNotEqual(self.i18n.LANG, old)
            # Окно пересобрано: секции шапки — на актуальном (новом) языке
            secs = [lb.text() for lb in self.win.findChildren(self.z.QLabel)
                    if lb.objectName() == "section"]
            self.assertIn(self.i18n.t("ui.sec_service"), secs)
            texts = [b.text() for b in self.win.findChildren(self.z.QPushButton)]
            self.assertTrue(any(x in ("RU", "EN") for x in texts))
        finally:
            self.i18n.save(old)   # вернуть язык пользователя (реальный ui_settings.json)

    def test_single_instance_mutex_roundtrip(self):
        # Именованный мьютекс ядра: берём и отпускаем (безопасно для реального приложения)
        handle, running = self.z._acquire_single_instance()
        try:
            self.assertIsInstance(running, bool)
            if handle:
                self.assertFalse(running)   # мы первые — мьютекс взят
        finally:
            self.z._release_mutex(handle)


class TestPySideSource(unittest.TestCase):
    """Текстовые проверки — работают даже без установленного PySide6."""
    def test_service_manager_imported(self):
        self.assertIn("import service_manager", _read_src())

    def test_all_action_strings_present(self):
        src = _read_src()
        for a in ["service_status", "service_install", "service_remove", "start",
                  "stop", "toggle_ipset", "toggle_check_updates", "check_updates",
                  "set_game_filter", "menu_status", "clear_discord",
                  "restore_payloads", "ipset_update", "update_hosts",
                  "remove_conflicts", "relaunch_admin"]:
            self.assertIn(f'"{a}"', src, f"Действие {a} не вызывается")

    def test_admin_gate_on_strategy(self):
        # Применение стратегии без прав должно честно отказываться
        src = _read_src()
        self.assertIn("is_admin()", src)


@unittest.skipUnless(HAS_PYSIDE, "PySide6 не установлен")
class TestPySideTray(unittest.TestCase):
    """Трей: сворачивание при закрытии, выход только через меню трея."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon

        import i18n
        import zapret_pyside as z
        cls.z, cls.i18n = z, i18n
        cls.QSystemTrayIcon = QSystemTrayIcon
        cls.app = QApplication.instance() or QApplication([])
        # В offscreen системного трея нет — имитируем наличие для проверки логики
        cls._orig_avail = QSystemTrayIcon.isSystemTrayAvailable
        QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
        cls.win = z.MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls.QSystemTrayIcon.isSystemTrayAvailable = cls._orig_avail
        cls.win._exiting = True
        cls.win.close()

    def test_tray_created_with_localized_menu(self):
        self.assertIsNotNone(self.win.tray, "Трей не создан при доступном системном")
        menu = self.win.tray.contextMenu()
        self.assertIsNotNone(menu)
        labels = [a.text() for a in menu.actions()]
        self.assertIn(self.i18n.t("ui.tray_show"), labels)
        self.assertIn(self.i18n.t("ui.tray_exit"), labels)

    def test_close_goes_to_tray_and_exit_really_closes(self):
        from PySide6.QtGui import QCloseEvent
        ev = QCloseEvent()
        self.win.closeEvent(ev)
        self.assertFalse(ev.isAccepted(), "Обычное закрытие должно уходить в трей (ignored)")
        # Настоящий выход — только через меню трея (_exiting)
        self.win._exiting = True
        ev2 = QCloseEvent()
        self.win.closeEvent(ev2)
        self.assertTrue(ev2.isAccepted(), "Выход через трей должен закрывать окно")
        self.win._exiting = False

    def test_exit_from_tray_really_closes(self):
        self.win._exit_from_tray()
        self.assertTrue(self.win._exiting)
        self.assertFalse(self.win.isVisible())
        self.win._exiting = False   # не тащим флаг в остальные тесты

    def test_on_tray_click_shows_window(self):
        self.win.hide()
        self.win._on_tray_activated(self.QSystemTrayIcon.Trigger)
        self.assertTrue(self.win.isVisible())
        self.win._on_tray_activated(self.QSystemTrayIcon.Context)  # прочие — игнор
        self.win._show_from_tray()
        self.assertTrue(self.win.isVisible())

    def test_status_done_updates_tray_tooltip(self):
        self.win._status_done({"status": "Running", "running": True,
                               "payloads": {"ok": True, "missing": []}})
        self.assertIn("Running", self.win.tray.toolTip())
        self.assertIsNotNone(self.win.tray.icon())

    def test_status_icon_is_paintable(self):
        from PySide6.QtGui import QColor
        icon = self.win._status_icon(QColor("#5ee87f"))
        self.assertFalse(icon.isNull())


if __name__ == "__main__":
    unittest.main(verbosity=2)
