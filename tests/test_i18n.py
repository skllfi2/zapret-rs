# tests/test_i18n.py — словарь локализации: полнота ru/en, подстановки, хранение выбора
import unittest, sys, os, json, tempfile, shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import i18n


class TestI18nDictionary(unittest.TestCase):
    def test_every_key_has_ru_and_en(self):
        # Ни одного ключа с пустым переводом — иначе в UI упадёт голый ключ
        for key, entry in i18n.STRINGS.items():
            self.assertIn("ru", entry, f"{key}: нет ru")
            self.assertIn("en", entry, f"{key}: нет en")
            self.assertTrue(entry["ru"].strip(), f"{key}: пустой ru")
            self.assertTrue(entry["en"].strip(), f"{key}: пустой en")

    def test_placeholders_match_between_languages(self):
        # {placeholders} должны совпадать, иначе format() упадёт на одном из языков
        import re
        ph = lambda s: set(re.findall(r"\{(\w+)\}", s))
        for key, entry in i18n.STRINGS.items():
            self.assertEqual(ph(entry["ru"]), ph(entry["en"]),
                             f"{key}: плейсхолдеры ru/en различаются")

    def test_format_works_in_both_languages(self):
        # Типовой вызов с параметрами не должен падать ни на одном языке
        for lang in ("ru", "en"):
            i18n.set_lang(lang)
            for key in ("sm.strategy_applied", "diag.summary", "tests.done",
                        "ui.payload_warn", "ui.applying_strategy"):
                entry = i18n.STRINGS[key]
                params = {m: "1" for m in __import__("re").findall(r"\{(\w+)\}", entry["en"])}
                out = i18n.t(key, **params)
                self.assertNotIn("{", out, f"{key} ({lang}): плейсхолдер не подставлен")
        i18n.set_lang("ru")

    def test_fallback_to_key_for_unknown(self):
        self.assertEqual(i18n.t("no.such.key"), "no.such.key")

    def test_switch_changes_output(self):
        i18n.set_lang("ru")
        ru = i18n.t("ui.install_service")
        i18n.set_lang("en")
        en = i18n.t("ui.install_service")
        self.assertNotEqual(ru, en)
        self.assertIn("Install Service", en)
        i18n.set_lang("ru")

    def test_set_lang_ignores_unknown(self):
        i18n.set_lang("ru")
        i18n.set_lang("de")
        self.assertEqual(i18n.LANG, "ru")
        i18n.set_lang("en")
        self.assertEqual(i18n.LANG, "en")
        i18n.set_lang("ru")


class TestI18nStorage(unittest.TestCase):
    """save() пишет выбор в ui_settings.json; читается при старте (_load)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old_dir, self._old_set = i18n._SETTINGS_DIR, i18n._SETTINGS
        i18n._SETTINGS_DIR = self.tmp
        i18n._SETTINGS = os.path.join(self.tmp, "ui_settings.json")
        self._old_lang = i18n.LANG

    def tearDown(self):
        i18n._SETTINGS_DIR, i18n._SETTINGS = self._old_dir, self._old_set
        i18n.LANG = self._old_lang
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_writes_file_and_sets_lang(self):
        i18n.save("en")
        self.assertEqual(i18n.LANG, "en")
        with open(i18n._SETTINGS, encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("lang"), "en")

    def test_save_rejects_unknown_lang(self):
        i18n.save("ru")
        i18n.save("fr")
        self.assertEqual(i18n.LANG, "ru")
        with open(i18n._SETTINGS, encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("lang"), "ru")

    def test_load_reads_saved_choice(self):
        i18n.save("en")
        i18n.LANG = "ru"
        i18n._load()
        self.assertEqual(i18n.LANG, "en")

    def test_load_tolerates_corrupt_file(self):
        with open(i18n._SETTINGS, "w", encoding="utf-8") as f:
            f.write("{broken")
        i18n.LANG = "en"
        i18n._load()
        self.assertEqual(i18n.LANG, "en")  # не упал, язык не сброшен


if __name__ == "__main__":
    unittest.main(verbosity=2)
