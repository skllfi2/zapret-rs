# tests/test_main_endpoints.py — реальные проверки эндпоинтов через Flask test_client
# Мутирующие эндпоинты теперь POST + X-Zapret-Token — тесты проверяют и защиту от CSRF.
import unittest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest.mock as mock

try:
    import main
except Exception as e:  # Flask может отсутствовать
    main = None
    _IMPORT_ERR = e


@unittest.skipIf(main is None, f"Flask dependency missing: {_IMPORT_ERR if main is None else ''}")
class TestMainEndpoints(unittest.TestCase):
    def setUp(self):
        self.c = main.app.test_client()
        self.h = {"X-Zapret-Token": main.CSRF_TOKEN}

    # === read-only ===
    def test_index_serves_html(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"<!DOCTYPE html>", r.data)
        # Токен инлайнится, а не остаётся плейсхолдером
        self.assertIn(main.CSRF_TOKEN.encode(), r.data)
        self.assertNotIn(b"__CSRF_TOKEN__", r.data)

    def test_status_shape(self):
        fake_pl = {"ok": True, "missing": [], "total": 16, "stdout": "stub", "stderr": ""}
        with mock.patch("main.service_manager.query_status", return_value="Running"), \
             mock.patch("main.service_manager.is_running", return_value=True), \
             mock.patch("main.service_manager.winws_is_running", return_value=True), \
             mock.patch("main.service_manager.is_admin", return_value=False), \
             mock.patch("main.service_manager.payloads_status", return_value=fake_pl):
            r = self.c.get("/api/status").get_json()
        self.assertEqual(r["running"], True)
        self.assertEqual(r["service"], "Running")
        self.assertIn("winws", r)
        self.assertIn("admin", r)
        self.assertIn("dir", r)
        # payload-файлы видны в статусе — UI предупреждает о их отсутствии
        self.assertTrue(r["payloads_ok"])
        self.assertEqual(r["payloads_missing"], 0)
        self.assertEqual(r["payloads_total"], 16)

    def test_strategies_from_disk(self):
        r = self.c.get("/api/strategies").get_json()
        ids = [s["id"] for s in r["strategies"]]
        self.assertIn("general", ids)  # general.bat существует в оригинале
        self.assertNotIn("service", ids)  # service*.bat — не стратегия

    def test_lists(self):
        r = self.c.get("/api/lists").get_json()
        self.assertIn("files", r)
        self.assertIn("dir", r)

    def test_lists_get_rejects_traversal(self):
        for name in ["../../evil.txt", "..%2F..%2Fevil.txt", "C:\\evil.txt"]:
            r = self.c.get(f"/api/lists_get?name={name}").get_json()
            self.assertFalse(r["ok"], name)

    # === CSRF: мутирующие запросы ===
    def test_get_rejected_on_mutating(self):
        for ep in ["/api/start", "/api/stop", "/api/clear_discord", "/api/update_ipset"]:
            r = self.c.get(ep)
            self.assertEqual(r.status_code, 405, ep)

    def test_post_without_token_rejected(self):
        r = self.c.post("/api/stop")
        self.assertEqual(r.status_code, 403)

    def test_post_with_bad_token_rejected(self):
        r = self.c.post("/api/stop", headers={"X-Zapret-Token": "deadbeef"})
        self.assertEqual(r.status_code, 403)

    def test_post_with_token_accepted(self):
        with mock.patch("main.service_manager.stop_service", return_value=(True, "Service stopped")):
            r = self.c.post("/api/stop", headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_status_needs_no_token(self):
        # статус — read-only, работает по GET без токена
        self.assertEqual(self.c.get("/api/status").status_code, 200)

    # === диспатч мутирующих действий ===
    def test_mutating_actions_dispatch(self):
        for ep, action in [("/api/update", "check_updates"),
                           ("/api/update_ipset", "ipset_update"),
                           ("/api/update_hosts", "update_hosts"),
                           ("/api/clear_discord", "clear_discord")]:
            with mock.patch("main.run_service_action") as m:
                m.return_value = {"ok": True, "service": "stub"}
                r = self.c.post(ep, headers=self.h).get_json()
                m.assert_called_once_with(action)
                self.assertTrue(r["ok"], ep)

    def test_replace_fakes_passes_args(self):
        with mock.patch("main.run_service_action") as m:
            m.return_value = {"ok": True}
            self.c.post("/api/replace_fakes?type=1&number=3", headers=self.h)
            m.assert_called_once_with("replace_active_fakes", fake_type="1", number="3")

    def test_lists_edit_traversal_rejected(self):
        r = self.c.post("/api/lists_edit?name=../../evil.txt&content=x", headers=self.h).get_json()
        self.assertFalse(r["ok"])
        r = self.c.post("/api/lists_edit", data={"name": "list-../../evil.txt", "content": "x"}, headers=self.h).get_json()
        self.assertFalse(r["ok"])

    def test_lists_edit_writes_in_lists_dir(self):
        import service_manager
        name = "list-test-unit.txt"
        full = os.path.join(service_manager.LISTS_DIR, name)
        try:
            r = self.c.post("/api/lists_edit",
                            data={"name": name, "content": "hello"}, headers=self.h).get_json()
            self.assertTrue(r["ok"], r)
            self.assertTrue(os.path.isfile(full))
            with open(full, encoding="utf-8") as f:
                self.assertEqual(f.read(), "hello")
        finally:
            if os.path.isfile(full):
                os.remove(full)

    def test_set_strategy_unknown_rejected(self):
        r = self.c.post("/api/set_strategy", data={"id": "no-such-strategy"}, headers=self.h).get_json()
        self.assertFalse(r["ok"])

    def test_set_strategy_parses_bat(self):
        # Реальная стратегия general.bat парсится; без админа — честный отказ, но аргументы разобраны
        with mock.patch("main.service_manager.is_admin", return_value=False):
            r = self.c.post("/api/set_strategy", data={"id": "general"}, headers=self.h).get_json()
        self.assertFalse(r["ok"])
        self.assertEqual(r["strategy"], "general")
        self.assertIn("администратор", r["service"])

    def test_set_strategy_applies_with_admin(self):
        with mock.patch("main.service_manager.is_admin", return_value=True), \
             mock.patch("main.service_manager.win32serviceutil") as w, \
             mock.patch("main.service_manager.query_status", return_value="Stopped"), \
             mock.patch("main.service_manager.is_running", return_value=False), \
             mock.patch("main.service_manager.start_service", return_value=(True, "ok")):
            w.QueryServiceStatus.side_effect = Exception("not installed")
            r = self.c.post("/api/set_strategy", data={"id": "general"}, headers=self.h).get_json()
        self.assertTrue(r["ok"], r)
        self.assertGreater(r["args_count"], 10)

    def test_dns_rebinding_blocked(self):
        # Чужой Host (вредоносный домен, перепривязанный на 127.0.0.1) должен получать 403
        for host in ["evil.example:8765", "127.0.0.1.evil.example:8765"]:
            r = self.c.get("/api/status", headers={"Host": host})
            self.assertEqual(r.status_code, 403, host)
        # Наш адрес — проходит
        self.assertEqual(self.c.get("/api/status", headers={"Host": "127.0.0.1:8765"}).status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
