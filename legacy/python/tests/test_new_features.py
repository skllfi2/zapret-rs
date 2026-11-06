# test_new_features.py — тесты автозагрузки, выбора папки, распаковки ZIP, DoH, звуков и диалогов
import os
import tempfile
import unittest
import zipfile
from unittest import mock

import service_manager


class TestNewFeatures(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_dir = service_manager.ORIG_DIR

    def tearDown(self) -> None:
        service_manager.reload_paths(self._orig_dir)

    def test_autostart_flow(self) -> None:
        with mock.patch("winreg.OpenKey"), \
             mock.patch("winreg.QueryValueEx", return_value=("test.exe", 1)), \
             mock.patch("winreg.SetValueEx") as set_val, \
             mock.patch("winreg.DeleteValue") as del_val:
            self.assertTrue(service_manager.is_autostart_enabled())
            ok, msg = service_manager.set_autostart_enabled(True)
            self.assertTrue(ok)
            set_val.assert_called_once()

            ok, msg = service_manager.set_autostart_enabled(False)
            self.assertTrue(ok)
            del_val.assert_called_once()

    def test_autostart_toggle_and_cmd(self) -> None:
        from zapret_core.autostart import _get_exec_command, toggle_autostart
        with mock.patch("zapret_core.autostart.is_autostart_enabled", side_effect=[False, True]), \
             mock.patch("zapret_core.autostart.set_autostart_enabled") as m_set:
            new_st = toggle_autostart()
            self.assertTrue(new_st)
            m_set.assert_called_with(True)

        cmd = _get_exec_command()
        self.assertIn("--minimized", cmd)

    def test_custom_zapret_dir_validation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # Without bin/winws.exe -> False
            ok, msg = service_manager.set_custom_zapret_dir(td)
            self.assertFalse(ok)

            # Non-existent dir -> False
            ok, msg = service_manager.set_custom_zapret_dir(os.path.join(td, "non_existent"))
            self.assertFalse(ok)

            # With bin/winws.exe -> True
            bin_dir = os.path.join(td, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            with open(os.path.join(bin_dir, "winws.exe"), "wb") as f:
                f.write(b"dummy")

            ok, msg = service_manager.set_custom_zapret_dir(td)
            self.assertTrue(ok)
            self.assertEqual(service_manager.ORIG_DIR, os.path.abspath(td))

    def test_unpack_zapret_archive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            zip_path = os.path.join(td, "zapret.zip")
            with zipfile.ZipFile(zip_path, "w") as z:
                z.writestr("zapret-dist/bin/winws.exe", b"dummy_winws")
                z.writestr("zapret-dist/service.bat", b"@echo off")

            target = os.path.join(td, "extracted")
            ok, msg = service_manager.unpack_zapret_archive(zip_path, target)
            self.assertTrue(ok)
            self.assertTrue(os.path.isfile(os.path.join(target, "bin", "winws.exe")))
            self.assertTrue(os.path.isfile(os.path.join(target, "service.bat")))

    def test_unpack_archive_edge_cases(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # 1. Non-existent file
            ok, msg = service_manager.unpack_zapret_archive(os.path.join(td, "missing.zip"))
            self.assertFalse(ok)

            # 2. Not a valid zip
            bad_zip = os.path.join(td, "bad.zip")
            with open(bad_zip, "w") as f:
                f.write("not a zip")
            ok, msg = service_manager.unpack_zapret_archive(bad_zip)
            self.assertFalse(ok)

            # 3. Zip without bin/winws.exe
            no_winws = os.path.join(td, "no_winws.zip")
            with zipfile.ZipFile(no_winws, "w") as z:
                z.writestr("something.txt", b"hello")
            ok, msg = service_manager.unpack_zapret_archive(no_winws)
            self.assertFalse(ok)
            self.assertIn("winws.exe", msg)

    def test_sound_module(self) -> None:
        from zapret_core.sound import is_sound_enabled, play_sound, set_sound_enabled, toggle_sound
        with tempfile.TemporaryDirectory() as td:
            s_file = os.path.join(td, "ui_settings.json")
            with mock.patch("zapret_core.sound.SETTINGS_FILE", s_file), \
                 mock.patch("zapret_core.sound.SETTINGS_DIR", td):
                self.assertTrue(is_sound_enabled())
                self.assertTrue(set_sound_enabled(False))
                self.assertFalse(is_sound_enabled())
                new_val = toggle_sound()
                self.assertTrue(new_val)
                self.assertTrue(is_sound_enabled())

        with mock.patch("zapret_core.sound.is_sound_enabled", return_value=False):
            self.assertFalse(play_sound("connect"))

        with mock.patch("zapret_core.sound.is_sound_enabled", return_value=True), \
             mock.patch("winsound.PlaySound") as m_play:
            self.assertTrue(play_sound("connect"))
            m_play.assert_called_once()

        self.assertFalse(play_sound("non_existent_event_sound_xyz"))

    def test_doh_module(self) -> None:
        from zapret_core.doh import disable_doh, get_doh_status, set_doh
        with mock.patch("zapret_core.doh._get_active_adapter_names", return_value=["Ethernet"]), \
             mock.patch("zapret_core.doh._run_cmd", return_value=(True, "1.1.1.1, 1.0.0.1")), \
             mock.patch("winreg.OpenKey"), \
             mock.patch("winreg.QueryValueEx", return_value=(2, 4)):
            stat = get_doh_status()
            self.assertTrue(stat["ok"])
            self.assertEqual(stat["provider"], "cloudflare")
            self.assertTrue(stat["autodoh"])

        # set_doh non-admin
        with mock.patch("zapret_core.doh.is_admin", return_value=False):
            r = set_doh("cloudflare")
            self.assertFalse(r["ok"])

        # set_doh unknown provider
        with mock.patch("zapret_core.doh.is_admin", return_value=True):
            r = set_doh("non_existent_provider")
            self.assertFalse(r["ok"])

        # set_doh success
        with mock.patch("zapret_core.doh.is_admin", return_value=True), \
             mock.patch("zapret_core.doh._get_active_adapter_names", return_value=["Ethernet"]), \
             mock.patch("zapret_core.doh._run_cmd", return_value=(True, "OK")), \
             mock.patch("winreg.CreateKey"), \
             mock.patch("winreg.SetValueEx"):
            r = set_doh("cloudflare")
            self.assertTrue(r["ok"])
            self.assertEqual(r["provider"], "cloudflare")

        # disable_doh success
        with mock.patch("zapret_core.doh.is_admin", return_value=True), \
             mock.patch("zapret_core.doh._get_active_adapter_names", return_value=["Ethernet"]), \
             mock.patch("zapret_core.doh._run_cmd", return_value=(True, "OK")), \
             mock.patch("winreg.OpenKey"), \
             mock.patch("winreg.DeleteValue"):
            r = disable_doh()
            self.assertTrue(r["ok"])

    def test_router_new_actions(self) -> None:
        with mock.patch("zapret_core.router.is_autostart_enabled", return_value=True):
            r = service_manager.run_service_action("is_autostart_enabled")
            self.assertTrue(r["ok"])
            self.assertTrue(r["enabled"])

        with mock.patch("zapret_core.router.toggle_autostart", return_value=False):
            r = service_manager.run_service_action("toggle_autostart")
            self.assertTrue(r["ok"])
            self.assertFalse(r["enabled"])

        with mock.patch("zapret_core.router.unpack_zapret_archive", return_value=(True, "unpacked")):
            r = service_manager.run_service_action("unpack_zip", zip_path="dummy.zip")
            self.assertTrue(r["ok"])
            self.assertEqual(r["service"], "unpacked")

        with mock.patch("zapret_core.router.set_custom_zapret_dir", return_value=(True, "saved")):
            r = service_manager.run_service_action("set_custom_zapret_dir", dir_path="dummy_dir")
            self.assertTrue(r["ok"])
            self.assertEqual(r["service"], "saved")

        with mock.patch("zapret_core.router.cleanup_orphans", return_value={"ok": True, "service": "cleaned"}):
            r = service_manager.run_service_action("cleanup_orphans")
            self.assertTrue(r["ok"])
            self.assertEqual(r["service"], "cleaned")

        with mock.patch("zapret_core.router.check_connectivity", return_value={"ok": True, "targets": []}):
            r = service_manager.run_service_action("check_connectivity")
            self.assertTrue(r["ok"])

    def test_cleanup_orphans_logic(self) -> None:
        from zapret_core.misc import cleanup_orphans
        class _MockProc:
            def __init__(self, code):
                self.returncode = code

        with mock.patch("subprocess.run", side_effect=[_MockProc(0), _MockProc(0), _MockProc(1)]):
            res = cleanup_orphans()
            self.assertTrue(res["ok"])
            self.assertIn("winws.exe", res["service"])

    def test_check_connectivity_logic(self) -> None:
        from zapret_core.misc import check_connectivity
        class _Resp:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def getcode(self):
                return 204

        # Success case
        with mock.patch("urllib.request.urlopen", return_value=_Resp()):
            res = check_connectivity()
            self.assertTrue(res["ok"])
            self.assertEqual(len(res["targets"]), 3)

        # Failure case
        with mock.patch("urllib.request.urlopen", side_effect=Exception("network down")):
            res = check_connectivity()
            self.assertFalse(res["ok"])
            self.assertEqual(len(res["targets"]), 3)

    def test_sound_error_branches(self) -> None:
        from zapret_core.sound import is_sound_enabled, play_sound, set_sound_enabled
        with tempfile.TemporaryDirectory() as td:
            bad_json = os.path.join(td, "bad.json")
            with open(bad_json, "w", encoding="utf-8") as f:
                f.write("not json content {")
            with mock.patch("zapret_core.sound.SETTINGS_FILE", bad_json):
                self.assertTrue(is_sound_enabled())
                # Write to read-only or invalid dir
                with mock.patch("builtins.open", side_effect=OSError("denied")):
                    self.assertFalse(set_sound_enabled(False))

        with mock.patch("zapret_core.sound.is_sound_enabled", return_value=True), \
             mock.patch("winsound.PlaySound", side_effect=RuntimeError("sound error")):
            self.assertFalse(play_sound("connect"))

    def test_autostart_error_branches(self) -> None:
        import sys

        from zapret_core.autostart import _get_exec_command, set_autostart_enabled
        # Frozen binary
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", "C:\\App\\zapret.exe"):
            cmd = _get_exec_command()
            self.assertEqual(cmd, '"C:\\App\\zapret.exe" --minimized')

        # winreg.DeleteValue raises OSError (handled cleanly)
        with mock.patch("winreg.OpenKey"), \
             mock.patch("winreg.DeleteValue", side_effect=OSError("not found")):
            ok, msg = set_autostart_enabled(False)
            self.assertTrue(ok)

        # winreg.OpenKey raises OSError
        with mock.patch("winreg.OpenKey", side_effect=OSError("access denied")):
            ok, msg = set_autostart_enabled(True)
            self.assertFalse(ok)
            self.assertIn("Ошибка реестра", msg)

    def test_doh_error_branches(self) -> None:
        from zapret_core.doh import _run_cmd, _run_ps_script, disable_doh, get_doh_status, set_doh
        # _run_cmd exception
        with mock.patch("subprocess.run", side_effect=Exception("subproc err")):
            ok, out = _run_cmd(["invalid_command"])
            self.assertFalse(ok)
            self.assertIn("subproc err", out)

        with mock.patch("base64.b64encode", side_effect=Exception("encode err")):
            ok, out = _run_ps_script("test")
            self.assertFalse(ok)

        # get_doh_status when no adapters
        with mock.patch("zapret_core.doh._get_active_adapter_names", return_value=[]):
            stat = get_doh_status()
            self.assertTrue(stat["ok"])
            self.assertFalse(stat["enabled"])
            self.assertEqual(stat["provider"], "disabled")

        # get_doh_status with custom DNS
        with mock.patch("zapret_core.doh._get_active_adapter_names", return_value=["Ethernet"]), \
             mock.patch("zapret_core.doh._run_cmd", return_value=(True, "192.168.1.1")), \
             mock.patch("winreg.OpenKey", side_effect=OSError):
            stat = get_doh_status()
            self.assertEqual(stat["provider"], "custom")
            self.assertIn("192.168.1.1", stat["provider_name"])

        # set_doh all adapters fail
        with mock.patch("zapret_core.doh.is_admin", return_value=True), \
             mock.patch("zapret_core.doh._get_active_adapter_names", return_value=["Ethernet"]), \
             mock.patch("zapret_core.doh._run_cmd", return_value=(False, "DNS error")):
            r = set_doh("cloudflare")
            self.assertFalse(r["ok"])
            self.assertIn("Не удалось применить DNS", r["error"])

        # set_doh winreg CreateKey OSError
        with mock.patch("zapret_core.doh.is_admin", return_value=True), \
             mock.patch("zapret_core.doh._get_active_adapter_names", return_value=["Ethernet"]), \
             mock.patch("zapret_core.doh._run_cmd", return_value=(True, "OK")), \
             mock.patch("winreg.CreateKey", side_effect=OSError("reg error")):
            r = set_doh("cloudflare")
            self.assertFalse(r["ok"])
            self.assertIn("Ошибка реестра", r["error"])

        # disable_doh non-admin
        with mock.patch("zapret_core.doh.is_admin", return_value=False):
            r = disable_doh()
            self.assertFalse(r["ok"])

        # disable_doh winreg DeleteValue exception is swallowed
        with mock.patch("zapret_core.doh.is_admin", return_value=True), \
             mock.patch("zapret_core.doh._get_active_adapter_names", return_value=["Ethernet"]), \
             mock.patch("zapret_core.doh._run_cmd", return_value=(True, "OK")), \
             mock.patch("winreg.OpenKey", side_effect=Exception("swallowed")):
            r = disable_doh()
            self.assertTrue(r["ok"])

    def test_paths_and_unpack_edges(self) -> None:
        from zapret_core.paths import (
            _saved_zapret_dir,
            set_custom_zapret_dir,
            set_zapret_dir,
            unpack_zapret_archive,
        )
        with tempfile.TemporaryDirectory() as td:
            bad_json = os.path.join(td, "bad.json")
            with open(bad_json, "w", encoding="utf-8") as f:
                f.write("corrupted json {")
            with mock.patch("zapret_core.paths.SETTINGS_FILE", bad_json):
                self.assertIsNone(_saved_zapret_dir())

            with mock.patch("builtins.open", side_effect=OSError("write err")):
                self.assertFalse(set_zapret_dir(td))

            # set_custom_zapret_dir when save fails
            bin_dir = os.path.join(td, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            with open(os.path.join(bin_dir, "winws.exe"), "wb") as f:
                f.write(b"exe")
            with mock.patch("zapret_core.paths.set_zapret_dir", return_value=False):
                ok, msg = set_custom_zapret_dir(td)
                self.assertFalse(ok)
                self.assertIn("Не удалось сохранить", msg)

            # Zip Slip protection and default target_dir
            zip_slip = os.path.join(td, "slip.zip")
            with zipfile.ZipFile(zip_slip, "w") as z:
                z.writestr("pkg/bin/winws.exe", b"exe")
                z.writestr("pkg/../../evil.txt", b"evil")
            out_target = os.path.join(td, "unpacked_safe")
            ok, msg = unpack_zapret_archive(zip_slip, out_target)
            self.assertTrue(ok)
            self.assertFalse(os.path.isfile(os.path.join(td, "evil.txt")))

            # Unpack with target_dir=None
            with mock.patch("zapret_core.paths.APP_DIR", td), \
                 mock.patch("zapret_core.paths.set_custom_zapret_dir"):
                ok, msg = unpack_zapret_archive(zip_slip)
                self.assertTrue(ok)

            # Unpack exception
            with mock.patch("zipfile.ZipFile", side_effect=Exception("corrupt archive")):
                with mock.patch("zipfile.is_zipfile", return_value=True), \
                     mock.patch("os.path.isfile", return_value=True):
                    ok, msg = unpack_zapret_archive("fake.zip")
                    self.assertFalse(ok)
                    self.assertIn("Ошибка распаковки", msg)


if __name__ == "__main__":
    unittest.main()
