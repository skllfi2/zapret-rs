# tests/test_updates.py — обновления: проверка версий zapret/приложения,
# применение релиза zapret (бэкап/распаковка/пере-применение) и самообновление
# приложения. СЕТЬ И ФАЙЛЫ — ТОЛЬКО ПОД МОКАМИ, реальных UAC/служб/загрузок нет.
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock as mock
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_zip(path: str, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)


class TestCheckUpdates(unittest.TestCase):
    """check_updates: локальная версия из service.bat vs GitHub."""

    def setUp(self):
        from zapret_core import updates as upd
        self.upd = upd
        self.tmp = tempfile.mkdtemp(prefix="zs-upd-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._orig = upd.ORIG_DIR
        upd.ORIG_DIR = self.tmp
        self.addCleanup(setattr, upd, "ORIG_DIR", self._orig)
        # включённый тумблер проверки (по умолчанию его отсутствие = отключено)
        os.makedirs(os.path.join(self.tmp, "utils"), exist_ok=True)
        open(os.path.join(self.tmp, "utils", "check_updates.enabled"), "w").close()

    def _write_service_bat(self, version="1.10.0"):
        with open(os.path.join(self.tmp, "service.bat"), "w", encoding="utf-8") as f:
            f.write(f'@echo off\r\nset "LOCAL_VERSION={version}"\r\n')

    def test_disabled_when_flag_missing(self):
        os.remove(os.path.join(self.tmp, "utils", "check_updates.enabled"))
        r = self.upd.check_updates()
        self.assertTrue(r["ok"])
        self.assertFalse(r["enabled"])
        self.assertIn("отключена", r["stdout"])

    def test_local_version_unreadable(self):
        r = self.upd.check_updates()
        self.assertFalse(r["ok"])
        self.assertIn("LOCAL_VERSION", r["stderr"])

    def test_network_error_is_not_fatal(self):
        self._write_service_bat()
        with mock.patch.object(self.upd, "_github_latest",
                               side_effect=OSError("net down")):
            r = self.upd.check_updates()
        self.assertTrue(r["ok"])           # не смогли проверить — не ошибка zapret
        self.assertEqual(r["local"], "1.10.0")
        self.assertIsNone(r["remote"])

    def test_up_to_date_and_new_version(self):
        self._write_service_bat("1.10.4")
        with mock.patch.object(self.upd, "_github_latest",
                               return_value={"tag_name": "1.10.4"}):
            r = self.upd.check_updates()
        self.assertTrue(r["ok"])
        self.assertFalse(r["update_available"])

        with mock.patch.object(self.upd, "_github_latest",
                               return_value={"tag_name": "1.11.0"}):
            r = self.upd.check_updates()
        self.assertTrue(r["update_available"])
        self.assertEqual(r["remote"], "1.11.0")
        self.assertIn("1.11.0", r["stdout"])

    def test_local_version_malformed_file(self):
        with open(os.path.join(self.tmp, "service.bat"), "w", encoding="utf-8") as f:
            f.write("@echo off\r\nno version here\r\n")
        r = self.upd.check_updates()
        self.assertFalse(r["ok"])


class TestGithubHelpers(unittest.TestCase):
    """_github_latest / _download поверх urllib — только мок-ответы."""

    def test_github_latest_success(self):
        from zapret_core import updates as upd
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = json.dumps(
            {"tag_name": "1.10.4", "assets": []}).encode()
        with mock.patch("zapret_core.updates.urllib.request.urlopen",
                        return_value=resp):
            d = upd._github_latest("owner/repo")
        self.assertEqual(d["tag_name"], "1.10.4")

    def test_github_latest_network_error_raises(self):
        from zapret_core import updates as upd
        with mock.patch("zapret_core.updates.urllib.request.urlopen",
                        side_effect=OSError("no net")):
            with self.assertRaises(OSError):
                upd._github_latest("owner/repo")

    def test_download_writes_bytes(self):
        from zapret_core import updates as upd

        class _Resp:
            def __init__(self):
                self._data = b"payload-bytes"

            def read(self, n=-1):
                out, self._data = self._data[:n] if n > 0 else self._data, b""
                return out

        resp = mock.MagicMock()
        resp.__enter__.return_value = _Resp()
        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "f.bin")
            with mock.patch("zapret_core.updates.urllib.request.urlopen",
                            return_value=resp):
                upd._download("http://x/f.bin", dest)
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), b"payload-bytes")


