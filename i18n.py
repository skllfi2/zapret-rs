# i18n.py — единая локализация zapret-simple (ru/en) для ядра и десктоп-UI.
# По умолчанию ru, выбор сохраняется в %LOCALAPPDATA%\zapret-simple\ui_settings.json.
# Использование: from i18n import t; t("sm.no_admin") — с подстановкой {placeholders}.
import json
import os
from typing import Any

LANG = "ru"

_SETTINGS_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                             "zapret-simple")
_SETTINGS = os.path.join(_SETTINGS_DIR, "ui_settings.json")


def _load() -> None:
    global LANG
    try:
        with open(_SETTINGS, encoding="utf-8") as f:
            lang = json.load(f).get("lang")
        if lang in ("ru", "en"):
            LANG = lang
    except (OSError, ValueError):
        pass


def save(lang: str) -> None:
    """Сохранить выбранный язык (и сделать текущим)."""
    global LANG
    if lang not in ("ru", "en"):
        return
    LANG = lang
    try:
        os.makedirs(_SETTINGS_DIR, exist_ok=True)
        with open(_SETTINGS, "w", encoding="utf-8") as f:
            json.dump({"lang": lang}, f)
    except OSError:
        pass


def set_lang(lang: str) -> None:
    """Сменить язык без записи настроек (для тестов)."""
    global LANG
    if lang in ("ru", "en"):
        LANG = lang


