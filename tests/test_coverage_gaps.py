# tests/test_coverage_gaps.py — добивка покрытия по краевым веткам ядра:
# apply_strategy (все пути службы под моками), misc/lists/winws (сеть и файлы моками),
# tests_runner (итоги/таймаут/отказы), router (все действия и алиасы),
# i18n/applog (краевые пути), diagnostics.remove_conflicts.
# Здесь НИКОГДА не вызываются реальный UAC и реальные мутации службы.
import contextlib
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest.mock as mock

try:
    import PySide6  # noqa: F401
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


class TestApplyStrategy(unittest.TestCase):
    """apply_strategy: пересоздание/перезапуск службы — только под моками win32serviceutil."""

    def setUp(self):
        from zapret_core import strategies as strat
        self.strat = strat
        self.d = tempfile.mkdtemp()
        with open(os.path.join(self.d, "general.bat"), "w", encoding="utf-8") as f:
            f.write('@echo off\r\n"%BIN%winws.exe" --wf-tcp=80,443 --filter-tcp=80 --new\r\n')
        self.sfile = os.path.join(self.d, ".strategy")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _base_patches(self, exists=True, running=False):
        """Общие условия: temp-каталог стратегий, права, служба под моками."""
        st = self.strat
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(st, "ORIG_DIR", self.d))
        stack.enter_context(mock.patch.object(st, "STRATEGY_FILE", self.sfile))
        stack.enter_context(mock.patch.object(st, "is_admin", return_value=True))
        stack.enter_context(mock.patch.object(st, "is_running", return_value=running))
        stack.enter_context(mock.patch.object(st, "query_status", return_value="Stopped"))
        stack.enter_context(mock.patch("time.sleep"))
        # ВСЕ мутирующие SCM-функции под моками — по-настоящему ничего не пересоздаём
        stack.enter_context(mock.patch("win32serviceutil.StartService"))
        stack.enter_context(mock.patch("win32serviceutil.StopService"))
        if exists:
            stack.enter_context(mock.patch("win32serviceutil.QueryServiceStatus",
                                           return_value=object()))
        else:
            stack.enter_context(mock.patch("win32serviceutil.QueryServiceStatus",
                                           side_effect=OSError("нет службы")))
        return stack

    def test_apply_changes_config_of_existing_service(self):
        with self._base_patches(exists=True), \
             mock.patch("win32serviceutil.ChangeServiceConfig") as change, \
             mock.patch("win32serviceutil.StartService") as start, \
             mock.patch("win32serviceutil.InstallService") as install:
            r = self.strat.apply_strategy("general")
        self.assertTrue(r["ok"], r)
        change.assert_called_once()
        start.assert_called_once()
        install.assert_not_called()
        # A1: первый аргумент — pythonClassString (None), имя службы — вторым
        args, kwargs = change.call_args
        self.assertIsNone(args[0])
        self.assertEqual(args[1], self.strat.SERVICE_NAME)
        self.assertTrue(kwargs["exeName"].endswith("winws.exe"))
        self.assertIn("--wf-tcp=80,443", kwargs["exeArgs"])
        with open(self.sfile, encoding="utf-8") as f:
            self.assertEqual(f.read(), "general")  # .strategy запомнен

    def test_apply_installs_missing_service(self):
        # Службы нет (QueryServiceStatus упал) — ставим новую через InstallService
        with self._base_patches(exists=False), \
             mock.patch("win32serviceutil.InstallService") as install, \
             mock.patch("win32serviceutil.ChangeServiceConfig") as change:
            r = self.strat.apply_strategy("general")
        self.assertTrue(r["ok"], r)
        install.assert_called_once()
        change.assert_not_called()
        # A2: pythonClassString=None, служба/отображение — 2-й/3-й, exeName — kwarg
        args, kwargs = install.call_args
        self.assertIsNone(args[0])
        self.assertEqual(args[1], self.strat.SERVICE_NAME)
        self.assertEqual(args[2], self.strat.SERVICE_DISPLAY)
        self.assertTrue(kwargs["exeName"].endswith("winws.exe"))

    def test_apply_stops_running_service_first(self):
        with self._base_patches(exists=True, running=True), \
             mock.patch("win32serviceutil.StopService") as stop, \
             mock.patch("win32serviceutil.ChangeServiceConfig") as change:
            r = self.strat.apply_strategy("general")
        self.assertTrue(r["ok"], r)
        stop.assert_called_once()
        change.assert_called_once()

    def test_apply_refuses_when_stop_fails(self):
        # D2: StopService упал (не 1062) — отказ ДО ChangeServiceConfig, конфиг не тронут
        with self._base_patches(exists=True, running=True), \
             mock.patch("win32serviceutil.StopService",
                        side_effect=OSError("access denied")), \
             mock.patch("win32serviceutil.ChangeServiceConfig") as change:
            r = self.strat.apply_strategy("general")
        self.assertFalse(r["ok"])
        change.assert_not_called()

    def test_apply_refuses_when_service_wont_stop(self):
        # D2: за 10 с не остановилась — отказ до ChangeServiceConfig
        with self._base_patches(exists=True, running=True), \
             mock.patch.object(self.strat, "query_status", return_value="Running"), \
             mock.patch("win32serviceutil.ChangeServiceConfig") as change:
            r = self.strat.apply_strategy("general")
        self.assertFalse(r["ok"])
        change.assert_not_called()

    def test_apply_treats_1056_start_as_success(self):
        # D2: 1056 = уже запущена — конфиг применён, это успех
        err = OSError("service already running")
        err.winerror = 1056
        with self._base_patches(exists=True), \
             mock.patch("win32serviceutil.ChangeServiceConfig"), \
             mock.patch("win32serviceutil.StartService", side_effect=err):
            r = self.strat.apply_strategy("general")
        self.assertTrue(r["ok"], r)

    def test_apply_without_restart_skips_start(self):
        with self._base_patches(exists=True), \
             mock.patch("win32serviceutil.ChangeServiceConfig"), \
             mock.patch("win32serviceutil.StartService") as start:
            r = self.strat.apply_strategy("general", restart=False)
        self.assertTrue(r["ok"], r)
        start.assert_not_called()

    def test_apply_service_error_reported(self):
        with self._base_patches(exists=True), \
             mock.patch("win32serviceutil.ChangeServiceConfig",
                        side_effect=RuntimeError("boom")):
            r = self.strat.apply_strategy("general")
        self.assertFalse(r["ok"])
        self.assertEqual(r["service"], "boom")

    def test_apply_refuses_without_admin(self):
        st = self.strat
        with mock.patch.object(st, "ORIG_DIR", self.d), \
             mock.patch.object(st, "is_admin", return_value=False), \
             mock.patch("win32serviceutil.InstallService") as install, \
             mock.patch("win32serviceutil.ChangeServiceConfig") as change:
            r = st.apply_strategy("general")
        self.assertFalse(r["ok"])
        install.assert_not_called()
        change.assert_not_called()

    def test_apply_unknown_strategy_fails_early(self):
        # Несуществующая стратегия → отказ до прав и службы (ветка parse-ошибки)
        with mock.patch.object(self.strat, "ORIG_DIR", self.d), \
             mock.patch.object(self.strat, "is_admin", return_value=True), \
             mock.patch("win32serviceutil.InstallService") as install:
            r = self.strat.apply_strategy("no-such-strategy")
        self.assertFalse(r["ok"])
        install.assert_not_called()

    def test_list_strategies_unreadable_dir(self):
        with mock.patch.object(self.strat, "ORIG_DIR", os.path.join(self.d, "gone")):
            self.assertEqual(self.strat.list_strategies(), [])

    def test_game_filter_ranges_per_mode(self):
        cases = [("all", ("500", "600")), ("tcp", ("500", "12")),
                 ("udp", ("12", "600")), ("disabled", ("12", "12"))]
        for mode, expect in cases:
            with self.subTest(mode=mode), \
                 mock.patch.object(self.strat, "game_filter_status",
                                   return_value={"mode": mode, "tcp": "500", "udp": "600"}):
                self.assertEqual(self.strat._game_filter_ranges(), expect)

    def test_parse_strategy_no_winws_line(self):
        with open(os.path.join(self.d, "nows.bat"), "w", encoding="utf-8") as f:
            f.write("echo nothing here\n")
        with mock.patch.object(self.strat, "ORIG_DIR", self.d):
            args, err = self.strat.parse_strategy_args("nows")
        self.assertIsNone(args)
        self.assertTrue(err)  # strategy_no_winws

    def test_parse_strategy_unreadable_file(self):
        with mock.patch.object(self.strat, "ORIG_DIR", self.d), \
             mock.patch("builtins.open", side_effect=OSError("нет доступа")):
            args, err = self.strat.parse_strategy_args("general")
        self.assertIsNone(args)
        self.assertEqual(err, "нет доступа")

    def test_current_strategy_empty_and_missing(self):
        # B8: читаем %LOCALAPPDATA%\.strategy, при отсутствии — legacy рядом с приложением
        st = self.strat
        with open(self.sfile, "w", encoding="utf-8"):
            pass
        with mock.patch.object(st, "STRATEGY_FILE", self.sfile), \
             mock.patch.object(st, "LEGACY_STRATEGY_FILE", os.path.join(self.d, "gone")):
            self.assertEqual(st.current_strategy(), "")
        with mock.patch.object(st, "STRATEGY_FILE", os.path.join(self.d, "gone")), \
             mock.patch.object(st, "LEGACY_STRATEGY_FILE", os.path.join(self.d, "gone2")):
            self.assertIsNone(st.current_strategy())

    def test_current_strategy_falls_back_to_legacy(self):
        st = self.strat
        legacy = os.path.join(self.d, "legacy.strategy")
        with open(legacy, "w", encoding="utf-8") as f:
            f.write("legacy-bat")
        with mock.patch.object(st, "STRATEGY_FILE", os.path.join(self.d, "gone")), \
             mock.patch.object(st, "LEGACY_STRATEGY_FILE", legacy):
            self.assertEqual(st.current_strategy(), "legacy-bat")