class TestApplyZapretUpdate(unittest.TestCase):
    """apply_zapret_update: бэкап -> остановка службы -> замена -> пере-применение."""

    def setUp(self):
        from zapret_core import updates as upd
        self.upd = upd
        self.tmp = tempfile.mkdtemp(prefix="zs-apply-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.orig = os.path.join(self.tmp, "orig")
        self.strat = os.path.join(self.tmp, "strat")
        os.makedirs(os.path.join(self.orig, "bin"))
        with open(os.path.join(self.orig, "service.bat"), "w", encoding="utf-8") as f:
            f.write('set "LOCAL_VERSION=1.10.0"')
        with open(os.path.join(self.orig, "bin", "winws.exe"), "wb") as f:
            f.write(b"OLD")
        for attr, val in (("ORIG_DIR", self.orig), ("STRATEGY_DIR", self.strat)):
            self._patch_attr(attr, val)

    def _patch_attr(self, attr, val):
        old = getattr(self.upd, attr)
        setattr(self.upd, attr, val)
        self.addCleanup(setattr, self.upd, attr, old)

    def _patch(self, target, **kw):
        p = mock.patch(target, **kw)
        self.addCleanup(p.stop)
        return p.start()

    def _release(self, tag="1.10.4"):
        return {"tag_name": tag,
                "assets": [{"name": f"zapret-discord-youtube-{tag}.zip",
                            "browser_download_url": "http://x/z.zip"}]}

    def _download_side_effect(self, members):
        def _dl(url, dest):
            _make_zip(dest, members)
        return _dl

    def _base_patches(self, members=None, running=False, apply_ok=True):
        members = members or {"z-1.10.4/bin/winws.exe": b"NEW",
                              "z-1.10.4/winws.bat": b"@echo new"}
        self._patch("zapret_core.updates._github_latest",
                    return_value=self._release())
        self._patch("zapret_core.updates._download",
                    side_effect=self._download_side_effect(members))
        self._patch("zapret_core.misc.is_admin", return_value=True)
        self._patch("zapret_core.scm.query_status",
                    return_value="Running" if running else "Stopped")
        self.stop_m = self._patch("zapret_core.scm.stop_service")
        self.apply_m = self._patch(
            "zapret_core.strategies.apply_strategy",
            return_value={"ok": apply_ok, "service": "ok" if apply_ok else "err"})
        self._patch("zapret_core.strategies.current_strategy", return_value="general")
        self._patch("zapret_core.strategies.default_strategy", return_value="general")

    def test_requires_admin(self):
        self._patch("zapret_core.misc.is_admin", return_value=False)
        r = self.upd.apply_zapret_update()
        self.assertFalse(r["ok"])
        self.assertIn("администратор", r["stderr"])

    def test_github_failure(self):
        self._patch("zapret_core.misc.is_admin", return_value=True)
        self._patch("zapret_core.updates._github_latest", side_effect=OSError("net"))
        r = self.upd.apply_zapret_update()
        self.assertFalse(r["ok"])

    def test_no_zip_asset(self):
        self._patch("zapret_core.misc.is_admin", return_value=True)
        self._patch("zapret_core.updates._github_latest",
                    return_value={"tag_name": "1.10.4", "assets": []})
        r = self.upd.apply_zapret_update()
        self.assertFalse(r["ok"])
        self.assertIn("zip", r["stderr"])

    def test_bad_archive_rejected(self):
        self._base_patches(members={"readme.txt": b"not a zapret copy"})
        r = self.upd.apply_zapret_update()
        self.assertFalse(r["ok"])
        self.assertIn("winws.exe", r["stderr"])
        # ничего не перезаписано
        with open(os.path.join(self.orig, "bin", "winws.exe"), "rb") as f:
            self.assertEqual(f.read(), b"OLD")

    def test_success_replaces_files_backups_and_reapplies(self):
        self._base_patches(running=True)
        lines: list[str] = []
        r = self.upd.apply_zapret_update(on_line=lines.append)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["version"], "1.10.4")
        with open(os.path.join(self.orig, "bin", "winws.exe"), "rb") as f:
            self.assertEqual(f.read(), b"NEW")
        with open(os.path.join(self.orig, "winws.bat"), "rb") as f:
            self.assertEqual(f.read(), b"@echo new")
        # бэкап старой копии лежит в STRATEGY_DIR/backups
        backups = os.listdir(os.path.join(self.strat, "backups"))
        self.assertTrue(any(b.startswith("zapret-1.10.0") for b in backups), backups)
        # работающая служба остановлена перед заменой, стратегия пере-применена
        self.stop_m.assert_called_once()
        self.apply_m.assert_called_once_with("general", restart=True)
        self.assertTrue(lines, "on_line не получал прогресс")

    def test_stopped_service_not_stopped_again(self):
        self._base_patches(running=False)
        r = self.upd.apply_zapret_update()
        self.assertTrue(r["ok"])
        self.stop_m.assert_not_called()

    def test_reapply_failure_reports_updated_but_degraded(self):
        self._base_patches(apply_ok=False)
        r = self.upd.apply_zapret_update()
        self.assertTrue(r["ok"])            # файлы обновлены
        self.assertTrue(r["stderr"])        # но стратегия не применилась
        with open(os.path.join(self.orig, "bin", "winws.exe"), "rb") as f:
            self.assertEqual(f.read(), b"NEW")

    def test_download_exception_reports_failure(self):
        self._base_patches()
        self._patch("zapret_core.updates._download",
                    side_effect=OSError("disk full"))
        r = self.upd.apply_zapret_update()
        self.assertFalse(r["ok"])
        self.assertIn("disk full", r["stderr"])

    def test_on_line_exception_does_not_break_update(self):
        self._base_patches()
        def _bad_line(_msg):
            raise RuntimeError("viewer crashed")
        r = self.upd.apply_zapret_update(on_line=_bad_line)
        self.assertTrue(r["ok"], r)


