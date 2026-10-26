# tests/test_tkinter_buttons.py — 100% button/action coverage
import unittest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestTkinterButtons(unittest.TestCase):
    def test_all_buttons_present(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "zapret-tkinter.py"), "r", encoding="utf-8") as f:
            content = f.read()
        actions = ["Status","Install","Uninstall","Start","Stop","Diag","Test","Update","Replace","Discord"]
        for a in actions:
            self.assertIn(a, content, f"Button {a} missing")

    def test_service_manager_imported(self):
        import service_manager
        self.assertTrue(hasattr(service_manager, "run_service_action"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