class TestMiscGaps(unittest.TestCase):
    def test_is_admin_true_via_windll(self):
        from zapret_core import misc
        with mock.patch.object(misc, "ctypes") as ct:
            ct.windll.shell32.IsUserAnAdmin.return_value = 1
            self.assertTrue(misc.is_admin())

    def test_is_admin_handles_windll_error(self):
        from zapret_core import misc
        with mock.patch.object(misc, "ctypes") as ct:
            ct.windll.shell32.IsUserAnAdmin.side_effect = OSError("нет ctypes")
            self.assertFalse(misc.is_admin())

    def test_admin_use_ok_when_commands_present(self):
        from zapret_core import misc
        with mock.patch.object(misc, "is_admin", return_value=True), \
             mock.patch.object(misc, "load_user_lists") as lists_mock, \
             mock.patch("subprocess.run") as sr:
            sr.return_value = mock.Mock(returncode=0)
            r = misc.admin_use()
        self.assertTrue(r["ok"])
        lists_mock.assert_called_once()

    def test_admin_use_reports_missing_commands(self):
        from zapret_core import misc
        with mock.patch.object(misc, "is_admin", return_value=True), \
             mock.patch("subprocess.run") as sr:
            sr.return_value = mock.Mock(returncode=1)
            r = misc.admin_use()
        self.assertFalse(r["ok"])
        self.assertIn("Admin missing commands", r["service"])

    def test_clear_discord_kills_and_removes_cache(self):
        from zapret_core import misc
        td = tempfile.mkdtemp()
        try:
            cache = os.path.join(td, "Discord", "Cache")
            os.makedirs(cache)
            with mock.patch.dict(os.environ, {"APPDATA": td, "LOCALAPPDATA": td}), \
                 mock.patch("subprocess.run") as sr:
                sr.return_value = mock.Mock(returncode=0, stdout=b"", stderr=b"")
                r = misc.clear_discord()
            self.assertTrue(r["ok"])
            self.assertIn("Discord.exe", r["stdout"])   # taskkill успешен
            self.assertEqual(sr.call_count, 3)           # три процесса Discord
            self.assertFalse(os.path.isdir(cache))       # кэш удалён
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_hidden_cmd_success_and_failure(self):
        from zapret_core import misc
        ok = misc.hidden_cmd(["cmd", "/c", "echo", "hi"])
        self.assertTrue(ok["ok"])
        self.assertIn("hi", ok["stdout"])
        bad = misc.hidden_cmd(["definitely-missing-tool-xyz.exe"])
        self.assertFalse(bad["ok"])
        self.assertTrue(bad["stderr"])