class TestCheckAppUpdate(unittest.TestCase):
    """check_app_update: soft-degrade без репозитория и ветки GitHub."""

    def setUp(self):
        from zapret_core import selfupdate as su
        self.su = su

    def _patch_repo(self, repo):
        p = mock.patch.object(self.su, "SELF_UPDATE_REPO", repo)
        p.start()
        self.addCleanup(p.stop)

    def test_unconfigured(self):
        self._patch_repo("")
        r = self.su.check_app_update()
        self.assertTrue(r["ok"])
        self.assertFalse(r["configured"])
        self.assertFalse(r["update_available"])
        self.assertIn("не настроен", r["stdout"])

    def test_network_error_soft(self):
        self._patch_repo("owner/repo")
        with mock.patch.object(self.su, "_github_latest", side_effect=OSError):
            r = self.su.check_app_update()
        self.assertTrue(r["ok"])
        self.assertTrue(r["configured"])
        self.assertIsNone(r["remote"])

    def test_new_version_with_v_prefix(self):
        self._patch_repo("owner/repo")
        with mock.patch.object(self.su, "_github_latest",
                               return_value={"tag_name": "v0.5.0"}):
            r = self.su.check_app_update()
        self.assertTrue(r["update_available"])
        self.assertEqual(r["remote"], "0.5.0")

    def test_up_to_date(self):
        self._patch_repo("owner/repo")
        with mock.patch.object(self.su, "_github_latest",
                               return_value={"tag_name": self.su.APP_VERSION}):
            r = self.su.check_app_update()
        self.assertFalse(r["update_available"])


