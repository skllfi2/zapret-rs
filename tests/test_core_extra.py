# tests/test_core_extra.py — новые модули zapret_core: best_strategy, обновления,
# хелперы диагностик, статусы списков/фильтров, лог applog
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest.mock as mock


class TestBestStrategy(unittest.TestCase):
    """Лучшая стратегия из последнего test_results_*.txt (строка 'Best strategy: X.bat')."""

    def _best(self, content, strats=("general (ALT11)", "general")):
        from zapret_core import tests_runner as tr
        with mock.patch.object(tr, "_latest_test_result",
                               return_value="C:/r/test_results_x.txt"), \
             mock.patch.object(tr, "list_strategies", return_value=list(strats)), \
             mock.patch("builtins.open", mock.mock_open(read_data=content)):
            return tr.best_strategy()

    def test_parses_best_line_and_strips_bat(self):
        r = self._best("=== ANALYTICS ===\ngeneral.bat : HTTP OK: 36\n"
                       "Best strategy: general (ALT11).bat\n")
        self.assertTrue(r["ok"])
        self.assertEqual(r["strategy"], "general (ALT11)")
        self.assertEqual(r["file"], "test_results_x.txt")

    def test_no_results_file(self):
        from zapret_core import tests_runner as tr
        with mock.patch.object(tr, "_latest_test_result", return_value=None):
            r = tr.best_strategy()
        self.assertFalse(r["ok"])
        self.assertIsNone(r["strategy"])

    def test_no_best_line(self):
        r = self._best("=== ANALYTICS ===\ngeneral.bat : HTTP OK: 36\n")
        self.assertFalse(r["ok"])
        self.assertIsNone(r["strategy"])

    def test_strategy_missing_in_list_refused(self):
        # Файл от чужой/старой копии — несуществующее имя не предлагаем
        r = self._best("Best strategy: ghost.bat\n", strats=("general",))
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "ghost")