class TestListsGaps(unittest.TestCase):
    class _Resp:
        def __init__(self, data):
            self._data = data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._data

    def test_ipset_update_downloads_with_backup(self):
        from zapret_core import lists as li
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "ipset-all.txt"), "w", encoding="utf-8") as f:
                f.write("9.9.9.9/32\n")
            data = b"1.2.3.4/32\n5.6.7.8/32\n"
            with mock.patch.object(li, "LISTS_DIR", d), \
                 mock.patch("urllib.request.urlopen", return_value=self._Resp(data)):
                r = li.ipset_update()
            self.assertTrue(r["ok"], r)
            with open(os.path.join(d, "ipset-all.txt"), "rb") as f:
                self.assertEqual(f.read(), data)
            self.assertTrue(os.path.isfile(os.path.join(d, "ipset-all.txt.bak")))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_ipset_update_empty_and_network_error(self):
        from zapret_core import lists as li
        d = tempfile.mkdtemp()
        try:
            with mock.patch.object(li, "LISTS_DIR", d), \
                 mock.patch("urllib.request.urlopen", return_value=self._Resp(b"  \n")):
                r = li.ipset_update()
            self.assertFalse(r["ok"])          # пустой ответ — не сохраняем
            with mock.patch.object(li, "LISTS_DIR", d), \
                 mock.patch("urllib.request.urlopen", side_effect=OSError("нет сети")):
                r = li.ipset_update()
            self.assertFalse(r["ok"])
            self.assertIn("нет сети", r["stderr"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_load_user_lists_creates_files(self):
        from zapret_core import lists as li
        base = tempfile.mkdtemp()
        d = os.path.join(base, "no-such-dir")
        try:
            with mock.patch.object(li, "LISTS_DIR", d):
                r = li.load_user_lists()
            self.assertTrue(r["ok"])
            for name in ("list-general-user.txt", "list-exclude-user.txt",
                         "ipset-exclude-user.txt"):
                self.assertTrue(os.path.isfile(os.path.join(d, name)), name)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_load_user_lists_makedirs_error(self):
        from zapret_core import lists as li
        base = tempfile.mkdtemp()
        try:
            with mock.patch.object(li, "LISTS_DIR", os.path.join(base, "nl")), \
                 mock.patch("os.makedirs", side_effect=OSError("нет прав")):
                r = li.load_user_lists()
            self.assertFalse(r["ok"])
            self.assertIn("нет прав", r["stderr"])
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_update_hosts_summary_and_missing(self):
        from zapret_core import lists as li
        td = tempfile.mkdtemp()
        empty = tempfile.mkdtemp()
        try:
            hosts = os.path.join(td, "System32", "drivers", "etc")
            os.makedirs(hosts)
            with open(os.path.join(hosts, "hosts"), "w", encoding="utf-8") as f:
                f.write("127.0.0.1 localhost\n0.0.0.0 youtube.com\n")
            with mock.patch.dict(os.environ, {"SystemRoot": td}):
                r = li.update_hosts()
            self.assertTrue(r["ok"])
            self.assertEqual(r["youtube_entries"], ["0.0.0.0 youtube.com"])
            with mock.patch.dict(os.environ, {"SystemRoot": empty}):
                r2 = li.update_hosts()
            self.assertFalse(r2["ok"])
            self.assertIn("hosts not found", r2["stderr"])
        finally:
            shutil.rmtree(td, ignore_errors=True)
            shutil.rmtree(empty, ignore_errors=True)

    def test_toggle_ipset_edges(self):
        from zapret_core import lists as li
        d = tempfile.mkdtemp()
        p = os.path.join(d, "ipset-all.txt")
        try:
            # loaded без бэкапа — честный отказ
            with open(p, "w", encoding="utf-8") as f:
                f.write("1.2.3.4/32\n")
            with mock.patch.object(li, "LISTS_DIR", d):
                r = li.toggle_ipset("loaded")
                self.assertFalse(r["ok"])
                # старый бэкап заменяется свежим при переходе в none (освободительная ветка)
                with open(p + ".backup", "w", encoding="utf-8") as f:
                    f.write("stale\n")
                r = li.toggle_ipset("none")
                self.assertTrue(r["ok"])
                with open(p + ".backup", encoding="utf-8") as f:
                    self.assertEqual(f.read(), "1.2.3.4/32\n")
            # OSError-ветка: не удалось создать каталог
            with mock.patch.object(li, "LISTS_DIR", os.path.join(d, "nl")), \
                 mock.patch("os.makedirs", side_effect=OSError("нет прав")):
                r = li.toggle_ipset("any")
            self.assertFalse(r["ok"])
            self.assertIn("нет прав", r["service"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestWinwsGaps(unittest.TestCase):
    def setUp(self):
        from zapret_core import winws as ww
        self.ww = ww
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _mk(self, name, data=b"\x01"):
        with open(os.path.join(self.d, name), "wb") as f:
            f.write(data)

    def test_replace_fakes_success_with_backup(self):
        self._mk("AAA_fake.bin", b"\xaa")
        self._mk("ACTIVE_DISCORD_UDP.bin", b"\x00")
        with mock.patch.object(self.ww, "BIN_DIR", self.d):
            r = self.ww.replace_fakes(1, 1)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["active"], "ACTIVE_DISCORD_UDP.bin")
        self.assertTrue(os.path.isfile(os.path.join(
            self.d, "ACTIVE_DISCORD_UDP.bin.bak")))           # откат сохранён
        with open(os.path.join(self.d, "ACTIVE_DISCORD_UDP.bin"), "rb") as f:
            self.assertEqual(f.read(), b"\xaa")                # источник скопирован

    def test_replace_fakes_input_validation(self):
        self._mk("AAA_fake.bin")
        with mock.patch.object(self.ww, "BIN_DIR", self.d):
            self.assertFalse(self.ww.replace_fakes()["ok"])        # нет выбора
            self.assertFalse(self.ww.replace_fakes(9, 1)["ok"])    # неизвестный тип
            self.assertFalse(self.ww.replace_fakes(1, "abc")["ok"])  # не число
            self.assertFalse(self.ww.replace_fakes(1, 42)["ok"])   # вне списка

    def test_replace_fakes_oserror(self):
        self._mk("AAA_fake.bin")
        with mock.patch.object(self.ww, "BIN_DIR", self.d), \
             mock.patch("shutil.copy2", side_effect=OSError("диск недоступен")):
            r = self.ww.replace_fakes(1, 1)
        self.assertFalse(r["ok"])
        self.assertIn("диск недоступен", r["stderr"])

    def test_winws_is_running_handles_tasklist_error(self):
        with mock.patch("subprocess.run", side_effect=OSError("нет tasklist")):
            self.assertFalse(self.ww.winws_is_running())

    def test_find_payload_source_from_versions(self):
        root = os.path.join(self.d, "AppWatch", "Versions", "zapretdiscord", "1103", "bin")
        os.makedirs(root)
        with open(os.path.join(root, "payload.bin"), "wb") as f:
            f.write(b"\x01")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.d,
                                          "ZAPRET_PAYLOADS_DIR": ""}):
            self.assertEqual(self.ww.find_payload_source(), root)

    def test_find_payload_source_none_when_nothing_found(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.d,
                                          "ZAPRET_PAYLOADS_DIR": ""}):
            self.assertIsNone(self.ww.find_payload_source())

    def test_restore_without_source(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.d,
                                          "ZAPRET_PAYLOADS_DIR": ""}):
            r = self.ww.restore_payloads(dest_dir=os.path.join(self.d, "dest"))
        self.assertFalse(r["ok"])   # источника нет

    def test_restore_copy_error(self):
        src = os.path.join(self.d, "src")
        dst = os.path.join(self.d, "dst")
        os.makedirs(src)
        with open(os.path.join(src, "x.bin"), "wb") as f:
            f.write(b"\x01")
        with mock.patch("shutil.copy2", side_effect=OSError("нет доступа")):
            r = self.ww.restore_payloads(dest_dir=dst, source_dir=src)
        self.assertFalse(r["ok"])
        self.assertIn("нет доступа", r["stderr"])

    def test_payloads_status_missing_dir(self):
        r = self.ww.payloads_status(os.path.join(self.d, "no-bin"))
        self.assertFalse(r["ok"])
        self.assertEqual(r["total"], 0)