def t(key: str, **kw: Any) -> str:
    """Перевод по ключу с подстановкой {placeholders}; fallback -> en -> ключ."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    s = entry.get(LANG) or entry.get("en") or key
    if kw:
        try:
            return s.format(**kw)
        except (KeyError, IndexError):
            return s
    return s


_load()


# === Словарь: key -> {"ru": ..., "en": ...} ===
# ru — текст по умолчанию для русскоязычного пользователя;
# en — дословно как в оригинальном service.bat / test zapret.ps1 (паритет маркеров).
STRINGS = {
    # ---------- service_manager: общие ----------
    "sm.bat_as_bin": {
        "ru": ".bat нельзя указывать как binPath службы: {exe}. "
              "Служба zapret устанавливается оригинальным service.bat и запускает winws.exe.",
        "en": ".bat cannot be used as service binPath: {exe}. "
              "The zapret service is installed by the original service.bat and runs winws.exe."},
    "sm.no_admin": {
        "ru": "Нет прав администратора — запусти от имени администратора (sc/netsh будут падать)",
        "en": "Administrator rights missing — run as Administrator (sc/netsh will fail)"},
    "sm.apply_no_admin": {
        "ru": "Нет прав администратора — перезапусти приложение от администратора "
              "(кнопка «Admin») и повтори",
        "en": "Administrator rights missing — restart the app as Administrator "
              "(the \"Admin\" button) and retry"},

    # ---------- fakes ----------
    "sm.fake_need_choice": {
        "ru": "Нужен выбор: fake_type (1=Discord, 2=GameFilter) и номер fake-файла. "
              "Сначала вызови list_fakes.",
        "en": "Choice required: fake_type (1=Discord, 2=GameFilter) and fake file number. "
              "Call list_fakes first."},
    "sm.fake_unknown_type": {
        "ru": "Неизвестный тип fake: {t} (нужен 1 или 2)",
        "en": "Unknown fake type: {t} (need 1 or 2)"},
    "sm.fake_number_not_int": {
        "ru": "Номер должен быть числом, получено: {n}",
        "en": "Number must be an integer, got: {n}"},
    "sm.fake_number_range": {
        "ru": "Номер {i} вне диапазона 1..{n}",
        "en": "Number {i} out of range 1..{n}"},
    "sm.fakes_note": {
        "ru": "ACTIVE_* — текущие; остальные нумеруются с 1 для replace_fakes",
        "en": "ACTIVE_* are the current ones; the rest are numbered from 1 for replace_fakes"},

    # ---------- game filter / ipset / updates ----------
    "sm.gf_absent": {
        "ru": "game_filter.enabled отсутствует — игровой фильтр выключен",
        "en": "game_filter.enabled is missing — game filter is off"},
    "sm.ipset_empty": {
        "ru": "Пустой ответ от сервера — файл не обновлён",
        "en": "Empty response from server — file not updated"},
    "sm.ipset_updated": {
        "ru": "ipset-all.txt обновлён: {b} байт, {n} строк",
        "en": "ipset-all.txt updated: {b} bytes, {n} lines"},
    "sm.ipset_update_fail": {
        "ru": "Не удалось обновить ipset: {e}",
        "en": "Failed to update ipset: {e}"},
    "sm.ipset_no_backup": {
        "ru": "Ошибка: нет бэкапа для восстановления. Сначала обнови список через меню",
        "en": "Error: no backup to restore. Update the list from the service menu first"},
    "sm.updates_disabled": {
        "ru": "Проверка обновлений отключена (нет utils/check_updates.enabled)",
        "en": "Update check disabled (no utils/check_updates.enabled)"},
    "sm.ver_unreadable": {
        "ru": "Не удалось прочитать LOCAL_VERSION из service.bat",
        "en": "Failed to read LOCAL_VERSION from service.bat"},
    "sm.ver_local_only": {
        "ru": "Локальная версия {l}; проверить GitHub не удалось ({e})",
        "en": "Local version {l}; could not check GitHub ({e})"},
    "sm.ver_latest": {
        "ru": "Установлена последняя версия: {l}",
        "en": "Latest version installed: {l}"},
    "sm.ver_new": {
        "ru": "Доступна новая версия: {r} (локальная: {l}). "
              "https://github.com/Flowseal/zapret-discord-youtube/releases/latest",
        "en": "New version available: {r} (local: {l}). "
              "https://github.com/Flowseal/zapret-discord-youtube/releases/latest"},

    # ---------- обновление zapret (apply_zapret_update) ----------
    "sm.upd_need_admin": {
        "ru": "Обновление zapret требует прав администратора",
        "en": "Updating zapret requires administrator rights"},
    "sm.upd_check_failed": {
        "ru": "Не удалось получить релиз с GitHub — обновление отменено",
        "en": "Failed to fetch the release from GitHub — update cancelled"},
    "sm.upd_no_zip": {
        "ru": "В релизе нет zip-архива — обновление отменено",
        "en": "Release has no zip archive — update cancelled"},
    "sm.upd_bad_archive": {
        "ru": "Архив релиза не похож на копию zapret (нет bin/winws.exe) — обновление отменено",
        "en": "Release archive does not look like a zapret copy (no bin/winws.exe) — update cancelled"},
    "sm.upd_downloading": {
        "ru": "Скачиваю zapret {v}...",
        "en": "Downloading zapret {v}..."},
    "sm.upd_backuping": {
        "ru": "Создаю бэкап текущей копии...",
        "en": "Backing up the current copy..."},
    "sm.upd_reapplying": {
        "ru": "Пере-применяю текущую стратегию к обновлённой копии...",
        "en": "Re-applying the current strategy to the updated copy..."},
    "sm.upd_done": {
        "ru": "zapret обновлён до {v}, стратегия пере-применена",
        "en": "zapret updated to {v}, strategy re-applied"},
    "sm.upd_reapply_failed": {
        "ru": "zapret обновлён, но стратегию пере-применить не удалось: {e}",
        "en": "zapret updated, but re-applying the strategy failed: {e}"},
    "sm.upd_failed": {
        "ru": "Обновление zapret не удалось: {e}",
        "en": "zapret update failed: {e}"},

    # ---------- самообновление приложения (selfupdate) ----------
    "sm.app_upd_unconfigured": {
        "ru": "Источник обновлений приложения не настроен (репозиторий не указан)",
        "en": "App update source is not configured (no repository set)"},
    "sm.app_upd_check_failed": {
        "ru": "Не удалось проверить обновления приложения (сеть/GitHub)",
        "en": "Failed to check for app updates (network/GitHub)"},
    "sm.app_upd_latest": {
        "ru": "Приложение актуально (v{l})",
        "en": "App is up to date (v{l})"},
    "sm.app_upd_new": {
        "ru": "Доступна новая версия приложения: v{r} (текущая: v{l})",
        "en": "New app version available: v{r} (current: v{l})"},
    "sm.app_upd_downloading": {
        "ru": "Скачиваю обновление приложения...",
        "en": "Downloading app update..."},
    "sm.app_upd_applying": {
        "ru": "Применяю обновление приложения...",
        "en": "Applying app update..."},
    "sm.app_upd_done": {
        "ru": "Обновление применено — приложение перезапустится",
        "en": "Update applied — the app will restart"},
    "sm.app_upd_no_exe": {
        "ru": "В релизе нет исполняемого файла {e} — обновление отменено",
        "en": "Release has no executable {e} — update cancelled"},
    "sm.app_upd_no_zip": {
        "ru": "В релизе нет zip-архива с исходниками — обновление отменено",
        "en": "Release has no source zip archive — update cancelled"},
    "sm.app_upd_bad_archive": {
        "ru": "Архив релиза не содержит zapret_pyside.py — обновление отменено",
        "en": "Release archive does not contain zapret_pyside.py — update cancelled"},
    "sm.app_upd_failed": {
        "ru": "Обновление приложения не удалось: {e}",
        "en": "App update failed: {e}"},

    # ---------- hosts / payload ----------
    "sm.service_bat_missing": {
        "ru": "service.bat не найден по пути: {p}",
        "en": "service.bat not found at: {p}"},
    "sm.service_bat_started": {
        "ru": "Оригинальный service.bat запущен в консоли",
        "en": "Original service.bat launched in console"},
    "sm.hosts_summary": {
        "ru": "hosts: {n} строк, записей youtube/youtu.be: {y}",
        "en": "hosts: {n} lines, youtube/youtu.be entries: {y}"},
    "sm.hosts_note": {
        "ru": "Записи youtube в hosts могут мешать — при необходимости удали их вручную",
        "en": "youtube entries in hosts may interfere — remove them manually if needed"},
    "sm.payload_src_missing": {
        "ru": "Источник *.bin не найден. Задай ZAPRET_PAYLOADS_DIR или проверь архив версий.",
        "en": "No *.bin source found. Set ZAPRET_PAYLOADS_DIR or check the versions archive."},
    "sm.payload_src_eq_dest": {
        "ru": "Источник и назначение совпадают — нечего копировать.",
        "en": "Source and destination are the same — nothing to copy."},
    "sm.payload_copied": {
        "ru": "Скопировано {c}, пропущено (уже были) {s}. {status}",
        "en": "Copied {c}, skipped (already present) {s}. {status}"},
    "sm.bin_dir_missing": {
        "ru": "Каталог bin не найден: {d}",
        "en": "bin directory not found: {d}"},
    "sm.payloads_summary": {
        "ru": "payload-файлов в bin: {n}; отсутствует обязательных: {m}",
        "en": "payload files in bin: {n}; required missing: {m}"},
    "sm.payloads_missing": {
        "ru": "Отсутствуют: {list}",
        "en": "Missing: {list}"},

    # ---------- стратегии ----------
    "sm.strategy_not_found": {
        "ru": "Файл стратегии не найден: {p}",
        "en": "Strategy file not found: {p}"},
    "sm.strategy_no_winws": {
        "ru": "В {s}.bat не найдена строка запуска winws.exe",
        "en": "No winws.exe launch line found in {s}.bat"},
    "sm.service_started_suffix": {
        "ru": ", служба запущена",
        "en": ", service started"},
    "sm.strategy_applied": {
        "ru": "Стратегия {s} применена ({n} аргументов){started}",
        "en": "Strategy {s} applied ({n} args){started}"},
    "sm.stop_failed": {
        "ru": "Не удалось остановить службу: {e}",
        "en": "Failed to stop the service: {e}"},
    "sm.strategy_write_failed": {
        "ru": "Стратегия применена, но не удалось сохранить выбор: {e}",
        "en": "Strategy applied, but failed to save the selection: {e}"},
    "sm.remove_stop_failed": {
        "ru": "Служба не остановилась за 10 с — удаление отменено",
        "en": "Service did not stop within 10 s — removal cancelled"},
    "sm.no_strategies": {
        "ru": "Не найдено ни одной стратегии (.bat) в каталоге zapret",
        "en": "No strategies (.bat) found in the zapret directory"},

    # ---------- меню-тумблеры ----------
    "sm.bad_game_filter_mode": {
        "ru": "Недопустимый режим: {m}",
        "en": "Invalid mode: {m}"},

    # ---------- диагностика (en — дословно оригинал) ----------
    "diag.bfe_bad": {
        "ru": "Base Filtering Engine не запущен. Этот сервис нужен для работы zapret",
        "en": "Base Filtering Engine is not running. This service is required for zapret to work"},
    "diag.bfe_ok": {"ru": "Проверка BFE пройдена", "en": "Base Filtering Engine check passed"},
    "diag.proxy_ok": {"ru": "Проверка прокси пройдена", "en": "Proxy check passed"},
    "diag.proxy_warn": {
        "ru": "Системный прокси включён: {p}. Убедись, что он рабочий, или отключи его",
        "en": "System proxy is enabled: {p}. Make sure it's valid or disable it if you don't use a proxy"},
    "diag.ts_ok": {"ru": "Проверка TCP timestamps пройдена", "en": "TCP timestamps check passed"},
    "diag.ts_enabling": {
        "ru": "TCP timestamps выключены. Включаю timestamps...",
        "en": "[?] TCP timestamps are disabled. Enabling timestamps..."},
    "diag.ts_enabled": {
        "ru": "TCP timestamps успешно включены",
        "en": "TCP timestamps successfully enabled"},
    "diag.ts_failed": {
        "ru": "Не удалось включить TCP timestamps: {e}",
        "en": "Failed to enable TCP timestamps: {e}"},
    "diag.ts_no_admin": {
        "ru": "TCP timestamps выключены — запусти от администратора, чтобы включить "
              "(как в оригинале: netsh set global timestamps=enabled)",
        "en": "TCP timestamps are disabled — run as Administrator to enable "
              "(as in the original: netsh set global timestamps=enabled)"},
    "diag.ts_check_failed": {"ru": "Проверка TCP не удалась: {e}", "en": "TCP check failed: {e}"},
    "diag.ts_unknown": {
        "ru": "Не удалось прочитать состояние TCP timestamps ({v}) — не изменяю",
        "en": "Could not read TCP timestamps state ({v}) — not changing"},
    "diag.adguard_bad": {
        "ru": "Найден процесс Adguard. Adguard может мешать Discord",
        "en": "Adguard process found. Adguard may cause problems with Discord"},
    "diag.adguard_ok": {"ru": "Проверка Adguard пройдена", "en": "Adguard check passed"},
    "diag.killer_bad": {
        "ru": "Найдены службы Killer. Killer конфликтует с zapret",
        "en": "Killer services found. Killer conflicts with zapret"},
    "diag.killer_ok": {"ru": "Проверка Killer пройдена", "en": "Killer check passed"},
    "diag.intel_bad": {
        "ru": "Найдена Intel Connectivity Network Service. Она конфликтует с zapret",
        "en": "Intel Connectivity Network Service found. It conflicts with zapret"},
    "diag.intel_ok": {"ru": "Проверка Intel Connectivity пройдена", "en": "Intel Connectivity check passed"},
    "diag.checkpoint_bad": {
        "ru": "Найдены службы Check Point. Check Point конфликтует с zapret. Попробуй удалить Check Point",
        "en": "Check Point services found. Check Point conflicts with zapret. Try to uninstall Check Point"},
    "diag.checkpoint_ok": {"ru": "Проверка Check Point пройдена", "en": "Check Point check passed"},
    "diag.smartbyte_bad": {
        "ru": "Найдены службы SmartByte. SmartByte конфликтует с zapret. "
              "Попробуй удалить или отключить SmartByte через services.msc",
        "en": "SmartByte services found. SmartByte conflicts with zapret. "
              "Try to uninstall or disable SmartByte through services.msc"},
    "diag.smartbyte_ok": {"ru": "Проверка SmartByte пройдена", "en": "SmartByte check passed"},
    "diag.cyrillic_warn": {
        "ru": "Путь установки zapret содержит кириллицу. Если обход не работает — "
              "перенеси zapret в другой каталог, например в C:\\zapret",
        "en": "The path where Zapret is installed contains Cyrillic characters. "
              "If bypass doesn't work, try to move Zapret to another directory, for example in C:\\zapret"},
    "diag.cyrillic_ok": {"ru": "Проверка пути (кириллица) пройдена", "en": "Cyrillic path check passed"},
    "diag.onedrive_bad": {
        "ru": "Zapret установлен в папке OneDrive. Если обход не работает — перенеси "
              "zapret в другой каталог, например в C:\\zapret",
        "en": "Zapret is installed in a OneDrive folder. If bypass doesn't work, try to "
              "move Zapret to another directory, for example in C:\\zapret"},
    "diag.onedrive_ok": {"ru": "Проверка OneDrive пройдена", "en": "OneDrive check passed"},
    "diag.windivert_ok": {
        "ru": "Драйвер WinDivert присутствует: {f}",
        "en": "WinDivert driver present: {f}"},
    "diag.windivert_bad": {"ru": "Файл WinDivert64.sys НЕ найден в bin/", "en": "WinDivert64.sys file NOT found in bin/"},
    "diag.windivert_bin_bad": {"ru": "Каталог bin не найден или недоступен", "en": "bin/ not found or unreadable"},
    "diag.vpn_warn": {
        "ru": "Найдены VPN-службы: {v}. Часть VPN конфликтует с zapret — отключи все VPN",
        "en": "VPN services found: {v}. Some VPNs can conflict with zapret. Make sure that all VPNs are disabled"},
    "diag.vpn_ok": {"ru": "Проверка VPN пройдена", "en": "VPN check passed"},
    "diag.dns_ok": {"ru": "Проверка Secure DNS пройдена", "en": "Secure DNS check passed"},
    "diag.dns_warn": {
        "ru": "Настрой защищённый DNS в браузере у непоставленного по умолчанию провайдера",
        "en": "Make sure you have configured secure DNS in a browser with some non-default DNS service provider"},
    "diag.hosts_bad": {
        "ru": "Файл hosts содержит записи для youtube.com или youtu.be — это может мешать YouTube",
        "en": "Your hosts file contains entries for youtube.com or youtu.be. This may cause problems with YouTube access"},
    "diag.hosts_ok": {"ru": "Проверка hosts пройдена", "en": "Hosts file check passed"},
    "diag.wd_conflict_bad": {
        "ru": "winws.exe не запущен, но служба WinDivert активна. Нажми «Remove conflicts», чтобы удалить её",
        "en": "winws.exe is not running but WinDivert service is active. Press \"Remove conflicts\" to delete it"},
    "diag.wd_conflict_ok": {"ru": "Проверка конфликта WinDivert пройдена", "en": "WinDivert conflict check passed"},
    "diag.conflicts_bad": {
        "ru": "Найдены конфликтные обходы: {c}. Нажми «Remove conflicts», чтобы удалить их",
        "en": "Conflicting bypass services found: {c}. Press \"Remove conflicts\" to remove them"},
    "diag.conflicts_ok": {"ru": "Конфликтных обходов не найдено", "en": "No conflicting bypasses found"},
    "diag.discord_warn": {
        "ru": "Найден Discord ({d}). Нажми «Clear Discord cache», чтобы очистить кэш",
        "en": "Discord found ({d}). Press \"Clear Discord cache\" to clean it"},
    "diag.discord_ok": {"ru": "Установки Discord не найдены", "en": "Discord installations were not found"},
    "diag.summary": {
        "ru": "Диагностика: {n} проверок, ошибок {b}, предупреждений {w}",
        "en": "Diagnostics: {n} checks, {b} errors, {w} warnings"},

    # ---------- remove_conflicts ----------
    "sm.conflicts_no_admin": {
        "ru": "Нет прав администратора — нужны для netsh/sc delete",
        "en": "Administrator rights missing — required for netsh/sc delete"},
    "sm.timestamps_enabled": {"ru": "включены", "en": "enabled"},
    "sm.timestamps_failed": {"ru": "НЕ УДАЛОСЬ: {e}", "en": "FAILED: {e}"},
    "sm.no_conflicts": {
        "ru": "Конфликтных служб нет — удалять нечего",
        "en": "No conflicting services found — nothing to remove"},

    # ---------- тесты ----------
    "tests.need_admin": {
        "ru": "Требуются права администратора",
        "en": "Run as Administrator to execute tests"},
    "tests.need_curl": {
        "ru": "curl.exe не найден — установи curl или добавь его в PATH",
        "en": "curl.exe not found — install curl or add it to PATH"},
    "tests.service_installed": {
        "ru": "Служба zapret установлена — удали её перед запуском тестов "
              "(как в оригинале: Remove Services -> Run Tests)",
        "en": "Windows service 'zapret' is installed — remove the service before "
              "running tests (as in the original: Remove Services -> Run Tests)"},
    "tests.script_missing": {
        "ru": "Не найден тест-скрипт: {p}",
        "en": "Test script not found: {p}"},
    "tests.not_started": {
        "ru": "Тесты не запущены: {p}",
        "en": "Tests not started: {p}"},
    "tests.ps_fail": {
        "ru": "Не удалось запустить PowerShell: {e}",
        "en": "Failed to launch PowerShell: {e}"},
    "tests.timeout": {"ru": "[X] Таймаут тестов — процесс остановлен", "en": "[X] Tests timeout — process killed"},
    "tests.results_saved": {"ru": "результаты сохранены", "en": "results saved"},
    "tests.done": {"ru": "Тесты завершены за {t} с{tail}", "en": "Tests finished in {t}s{tail}"},
    "tests.aborted": {"ru": "Тесты прерваны с ошибкой — см. вывод", "en": "Tests aborted with an error — see output"},
    "tests.stopped": {"ru": "[X] Тесты остановлены пользователем", "en": "[X] Tests stopped by user"},
    "tests.prereq_ok": {"ru": "Условия выполнены — можно запускать", "en": "All conditions met — ready to run"},
    "tests.wont_start": {"ru": "Тесты не запустятся: {p}", "en": "Tests won't start: {p}"},
    "tests.best_none": {
        "ru": "Результатов тестов нет или в них нет \"Best strategy\" — сначала запусти Run Tests",
        "en": "No test results or no \"Best strategy\" line yet — run Run Tests first"},

    # ---------- relaunch / статус ----------
    "sm.relaunch_ok": {"ru": "Перезапуск с правами администратора", "en": "Relaunching with administrator rights"},
    "sm.relaunch_fail": {"ru": "Не удалось запустить с повышением прав", "en": "Failed to relaunch elevated"},

    # ---------- PySide6 UI ----------
    "ui.strategy": {"ru": "Стратегия:", "en": "Strategy:"},
    "ui.apply": {"ru": "Применить", "en": "Apply"},
    "ui.lang": {"ru": "Язык:", "en": "Language:"},
    "ui.status_unknown": {"ru": "Неизвестно", "en": "Unknown"},
    "ui.output": {"ru": "ВЫВОД", "en": "OUTPUT"},
    "ui.footer": {
        "ru": "zapret-simple — нативный SCM (pywin32) | без service.bat | PySide6 6.12 | Python 3.15+",
        "en": "zapret-simple — native SCM (pywin32) | no service.bat | PySide6 6.12 | Python 3.15+"},
    "ui.ready_msg": {
        "ru": "Готово. Меню как в оригинальном service.bat — все действия работают через service_manager.",
        "en": "Ready. Menu matches the original service.bat — all actions go through service_manager."},
    # секции
    "ui.sec_service": {"ru": "СЛУЖБА", "en": "SERVICE"},
    "ui.sec_settings": {"ru": "НАСТРОЙКИ", "en": "SETTINGS"},
    "ui.sec_updates": {"ru": "ОБНОВЛЕНИЯ", "en": "UPDATES"},
    "ui.sec_tools": {"ru": "ИНСТРУМЕНТЫ", "en": "TOOLS"},
    # пункты меню
    "ui.install_service": {"ru": "Установить службу", "en": "Install Service"},
    "ui.remove_services": {"ru": "Удалить службы", "en": "Remove Services"},
    "ui.check_status": {"ru": "Проверить статус", "en": "Check Status"},
    "ui.start_service": {"ru": "Запустить службу", "en": "Start Service"},
    "ui.stop_service": {"ru": "Остановить службу", "en": "Stop Service"},
    "ui.admin_rights": {"ru": "Права админа", "en": "Admin rights"},
    "ui.game_filter": {"ru": "Игровой фильтр", "en": "Game Filter"},
    "ui.ipset_filter": {"ru": "IPSet фильтр", "en": "IPSet Filter"},
    "ui.autoupdate_check": {"ru": "Проверка обновлений", "en": "Auto-Update Check"},
    "ui.replace_fakes": {"ru": "Заменить активные fakes", "en": "Replace active fakes"},
    "ui.update_ipset": {"ru": "Обновить IPSet список", "en": "Update IPSet List"},
    "ui.update_hosts": {"ru": "Обновить hosts-файл", "en": "Update Hosts File"},
    "ui.check_updates": {"ru": "Проверить обновления", "en": "Check for Updates"},
    "ui.run_diagnostics": {"ru": "Запустить диагностику", "en": "Run Diagnostics"},
    "ui.run_tests": {"ru": "Запустить тесты", "en": "Run Tests"},
    "ui.remove_conflicts": {"ru": "Удалить конфликты", "en": "Remove conflicts"},
    "ui.clear_discord": {"ru": "Очистить кэш Discord", "en": "Clear Discord cache"},
    "ui.restore_payload": {"ru": "Восстановить payload (.bin)", "en": "Restore payload (.bin)"},
    "ui.open_original_service": {"ru": "Оригинальный service.bat", "en": "Original service.bat"},
    # игровые режимы
    "ui.gf_disabled": {"ru": "выключен", "en": "disabled"},
    "ui.gf_all": {"ru": "Все (TCP и UDP)", "en": "All (TCP and UDP)"},
    "ui.gf_tcp": {"ru": "TCP", "en": "TCP"},
    "ui.gf_udp": {"ru": "UDP", "en": "UDP"},
    # диалог fake
    "ui.fake_dialog_title": {"ru": "Замена активного fake", "en": "Replace Active Fake"},
    "ui.fake_kind": {"ru": "Тип fake:", "en": "Fake type:"},
    "ui.fake_kind_1": {"ru": "1 — Discord UDP", "en": "1 — Discord UDP"},
    "ui.fake_kind_2": {"ru": "2 — GameFilter UDP", "en": "2 — GameFilter UDP"},
    "ui.fake_number": {"ru": "Номер файла:", "en": "File number:"},
    # диалог тестов
    "ui.tests_dialog_title": {"ru": "Запуск тестов", "en": "Run Tests"},
    "ui.tests_kind": {"ru": "Тип теста:", "en": "Test type:"},
    "ui.tests_kind_std": {"ru": "Стандартные (HTTP/ping)", "en": "Standard tests (HTTP/ping)"},
    "ui.tests_kind_dpi": {"ru": "DPI-чекеры (TCP 16-20 freeze)", "en": "DPI checkers (TCP 16-20 freeze)"},
    "ui.tests_mode": {"ru": "Режим:", "en": "Mode:"},
    "ui.tests_mode_all": {"ru": "Все конфиги", "en": "All configs"},
    "ui.tests_mode_sel": {"ru": "Выбранные конфиги", "en": "Selected configs"},
    "ui.tests_sel_config": {"ru": "Конфиг (при Selected):", "en": "Config (for Selected):"},
    "ui.tests_note": {
        "ru": "Тесты требуют прав администратора и УДАЛЁННОЙ службы zapret (как в оригинале). "
              "Идут несколько минут.",
        "en": "Tests require administrator rights and the zapret service REMOVED (as in the "
              "original). Takes several minutes."},
    # сообщения вывода PySide
    "ui.err_no_strategy": {"ru": "[X] Стратегия не выбрана", "en": "[X] No strategy selected"},
    "ui.apply_need_admin": {
        "ru": "[X] Применение стратегии требует прав администратора — нажми «Права админа» и повтори",
        "en": "[X] Applying a strategy requires administrator rights — press \"Admin rights\" and retry"},
    "ui.applying_strategy": {
        "ru": ">>> Применение стратегии: {s} (служба будет перезапущена)...",
        "en": ">>> Applying strategy: {s} (the service will be restarted)..."},
    "ui.games_running": {"ru": "[?] Тесты уже выполняются", "en": "[?] Tests are already running"},
    "ui.fix_errors": {"ru": "Исправь ошибки выше и запусти снова.", "en": "Fix the errors above and rerun."},
    "ui.running_tests": {
        "ru": ">>> Запуск тестов: тип {t}, режим {m} (идёт несколько минут)...",
        "en": ">>> Running tests: type {t}, mode {m} (takes several minutes)..."},
    "ui.no_bins": {"ru": "[X] Нет .bin файлов в bin/", "en": "[X] No .bin files in bin/"},
    "ui.fakes_list": {"ru": "Fake-файлы:", "en": "Fake files:"},
    "ui.payload_warn": {"ru": "⚠ нет .bin: {n} — восстановить", "en": "⚠ missing .bin: {n} — restore"},
    # панель вывода: копирование / сохранение / очистка
    "ui.out_copy": {"ru": "Копировать", "en": "Copy"},
    "ui.out_save": {"ru": "Сохранить...", "en": "Save..."},
    "ui.out_clear": {"ru": "Очистить", "en": "Clear"},
    "ui.out_copy_done": {"ru": "[+] Вывод скопирован в буфер обмена", "en": "[+] Output copied to clipboard"},
    "ui.out_saved": {"ru": "[+] Вывод сохранён: {p}", "en": "[+] Output saved: {p}"},
    "ui.out_save_fail": {"ru": "[X] Не удалось сохранить: {e}", "en": "[X] Failed to save: {e}"},
    # лучшая стратегия из результатов тестов
    "ui.apply_best": {"ru": "Применить лучшую стратегию", "en": "Apply best strategy"},
    "ui.best_found": {
        "ru": "[+] Лучшая стратегия по тестам: {s} — применяю...",
        "en": "[+] Best strategy from tests: {s} — applying..."},
    "ui.best_fail": {"ru": "[X] Не удалось применить лучшую стратегию: {e}",
                     "en": "[X] Failed to apply best strategy: {e}"},
    # трей
    "ui.tray_show": {"ru": "Показать окно", "en": "Show window"},
    "ui.tray_exit": {"ru": "Выход", "en": "Quit"},
    "ui.tray_tooltip": {"ru": "zapret-simple — служба: {s}", "en": "zapret-simple — service: {s}"},
    # надёжность: единственный экземпляр и crash-лог
    "ui.already_running": {"ru": "zapret-simple уже запущено.", "en": "zapret-simple is already running."},
    "ui.crash_title": {"ru": "Непредвиденная ошибка", "en": "Unexpected error"},
    "ui.crash_msg": {
        "ru": "Приложение продолжит работу.\nПодробности записаны в лог:\n{p}",
        "en": "The application will continue.\nDetails were written to the log:\n{p}"},

    # ---------- диалог обновлений ----------
    "ui.upd_title": {"ru": "Обновления", "en": "Updates"},
    "ui.upd_zapret_sec": {"ru": "zapret (файлы обхода DPI)", "en": "zapret (DPI bypass files)"},
    "ui.upd_app_sec": {"ru": "zapret-simple (приложение)", "en": "zapret-simple (the app)"},
    "ui.upd_checking": {"ru": "Проверяю...", "en": "Checking..."},
    "ui.upd_disabled": {"ru": "Проверка отключена в настройках zapret", "en": "Check is disabled in zapret settings"},
    "ui.upd_local_ver": {"ru": "Локальная версия: {v}", "en": "Local version: {v}"},
    "ui.upd_none": {"ru": "Обновлений нет", "en": "No updates"},
    "ui.upd_btn_zapret": {"ru": "Обновить zapret", "en": "Update zapret"},
    "ui.upd_btn_app": {"ru": "Обновить приложение", "en": "Update the app"},
    "ui.upd_btn_check": {"ru": "Проверить снова", "en": "Check again"},
    "ui.dlg_close": {"ru": "Закрыть", "en": "Close"},
    "ui.working": {"ru": "Проверяю...", "en": "Checking..."},
    "ui.upd_busy": {"ru": "Обновление уже выполняется...", "en": "An update is already in progress..."},
    "ui.upd_confirm_zapret": {
        "ru": "Обновить zapret до {v}?\nТекущая копия будет сохранена в бэкап, "
              "служба остановится и перезапустится с текущей стратегией.",
        "en": "Update zapret to {v}?\nThe current copy will be backed up, "
              "the service will stop and restart with the current strategy."},
    "ui.upd_confirm_app": {
        "ru": "Обновить приложение до v{v}?\nПриложение перезапустится.",
        "en": "Update the app to v{v}?\nThe app will restart."},
    # ---------- диалог статуса ----------
    "ui.status_title": {"ru": "Статус службы", "en": "Service Status"},
    "ui.status_service": {"ru": "Служба:", "en": "Service:"},
    "ui.status_winws": {"ru": "winws.exe:", "en": "winws.exe:"},
    "ui.status_version": {"ru": "Версия zapret:", "en": "zapret version:"},
    "ui.status_strategy": {"ru": "Стратегия:", "en": "Strategy:"},
    "ui.status_running": {"ru": "запущен", "en": "running"},
    "ui.status_stopped": {"ru": "остановлен", "en": "stopped"},
    # ---------- диалог диагностики ----------
    "ui.diag_title": {"ru": "Диагностика", "en": "Diagnostics"},
    "ui.diag_counts": {"ru": "Итог: {ok} ok, {warn} предупреждений, {bad} ошибок",
                       "en": "Total: {ok} ok, {warn} warnings, {bad} errors"},
    "ui.diag_no_checks": {"ru": "Диагностика не вернула проверок", "en": "Diagnostics returned no checks"},
    # ---------- подтверждение лучшей стратегии ----------
    "ui.best_confirm_title": {"ru": "Лучшая стратегия", "en": "Best strategy"},
    "ui.best_confirm_text": {
        "ru": "Тесты определили лучшую стратегию: {s}.\nПрименить её? "
              "(служба будет перезапущена)",
        "en": "Tests determined the best strategy: {s}.\nApply it? "
              "(the service will be restarted)"},
    # ---------- панель вывода: тумблер ----------
    "ui.out_show": {"ru": "Показать вывод", "en": "Show output"},
    "ui.out_hide": {"ru": "Скрыть вывод", "en": "Hide output"},
    # ---------- диалог DoH ----------
    "ui.doh_title": {"ru": "Настройка DNS over HTTPS (DoH)", "en": "Configure DNS over HTTPS (DoH)"},
    "ui.doh_sec": {"ru": "DNS over HTTPS (DoH)", "en": "DNS over HTTPS (DoH)"},
    "ui.doh_provider": {"ru": "Провайдер DoH:", "en": "DoH Provider:"},
    "ui.doh_status": {"ru": "Текущий статус DoH:", "en": "Current DoH status:"},
    "ui.doh_apply": {"ru": "Включить DoH", "en": "Enable DoH"},
    "ui.doh_disable": {"ru": "Отключить DoH (DHCP)", "en": "Disable DoH (DHCP)"},
    "ui.doh_active": {"ru": "Активен: {p}", "en": "Active: {p}"},
    "ui.doh_inactive": {"ru": "Отключен (DHCP)", "en": "Disabled (DHCP)"},
    "ui.sound_on": {"ru": "Звуки: Вкл", "en": "Sound: On"},
    "ui.sound_off": {"ru": "Звуки: Выкл", "en": "Sound: Off"},
    "ui.unpack_zip": {"ru": "Распаковать ZIP...", "en": "Unpack ZIP..."},
    "ui.select_folder": {"ru": "Выбрать папку...", "en": "Select folder..."},
    "ui.autostart": {"ru": "Автозагрузка:", "en": "Autostart:"},
    "ui.autostart_on": {"ru": "Включена", "en": "Enabled"},
    "ui.autostart_off": {"ru": "Отключена", "en": "Disabled"},
    "ui.zip_filter": {"ru": "Архивы ZIP (*.zip);;Все файлы (*)", "en": "ZIP Archives (*.zip);;All files (*)"},
    "ui.choose_zapret_zip": {"ru": "Выберите архив с zapret", "en": "Select zapret ZIP archive"},
    "ui.quick_check": {"ru": "Быстрая проверка доступности", "en": "Quick Connectivity Check"},
    "ui.choose_zapret_folder": {"ru": "Выберите папку с zapret (где находится bin/winws.exe)",
                                "en": "Select zapret folder (containing bin/winws.exe)"},
}
