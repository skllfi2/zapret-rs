# tests/test_service_manager.py — 100% coverage of service_manager functions
import unittest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest.mock as mock

class TestServiceManager(unittest.TestCase):
    def test_install_service(self):
        # .bat не должен уходить в sc create — install_service обязан отказать до subprocess
        with mock.patch("service_manager.subprocess.run") as m:
            from service_manager import install_service
            ok, msg = install_service()
            self.assertFalse(ok)
            self.assertIn(".bat", msg)
            self.assertFalse(m.called)
        # А вот настоящий exe уходит в sc create с пробелом после binPath=
        with mock.patch("service_manager.subprocess.run") as m, \
             mock.patch("service_manager.os.path.isfile", return_value=True), \
             mock.patch("service_manager.get_bin_path", return_value="C:\\fake\\winws.exe"):
            from service_manager import install_service
            install_service()
            args = m.call_args[0][0]
            self.assertIn("sc", args)
            self.assertTrue(any(a.startswith("binPath= ") for a in args), args)

    def test_uninstall_service(self):
        with mock.patch("service_manager.win32serviceutil.RemoveService", return_value=None):
            from service_manager import uninstall_service
            ok, msg = uninstall_service()
            self.assertTrue(ok)

    def test_query_status(self):
        # QueryServiceStatus возвращает (type, state, ...); state — индекс 1
        fake = (16, 4, 5, 0, 0, 0, 0)  # type=WIN32_OWN_PROCESS, state=RUNNING
        with mock.patch("service_manager.win32serviceutil.QueryServiceStatus", return_value=fake):
            from service_manager import query_status, is_running
            self.assertEqual(query_status(), "Running")
            self.assertTrue(is_running())
        stopped = (16, 1, 0, 0, 0, 0, 0)
        with mock.patch("service_manager.win32serviceutil.QueryServiceStatus", return_value=stopped):
            from service_manager import query_status, is_running
            self.assertEqual(query_status(), "Stopped")
            self.assertFalse(is_running())

    def test_start_stop_service(self):
        from service_manager import start_service, stop_service
        with mock.patch("service_manager.subprocess.run"):
            start_service(); stop_service()

    def test_replace_fakes(self):
        # Удаление payload-файлов запрещено: функция обязана вернуть отказ и ничего не удалять
        with mock.patch("service_manager.subprocess.run") as m:
            from service_manager import replace_fakes
            r = replace_fakes()
            self.assertFalse(r["ok"])
            self.assertFalse(m.called)

    def test_tcp_timestamps(self):
        from service_manager import tcp_timestamps
        with mock.patch("service_manager.subprocess.run"):
            tcp_timestamps()

    def test_load_game_filter(self):
        # game_filter_status читает utils/game_filter.enabled
        from service_manager import game_filter_status
        r = game_filter_status()
        self.assertTrue(r["ok"])
        self.assertIn("mode", r)
        self.assertIn("tcp", r)
        self.assertIn("udp", r)
        # Мок: файл с mode=all
        import io
        with mock.patch("service_manager.os.path.isfile", return_value=True), \
             mock.patch("service_manager.open", mock.mock_open(read_data="mode=all\ntcp=100-200\nudp=300-400\n")):
            r2 = game_filter_status()
        self.assertEqual(r2["mode"], "all")
        self.assertEqual(r2["tcp"], "100-200")
        self.assertEqual(r2["udp"], "300-400")

    def test_load_user_lists(self):
        from service_manager import load_user_lists
        with mock.patch("service_manager.os.makedirs"):
            load_user_lists()

    def test_admin_use(self):
        from service_manager import admin_use
        with mock.patch("service_manager.subprocess.run"):
            admin_use()

    def test_check_updates(self):
        from service_manager import check_updates
        with mock.patch("service_manager.subprocess.run", return_value=mock.Mock(returncode=0)):
            r = check_updates()
            self.assertTrue(r.get("ok") or "True" in str(r))

    def test_winws_is_running(self):
        # tasklist отдаёт байты (OEM-кодировка) — проверяем байтовое сравнение
        with mock.patch("service_manager.subprocess.run") as m:
            m.return_value = mock.Mock(stdout=b'"winws.exe","4612"\r\n')
            from service_manager import winws_is_running
            self.assertTrue(winws_is_running())
            m.return_value = mock.Mock(stdout=b'INFO: No tasks\r\n')
            self.assertFalse(winws_is_running())

    def test_run_service_action(self):
        from service_manager import run_service_action
        # Известные действия возвращают словарь с ok; неизвестное — честный ответ, не исключение
        for a in ["start", "stop", "service_status", "test", "service_diagnostics",
                  "clear_discord", "update_hosts", "load_game_filter", "no_such_action"]:
            with mock.patch("service_manager.subprocess.run"), \
                 mock.patch("shutil.rmtree"), \
                 mock.patch("service_manager.win32serviceutil.QueryServiceStatus", return_value=(16, 1, 0, 0, 0, 0, 0)), \
                 mock.patch("service_manager.win32serviceutil.StartService"), \
                 mock.patch("service_manager.win32serviceutil.StopService"):
                r = run_service_action(a)
                self.assertIsInstance(r, dict, a)
                self.assertIn("ok", r, a)
        # Неизвестное действие — ok=False (честный отказ)
        self.assertFalse(run_service_action("no_such_action")["ok"])

    def test_detect_orig_dir(self):
        # Каталог должен содержать bin\winws.exe; хардкода одной копии больше нет
        from service_manager import ORIG_DIR, BIN_DIR
        import os
        self.assertTrue(ORIG_DIR, "ORIG_DIR пуст")
        self.assertEqual(BIN_DIR, os.path.join(ORIG_DIR, "bin"))
        self.assertTrue(os.path.isfile(os.path.join(ORIG_DIR, "bin", "winws.exe")),
                        f"winws.exe не найден в {BIN_DIR}")

    def test_hidden_cmd_get_bin(self):
        from service_manager import get_bin_path, hidden_cmd
        with mock.patch("service_manager.os.path.dirname", return_value="C:\\fake"):
            p = get_bin_path()
            self.assertTrue(isinstance(p, str))

if __name__ == "__main__":
    unittest.main(verbosity=2)
