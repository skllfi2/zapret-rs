# zapret-simple

Локальный веб- и десктоп-интерфейс для управления [zapret](https://github.com/Flowseal/zapret-discord-youtube)
(DPI-bypass через `winws.exe`) — **без** интерактивного `service.bat`.

## Как это устроено

| Файл | Роль |
|---|---|
| `service_manager.py` | Вся логика: SCM-служба `zapret` (pywin32), winws.exe, списки, fakes, обновления. Полная замена `service.bat`. |
| `main.py` | Flask-сервер на `http://127.0.0.1:8765/` (REST API + `index.html`). |
| `index.html` | Веб-интерфейс: 4 вкладки, темы, i18n (ru/en), поллинг статуса. |
| `i18n.py` | Единый словарь локализации ru/en для ядра и обоих десктоп-UI + хранение выбора. |
| `zapret_pyside.py` | **Основной десктоп-UI на PySide6 6.12 (Qt 6).** Структура меню как в оригинальном `service.bat` (секции `:: SERVICE/SETTINGS/UPDATES/TOOLS`, пункты 1–12, статусы в `[]`), тёмная тема, фоновые потоки `QThreadPool`, живой вывод тестов через сигнал. |
| `zapret-tkinter.py` | Запасной десктоп-UI на чистом tkinter — работает, если PySide6 не установлен. |

Каталог с самим zapret (`bin/winws.exe`, `lists/`, `service.bat`) определяется автоматически:
переменная окружения `ZAPRET_DIR` → `%LOCALAPPDATA%\AppWatch\Apps\zapret-discord-youtube`
→ `~/Pictures\zapret-discord-youtube`.

## Запуск

```bat
start.bat        # Flask-сервер -> откроется http://127.0.0.1:8765/
python zapret_pyside.py   # десктопный UI на PySide6 (основной)
python zapret-tkinter.py  # десктопный UI на tkinter (запасной, без зависимостей)
```

Зависимости: `pip install -r requirements.txt` (flask, pywin32, PySide6-Essentials).
PySide6 ставится только `Essentials` (~215 МБ) — метапакет с `Addons` (~100 МБ) в проекте
не нужен. Некоторые действия (`sc`, `netsh`, управление службой) требуют запуска
**от администратора** — статус прав отображается в интерфейсе, кнопка «Права админа»
перезапускает приложение с повышением (UAC).

## Локализация (ru/en)

Один переключатель языка на все интерфейсы, выбор общий:

- **Словарь** — `i18n.py` (`STRINGS`: ключ → `{ru, en}`), вызовы `t("key", **переменные)`.
  Дефолт `ru`; `en` — дословно как в оригинальном `service.bat` / `test zapret.ps1`
  (маркеры `[+]`/`[?]`/`[X]` и тексты диагностик совпадают с оригиналом 1-в-1).
- **Хранение** — `%LOCALAPPDATA%\zapret-simple\ui_settings.json` (`{"lang": "ru"}`),
  читается при старте (`i18n._load()`).
- **Десктоп** — кнопка `RU`/`EN` в шапке PySide6-окна (перестраивает окно на месте)
  и в шапке tkinter-окна (пересоздаёт окно). Пункты меню, диалоги, вывод — через `t()`.
- **Веб** — выбор в `localStorage['zapret-lang']` (как раньше); запросы теперь несут
  заголовок `X-Zapret-Lang`, и API-ответы (`msg`, диагностикa, пре-чеки тестов)
  приходят на языке вкладки.

## Меню, диагностикa и тесты

Десктопный UI повторяет структуру `service.bat` (ZAPRET SERVICE MANAGER v1.10.4):
заголовок с версией и активной стратегией, секции `:: SERVICE` (Install / Remove /
Check Status), `:: SETTINGS` (Game Filter `[enabled (TCP)]`, IPSet Filter `[loaded]`,
Auto-Update Check `[enabled]`, Replace active fakes), `:: UPDATES` (Update IPSet /
Update Hosts / Check for Updates), `:: TOOLS` (Run Diagnostics / Run Tests).
Статусы тумблеров читаются из тех же файлов, что и в оригинале
(`utils/game_filter.enabled`, `lists/ipset-all.txt`, `utils/check_updates.enabled`).

- **Run Diagnostics** — полный порт `:service_diagnostics` на Python (17 проверок: BFE,
  прокси, TCP timestamps, Adguard, Killer, Intel Connectivity, Check Point, SmartByte,
  кириллица в пути, OneDrive, WinDivert, VPN, DoH, hosts, конфликты). Цвета
  `[+]`/`[?]`/`[X]` — как PrintGreen/PrintYellow/PrintRed. Как в оригинале, выключенные
  TCP timestamps диагностика включает сама (при правах админа); разрушающие фиксы
  (удаление WinDivert и конфликтных служб) — отдельная кнопка «Remove conflicts».
- **Run Tests** — пре-чеки (права админа, curl, служба zapret удалена), затем запуск
  оригинального `utils\test zapret.ps1` с ответами на его `Read-Host` через stdin;
  строки вывода идут в UI живьём, итог и «Best strategy» берутся из
  `utils/test results/test_results_*.txt`.

## API

Чтение — GET: `/api/status`, `/api/diag` (чек-лист диагностик), `/api/test`
(только пре-чеки условий), `/api/tests_state`, `/api/menu_status`, `/api/fakes`,
`/api/game_filter`, `/api/hosts_check`, `/api/strategies`, `/api/lists`,
`/api/lists_get?name=...`.

Изменения — **только POST** с заголовком `X-Zapret-Token` (токен: GET `/csrf-token`
или инлайнится в `index.html`). Это защита от CSRF: раньше любая веб-страница могла
остановить службу обычным `<img src="http://127.0.0.1:8765/api/stop">`.

`/api/start`, `/api/stop`, `/api/service_install`, `/api/service_uninstall`,
`/api/update`, `/api/update_ipset`, `/api/update_hosts`, `/api/replace_fakes`,
`/api/set_strategy`, `/api/clear_discord`, `/api/tcp_timestamps`, `/api/admin_use`,
`/api/lists_edit`, `/api/autostart`, `/api/run_tests` (запуск тестов в фоне),
`/api/set_game_filter`, `/api/toggle_check_updates`, `/api/toggle_ipset`,
`/api/remove_conflicts`.

## Тесты

```bat
python -m unittest discover -s tests -v   # 80 тестов, включая полноту словаря i18n
python test_verify.py
```

## Правила безопасности в коде

- `subprocess` всегда с `CREATE_NO_WINDOW` и явной обработкой кодировки (OEM/CP866).
- Запись в `lists/` — только базовые имена `list-*.txt` / `ipset-*.txt`, с проверкой
  `commonpath` (защита от path traversal).
- `replace_fakes` копирует выбранный fake поверх `ACTIVE_*.bin` с бэкапом `.bak`,
  ничего не удаляет без выбора пользователя.