class TestRunTestsGaps(unittest.TestCase):
    """run_tests: полный проход чтения вывода, итог из файла, таймаут, отказы."""

    class _Proc:
        def __init__(self, lines, pipe_ok=True):
            self.stdout = iter(lines)
            self.stdin = mock.Mock()
            if not pipe_ok:
                self.stdin.write.side_effect = BrokenPipeError("pipe закрыт")
            self.wait = mock.Mock(return_value=0)
            self.killed = False

        def kill(self):
            self.killed = True

        def poll(self):
            return -1 if self.killed else None

    class _SilentHangStdout:
        """Молча зависший процесс: ни строк, ни EOF — ровно то, что ловил B3."""
        def __iter__(self):
            return self

        def __next__(self):
            time.sleep(3600)  # блокировка читающего потока (daemon — не держит процесс)

    def setUp(self):
        from zapret_core import tests_runner as tr
        self.tr = tr
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _res_file(self, content, age=0.0):
        p = os.path.join(self.tmp, "test_results_x.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        if age:
            old = time.time() - age
            os.utime(p, (old, old))
        return p

    def test_popen_failure_reported(self):
        with mock.patch.object(self.tr, "tests_prerequisites", return_value=[]), \
             mock.patch("subprocess.Popen", side_effect=OSError("нет powershell")):
            r = self.tr.run_tests()
        self.assertFalse(r["ok"])
        self.assertIn("нет powershell", r["service"])

    def test_done_summary_with_best_strategy_tail(self):
        res = self._res_file("Best strategy: general.bat\n")
        proc = self._Proc(["[OK] all good"])
        with mock.patch.object(self.tr, "tests_prerequisites", return_value=[]), \
             mock.patch("subprocess.Popen", return_value=proc), \
             mock.patch.object(self.tr, "_latest_test_result", return_value=res):
            r = self.tr.run_tests()
        self.assertTrue(r["ok"])
        self.assertIn("Best strategy: general.bat", r["service"])
        self.assertEqual(r["results_file"], res)

    def test_error_line_marks_run_aborted(self):
        proc = self._Proc(["[OK] start", "[ERROR] broken config", "[OK] finish"])
        seen = []
        with mock.patch.object(self.tr, "tests_prerequisites", return_value=[]), \
             mock.patch("subprocess.Popen", return_value=proc), \
             mock.patch.object(self.tr, "_latest_test_result", return_value=None):
            r = self.tr.run_tests(on_line=seen.append, test_type=2, mode=2, selection=7)
        self.assertFalse(r["ok"])                      # [ERROR] -> aborted
        self.assertEqual(seen, ["[OK] start", "[ERROR] broken config", "[OK] finish"])
        # Ответы Read-Host: тип, режим, номер конфига
        self.assertEqual(proc.stdin.write.call_args[0][0], "2\n2\n7\n")

    def test_timeout_kills_process(self):
        proc = self._Proc(["line"])
        with mock.patch.object(self.tr, "tests_prerequisites", return_value=[]), \
             mock.patch("subprocess.Popen", return_value=proc), \
             mock.patch.object(self.tr, "_latest_test_result", return_value=None):
            r = self.tr.run_tests(timeout=0)
        self.assertTrue(proc.killed)
        import i18n
        self.assertIn(i18n.t("tests.timeout"), r["stdout"])

    def test_silent_hang_still_times_out(self):
        # B3: процесс молчит (нет строк, нет EOF) — таймаут обязан сработать,
        # а не зависнуть навсегда в блокирующем чтении stdout
        proc = mock.Mock()
        proc.stdout = self._SilentHangStdout()
        proc.stdin = mock.Mock()
        proc.wait = mock.Mock(return_value=0)
        proc.poll = mock.Mock(return_value=None)
        started = time.monotonic()
        with mock.patch.object(self.tr, "tests_prerequisites", return_value=[]), \
             mock.patch("subprocess.Popen", return_value=proc), \
             mock.patch.object(self.tr, "_latest_test_result", return_value=None):
            r = self.tr.run_tests(timeout=1)
        self.assertLess(time.monotonic() - started, 10)  # не виснет
        self.assertTrue(proc.killed)
        import i18n
        self.assertIn(i18n.t("tests.timeout"), r["stdout"])

    def test_should_stop_kills_and_reports(self):
        # B2: закрытие окна UI -> should_stop() -> процесс убит, итог «остановлен»
        proc = self._Proc(["line"])
        with mock.patch.object(self.tr, "tests_prerequisites", return_value=[]), \
             mock.patch("subprocess.Popen", return_value=proc), \
             mock.patch.object(self.tr, "_latest_test_result", return_value=None):
            r = self.tr.run_tests(should_stop=lambda: True)
        self.assertTrue(proc.killed)
        self.assertFalse(r["ok"])
        import i18n
        self.assertIn(i18n.t("tests.stopped"), r["stdout"])

    def test_broken_stdin_and_failing_on_line(self):
        proc = self._Proc(["x", "y"], pipe_ok=False)

        def bad_cb(line):
            raise RuntimeError("колбэк упал")

        with mock.patch.object(self.tr, "tests_prerequisites", return_value=[]), \
             mock.patch("subprocess.Popen", return_value=proc), \
             mock.patch.object(self.tr, "_latest_test_result", return_value=None):
            r = self.tr.run_tests(on_line=bad_cb)
        self.assertTrue(r["ok"])        # сломанный pipe и колбэк — не фатальны
        self.assertEqual(r["stdout"], ["x", "y"])

    def test_stale_results_file_gives_no_tail(self):
        res = self._res_file("Best strategy: general.bat\n", age=3600)
        proc = self._Proc(["[OK] finish"])
        with mock.patch.object(self.tr, "tests_prerequisites", return_value=[]), \
             mock.patch("subprocess.Popen", return_value=proc), \
             mock.patch.object(self.tr, "_latest_test_result", return_value=res):
            r = self.tr.run_tests()
        self.assertTrue(r["ok"])
        self.assertNotIn("Best strategy", r["service"])  # файл старше запуска — хвост пуст

    def test_prerequisites_curl_missing_service_present(self):
        import i18n
        with mock.patch.object(self.tr, "is_admin", return_value=True), \
             mock.patch("shutil.which", return_value=None), \
             mock.patch("win32serviceutil.QueryServiceStatus", return_value=object()), \
             mock.patch.object(self.tr, "ORIG_DIR", os.path.join(self.tmp, "no-orig")):
            probs = self.tr.tests_prerequisites()
        # Нет curl + служба установлена (её надо удалить!) + нет ps1-скрипта
        self.assertEqual(len(probs), 3)
        self.assertIn(i18n.t("tests.need_curl"), probs)
        self.assertIn(i18n.t("tests.service_installed"), probs)
        self.assertTrue(any("test zapret.ps1" in p for p in probs))

    def test_prerequisites_all_ok(self):
        orig = os.path.join(self.tmp, "orig")
        os.makedirs(os.path.join(orig, "utils"))
        with open(os.path.join(orig, "utils", "test zapret.ps1"), "w", encoding="utf-8"):
            pass
        with mock.patch.object(self.tr, "is_admin", return_value=True), \
             mock.patch("shutil.which", return_value="C:/Windows/System32/curl.exe"), \
             mock.patch("win32serviceutil.QueryServiceStatus",
                        side_effect=OSError("нет службы")), \
             mock.patch.object(self.tr, "ORIG_DIR", orig):
            self.assertEqual(self.tr.tests_prerequisites(), [])

    def test_latest_test_result_picks_newest_and_tolerates_error(self):
        orig = os.path.join(self.tmp, "orig")
        d = os.path.join(orig, "utils", "test results")
        os.makedirs(d)
        old_p = os.path.join(d, "test_results_old.txt")
        new_p = os.path.join(d, "test_results_new.txt")
        for p in (old_p, new_p):
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
        past = time.time() - 600
        os.utime(old_p, (past, past))
        with mock.patch.object(self.tr, "ORIG_DIR", orig):
            self.assertEqual(self.tr._latest_test_result(), new_p)
        with mock.patch.object(self.tr, "ORIG_DIR", os.path.join(self.tmp, "gone")):
            self.assertIsNone(self.tr._latest_test_result())   # каталога нет -> OSError

    def test_finally_survives_broken_streams(self):
        proc = self._Proc(["x"])
        proc.stdin.close.side_effect = OSError("закрыт")
        proc.wait.side_effect = OSError("wait упал")
        with mock.patch.object(self.tr, "tests_prerequisites", return_value=[]), \
             mock.patch("subprocess.Popen", return_value=proc), \
             mock.patch.object(self.tr, "_latest_test_result", return_value=None):
            r = self.tr.run_tests()
        self.assertTrue(proc.killed)   # wait упал -> kill в finally
        self.assertTrue(r["ok"])

    def test_results_file_unreadable_is_ignored(self):
        # _latest вернул каталог: getmtime проходит, open падает — хвост молча пуст
        proc = self._Proc(["[OK] x"])
        with mock.patch.object(self.tr, "tests_prerequisites", return_value=[]), \
             mock.patch("subprocess.Popen", return_value=proc), \
             mock.patch.object(self.tr, "_latest_test_result", return_value=self.tmp):
            r = self.tr.run_tests()
        self.assertTrue(r["ok"])
        self.assertNotIn("Best strategy", r["service"])

    def test_best_strategy_unreadable_file(self):
        with mock.patch.object(self.tr, "_latest_test_result",
                               return_value="C:/r/test_results_x.txt"), \
             mock.patch("builtins.open", side_effect=OSError("нет доступа")):
            r = self.tr.best_strategy()
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "нет доступа")


