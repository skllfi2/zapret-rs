# zapret-simple

Локальный веб- и десктоп-интерфейс для управления [zapret](https://github.com/Flowseal/zapret-discord-youtube)
(DPI-bypass через `winws.exe`) — **без** интерактивного `service.bat`.

## Как это устроено

| Файл | Роль |
|---|---|
| `service_manager.py` | Вся логика: SCM-служба `zapret` (pywin32), winws.exe, списки, fakes, обновления. Полная замена `service.bat`. |
| `main.py` | Flask-сервер на `http://127.0.0.1:8765/` (REST API + `index.html`). |
| `index.html` | Веб-интерфейс: 4 вкладки, темы, i18n (ru/en), поллинг статуса. |
| `zapret_pyside.py` | **Основной десктоп-UI на PySide6 6.12 (Qt 6).** Тёмная тема, фоновые потоки `QThreadPool`. |
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
**от администратора** — статус прав отображается в интерфейсе, кнопка «Admin (права)»
перезапускает приложение с повышением (UAC).

## API

Чтение — GET: `/api/status`, `/api/diag`, `/api/test`, `/api/fakes`, `/api/game_filter`,
`/api/hosts_check`, `/api/strategies`, `/api/lists`, `/api/lists_get?name=...`.

Изменения — **только POST** с заголовком `X-Zapret-Token` (токен: GET `/csrf-token`
или инлайнится в `index.html`). Это защита от CSRF: раньше любая веб-страница могла
остановить службу обычным `<img src="http://127.0.0.1:8765/api/stop">`.

`/api/start`, `/api/stop`, `/api/service_install`, `/api/service_uninstall`,
`/api/update`, `/api/update_ipset`, `/api/update_hosts`, `/api/replace_fakes`,
`/api/set_strategy`, `/api/clear_discord`, `/api/tcp_timestamps`, `/api/admin_use`,
`/api/lists_edit`, `/api/autostart`.

## Тесты

```bat
python -m unittest discover -s tests -v
python test_verify.py
```

## Правила безопасности в коде

- `subprocess` всегда с `CREATE_NO_WINDOW` и явной обработкой кодировки (OEM/CP866).
- Запись в `lists/` — только базовые имена `list-*.txt` / `ipset-*.txt`, с проверкой
  `commonpath` (защита от path traversal).
- `replace_fakes` копирует выбранный fake поверх `ACTIVE_*.bin` с бэкапом `.bak`,
  ничего не удаляет без выбора пользователя.