class TestUpdates(unittest.TestCase):
    """check_updates: локальная версия из service.bat vs GitHub (мок сети)."""

    def _dir(self, enabled=True, version='set "LOCAL_VERSION=1.2.3"'):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "utils"), exist_ok=True)
        if enabled:
            with open(os.path.join(d, "utils", "check_updates.enabled"), "w") as f:
                f.write("ENABLED\n")
        with open(os.path.join(d, "service.bat"), "w", encoding="utf-8") as f:
            f.write(version + "\n")
        return d

    def test_disabled_by_flag_file(self):
        from zapret_core import updates
        d = self._dir(enabled=False)
        try:
            with mock.patch.object(updates, "ORIG_DIR", d):
                r = updates.check_updates()
            self.assertTrue(r["ok"])
            self.assertFalse(r["enabled"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_network_error_is_not_fatal(self):
        # Как в оригинале: не смогли проверить — это не ошибка работы zapret
        from zapret_core import updates
        d = self._dir()
        try:
            with mock.patch.object(updates, "ORIG_DIR", d), \
                 mock.patch("urllib.request.urlopen", side_effect=OSError("no net")):
                r = updates.check_updates()
            self.assertTrue(r["ok"])
            self.assertEqual(r["local"], "1.2.3")
            self.assertIsNone(r["remote"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_update_available_flag(self):
        from zapret_core import updates

        class _Resp:
            """Ответ GitHub API latest release (новая модель: JSON, а не raw version.txt)."""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"tag_name": "9.9.9", "assets": []}'

        d = self._dir()
        try:
            with mock.patch.object(updates, "ORIG_DIR", d), \
                 mock.patch("urllib.request.urlopen", return_value=_Resp()):
                r = updates.check_updates()
            self.assertTrue(r["update_available"])
            self.assertEqual(r["remote"], "9.9.9")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_version_unreadable(self):
        from zapret_core import updates
        d = self._dir(version=":: no version here")
        try:
            with mock.patch.object(updates, "ORIG_DIR", d):
                r = updates.check_updates()
            self.assertFalse(r["ok"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestDiagnosticsHelpers(unittest.TestCase):
    def test_sc_service_names_via_enum_services_status(self):
        # A4: имена служб — через win32service (не зависит от локали), sc query не парсим
        from zapret_core import diagnostics as dg
        fake_services = [("BFE", "Base Filtering Engine", (16, 4, 0, 0, 0, 0, 0)),
                         ("WinDivert", "WinDivert", (16, 1, 0, 0, 0, 0, 0))]
        with mock.patch.object(dg.win32service, "OpenSCManager", return_value="HNDL") as oscm, \
             mock.patch.object(dg.win32service, "EnumServicesStatus",
                               return_value=fake_services) as enum, \
             mock.patch.object(dg.win32service, "CloseServiceHandle") as close:
            names = dg._sc_service_names()
        self.assertEqual(names, ["BFE", "WinDivert"])
        oscm.assert_called_once()
        enum.assert_called_once_with("HNDL")
        close.assert_called_once_with("HNDL")

    def test_sc_service_names_swallows_errors(self):
        from zapret_core import diagnostics as dg
        with mock.patch.object(dg.win32service, "OpenSCManager",
                               side_effect=OSError("access denied")):
            self.assertEqual(dg._sc_service_names(), [])

    def test_tasklist_running(self):
        # B6: tasklist ловится в байтах (cp866 на русской локали) — decode_output разбирает
        from zapret_core import diagnostics as dg
        with mock.patch("subprocess.run") as sr:
            sr.return_value = mock.Mock(stdout=b"AdguardSvc.exe PID 123")
            self.assertTrue(dg._tasklist_running("AdguardSvc.exe"))
            sr.return_value = mock.Mock(stdout=b"INFO: No tasks")
            self.assertFalse(dg._tasklist_running("AdguardSvc.exe"))

    def test_tasklist_running_cp866_image_name(self):
        # Имя процесса в OEM-кодировке (кириллица в пути) тоже находится
        from zapret_core import diagnostics as dg
        with mock.patch("subprocess.run") as sr:
            sr.return_value = mock.Mock(stdout="Имя.exe PID 1".encode("cp866"))
            self.assertTrue(dg._tasklist_running("Имя.exe"))

    def test_remove_conflicts_refuses_without_admin(self):
        # Без прав — отказ до любого subprocess: ничего не удаляем молча
        from zapret_core import diagnostics as dg
        with mock.patch.object(dg, "is_admin", return_value=False), \
             mock.patch("subprocess.run") as sr:
            r = dg.remove_conflicts()
        self.assertFalse(r["ok"])
        self.assertFalse(sr.called)


class TestListAndFilterStatus(unittest.TestCase):
    def test_ipset_status_variants(self):
        from zapret_core import lists as li
        d = tempfile.mkdtemp()
        p = os.path.join(d, "ipset-all.txt")
        try:
            with mock.patch.object(li, "LISTS_DIR", d):
                self.assertEqual(li.ipset_status(), "none")   # файла нет
                with open(p, "w") as f:
                    f.write("")
                self.assertEqual(li.ipset_status(), "any")    # пустой = пропускать всё
                with open(p, "w") as f:
                    f.write("203.0.113.113/32\n")
                self.assertEqual(li.ipset_status(), "none")   # заглушка-маркер
                with open(p, "w") as f:
                    f.write("1.2.3.4/32\n")
                self.assertEqual(li.ipset_status(), "loaded")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_game_filter_absent_file_is_disabled(self):
        from zapret_core import settings as se
        d = tempfile.mkdtemp()  # utils/game_filter.enabled отсутствует
        try:
            with mock.patch.object(se, "ORIG_DIR", d):
                r = se.game_filter_status()
                label = se.game_filter_label()
            self.assertTrue(r["ok"])
            self.assertFalse(r["enabled"])
            self.assertEqual(label, "disabled")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_game_filter_udp_label(self):
        from zapret_core import settings as se
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "utils"))
            with open(os.path.join(d, "utils", "game_filter.enabled"), "w") as f:
                f.write("mode=udp\ntcp=1024-65535\nudp=1024-65535\n")
            with mock.patch.object(se, "ORIG_DIR", d):
                self.assertEqual(se.game_filter_label(), "enabled (UDP)")
                self.assertTrue(se.game_filter_status()["enabled"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestScmAndMisc(unittest.TestCase):
    def test_set_autostart_switches_start_type(self):
        from zapret_core import scm
        with mock.patch("subprocess.run") as sr:
            sr.return_value = mock.Mock(returncode=0, stdout="OK", stderr="")
            ok_auto, _ = scm.set_autostart(True)
            ok_demand, _ = scm.set_autostart(False)
        self.assertTrue(ok_auto and ok_demand)
        cmds = [c.args[0] for c in sr.call_args_list]
        self.assertIn("auto", cmds[0])
        self.assertIn("demand", cmds[1])

    def test_admin_use_refuses_without_admin(self):
        from zapret_core import misc
        with mock.patch.object(misc, "is_admin", return_value=False), \
             mock.patch("subprocess.run") as sr:
            r = misc.admin_use()
        self.assertFalse(r["ok"])
        self.assertFalse(sr.called)  # отказ до проверки команд

    def test_router_best_strategy_action(self):
        from zapret_core import router
        with mock.patch.object(router, "best_strategy",
                               return_value={"ok": True, "strategy": "general"}):
            r = router.run_service_action("best_strategy")
        self.assertTrue(r["ok"])
        self.assertEqual(r["strategy"], "general")


class TestWinwsFakes(unittest.TestCase):
    def test_list_fakes_hashes_and_active_flag(self):
        from zapret_core import winws as ww
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "ACTIVE_DISCORD_UDP.bin"), "wb") as f:
                f.write(b"\x00")
            with open(os.path.join(d, "other.bin"), "wb") as f:
                f.write(b"\x01")
            with mock.patch.object(ww, "BIN_DIR", d):
                r = ww.list_fakes()
            items = {i["name"]: i for i in r["stdout"]}
            self.assertTrue(items["ACTIVE_DISCORD_UDP.bin"]["active"])
            self.assertFalse(items["other.bin"]["active"])
            self.assertNotEqual(items["other.bin"]["sha256"], "?")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestAppLog(unittest.TestCase):
    """Лог и excepthook: любая необработанная ошибка уходит в zapret.log."""

    def setUp(self):
        from zapret_core import applog
        self.applog = applog
        self.tmp = tempfile.mkdtemp()
        self._old = applog.LOG_DIR, applog.LOG_FILE
        applog.LOG_DIR = self.tmp
        applog.LOG_FILE = os.path.join(self.tmp, "zapret.log")

    def tearDown(self):
        self.applog.LOG_DIR, self.applog.LOG_FILE = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read(self):
        with open(self.applog.LOG_FILE, encoding="utf-8") as f:
            return f.read()

    def test_log_writes_timestamped_line(self):
        self.applog.log("hello-marker")
        data = self._read()
        self.assertIn("hello-marker", data)
        self.assertIn("[", data)  # метка времени

    def test_log_never_raises_on_broken_dir(self):
        self.applog.LOG_FILE = os.path.join("::bad::path", "zapret.log")
        self.applog.log("must not raise")  # не должно бросить

    def test_excepthook_sends_traceback_to_log(self):
        import sys as _sys
        old_hook = _sys.excepthook
        old_thread_hook = threading.excepthook
        try:
            with mock.patch.object(self.applog, "_show_dialog"), \
                 mock.patch.object(_sys, "frozen", True, create=True):
                self.applog.install_excepthook()
                try:
                    raise ValueError("boom-value")
                except ValueError:
                    self.applog._handle(*sys.exc_info())
            data = self._read()
            self.assertIn("UNHANDLED", data)
            self.assertIn("boom-value", data)
        finally:
            _sys.excepthook = old_hook
            threading.excepthook = old_thread_hook


if __name__ == "__main__":
    unittest.main(verbosity=2)