class TestRouterDispatch(unittest.TestCase):
    """Все действия маршрутизатора под патчами функций-мишеней (включая алиасы)."""

    DICT_FNS = ["game_filter_status", "load_user_lists", "run_diagnostics",
                "remove_conflicts", "run_tests", "payloads_status", "restore_payloads",
                "list_fakes", "check_updates", "ipset_update", "update_hosts",
                "clear_discord", "admin_use", "menu_status", "set_game_filter",
                "toggle_check_updates", "toggle_ipset", "apply_strategy",
                "best_strategy", "replace_fakes",
                "apply_zapret_update", "check_app_update", "update_app"]
    TUPLE_FNS = ["install_service", "uninstall_service", "start_service", "stop_service"]

    def _stack(self):
        from zapret_core import router
        st = contextlib.ExitStack()
        for fn in self.DICT_FNS:
            st.enter_context(mock.patch.object(router, fn, return_value={"ok": True}))
        for fn in self.TUPLE_FNS:
            st.enter_context(mock.patch.object(router, fn, return_value=(True, "msg")))
        st.enter_context(mock.patch.object(router, "query_status", return_value="Running"))
        st.enter_context(mock.patch.object(router, "winws_is_running", return_value=True))
        # relaunch_as_admin НИКОГДА не выполняем по-настоящему (реальный UAC)
        st.enter_context(mock.patch.object(router, "relaunch_as_admin", return_value=True))
        st.enter_context(mock.patch.object(router, "tests_prerequisites", return_value=[]))
        # service_install зовёт стратегии — под моками, без реального ORIG_DIR
        st.enter_context(mock.patch.object(router, "current_strategy", return_value="general"))
        st.enter_context(mock.patch.object(router, "default_strategy", return_value="general"))
        return st

    def test_every_action_returns_dict(self):
        from zapret_core import router
        actions = ["service_install", "service_remove", "service_status", "start", "stop",
                   "load_game_filter", "load_user_lists", "service_diagnostics", "diagnostics",
                   "remove_conflicts", "tests_prereq", "tests_precheck", "run_tests", "test",
                   "payloads_status", "restore_payloads", "status_zapret",
                   "replace_active_fakes", "list_fakes", "check_updates", "ipset_update",
                   "update_ipset", "8", "update_hosts", "hosts_update", "9", "clear_discord",
                   "admin", "admin_use", "menu_status", "set_game_filter",
                   "toggle_check_updates", "toggle_ipset", "apply_strategy", "relaunch_admin",
                   "best_strategy", "update_zapret", "check_app_update", "update_app"]
        with self._stack():
            for a in actions:
                with self.subTest(action=a):
                    r = router.run_service_action(a)
                    self.assertIsInstance(r, dict)
            # дефолтный аргумент — status_zapret
            r = router.run_service_action()
            self.assertTrue(r["ok"])

    def test_tests_prereq_branches(self):
        from zapret_core import router
        with mock.patch.object(router, "tests_prerequisites", return_value=[]):
            r = router.run_service_action("tests_prereq")
            self.assertTrue(r["ok"])
        with mock.patch.object(router, "tests_prerequisites", return_value=["no admin"]):
            r = router.run_service_action("tests_precheck")
            self.assertFalse(r["ok"])
            self.assertIn("no admin", r["service"])

    def test_kwargs_passthrough(self):
        from zapret_core import router
        with mock.patch.object(router, "apply_strategy") as apply_m, \
             mock.patch.object(router, "set_game_filter") as gf_m, \
             mock.patch.object(router, "toggle_check_updates") as tc_m, \
             mock.patch.object(router, "toggle_ipset") as ti_m, \
             mock.patch.object(router, "replace_fakes") as rf_m, \
             mock.patch.object(router, "restore_payloads") as rp_m, \
             mock.patch.object(router, "run_tests") as rt_m:
            router.run_service_action("apply_strategy", strategy="general")
            apply_m.assert_called_with("general")
            router.run_service_action("apply_strategy", "from-arg")  # через arg
            apply_m.assert_called_with("from-arg")
            router.run_service_action("set_game_filter", mode="tcp", tcp="10-20", udp="30-40")
            gf_m.assert_called_with("tcp", "10-20", "30-40")
            router.run_service_action("toggle_check_updates", enable=True)
            tc_m.assert_called_with(True)
            router.run_service_action("toggle_ipset", mode="loaded")
            ti_m.assert_called_with("loaded")
            router.run_service_action("replace_active_fakes", fake_type=2, number=3)
            rf_m.assert_called_with(fake_type=2, number=3)
            router.run_service_action("restore_payloads", source_dir="S")
            rp_m.assert_called_with(source_dir="S")
            router.run_service_action("run_tests", test_type=2, mode=2, selection=5)
            kwargs = rt_m.call_args.kwargs
            self.assertEqual(kwargs["test_type"], 2)
            self.assertEqual(kwargs["mode"], 2)
            self.assertEqual(kwargs["selection"], 5)

    def test_status_zapret_composes_string(self):
        from zapret_core import router
        with mock.patch.object(router, "winws_is_running", return_value=True), \
             mock.patch.object(router, "query_status", return_value="Running"):
            r = router.run_service_action("status_zapret")
        self.assertTrue(r["ok"])
        self.assertIn("winws.exe running=True", r["service"])
        self.assertIn("service=Running", r["service"])

    def test_service_install_uses_apply_strategy(self):
        # B5: «Установить службу» = apply_strategy(текущая/дефолтная, restart=True) —
        # паритет с :service_install (stop -> create winws.exe+ARGS -> start)
        from zapret_core import router
        with mock.patch.object(router, "current_strategy", return_value="prev"), \
             mock.patch.object(router, "apply_strategy", return_value={"ok": True}) as am:
            r = router.run_service_action("service_install")
        self.assertTrue(r["ok"])
        am.assert_called_once_with("prev", restart=True)

    def test_service_install_falls_back_to_default_strategy(self):
        from zapret_core import router
        with mock.patch.object(router, "current_strategy", return_value=None), \
             mock.patch.object(router, "default_strategy", return_value="general"), \
             mock.patch.object(router, "apply_strategy", return_value={"ok": True}) as am:
            r = router.run_service_action("service_install")
        self.assertTrue(r["ok"])
        am.assert_called_once_with("general", restart=True)

    def test_service_install_without_strategies_refuses(self):
        from zapret_core import router
        with mock.patch.object(router, "current_strategy", return_value=None), \
             mock.patch.object(router, "default_strategy", return_value=None), \
             mock.patch.object(router, "apply_strategy") as am:
            r = router.run_service_action("service_install")
        self.assertFalse(r["ok"])
        am.assert_not_called()

    def test_relaunch_admin_never_runs_real_uac(self):
        from zapret_core import router
        with mock.patch.object(router, "relaunch_as_admin", return_value=True) as m:
            r = router.run_service_action("relaunch_admin")
            m.assert_called_once()
        self.assertTrue(r["ok"])
        with mock.patch.object(router, "relaunch_as_admin", return_value=False):
            r = router.run_service_action("relaunch_admin")
        self.assertFalse(r["ok"])

    def test_unknown_action(self):
        from zapret_core import router
        r = router.run_service_action("no-such-action")
        self.assertFalse(r["ok"])
        self.assertIn("Unknown action", r["service"])


