# tests/test_service_manager.py — 100% coverage of service_manager functions
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest.mock as mock


class TestServiceManager(unittest.TestCase):
    def test_install_service(self):
        # Явный .bat не должен уходи��ь в sc create — install_service обязан отказать до subprocess
        with mock.patch("service_manager.subprocess.run") as m:
            from service_manager import install_service
            ok, msg = install_service("C:\\zapret\\service.bat")
            self.assertFalse(ok)
            self.assertIn(".bat", msg)
            self.assertFalse(m.called)
        # Без аргументов: binPath = winws.exe + ARGS текущей стратегии, start=auto
        # (паритет с оригинальным :service_install: sc create ... start= auto)
        with mock.patch("service_manager.subprocess.run") as m, \
             mock.patch("service_manager.os.path.isfile", return_value=True), \
             mock.patch("zapret_core.scm.BIN_DIR", "C:\\fake\\bin"), \
             mock.patch("zapret_core.strategies.current_strategy", return_value="general"), \
             mock.patch("zapret_core.strategies.parse_strategy_args",
                        return_value=(["--wf-tcp=1", "--file=C:\\fake dir\\a.bin"], None)):
            m.return_value = mock.Mock(returncode=0, stdout=b"", stderr=b"")
            from service_manager import install_service
            ok, msg = install_service()
            self.assertTrue(ok, msg)
            args = m.call_args[0][0]
            self.assertIn("sc", args)
            self.assertTrue(any(a.startswith("binPath= ") for a in args), args)
            binpath = next(a for a in args if a.startswith("binPath= "))
            self.assertIn("winws.exe", binpath)
            self.assertIn("--wf-tcp=1", binpath)
            self.assertIn('"--file=C:\\fake dir\\a.bin"', binpath)  # пробелы — в кавычках
            self.assertIn("auto", args)  # start= auto, как в оригинале

    def test_uninstall_service(self):
        # Служба отсутствует в SCM: просто RemoveService + проверка исчезновения
        with mock.patch("service_manager.win32serviceutil.RemoveService", return_value=None), \
             mock.patch("service_manager.win32serviceutil.QueryServiceStatus",
                        side_effect=Exception("does not exist")):
            from service_manager import uninstall_service
            ok, msg = uninstall_service()
            self.assertTrue(ok, msg)

    def test_uninstall_service_stops_running_first(self):
        # Running-служба: сначала StopService + ожидание Stopped, иначе отказ (B4)
        import win32service
        running = (16, win32service.SERVICE_RUNNING, 0, 0, 0, 0, 0)
        stopped = (16, win32service.SERVICE_STOPPED, 0, 0, 0, 0, 0)
        with mock.patch("service_manager.win32serviceutil.QueryServiceStatus",
                        side_effect=[running, stopped, Exception("gone")]), \
             mock.patch("service_manager.win32serviceutil.StopService", return_value=None) as st, \
             mock.patch("service_manager.win32serviceutil.RemoveService", return_value=None), \
             mock.patch("time.sleep"):
            from service_manager import uninstall_service
            ok, msg = uninstall_service()
            self.assertTrue(ok, msg)
            st.assert_called_once()

    def test_uninstall_service_refuses_when_wont_stop(self):
        # Служба не останавливается за отведённое время — RemoveService не вызывается
        import win32service
        running = (16, win32service.SERVICE_RUNNING, 0, 0, 0, 0, 0)
        with mock.patch("service_manager.win32serviceutil.QueryServiceStatus",
                        return_value=running), \
             mock.patch("service_manager.win32serviceutil.StopService", return_value=None), \
             mock.patch("service_manager.win32serviceutil.RemoveService") as rm, \
             mock.patch("time.sleep"):
            from service_manager import uninstall_service
            ok, msg = uninstall_service()
            self.assertFalse(ok)
            self.assertFalse(rm.called)

    def test_query_status(self):
        # QueryServiceStatus возвращает (type, state, ...); state — индекс 1
        fake = (16, 4, 5, 0, 0, 0, 0)  # type=WIN32_OWN_PROCESS, state=RUNNING
        with mock.patch("service_manager.win32serviceutil.QueryServiceStatus", return_value=fake):
            from service_manager import is_running, query_status
            self.assertEqual(query_status(), "Running")
            self.assertTrue(is_running())
        stopped = (16, 1, 0, 0, 0, 0, 0)
        with mock.patch("service_manager.win32serviceutil.QueryServiceStatus", return_value=stopped):
            from service_manager import is_running, query_status
            self.assertEqual(query_status(), "Stopped")
            self.assertFalse(is_running())

    def test_start_stop_service(self):
        from service_manager import start_service, stop_service
        with mock.patch("service_manager.subprocess.run"):
            start_service()
            stop_service()

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
        with mock.patch("service_manager.os.path.isfile", return_value=True), \
             mock.patch("builtins.open", mock.mock_open(read_data="mode=all\ntcp=100-200\nudp=300-400\n")):
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
        import os

        from service_manager import BIN_DIR, ORIG_DIR
        self.assertTrue(ORIG_DIR, "ORIG_DIR пуст")
        self.assertEqual(BIN_DIR, os.path.join(ORIG_DIR, "bin"))
        self.assertTrue(os.path.isfile(os.path.join(ORIG_DIR, "bin", "winws.exe")),
                        f"winws.exe не найден в {BIN_DIR}")

    def test_payloads_status(self):
        from service_manager import payloads_status
        r = payloads_status()
        self.assertIsInstance(r["total"], int)
        self.assertIsInstance(r["missing"], list)
        self.assertIn("ok", r)
        # Мок: все обязательные файлы на месте
        with mock.patch("service_manager.os.path.isdir", return_value=True), \
             mock.patch("service_manager.os.listdir",
                        return_value=["ACTIVE_DISCORD_UDP.bin", "ACTIVE_GAME_UDP.bin",
                                      "quic_initial_www_google_com.bin",
                                      "tls_clienthello_www_google_com.bin"]):
            r2 = payloads_status()
        self.assertTrue(r2["ok"])
        self.assertEqual(r2["missing"], [])

    def test_restore_payloads(self):
        import shutil
        import tempfile

        from service_manager import restore_payloads
        src = tempfile.mkdtemp()
        dst = tempfile.mkdtemp()
        try:
            # обязательные + лишний не-.bin файл
            for n in ["ACTIVE_DISCORD_UDP.bin", "ACTIVE_GAME_UDP.bin",
                      "quic_initial_www_google_com.bin", "tls_clienthello_www_google_com.bin"]:
                with open(os.path.join(src, n), "wb") as f:
                    f.write(b"\x00" * 16)
            with open(os.path.join(src, "winws.exe"), "wb") as f:
                f.write(b"MZ")
            # в назначении уже лежит один файл — его перезаписывать нельзя
            with open(os.path.join(dst, "ACTIVE_GAME_UDP.bin"), "wb") as f:
                f.write(b"MANUAL")
            r = restore_payloads(dest_dir=dst, source_dir=src)
            self.assertTrue(r["ok"], r)
            self.assertIn("ACTIVE_DISCORD_UDP.bin", r["copied"])
            self.assertIn("ACTIVE_GAME_UDP.bin", r["skipped"])  # не перезаписан
            self.assertEqual(open(os.path.join(dst, "ACTIVE_GAME_UDP.bin"), "rb").read(), b"MANUAL")
            self.assertFalse(os.path.exists(os.path.join(dst, "winws.exe")))  # только .bin
            # повторный вызов — копировать нечего
            r2 = restore_payloads(dest_dir=dst, source_dir=src)
            self.assertEqual(r2["copied"], [])
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(dst, ignore_errors=True)

    def test_restore_payloads_same_dir_refused(self):
        from service_manager import restore_payloads
        r = restore_payloads(dest_dir="C:\\x", source_dir="C:\\x\\")
        self.assertFalse(r["ok"])

    def test_parse_strategy_args(self):
        import service_manager as s
        # general.bat существует в любой копии zapret — парсим по-настоящему
        args, err = s.parse_strategy_args("general")
        self.assertIsNone(err, err)
        self.assertTrue(args)
        self.assertTrue(any(a.startswith("--wf-tcp=") for a in args))
        self.assertTrue(any("winws" in a.lower() or a.endswith(".exe") or "bin" in a.lower()
                            for a in args))
        # несуществующая стратегия — честная ошибка
        args2, err2 = s.parse_strategy_args("no-such-strategy")
        self.assertIsNone(args2)
        self.assertIn("no-such-strategy", err2)  # путь в сообщении (ru/en из i18n)

    def test_parse_strategy_reassembles_caret_lines(self):
        # .bat пишет аргументы длинными строками с продолжением через ^
        import os as _os
        import shutil
        import tempfile

        import service_manager as s
        import zapret_core.strategies as strat
        d = tempfile.mkdtemp()
        try:
            bat = _os.path.join(d, "test-strategy.bat")
            with open(bat, "w", encoding="utf-8") as f:
                f.write('@echo off\r\nset "BIN=%~dp0bin\\"r\n'
                        'start "x" /min "%BIN%winws.exe" --wf-tcp=80,443 ^\r\n'
                        '--filter-tcp=443 --hostlist="%LISTS%list-general.txt" ^\r\n'
                        '--dpi-desync=fake --new\r\n')
            with mock.patch.object(strat, "ORIG_DIR", d), \
                 mock.patch.object(strat, "BIN_DIR", _os.path.join(d, "bin")), \
                 mock.patch.object(strat, "LISTS_DIR", _os.path.join(d, "lists")):
                args, err = s.parse_strategy_args("test-strategy")
            self.assertIsNone(err, err)
            # все три строки склеены в один список аргументов
            self.assertEqual(args, ["--wf-tcp=80,443", "--filter-tcp=443",
                                    '--hostlist="' + _os.path.join(d, "lists") + '\\list-general.txt"',
                                    "--dpi-desync=fake", "--new"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_current_strategy_file(self):
        import service_manager as s
        # Файл либо отсутствует (None), либо содержит непустую стратегию
        cur = s.current_strategy()
        self.assertTrue(cur is None or isinstance(cur, str))

    def test_find_payload_source_env(self):
        # ZAPRET_PAYLOADS_DIR имеет приоритет
        import shutil
        import tempfile

        from service_manager import find_payload_source
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "a.bin"), "wb") as f:
                f.write(b"x")
            with mock.patch.dict("os.environ", {"ZAPRET_PAYLOADS_DIR": d}):
                self.assertEqual(find_payload_source(), d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_hidden_cmd_get_bin(self):
        from service_manager import get_bin_path
        with mock.patch("service_manager.os.path.dirname", return_value="C:\\fake"):
            p = get_bin_path()
            self.assertTrue(isinstance(p, str))

    # === Переработка меню: диагностикa, тесты, тумблеры (порт service.bat) ===

    def test_menu_status_shape(self):
        # Шапка меню: версия, стратегия и три тумблера как в оригинале
        from service_manager import menu_status
        ms = menu_status()
        self.assertTrue(ms["ok"])
        for key in ("version", "strategy", "game_filter", "ipset", "check_updates", "admin"):
            self.assertIn(key, ms)
        self.assertIn(ms["ipset"], ("any", "none", "loaded"))
        self.assertIn(ms["check_updates"], ("enabled", "disabled"))

    def test_run_diagnostics_all_checks(self):
        # Диагностика: 17+ проверок оригинала, каждая с уровнем ok/warn/bad
        from service_manager import run_diagnostics
        with mock.patch("service_manager.subprocess.run") as sr:
            # sc query BFE -> RUNNING; прочие команды — пустой вывод
            def _side(cmd, **kw):
                r = mock.Mock()
                r.returncode = 0
                r.stdout = "        STATE              : 4  RUNNING\n" if cmd[:3] == ["sc", "query", "BFE"] else ""
                r.stderr = ""
                return r
            sr.side_effect = _side
            with mock.patch("zapret_core.diagnostics.winws_is_running", return_value=True), \
                 mock.patch("zapret_core.diagnostics.is_admin", return_value=False):
                d = run_diagnostics()
        self.assertGreaterEqual(len(d["checks"]), 17)
        names = {c["name"] for c in d["checks"]}
        for n in ("BFE", "Proxy", "TCP timestamps", "Adguard", "Killer", "Check Point",
                  "SmartByte", "Cyrillic path", "OneDrive", "WinDivert", "VPN",
                  "Secure DNS", "Hosts file", "Conflicting bypasses", "Discord"):
            self.assertIn(n, names)
        for c in d["checks"]:
            self.assertIn(c["level"], ("ok", "warn", "bad"))
        self.assertIn("counts", d)
        self.assertEqual(sum(d["counts"].values()), len(d["checks"]))

    def test_diagnostics_autofixes_timestamps_like_original(self):
        # Как в оригинале: реально выключенные timestamps диагностика включает сама
        # при правах админа (netsh локализован — парсим по «Метки времени RFC 1323»)
        from service_manager import run_diagnostics
        with mock.patch("service_manager.subprocess.run") as sr:
            def _side(cmd, **kw):
                r = mock.Mock()
                r.returncode = 0
                if cmd[:3] == ["sc", "query", "BFE"]:
                    r.stdout = b"        STATE              : 4  RUNNING\n"
                elif cmd[:2] == ["netsh", "interface"]:
                    r.stdout = ("Метки времени RFC 1323                 : disabled \n"
                                ).encode("utf-8")
                else:
                    r.stdout = b""
                r.stderr = b""
                return r
            sr.side_effect = _side
            with mock.patch("zapret_core.diagnostics.winws_is_running", return_value=True), \
                 mock.patch("zapret_core.diagnostics.is_admin", return_value=True), \
                 mock.patch("zapret_core.diagnostics.tcp_timestamps", return_value=(True, "enabled")):
                d = run_diagnostics()
        ts = next(c for c in d["checks"] if c["name"] == "TCP timestamps")
        self.assertEqual(ts["level"], "ok")
        import i18n
        self.assertEqual(ts["msg"], i18n.t("diag.ts_enabled"))

    def test_diagnostics_no_autofix_when_timestamps_enabled(self):
        # Русский netsh с enabled: авто-включения НЕТ — честный ok (B7)
        from service_manager import run_diagnostics
        with mock.patch("service_manager.subprocess.run") as sr:
            def _side(cmd, **kw):
                r = mock.Mock()
                r.returncode = 0
                if cmd[:3] == ["sc", "query", "BFE"]:
                    r.stdout = b"        STATE              : 4  RUNNING\n"
                elif cmd[:2] == ["netsh", "interface"]:
                    r.stdout = ("Метки времени RFC 1323                 : enabled \n"
                                ).encode("utf-8")
                else:
                    r.stdout = b""
                r.stderr = b""
                return r
            sr.side_effect = _side
            with mock.patch("zapret_core.diagnostics.winws_is_running", return_value=True), \
                 mock.patch("zapret_core.diagnostics.is_admin", return_value=True), \
                 mock.patch("zapret_core.diagnostics.tcp_timestamps") as ts_set:
                d = run_diagnostics()
        ts = next(c for c in d["checks"] if c["name"] == "TCP timestamps")
        self.assertEqual(ts["level"], "ok")
        import i18n
        self.assertEqual(ts["msg"], i18n.t("diag.ts_ok"))
        ts_set.assert_not_called()  # ничего не включали

    def test_diagnostics_unknown_timestamps_state_no_autofix(self):
        # Строку timestamps не удалось распарсить — warn без вмешательства (B7)
        from service_manager import run_diagnostics
        with mock.patch("service_manager.subprocess.run") as sr:
            def _side(cmd, **kw):
                r = mock.Mock()
                r.returncode = 0
                r.stdout = (b"        STATE              : 4  RUNNING\n"
                            if cmd[:3] == ["sc", "query", "BFE"]
                            else b"no such global parameters\n")
                r.stderr = b""
                return r
            sr.side_effect = _side
            with mock.patch("zapret_core.diagnostics.winws_is_running", return_value=True), \
                 mock.patch("zapret_core.diagnostics.is_admin", return_value=True), \
                 mock.patch("zapret_core.diagnostics.tcp_timestamps") as ts_set:
                d = run_diagnostics()
        ts = next(c for c in d["checks"] if c["name"] == "TCP timestamps")
        self.assertEqual(ts["level"], "warn")
        ts_set.assert_not_called()

    def test_tests_prerequisites_reports_problems(self):
        # Пре-чеки тестов честно перечисляют проблемы (права/curl/служба)
        from service_manager import tests_prerequisites
        with mock.patch("zapret_core.tests_runner.is_admin", return_value=False):
            probs = tests_prerequisites()
        import i18n
        self.assertIn(i18n.t("tests.need_admin"), probs)

    def test_run_tests_refuses_without_prereq(self):
        # Без прав тесты не запускаются вообще — возвращается список проблем
        from service_manager import run_tests
        with mock.patch("zapret_core.tests_runner.tests_prerequisites",
                        return_value=["no admin"]):
            r = run_tests()
        self.assertFalse(r["ok"])
        self.assertEqual(r["problems"], ["no admin"])

    def test_run_tests_answers_readhost(self):
        # Ответы на Read-Host пишутся в stdin ps1-скрипта (тип, режим, номер)
        from service_manager import run_tests
        proc = mock.Mock()
        proc.stdout = iter(["[OK] Administrator rights detected", "done"])
        proc.stdin = mock.Mock()
        with mock.patch("zapret_core.tests_runner.tests_prerequisites", return_value=[]), \
             mock.patch("service_manager.subprocess.Popen", return_value=proc), \
             mock.patch("zapret_core.tests_runner._latest_test_result", return_value=None):
            r = run_tests(test_type=1, mode=2, selection=3)
        written = proc.stdin.write.call_args[0][0]
        self.assertEqual(written, "1\n2\n3\n")
        self.assertTrue(r["ok"])
        self.assertIn("[OK] Administrator rights detected", r["stdout"])

    def test_toggle_ipset_cycle(self):
        # Цикл loaded->none->any->loaded с backup-файлом (как :ipset_switch)
        import shutil
        import tempfile

        from service_manager import ipset_status, toggle_ipset
        d = tempfile.mkdtemp()
        lf = os.path.join(d, "ipset-all.txt")
        with open(lf, "w", encoding="utf-8") as f:
            f.write("1.2.3.4/32\n")
        try:
            with mock.patch("zapret_core.lists.LISTS_DIR", d):
                self.assertEqual(ipset_status(), "loaded")
                r = toggle_ipset()
                self.assertTrue(r["ok"])
                self.assertEqual(ipset_status(), "none")
                r = toggle_ipset()
                self.assertTrue(r["ok"])
                self.assertEqual(ipset_status(), "any")
                r = toggle_ipset()
                self.assertTrue(r["ok"])
                self.assertEqual(ipset_status(), "loaded")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_set_game_filter_writes_file(self):
        import shutil
        import tempfile

        from service_manager import game_filter_label, set_game_filter
        d = tempfile.mkdtemp()
        try:
            with mock.patch("zapret_core.settings.ORIG_DIR", d):
                r = set_game_filter("tcp")
                self.assertTrue(r["ok"])
                with open(os.path.join(d, "utils", "game_filter.enabled"), encoding="utf-8") as f:
                    self.assertIn("mode=tcp", f.read())
                self.assertEqual(game_filter_label(), "enabled (TCP)")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_toggle_check_updates_flag_file(self):
        import shutil
        import tempfile

        from service_manager import check_updates_flag, toggle_check_updates
        d = tempfile.mkdtemp()
        try:
            with mock.patch("zapret_core.settings.ORIG_DIR", d):
                self.assertEqual(check_updates_flag(), "disabled")
                r = toggle_check_updates(True)
                self.assertTrue(r["ok"])
                self.assertEqual(check_updates_flag(), "enabled")
                r = toggle_check_updates(False)
                self.assertTrue(r["ok"])
                self.assertEqual(check_updates_flag(), "disabled")
        finally:
            shutil.rmtree(d, ignore_errors=True)

if __name__ == "__main__":
    unittest.main(verbosity=2)
