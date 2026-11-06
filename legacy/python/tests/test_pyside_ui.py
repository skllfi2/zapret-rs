# tests/test_pyside_ui.py — десктопный UI на PySide6: кнопки, стратегии, потоки
import os
import sys
import time
import unittest
from unittest import mock

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
        # Язык пользователя до тестов: _switch_lang пишет настоящий
        # ui_settings.json — восстановим его в tearDownClass
        cls._orig_lang = i18n.LANG
        # Детерминированный язык: пункты меню сверяются с en-паритетом service.bat
        i18n.set_lang("en")
        cls.QPushButton = QPushButton
        cls.QComboBox = QComboBox
        cls.QLabel = QLabel
        cls.app = QApplication.instance() or QApplication([])
        cls.win = z.MainWindow()
        cls.win.timer.stop()
        cls.win._flash_timer.stop()
        cls.win.pool.waitForDone(1000)
        # Окно должно быть показано: isVisible() скрытого окна всегда False,
        # и проверки видимости панели вывода потеряли бы смысл
        cls.win.show()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.win._exiting = True
        cls.win.timer.stop()
        cls.win._flash_timer.stop()
        cls.win.close()
        cls.win.pool.waitForDone(1000)
        # Вернуть и память, и файл настроек на язык пользователя (не тащим
        # тестовый "en" в остальные тесты и в реальную среду)
        cls.i18n.save(cls._orig_lang)

    def tearDown(self):
        self.win.pool.waitForDone(3000)
        self.app.processEvents()

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

    def test_output_panel_hidden_by_default_and_toggles(self):
        # Панель вывода скрыта по умолчанию; кнопка в шапке показывает/прячет
        self.assertFalse(self.win.out_panel.isVisible(),
                         "Панель вывода должна быть скрыта по умолчанию")
        self.assertEqual(self.win.out_toggle.text(), self.i18n.t("ui.out_show"))
        self.win._toggle_output()
        self.assertTrue(self.win.out_panel.isVisible())
        self.assertEqual(self.win.out_toggle.text(), self.i18n.t("ui.out_hide"))
        self.win._toggle_output()
        self.assertFalse(self.win.out_panel.isVisible())
        # _show_output (живой вывод тестов) раскрывает панель и синхронизирует кнопку
        self.win._show_output()
        self.assertTrue(self.win.out_panel.isVisible())
        self.assertEqual(self.win.out_toggle.text(), self.i18n.t("ui.out_hide"))
        self.win._toggle_output()   # вернуть скрытое состояние

    def test_lang_switch_keeps_output_hidden(self):
        # Пересборка UI при смене языка сохраняет состояние панели вывода
        self.assertFalse(self.win._out_visible)
        old_lang = self.i18n.LANG
        try:
            self.win._switch_lang()
            self.assertNotEqual(self.i18n.LANG, old_lang)
            self.assertFalse(self.win.out_panel.isVisible())
            self.assertFalse(self.win._out_visible)
        finally:
            # Вернуть язык НУЖНО пересборкой: без неё окно останется на
            # тестовом языке, а i18n.t — на старом (рассинхрон для следующих тестов)
            if self.i18n.LANG != old_lang:
                self.win._switch_lang()
            self.i18n.save(old_lang)   # и файл ui_settings.json к исходному языку
            self.assertEqual(self.i18n.LANG, old_lang)

    def test_copy_output_to_clipboard(self):
        self.win.output.setPlainText("copy-test-body")
        self.win._copy_output()
        self.assertEqual(self.app.clipboard().text(), "copy-test-body")

    def test_best_strategy_applies_to_selector(self):
        # Мок best_strategy(ok) -> имя попадает в селектор; применение — после
        # подтверждения в диалоге. is_admin=False: Apply останавливается на
        # воротах прав — реальной установки службы в тестах не происходит.
        import unittest.mock as mock
        need = self.i18n.t("ui.apply_need_admin")
        with mock.patch("service_manager.best_strategy",
                        return_value={"ok": True, "strategy": "general", "file": "r.txt"}), \
             mock.patch.object(self.z.QMessageBox, "question",
                               return_value=self.z.QMessageBox.StandardButton.Yes), \
             mock.patch("service_manager.is_admin", return_value=False):
            self.win.apply_best_strategy()
            # Ждём ПОЛНОЙ доставки результата воркера (до ворот прав): выйти
            # раньше — значит оставить воркера стрелять в следующий тест
            self.assertTrue(self._wait_best_done(
                lambda: need in self.win.flash.text()), self.win.flash.text())
        self.assertIn("general", self.win.strat_box.currentText())
        self.assertIn(need, self.win.flash.text())

    def _wait_best_done(self, cond, tries=150):
        import time
        for _ in range(tries):
            self.app.processEvents()
            time.sleep(0.02)
            if cond():
                return True
        return False

    def test_best_strategy_cancel_keeps_selector(self):
        # Отмена в диалоге подтверждения — стратегия выбрана, но не применяется
        import unittest.mock as mock
        with mock.patch("service_manager.best_strategy",
                        return_value={"ok": True, "strategy": "general", "file": "r.txt"}), \
             mock.patch.object(self.z.QMessageBox, "question",
                               return_value=self.z.QMessageBox.StandardButton.No) as quest, \
             mock.patch("service_manager.is_admin", return_value=True), \
             mock.patch("service_manager.apply_strategy") as apply_m:
            self.win.apply_best_strategy()
            # Довести воркера до вопроса ОБЯЗАТЕЛЬНО (иначе его ok-результат
            # доставится в следующем тесте и откроет настоящую модалку)
            self.assertTrue(self._wait_best_done(lambda: quest.called),
                            "результат best_strategy не доставился")
        self.assertIn("general", self.win.strat_box.currentText())
        apply_m.assert_not_called()

    def test_best_strategy_without_results_warns(self):
        import unittest.mock as mock
        self.win.flash.setText("")   # не доверяем чужому флешу из прошлого теста
        with mock.patch("service_manager.best_strategy",
                        return_value={"ok": False, "strategy": None, "reason": "no-results"}):
            self.win.apply_best_strategy()
            self.assertTrue(self._wait_best_done(
                lambda: "no-results" in self.win.flash.text()),
                f"флеш не обновился: {self.win.flash.text()!r}")
        self.assertIn("no-results", self.win.flash.text())

    def test_status_updates_via_threadpool(self):
        # B9: честная проверка — мокаем _read_status с конкретным значением и ждём
        # именно его (старый assertNotEqual(text, "") проходил и при сломанном refresh)
        import unittest.mock as mock
        self.win._busy = False
        with mock.patch.object(self.win, "_read_status",
                               return_value={"status": "MOCK-STATUS-42", "running": True,
                                             "payloads": {"ok": True, "missing": []}}):
            self.win.refresh()
            for _ in range(60):
                self.app.processEvents()
                time.sleep(0.02)
                if self.win.status_text.text() == "MOCK-STATUS-42":
                    break
        self.assertEqual(self.win.status_text.text(), "MOCK-STATUS-42")
        # running=True -> зелёный кружок в шапке
        self.assertIn("#5ee87f", self.win.dot.styleSheet())

    def test_no_widget_access_from_worker_threads(self):
        # B9: реальный контроль — add_out вызывается только из главного потока.
        # Воркер эмитит через сигнал; спай на add_out ловит поток каждого вызова.
        import threading
        import unittest.mock as mock
        main_thread = threading.main_thread()
        seen_threads = []
        orig_add_out = self.win.add_out

        def spy_add_out(text, level="info"):
            seen_threads.append(threading.current_thread())
            return orig_add_out(text, level)

        self.win.output.clear()
        with mock.patch.object(self.win, "add_out", spy_add_out):
            w = self.z.Worker(lambda: self.win._emit_line("[OK] из-воркера"))
            self.win.pool.start(w)
            for _ in range(60):
                self.app.processEvents()
                time.sleep(0.02)
                if "из-воркера" in self.win.output.toPlainText():
                    break
        self.assertIn("из-воркера", self.win.output.toPlainText())
        self.assertTrue(seen_threads, "add_out не вызывался вовсе")
        for th in seen_threads:
            self.assertIs(th, main_thread,
                          f"add_out вызван из фонового потока {th.name}")


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
        cls.win.timer.stop()
        cls.win._flash_timer.stop()
        cls.win.pool.waitForDone(1000)

    @classmethod
    def tearDownClass(cls):
        cls.win._exiting = True
        cls.win.timer.stop()
        cls.win._flash_timer.stop()
        cls.win.close()
        cls.win.pool.waitForDone(1000)

    def tearDown(self):
        self.win.pool.waitForDone(3000)
        self.app.processEvents()
        self.win._busy = False
        self.win._tests_running = False

    def _wait(self, pred, tries=150):
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
        # Результат — флеш-статус в шапке, лог вывода не засоряется
        self.assertIn(self.i18n.t("ui.out_saved", p=path), self.win.flash.text())

    def test_save_output_reports_failure(self):
        import tempfile
        import unittest.mock as mock
        self.win.output.clear()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "no-dir", "out.txt")   # каталога нет -> OSError
            with mock.patch.object(self.z.QFileDialog, "getSaveFileName",
                                   return_value=(path, "")):
                self.win._save_output()
            prefix = self.i18n.t("ui.out_save_fail", e="").split(":")[0]
            self.assertIn(prefix, self.win.flash.text())    # bad-статус в шапке
            self.assertIn("out.txt", self.win.flash.text())  # путь в тексте ошибки

    def test_clear_output(self):
        self.win.output.setPlainText("x")
        self.win._clear_output()
        self.assertEqual(self.win.output.toPlainText(), "")

    # ---------- Ворота прав на применение стратегии ----------
    def test_apply_strategy_requires_admin(self):
        import unittest.mock as mock
        with mock.patch("service_manager.is_admin", return_value=False), \
             mock.patch("service_manager.apply_strategy") as apply_m:
            self.win.apply_strategy()
        self.assertIn(self.i18n.t("ui.apply_need_admin"), self.win.flash.text())
        apply_m.assert_not_called()

    def test_apply_strategy_empty_selection(self):
        import unittest.mock as mock
        with mock.patch.object(self.win.strat_box, "currentText", return_value=""):
            self.win.apply_strategy()
        self.assertIn(self.i18n.t("ui.err_no_strategy"), self.win.flash.text())

    def test_apply_strategy_success_flow(self):
        import unittest.mock as mock
        with mock.patch("service_manager.is_admin", return_value=True), \
             mock.patch("service_manager.apply_strategy",
                        return_value={"ok": True, "service": "применено"}):
            self.win.apply_strategy()
            ok = self._wait(lambda: "применено" in self.win.flash.text())
        self.assertTrue(ok, self.win.flash.text())

    # ---------- Действия и ветки _action_done ----------
    def test_run_action_dispatch_and_done(self):
        import unittest.mock as mock
        self.win.output.clear()
        with mock.patch("service_manager.run_service_action",
                        return_value={"ok": True, "service": "статус-ок"}):
            self.win.run_action("service_status")
            ok = self._wait(lambda: "статус-ок" in self.win.flash.text())
        self.assertTrue(ok)
        # Итог — во флеш-статусе; служебные строки ">>> ..." в логе больше нет
        self.assertIn("статус-ок", self.win.flash.text())
        self.assertNotIn(">>>", self.win.output.toPlainText())

    def test_action_done_branches(self):
        self.win.output.clear()
        self.win._action_done((True, "кортеж"))                       # кортеж
        self.assertIn("кортеж", self.win.flash.text())
        self.win._action_done({"ok": False, "stderr": b"bytes-error"})  # bytes
        self.assertIn("bytes-error", self.win.flash.text())
        self.win._action_done({"ok": True, "actions": ["act-1"],
                               "stdout": ["line-1", "line-2"]})        # списки
        # Списочные результаты — живой вывод: панель показана, строки в логе
        self.assertTrue(self.win._out_visible)
        txt = self.win.output.toPlainText()
        self.assertIn("act-1", txt)
        self.assertIn("line-1", txt)
        self.assertIn("line-2", txt)
        self.win.output.clear()
        self.win._action_done({"ok": True, "actions": ["act-2"],
                               "stdout": "строка-вывода"})             # строка не-список
        self.assertIn("act-2", self.win.output.toPlainText())
        self.assertNotIn("строка-вывода", self.win.output.toPlainText())  # текст — во флеше
        self.assertIn("строка-вывода", self.win.flash.text())
        self.win._action_done("просто строка")                         # не dict
        self.assertIn("просто строка", self.win.flash.text())

    def test_set_game_filter_menu_action(self):
        import unittest.mock as mock
        with mock.patch("service_manager.run_service_action",
                        return_value={"ok": True, "service": "gf-ok"}) as m:
            self.win._set_game_filter("tcp")
            self.assertTrue(self._wait(lambda: "gf-ok" in self.win.flash.text()))
        self.assertIn("gf-ok", self.win.flash.text())
        self.assertTrue(m.called)

    # ---------- Тесты (test zapret.ps1) из UI ----------
    def test_run_tests_guard_when_running(self):
        self.win._tests_running = True
        try:
            self.win.run_tests()
            self.assertIn(self.i18n.t("ui.games_running"), self.win.flash.text())
        finally:
            self.win._tests_running = False

    def test_run_tests_prereq_fail(self):
        import unittest.mock as mock
        warned = []
        with mock.patch("service_manager.run_service_action",
                        return_value={"ok": False, "problems": ["проблема-1"]}), \
             mock.patch.object(self.z.QMessageBox, "warning",
                               side_effect=lambda *a: warned.append(a)):
            try:
                self.win.run_tests()
                # Ждём доставку результата ВНУТРИ with: после выхода мок снят и
                # настоящий QMessageBox.warning заморозит тест модальным окном
                self.assertTrue(self._wait(lambda: warned),
                                "предупреждение о prereq не показано")
            finally:
                self.win.pool.waitForDone(3000)
                self.app.processEvents()
        text = warned[0][2]                                   # текст диалога
        self.assertIn("проблема-1", text)
        self.assertIn(self.i18n.t("ui.fix_errors"), text)

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
            try:
                self.win.run_tests()
                # Ждём ПОЛНОЙ доставки результата воркера: диалог создаётся и закрывается
                # внутри колбэка. Без этого запоздавший finished-сигнал выстрелит уже в
                # чужом тесте, где TestDialog снова настоящий и exec() заблокирует навсегда.
                self.assertTrue(self._wait(lambda: dialogs),
                                "диалог предпроверки не был показан")
            finally:
                self.win.pool.waitForDone(3000)
                self.app.processEvents()
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
            try:
                self.win.run_tests()
                ok = self._wait(lambda: "тесты-готово" in self.win.flash.text())
            finally:
                self.win.pool.waitForDone(3000)
                self.app.processEvents()
        self.assertTrue(ok, self.win.flash.text())
        self.assertIn("строка-теста", self.win.output.toPlainText())   # живой вывод
        self.assertTrue(self.win._out_visible)                         # панель показана сама
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
        # B9: эмитим из НАСТОЯЩЕГО фонового потока (не из главного) —
        # queued-доставка сигнала в главный поток работает и без processEvents в потоке
        import threading
        self.win.output.clear()
        worker_thread = {}

        def emit_from_thread():
            worker_thread["name"] = threading.current_thread().name
            self.win._emit_line("[OK] из-потока")

        th = threading.Thread(target=emit_from_thread, name="emit-worker")
        th.start()
        th.join()
        self.assertTrue(self._wait(lambda: "из-потока" in self.win.output.toPlainText()))
        self.assertNotEqual(worker_thread.get("name"), threading.current_thread().name)

    def test_tests_done_prints_summary(self):
        self.win.output.clear()
        self.win._tests_running = True
        self.win._tests_done({"ok": False, "service": "тесты упали",
                              "stdout": ["ошибка-теста"]})
        self.assertFalse(self.win._tests_running)
        self.assertIn("ошибка-теста", self.win.output.toPlainText())   # живой вывод
        self.assertIn("тесты упали", self.win.flash.text())            # итог — флеш
        self.win._tests_done("не-словарь")   # не должен падать

    # ---------- Диагностика (диалог вместо лога) ----------
    def test_run_diagnostics_opens_dialog(self):
        import unittest.mock as mock
        opened = []

        class _Fake:
            def __init__(self, parent=None):
                opened.append(self)

            def exec(self):
                return 0

        with mock.patch.object(self.z, "DiagnosticsDialog", _Fake):
            self.win.run_diagnostics()
        self.assertTrue(opened, "Диагностика не открыла диалог")

    def test_diagnostics_dialog_fills_checks(self):
        checks = [{"name": "c1", "level": "ok", "msg": "норм"},
                  {"name": "c2", "level": "bad", "msg": "плохо",
                   "url": "http://example.com"},
                  {"name": "c3", "level": "warn", "msg": "внимание"}]
        import unittest.mock as mock
        with mock.patch("service_manager.run_diagnostics",
                        return_value={"ok": False, "checks": checks, "service": "итог"}):
            dlg = self.z.DiagnosticsDialog(self.win)
            dlg._fill({"ok": False, "checks": checks, "service": "итог"})
        texts = [lb.text() for lb in dlg.findChildren(self.z.QLabel)]
        self.assertIn("[+] c1: норм", texts)
        self.assertIn("[X] c2: плохо", texts)
        self.assertTrue(any("http://example.com" in x for x in texts), texts)  # URL с отступом
        self.assertIn("[?] c3: внимание", texts)
        self.assertIn(self.i18n.t("ui.diag_counts", ok=1, warn=1, bad=1),
                      dlg._counts.text())
        dlg.deleteLater()

    def test_diagnostics_dialog_no_checks(self):
        import unittest.mock as mock
        with mock.patch("service_manager.run_diagnostics",
                        return_value={"ok": True, "checks": []}):
            dlg = self.z.DiagnosticsDialog(self.win)
        dlg._fill("не-словарь")   # не-dict -> пустой чек-лист, без падения
        texts = [lb.text() for lb in dlg.findChildren(self.z.QLabel)]
        self.assertIn(self.i18n.t("ui.diag_no_checks"), texts)
        dlg.deleteLater()

    # ---------- Диалог статуса службы ----------
    def test_status_dialog_fills_fields(self):
        import unittest.mock as mock
        with mock.patch("service_manager.query_status", return_value="Running"), \
             mock.patch("service_manager.is_running", return_value=True), \
             mock.patch("service_manager.run_service_action",
                        return_value={"version": "1.2.3", "strategy": "general"}):
            dlg = self.z.StatusDialog(self.win)
            dlg._fill(dlg._load())
        self.assertEqual(dlg._vals["service"].text(), "Running")
        self.assertEqual(dlg._vals["winws"].text(), self.i18n.t("ui.status_running"))
        self.assertEqual(dlg._vals["version"].text(), "1.2.3")
        self.assertEqual(dlg._vals["strategy"].text(), "general")
        dlg.deleteLater()

    def test_status_dialog_load_error_branch(self):
        import unittest.mock as mock
        with mock.patch("service_manager.query_status", side_effect=RuntimeError("err")), \
             mock.patch("service_manager.is_running", side_effect=RuntimeError("err2")), \
             mock.patch("service_manager.run_service_action", side_effect=RuntimeError("err3")):
            dlg = self.z.StatusDialog(self.win)
            dlg._fill(dlg._load())
        self.assertIn("ERR", dlg._vals["service"].text())
        self.assertEqual(dlg._vals["winws"].text(), self.i18n.t("ui.status_stopped"))
        dlg._fill("мусор")   # не-dict — без падения
        dlg.deleteLater()

    def test_open_status_opens_dialog(self):
        import unittest.mock as mock
        opened = []

        class _Fake:
            def __init__(self, parent=None):
                opened.append(self)

            def exec(self):
                return 0

        with mock.patch.object(self.z, "StatusDialog", _Fake):
            self.win._open_status()
        self.assertTrue(opened, "Статус не открыл диалог")

    # ---------- Диалог обновлений ----------
    def _make_updates_dialog(self, zapret=None, app=None):
        import unittest.mock as mock
        zapret = zapret or {"ok": True, "stdout": "нет данных", "enabled": True}
        app = app or {"ok": True, "configured": False,
                      "stdout": self.i18n.t("sm.app_upd_unconfigured")}
        with mock.patch("service_manager.check_updates", return_value=zapret), \
             mock.patch("service_manager.check_app_update", return_value=app):
            dlg = self.z.UpdatesDialog(self.win)
            # Обе секции проверяются разными воркерами — ждём обе подстановки
            working = self.i18n.t("ui.working")
            self._wait(lambda: dlg.zapret_lbl.text() != working
                       and dlg.app_lbl.text() != working)
        return dlg

    def test_updates_dialog_shows_new_zapret_version(self):
        dlg = self._make_updates_dialog(
            zapret={"ok": True, "enabled": True, "local": "1.10.0",
                    "remote": "1.10.4", "update_available": True})
        self.assertIn("1.10.4", dlg.zapret_lbl.text())
        self.assertTrue(dlg.zapret_btn.isEnabled())
        self.assertFalse(dlg.app_btn.isEnabled())   # репозиторий не настроен
        dlg.deleteLater()

    def test_updates_dialog_latest_and_disabled(self):
        dlg = self._make_updates_dialog(
            zapret={"ok": True, "enabled": True, "local": "1.10.4",
                    "remote": "1.10.4", "update_available": False,
                    "stdout": self.i18n.t("sm.ver_latest", l="1.10.4")})
        self.assertIn("1.10.4", dlg.zapret_lbl.text())
        self.assertFalse(dlg.zapret_btn.isEnabled())
        dlg.deleteLater()
        dlg2 = self._make_updates_dialog(zapret={"ok": True, "enabled": False})
        self.assertEqual(dlg2.zapret_lbl.text(), self.i18n.t("ui.upd_disabled"))
        dlg2.deleteLater()

    def test_updates_dialog_app_update_available(self):
        dlg = self._make_updates_dialog(
            app={"ok": True, "configured": True, "local": "0.4.0",
                 "remote": "0.5.0", "update_available": True})
        self.assertIn("0.5.0", dlg.app_lbl.text())
        self.assertTrue(dlg.app_btn.isEnabled())
        dlg.deleteLater()

    def test_update_zapret_confirmed_dispatches_action(self):
        import unittest.mock as mock
        dlg = self._make_updates_dialog(
            zapret={"ok": True, "enabled": True, "local": "1.10.0",
                    "remote": "1.10.4", "update_available": True})
        with mock.patch.object(self.z.QMessageBox, "question",
                               return_value=self.z.QMessageBox.StandardButton.Yes), \
             mock.patch("service_manager.run_service_action") as m:
            dlg._update_zapret()
            self.assertTrue(self._wait(lambda: m.called))
        call = m.call_args
        self.assertEqual(call.args[0], "update_zapret")
        self.assertIn("on_line", call.kwargs)
        self.assertTrue(self.win._out_visible)   # панель показана для хода обновления
        dlg.deleteLater()

    def test_update_zapret_cancel_noop(self):
        import unittest.mock as mock
        dlg = self._make_updates_dialog(
            zapret={"ok": True, "enabled": True, "local": "1.10.0",
                    "remote": "1.10.4", "update_available": True})
        with mock.patch.object(self.z.QMessageBox, "question",
                               return_value=self.z.QMessageBox.StandardButton.No), \
             mock.patch("service_manager.run_service_action") as m:
            dlg._update_zapret()
        m.assert_not_called()
        dlg.deleteLater()

    def test_update_app_result_branches(self):
        import unittest.mock as mock
        dlg = self._make_updates_dialog()
        # Успех: приложение выходит (вспомогательный скрипт перезапустит)
        with mock.patch.object(self.win, "close") as close_m:
            dlg._app_updated({"ok": True, "restart": True})
        self.assertTrue(self.win._exiting)
        close_m.assert_called_once()
        self.win._exiting = False
        # Ошибка: предупреждение + перепроверка обеих секций
        warned = []
        with mock.patch.object(self.z.QMessageBox, "warning",
                               side_effect=lambda *a: warned.append(a)), \
             mock.patch("service_manager.check_updates",
                        return_value={"ok": True, "stdout": "x", "enabled": True}), \
             mock.patch("service_manager.check_app_update",
                        return_value={"ok": True, "configured": False}):
            dlg._app_updated({"ok": False, "stderr": "нет ассета"})
        self.assertTrue(warned)
        self.assertIn("нет ассета", warned[0][2])
        dlg.deleteLater()

    def test_update_zapret_result_error_warns(self):
        import unittest.mock as mock
        dlg = self._make_updates_dialog()
        warned = []
        with mock.patch.object(self.z.QMessageBox, "warning",
                               side_effect=lambda *a: warned.append(a)), \
             mock.patch("service_manager.check_updates",
                        return_value={"ok": True, "stdout": "x", "enabled": True}), \
             mock.patch("service_manager.check_app_update",
                        return_value={"ok": True, "configured": False}):
            dlg._updated({"ok": False, "stderr": "сеть недоступна"})
        self.assertTrue(warned)
        self.assertIn("сеть недоступна", warned[0][2])
        dlg.deleteLater()

    def test_update_garbage_result_no_modal(self):
        # Не-dict результат воркера (гонка доставки после deleteLater, мок) —
        # без модального окна: вложенный цикл QMessageBox мог бы уничтожить
        # диалог с уже запланированным удалением посреди показа (порча кучи)
        import unittest.mock as mock
        dlg = self._make_updates_dialog()
        with mock.patch.object(self.z.QMessageBox, "warning") as warn_m, \
             mock.patch.object(self.z.QMessageBox, "question") as quest_m:
            dlg._updated(object())          # мусор вместо dict
            dlg._app_updated("не-словарь")
            dlg._updated("строка")
        warn_m.assert_not_called()
        quest_m.assert_not_called()
        dlg.deleteLater()

    def test_open_updates_opens_dialog(self):
        import unittest.mock as mock
        opened = []

        class _Fake:
            def __init__(self, parent=None):
                opened.append(self)

            def exec(self):
                return 0

        with mock.patch.object(self.z, "UpdatesDialog", _Fake):
            self.win._open_updates()
        self.assertTrue(opened, "Обновления не открыли диалог")

    # ---------- Статусы ----------
    def test_read_status_error_branch(self):
        import unittest.mock as mock
        with mock.patch("service_manager.query_status",
                        side_effect=RuntimeError("err")):
            d = self.win._read_status()
        self.assertTrue(d["status"].startswith("ERR:"))
        self.assertFalse(d["running"])

    def test_refresh_busy_guard_and_status_done(self):
        import unittest.mock as mock
        with mock.patch("service_manager.query_status", return_value="Running"), \
             mock.patch("service_manager.is_running", return_value=True), \
             mock.patch("service_manager.payloads_status", return_value={"ok": True, "missing": []}):
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
        self.win._fakes_replaced({"ok": False, "stderr": "нет такого fake"})
        self.assertIn("нет такого fake", self.win.flash.text())
        self.win._fakes_replaced({"ok": True, "stdout": "заменено"})
        self.assertIn("заменено", self.win.flash.text())

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
            # Язык возвращаем ТОЛЬКО пересборкой (тоггл _switch_lang),
            # иначе окно и i18n.t разойдутся у следующих тестов
            if self.i18n.LANG != old:
                self.win._switch_lang()
            self.i18n.save(old)   # и файл ui_settings.json к исходному языку

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
        for a in ["service_install", "service_remove", "start",
                  "stop", "toggle_ipset", "toggle_check_updates",
                  "set_game_filter", "menu_status", "clear_discord",
                  "restore_payloads", "ipset_update", "update_hosts",
                  "remove_conflicts", "relaunch_admin",
                  "update_zapret", "update_app"]:   # действия обновлений (диалог)
            self.assertIn(f'"{a}"', src, f"Действие {a} не вызывается")
        # Диалоги зовут ядро напрямую — сервисные действия в лог не попадают
        for fn in ("check_updates", "check_app_update", "run_diagnostics",
                   "query_status"):
            self.assertIn(fn, src, f"Вызов {fn} отсутствует")

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
        cls.win.timer.stop()
        cls.win._flash_timer.stop()
        cls.win.pool.waitForDone(1000)

    @classmethod
    def tearDownClass(cls):
        cls.QSystemTrayIcon.isSystemTrayAvailable = cls._orig_avail
        cls.win._exiting = True
        cls.win.timer.stop()
        cls.win._flash_timer.stop()
        cls.win.close()
        cls.win.pool.waitForDone(1000)

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