class TestUpdateApp(unittest.TestCase):
    """update_app: source-режим (zip поверх) и frozen-exe (staging + helper)."""

    def setUp(self):
        from zapret_core import selfupdate as su
        self.su = su

    def _patch(self, target, *args, **kw):
        p = mock.patch(target, *args, **kw)
        self.addCleanup(p.stop)
        return p.start()

    def _patch_object(self, obj, attr, value, create=False):
        p = mock.patch.object(obj, attr, value, create=create)
        self.addCleanup(p.stop)
        return p.start()

    def _patch_repo(self, repo="owner/repo"):
        self._patch("zapret_core.selfupdate.SELF_UPDATE_REPO", repo)

    def test_unconfigured(self):
        self._patch_repo("")
        r = self.su.update_app()
        self.assertFalse(r["ok"])

    def test_github_failure(self):
        self._patch_repo()
        self._patch("zapret_core.selfupdate._github_latest", side_effect=OSError)
        r = self.su.update_app()
        self.assertFalse(r["ok"])

    def test_frozen_without_exe_asset(self):
        self._patch_repo()
        self._patch("zapret_core.selfupdate._github_latest",
                    return_value={"assets": [{"name": "src.zip",
                                              "browser_download_url": "http://x"}]})
        self._patch_object(sys, "frozen", True, create=True)
        r = self.su.update_app()
        self.assertFalse(r["ok"])
        self.assertIn("zapret-simple.exe", r["stderr"])

    def test_frozen_success_stages_outside_tmp(self):
        self._patch_repo()
        self._patch("zapret_core.selfupdate._github_latest",
                    return_value={"assets": [
                        {"name": self.su.APP_EXE_NAME,
                         "browser_download_url": "http://x/e.exe"}]})
        self._patch_object(sys, "frozen", True, create=True)
        dl = self._patch("zapret_core.selfupdate._download")
        spawn = self._patch("zapret_core.selfupdate._spawn_replace_helper")
        r = self.su.update_app()
        self.assertTrue(r["ok"])
        self.assertTrue(r["restart"])
        # helper получает staging-файл, а не путь внутри уже удалённого tmp
        staged, cur = spawn.call_args.args
        self.assertFalse(os.path.basename(os.path.dirname(staged)).startswith(
            "zapret-simple-upd-"))
        self.assertEqual(staged, dl.call_args.args[1])

    def test_source_zip_overwrites_app_dir(self):
        self._patch_repo()
        self._patch("zapret_core.selfupdate._github_latest",
                    return_value={"assets": [
                        {"name": "zapret-simple-0.5.0.zip",
                         "browser_download_url": "http://x/z.zip"}]})

        def _dl(url, dest):
            _make_zip(dest, {"zapret-simple-0.5.0/zapret_pyside.py": b"# new ui",
                             "zapret-simple-0.5.0/i18n.py": b"# new i18n"})

        self._patch("zapret_core.selfupdate._download", side_effect=_dl)
        tmp_app = tempfile.mkdtemp(prefix="zs-app-")
        self.addCleanup(shutil.rmtree, tmp_app, True)
        self._patch("zapret_core.selfupdate.APP_DIR", tmp_app)
        lines: list[str] = []
        r = self.su.update_app(on_line=lines.append)
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["restart"])
        with open(os.path.join(tmp_app, "zapret_pyside.py"), "rb") as f:
            self.assertEqual(f.read(), b"# new ui")
        self.assertTrue(lines)

    def test_source_without_zip_asset(self):
        self._patch_repo()
        self._patch("zapret_core.selfupdate._github_latest",
                    return_value={"assets": [{"name": "only.exe",
                                              "browser_download_url": "http://x"}]})
        r = self.su.update_app()
        self.assertFalse(r["ok"])

    def test_source_bad_archive(self):
        self._patch_repo()
        self._patch("zapret_core.selfupdate._github_latest",
                    return_value={"assets": [
                        {"name": "z.zip", "browser_download_url": "http://x/z.zip"}]})

        def _dl(url, dest):
            _make_zip(dest, {"somewhere/readme.txt": b"nope"})

        self._patch("zapret_core.selfupdate._download", side_effect=_dl)
        r = self.su.update_app()
        self.assertFalse(r["ok"])
        self.assertIn("zapret_pyside.py", r["stderr"])

    def test_download_exception_reports_failure(self):
        self._patch_repo()
        self._patch("zapret_core.selfupdate._github_latest",
                    return_value={"assets": [
                        {"name": "z.zip", "browser_download_url": "http://x/z.zip"}]})
        self._patch("zapret_core.selfupdate._download", side_effect=OSError("nope"))
        r = self.su.update_app()
        self.assertFalse(r["ok"])
        self.assertIn("nope", r["stderr"])


class TestSelfupdateHelpers(unittest.TestCase):
    """_find_app_root и _spawn_replace_helper."""

    def test_find_app_root_at_various_depths(self):
        from zapret_core import selfupdate as su
        with tempfile.TemporaryDirectory() as td:
            # уровень 0: файл прямо в корне распаковки
            open(os.path.join(td, "zapret_pyside.py"), "w").close()
            self.assertEqual(su._find_app_root(td), td)
            # уровень 1: owner-repo-tag/zapret_pyside.py (нормальный GitHub zip)
            sub = os.path.join(td, "x", "repo-1.0")
            os.makedirs(sub)
            open(os.path.join(sub, "zapret_pyside.py"), "w").close()
            self.assertEqual(su._find_app_root(os.path.join(td, "x")), sub)
            # глубже 2 уровней — не ищем (чужая структура архива)
            deep = os.path.join(td, "y", "a", "b", "c")
            os.makedirs(deep)
            open(os.path.join(deep, "zapret_pyside.py"), "w").close()
            self.assertIsNone(su._find_app_root(os.path.join(td, "y")))

    def test_spawn_replace_helper_writes_bat_and_starts(self):
        from zapret_core import selfupdate as su
        with tempfile.TemporaryDirectory() as td:
            staged = os.path.join(td, "zapret-simple.exe.new")
            open(staged, "w").close()
            cur = os.path.join(td, "zapret-simple.exe")
            with mock.patch("zapret_core.selfupdate.subprocess.Popen") as popen, \
                 mock.patch("zapret_core.selfupdate.tempfile.gettempdir",
                            return_value=td):
                su._spawn_replace_helper(staged, cur)
            popen.assert_called_once()
            helper = os.path.join(td, "zapret-simple-selfupd.bat")
            self.assertTrue(os.path.isfile(helper))
            with open(helper, encoding="utf-8") as f:
                content = f.read()
            self.assertIn(staged, content)      # копирует staging-файл
            self.assertIn(cur, content)         # в наш exe
            self.assertIn(str(os.getpid()), content)  # ждёт смерти нашего PID
            self.assertIn("copy /y", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