class TestI18nEdges(unittest.TestCase):
    def test_save_swallows_oserror(self):
        import i18n
        old_lang = i18n.LANG
        td = tempfile.mkdtemp()
        try:
            blocker = os.path.join(td, "as-file")
            with open(blocker, "w", encoding="utf-8") as f:
                f.write("x")
            # makedirs упадёт NotADirectoryError (подкласс OSError) — save не должен бросить
            with mock.patch.object(i18n, "_SETTINGS_DIR", os.path.join(blocker, "sub")):
                i18n.save("en")
            self.assertEqual(i18n.LANG, "en")   # язык всё равно переключился
        finally:
            i18n.LANG = old_lang
            shutil.rmtree(td, ignore_errors=True)

    def test_t_returns_unformatted_on_wrong_placeholder(self):
        import i18n
        out = i18n.t("ui.out_saved", wrong="x")   # нет ключа {p} -> KeyError -> сырой текст
        self.assertIn("{p}", out)


class TestAppLogGaps(unittest.TestCase):
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

    def test_log_path(self):
        self.assertEqual(self.applog.log_path(), self.applog.LOG_FILE)

    def test_thread_exception_goes_to_log(self):
        old_sys, old_thr = sys.excepthook, threading.excepthook
        try:
            self.applog.install_excepthook()

            def boom():
                raise RuntimeError("thread-boom")

            th = threading.Thread(target=boom)
            th.start()
            th.join(5)
            data = self._read()
            self.assertIn("thread-boom", data)
            self.assertIn("(thread", data)
        finally:
            sys.excepthook = old_sys
            threading.excepthook = old_thr

    def test_handle_calls_console_excepthook_when_not_frozen(self):
        with mock.patch.object(self.applog, "_show_dialog"), \
             mock.patch.object(sys, "__excepthook__") as defhook:
            self.applog._handle(ValueError, ValueError("boom"), None)
        defhook.assert_called_once()
        self.assertIn("boom", self._read())

    @unittest.skipUnless(HAS_PYSIDE, "PySide6 не установлен")
    def test_show_dialog_builds_messagebox_without_exec_block(self):
        # QApplication/QMessageBox подменяются целиком — модальный exec() не блокирует тест
        with mock.patch("PySide6.QtWidgets.QApplication") as app_cls, \
             mock.patch("PySide6.QtWidgets.QMessageBox") as box_cls:
            app_cls.instance.return_value = mock.Mock()   # Qt уже «жив»
            self.applog._show_dialog(ValueError, ValueError("dlg"), "tb-text")
        box_cls.assert_called_once()
        box_cls.return_value.exec.assert_called_once()