class TestPySideNewUIFeatures(unittest.TestCase):
    """Тесты новых UI компонентов: DoH диалог, переключатель звука, автозагрузка и выбор папки."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        import i18n
        import zapret_pyside as z
        cls.z, cls.i18n = z, i18n
        cls.app = QApplication.instance() or QApplication([])
        cls.win = z.MainWindow()
        cls.win.timer.stop()
        cls.win._flash_timer.stop()
        cls.win.pool.waitForDone(1000)

    @classmethod
    def tearDownClass(cls):
        cls.win._exiting = True
        cls.win.timer.stop()
        cls.win._flash_timer.stop()
        cls.win.close()
        cls.win.pool.waitForDone(1000)

    def test_doh_dialog_lifecycle(self):
        with mock.patch.object(self.win, "submit") as submit_m, \
             mock.patch.object(self.z.QMessageBox, "information"), \
             mock.patch.object(self.z.QMessageBox, "warning"), \
             mock.patch("service_manager.play_sound"):
            dlg = self.z.DohDialog(self.win)
            self.assertEqual(submit_m.call_count, 1)  # _refresh в __init__
            dlg._on_status({
                "provider": "cloudflare",
                "provider_name": "Cloudflare",
                "servers": ["1.1.1.1"],
                "adapters": ["Ethernet"],
                "autodoh": True,
            })
            self.assertIn("Cloudflare", dlg.status_lbl.text())
            self.assertEqual(dlg.provider_combo.currentData(), "cloudflare")

            # Проверяем отправку команд в воркер
            dlg._apply_doh()
            self.assertEqual(submit_m.call_count, 2)
            dlg._disable_doh()
            self.assertEqual(submit_m.call_count, 3)

            # Проверяем обработчик завершения действия (ok и error)
            dlg._on_action_done({"ok": True, "message": "done"})
            dlg._on_action_done({"ok": False, "error": "failed"})

            dlg.deleteLater()

    def test_sound_toggle_button(self):
        with mock.patch("service_manager.toggle_sound", side_effect=[False, True]), \
             mock.patch("service_manager.play_sound"):
            self.win._toggle_sound()
            self.assertEqual(self.win.sound_btn.text(), "🔇")
            self.win._toggle_sound()
            self.assertEqual(self.win.sound_btn.text(), "🔊")

    def test_autostart_toggle_ui(self):
        with mock.patch("service_manager.toggle_autostart", side_effect=[True, False]), \
             mock.patch("service_manager.play_sound"):
            self.win._toggle_autostart()
            self.assertIn(self.i18n.t("ui.autostart_on"), self.win.lbl_autostart.text())
            self.win._toggle_autostart()
            self.assertIn(self.i18n.t("ui.autostart_off"), self.win.lbl_autostart.text())

    def test_choose_zapret_folder_flow(self):
        with mock.patch("PySide6.QtWidgets.QFileDialog.getExistingDirectory", return_value="/custom/zapret"), \
             mock.patch("service_manager.set_custom_zapret_dir", return_value=(True, "OK")):
            self.win._choose_zapret_folder()
            self.assertIn("OK", self.win.flash.text())

    def test_unpack_zapret_zip_flow(self):
        with mock.patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=("/custom/zapret.zip", "zip")):
            self.win._unpack_zapret_zip()

        self.win._unpack_done({"ok": True, "service": "Распакован"})
        self.assertIn("Распакован", self.win.flash.text())

    def test_quick_check_flow(self):
        with mock.patch.object(self.win, "submit") as submit_m:
            self.win._quick_check()
            submit_m.assert_called_once()

        self.win._quick_check_done({
            "ok": True,
            "targets": [{"name": "YouTube", "ok": True, "latency_ms": 42}],
        })
        self.assertIn("YouTube: OK (42 ms)", self.win.flash.text())
        self.assertIn("YouTube: OK (42 ms)", self.win.output.toPlainText())

        self.win._quick_check_done({
            "ok": False,
            "targets": [{"name": "YouTube", "ok": False, "latency_ms": None}],
        })
        self.assertIn("YouTube: FAIL", self.win.flash.text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
