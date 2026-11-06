# tests/test_smoke_live.py — живой smoke-скрипт: CLI, выбор стратегии, отчёт, dry-run
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import smoke_live


class TestParseArgs(unittest.TestCase):
    def test_defaults(self):
        a = smoke_live.parse_args([])
        self.assertFalse(a.tests)
        self.assertFalse(a.dry_run)
        self.assertEqual((a.test_type, a.mode, a.selection), (1, 1, 1))
        self.assertEqual(a.timeout, 1800)

    def test_full_invocation(self):
        a = smoke_live.parse_args(["--tests", "--yes", "--mode", "2", "--selection", "3",
                                   "--strategy", "general (ALT)", "--no-apply"])
        self.assertTrue(a.tests and a.yes and a.no_apply)
        self.assertEqual((a.mode, a.selection), (2, 3))
        self.assertEqual(a.strategy, "general (ALT)")

    def test_unknown_arg_fails(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            smoke_live.parse_args(["--no-such-flag"])


class TestSelectedStrategy(unittest.TestCase):
    """_selected_strategy: предыдущая реальная стратегия, иначе дефолт ядра, иначе пусто."""

    def test_prefers_previous_strategy(self):
        with mock.patch.object(smoke_live, "list_strategies", return_value=["a", "b"]), \
                mock.patch.object(smoke_live, "current_strategy", return_value="b"):
            self.assertEqual(smoke_live._selected_strategy(), "b")

    def test_core_default_when_no_previous(self):
        with mock.patch.object(smoke_live, "list_strategies", return_value=["a", "b"]), \
                mock.patch.object(smoke_live, "current_strategy", return_value=None), \
                mock.patch.object(smoke_live, "default_strategy", return_value="a"):
            self.assertEqual(smoke_live._selected_strategy(), "a")

    def test_empty_when_no_strategies(self):
        with mock.patch.object(smoke_live, "list_strategies", return_value=[]), \
                mock.patch.object(smoke_live, "current_strategy", return_value=None), \
                mock.patch.object(smoke_live, "default_strategy", return_value=None):
            self.assertEqual(smoke_live._selected_strategy(), "")


class TestReport(unittest.TestCase):
    def setUp(self):
        smoke_live.RESULTS.clear()

    def test_check_prints_and_records(self):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertTrue(smoke_live.check(True, "ok-пункт"))
            self.assertFalse(smoke_live.check(False, "bad-пункт", "деталь"))
        out = buf.getvalue()
        self.assertIn("[PASS] ok-пункт", out)
        self.assertIn("[FAIL] bad-пункт — деталь", out)
        self.assertEqual(len(smoke_live.RESULTS), 2)

    def test_summary_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            smoke_live.check(True, "хорошо")
            self.assertEqual(smoke_live.summary(), 0)
            smoke_live.check(False, "плохо")
            self.assertEqual(smoke_live.summary(), 1)
        self.assertIn("FAIL: плохо", buf.getvalue())

    def test_summary_empty_is_success(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(smoke_live.summary(), 0)


class TestStepsDryRun(unittest.TestCase):
    def setUp(self):
        smoke_live.RESULTS.clear()

    def test_step_apply_dry_run_touches_nothing(self):
        with mock.patch.object(smoke_live, "apply_strategy") as apply_mock, \
                mock.patch.object(smoke_live, "is_admin") as admin_mock, \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            smoke_live.step_apply("general", dry=True)
        apply_mock.assert_not_called()
        admin_mock.assert_not_called()
        self.assertIn("[SKIP]", buf.getvalue())
        self.assertEqual(smoke_live.RESULTS, [])

    def test_step_apply_without_admin_is_fail(self):
        with mock.patch.object(smoke_live, "is_admin", return_value=False), \
                mock.patch.object(smoke_live, "apply_strategy") as apply_mock, \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            smoke_live.step_apply("general", dry=False)
        apply_mock.assert_not_called()
        self.assertIn("[FAIL]", buf.getvalue())
        self.assertEqual(smoke_live.RESULTS, [(False, "применение стратегии")])

    def test_step_tests_dry_run_skips_removal_and_run(self):
        args = smoke_live.parse_args(["--dry-run", "--tests"])
        with mock.patch.object(smoke_live, "uninstall_service") as un_mock, \
                mock.patch.object(smoke_live, "run_tests") as run_mock, \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            smoke_live.step_tests(args, "general")
        un_mock.assert_not_called()
        run_mock.assert_not_called()
        self.assertIn("[SKIP]", buf.getvalue())


class TestMainWiring(unittest.TestCase):
    def setUp(self):
        smoke_live.RESULTS.clear()

    def test_apply_only_by_default(self):
        with mock.patch.object(smoke_live, "preflight", return_value="general"), \
                mock.patch.object(smoke_live, "step_apply") as apply_step, \
                mock.patch.object(smoke_live, "step_tests") as tests_step, \
                contextlib.redirect_stdout(io.StringIO()):
            code = smoke_live.main(["--dry-run"])
        self.assertEqual(code, 0)
        apply_step.assert_called_once_with("general", True)
        tests_step.assert_not_called()

    def test_tests_step_runs_with_flag(self):
        with mock.patch.object(smoke_live, "preflight", return_value="general"), \
                mock.patch.object(smoke_live, "step_apply"), \
                mock.patch.object(smoke_live, "step_tests") as tests_step, \
                contextlib.redirect_stdout(io.StringIO()):
            code = smoke_live.main(["--dry-run", "--tests"])
        self.assertEqual(code, 0)
        tests_step.assert_called_once()

    def test_no_strategies_short_circuits(self):
        with mock.patch.object(smoke_live, "preflight", return_value=""), \
                mock.patch.object(smoke_live, "step_apply") as apply_step, \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            code = smoke_live.main(["--dry-run"])
        self.assertEqual(code, 1)
        apply_step.assert_not_called()
        self.assertIn("FAIL", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