class TestDiagnosticsConflicts(unittest.TestCase):
    def test_remove_conflicts_removes_conflicting_services(self):
        from zapret_core import diagnostics as dg
        with mock.patch.object(dg, "is_admin", return_value=True), \
             mock.patch.object(dg, "tcp_timestamps", return_value=(True, "")), \
             mock.patch.object(dg, "_sc_service_names",
                               return_value=["WinDivert", "zapret"]), \
             mock.patch("subprocess.run") as sr:
            sr.return_value = mock.Mock(returncode=0, stdout="")
            r = dg.remove_conflicts()
        self.assertTrue(r["ok"])
        cmds = [" ".join(c.args[0]) for c in sr.call_args_list]
        self.assertTrue(any(c == "net stop WinDivert" for c in cmds), cmds)
        self.assertTrue(any(c == "sc delete WinDivert" for c in cmds), cmds)
        self.assertTrue(any("Removed service" in a for a in r["actions"]))
        # zapret не входит в список конфликтов — его не трогаем
        self.assertFalse(any("zapret" in c for c in cmds))

    def test_remove_conflicts_timestamps_failed(self):
        from zapret_core import diagnostics as dg
        with mock.patch.object(dg, "is_admin", return_value=True), \
             mock.patch.object(dg, "tcp_timestamps", return_value=(False, "reg err")), \
             mock.patch.object(dg, "_sc_service_names", return_value=[]), \
             mock.patch("subprocess.run"):
            r = dg.remove_conflicts()
        self.assertFalse(r["ok"])       # неудача timestamps бьёт по общему ok

    def test_remove_conflicts_no_targets_message(self):
        import i18n
        from zapret_core import diagnostics as dg
        with mock.patch.object(dg, "is_admin", return_value=True), \
             mock.patch.object(dg, "tcp_timestamps", return_value=(True, "")), \
             mock.patch.object(dg, "_sc_service_names", return_value=["zapret"]), \
             mock.patch("subprocess.run") as sr:
            r = dg.remove_conflicts()
        self.assertTrue(r["ok"])
        self.assertFalse(sr.called)     # удалять нечего — subprocess не вызывается
        self.assertIn(i18n.t("sm.no_conflicts"), r["service"])

    def test_remove_conflicts_delete_failed(self):
        from zapret_core import diagnostics as dg
        with mock.patch.object(dg, "is_admin", return_value=True), \
             mock.patch.object(dg, "tcp_timestamps", return_value=(True, "")), \
             mock.patch.object(dg, "_sc_service_names", return_value=["GoodbyeDPI"]), \
             mock.patch("subprocess.run") as sr:
            sr.return_value = mock.Mock(returncode=1, stdout="")
            r = dg.remove_conflicts()
        self.assertFalse(r["ok"])
        self.assertTrue(any("[X] Failed to remove" in a for a in r["actions"]),
                        r["actions"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
