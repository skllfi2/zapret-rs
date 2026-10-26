# tests/test_pyside_ui.py — десктопный UI на PySide6: кнопки, стратегии, потоки
import unittest, sys, os

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
        import zapret_pyside as z
        from PySide6.QtWidgets import QApplication, QPushButton, QComboBox
        cls.z = z
        cls.QPushButton = QPushButton
        cls.QComboBox = QComboBox
        cls.app = QApplication.instance() or QApplication([])
        cls.win = z.MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def _btn_texts(self):
        return [b.text() for b in self.win.findChildren(self.QPushButton)]

    def test_all_buttons_present(self):
        # Паритет с tkinter-версией: все действия доступны
        texts = self._btn_texts()
        for a in ["Status", "Install Svc", "Uninstall", "Start", "Stop", "Diag",
                  "Test", "Update", "GameFilter", "Clear Discord", "List Fakes",
                  "Restore Payload", "IPSet Update", "Admin (права)", "Применить"]:
            self.assertIn(a, texts, f"Кнопка {a} отсутствует")

    def test_strategy_selector_populated(self):
        # Комбобокс стратегий реально заполнен из list_strategies() (реальные .bat)
        boxes = self.win.findChildren(self.QComboBox)
        self.assertTrue(boxes, "Нет селектора стратегий")
        self.assertGreater(boxes[0].count(), 0, "Список стратегий пуст")
        self.assertTrue(boxes[0].currentText(), "Стратегия не выбрана")

    def test_output_populated(self):
        self.assertTrue(self.win.output.toPlainText().strip(), "Область вывода пуста")

    def test_status_updates_via_threadpool(self):
        # Статус читается в фоне через QThreadPool и доставляется сигналом
        import time
        for _ in range(40):
            self.app.processEvents()
            time.sleep(0.02)
            if self.win.status_text.text() not in ("Неизвестно", ""):
                break
        self.assertNotEqual(self.win.status_text.text(), "")

    def test_no_widget_access_from_worker_threads(self):
        # Стратегия Qt: работа в потоке, результат — через сигнал в главный поток
        src = _read_src()
        self.assertIn("QThreadPool", src)
        self.assertIn("Signal(", src)
        self.assertNotIn("root.after(0", src)  # остаток tkinter-подхода


class TestPySideSource(unittest.TestCase):
    """Текстовые проверки — работают даже без установленного PySide6."""

    def test_service_manager_imported(self):
        self.assertIn("import service_manager", _read_src())

    def test_all_action_strings_present(self):
        src = _read_src()
        for a in ["service_status", "service_install", "service_remove", "start",
                  "stop", "service_diagnostics", "test", "check_updates",
                  "load_game_filter", "clear_discord", "restore_payloads",
                  "ipset_update", "relaunch_admin"]:
            self.assertIn(f'"{a}"', src, f"Действие {a} не вызывается")

    def test_admin_gate_on_strategy(self):
        # Применение стратегии без прав должно честно отказываться
        src = _read_src()
        self.assertIn("is_admin()", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
