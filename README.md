# zapret-simple

[![CI](https://github.com/skllfi2/zapret-simple/actions/workflows/ci.yml/badge.svg)](https://github.com/skllfi2/zapret-simple/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-272%20passed-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/Coverage-91%25-brightgreen.svg)]()
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue.svg)]()
[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.15-blue.svg)]()
[![Rust](https://img.shields.io/badge/Rust-2021%20Edition-orange.svg)]()

Десктопный интерфейс для управления [zapret](https://github.com/Flowseal/zapret-discord-youtube)
(DPI-bypass через `winws.exe`) — **без** интерактивного `service.bat`.

Доступно два независимых варианта интерфейса:
1. **PySide6 (Qt 6, Python)** — полнофункциональный интерфейс со всеми системными диалогами, треем и живым выводом тестов.
2. **Slint (Rust, Native)** — сверхбыстрый автономный бинарник (~10 МБ, старт <20 мс, ~15 МБ RAM, прямые Win32 API вызовы без запуска `tasklist`/консолей).

## Как это устроено

| Файл / каталог | Роль |
|---|---|
| `zapret_core/` | **Python-ядро**: `paths` (каскад автоопределения каталога zapret), `scm` (служба Windows через pywin32 / direct API), `winws` (процессы и fake-payload, in-process Win32 ToolHelp), `lists` (ipset/user-списки/hosts), `settings` (тумблеры `utils/*`), `updates` (обновления zapret: проверка версии и применение релиза GitHub с бэкапом), `selfupdate` (самообновление приложения), `strategies` (разбор и применение стратегий напрямую), `menu` (шапка меню), `diagnostics` (18 проверок), `tests_runner` (запуск `test zapret.ps1`), `misc` (быстрый опрос процессов без tasklist, запуск оригинального service.bat), `router` (маршрутизатор действий), `applog` (лог-файл и перехват крашей). |
| `service_manager.py` | **Публичный фасад**: реэкспорт всего API ядра — импорты `from service_manager import X` работают как раньше и служат точкой патчинга для тестов. |
| `zapret_pyside.py` | **UI на PySide6 (Qt 6).** Структура меню как в оригинальном `service.bat`, тёмная тема, фоновые потоки `QThreadPool`, трей, диалоги статуса и обновлений. |
| `zapret-slint/` | **Нативный UI на Rust + Slint.** Автономный бинарник в `target/release/zapret-slint.exe` без внешних зависимостей. |
| `start-slint.bat` | Запуск Slint-версии (с автосборкой при первом запуске). |
| `i18n.py` | Словарь локализации ru/en для ядра и UI + хранение выбора языка. |
| `build_exe.py` / `.bat` | Сборка одиночного portable-exe для Python-версии. |
| `ruff.toml` | Конфиг линта (pyflakes, bugbear, isort, `E4/E7/E9`). |

### Автоопределение каталога zapret (каскадный поиск)

Каталог с самим zapret (`bin/winws.exe`, `lists/`, `service.bat`) определяется по каскаду:
1. Переменная окружения `ZAPRET_DIR`
2. Ранее сохранённый пользователем каталог в `%LOCALAPPDATA%\zapret-simple\ui_settings.json`
3. Локальный каталог `./zapret/` или корень приложения
4. `%LOCALAPPDATA%\zapret-simple\zapret`
5. Legacy-пути: `%LOCALAPPDATA%\AppWatch\Apps\zapret-discord-youtube` → `~/Pictures\zapret-discord-youtube`

### Независимость от обновлений zapret и service.bat

- **Обновление zapret:** Приложение не зависит от жестко зашитых стратегий — оно динамически считывает все `*.bat` файлы из папки zapret и парсит параметры запуска `winws.exe`. Если выходит новый релиз zapret с новыми стратегиями, они сразу появляются в UI.
- **Изменения в service.bat:** Управление службой (`start`, `stop`, `install`, `change config`) выполняется напрямую через Windows Service Control Manager (Win32 SCM API), поэтому любые изменения в `service.bat` не ломают приложение.
- **Оригинальное меню:** Для доступа к специфическим функциям `service.bat` предусмотрена кнопка *«Оригинальное меню zapret (service.bat)»*, запускающая батник автора в отдельном окне.

## Запуск

```bat
start-gui.bat             # десктопный UI на PySide6
start-slint.bat           # сверхбыстрый нативный UI на Rust + Slint
python zapret_pyside.py   # прямой запуск PySide6
dist\zapret-simple.exe    # portable-exe без Python (после сборки)
update.bat                # проверка обновлений (service_manager.check_updates)
```

Зависимости: `pip install -r requirements.txt` (pywin32, PySide6-Essentials).
PySide6 ставится только `Essentials` (~215 МБ) — метапакет с `Addons` (~100 МБ) в проекте
не нужен. Для разработки (линт, типизация, покрытие, сборка exe):
`pip install -r requirements-dev.txt`.

### Надёжность

- **Права**: при старте один раз спрашивается UAC; отказ — приложение работает без прав
  (статус прав виден в интерфейсе, кнопка «Права админа» повторяет повышение).
  Флаг `--no-elevate` отключает автоповышение. Некоторые действия (`sc`, `netsh`,
  управление службой) требуют админа.
- **Один экземпляр**: именованный мьютекс `Local\zapret-simple-ui` — двойной кликт по
  ярлыку не откроет второе окно.
- **Лог и краши**: `%LOCALAPPDATA%\zapret-simple\zapret.log` — старт приложения и любой
  необработанный exception (главный поток и фоновые потоки) с traceback; в UI — диалог
  с путём к логу (`zapret_core/applog.py`).
- **Трей**: кружок-индикатор статуса службы; закрытие окна сворачивает в трей,
  выход — только через меню трея.

### Функции поверх меню оригинала

- **Копировать / Сохранить… / Очистить** — кнопки над панелью вывода (скрыта по умолчанию,
  показывается по кнопке в шапке и автоматически при живом выводе тестов/списков).
- **DNS over HTTPS (DoH)** — диалог настройки шифрования DNS на уровне Windows с поддержкой
  IPv4 и IPv6 (Cloudflare, Google, Quad9, AdGuard) и включением Auto-DoH в реестре.
- **Звуковые уведомления** — отключаемые звуки системных событий (успех, сбой, подключение).
- **Автозагрузка** — запуск вместе с Windows в свернутом виде в трей (`--minimized`).
- **Выбор папки и распаковка ZIP** — распаковка дистрибутива zapret с защитой от Zip Slip и валидацией `bin/winws.exe`.
- **Быстрая проверка доступности** — мгновенный замер latency и доступности YouTube, Discord и Google без запуска долгого теста.
- **Применить лучшую стратегию** — читает строку `Best strategy: X.bat` из последнего
  `utils/test results/test_results_*.txt`, выбирает стратегию в списке, спрашивает
  подтверждение (служба перезапускается) и применяет её тем же фоновым путём, что и
  кнопка Apply.
- **Обновления** — диалог «Проверить обновления» проверяет две независимые пары:
  zapret (Flowseal/zapret-discord-youtube, GitHub Releases) и само приложение
  (свой репозиторий, константа `SELF_UPDATE_REPO`; пока не настроен — мягкая
  деградация). Обновление zapret: бэкап копии в `%LOCALAPPDATA%\zapret-simple\backups`,
  остановка службы, распаковка релиза поверх, пере-применение текущей стратегии.
  Обновление приложения не трогает каталог zapret; настройки (`utils/*.enabled`) и
  `.strategy` переживают обновление обоих компонентов.
- **Диалоги вместо служебного вывода** — статус службы («Check Status»), диагностика
  и результаты обновлений открываются в диалоговых окнах; лог панели вывода
  используется только для живого вывода тестов и списочных результатов действий.

## Меню, диагностикa и тесты

UI повторяет структуру `service.bat` (ZAPRET SERVICE MANAGER v1.10.4):
заголовок с версией и активной стратегией, секции `:: SERVICE` (Install / Remove /
Check Status), `:: SETTINGS` (Game Filter `[enabled (TCP)]`, IPSet Filter `[loaded]`,
Auto-Update Check `[enabled]`, Replace active fakes), `:: UPDATES` (Update IPSet /
Update Hosts / Check for Updates), `:: TOOLS` (Run Diagnostics / Run Tests).
Статусы тумблеров читаются из тех же файлов, что и в оригинале
(`utils/game_filter.enabled`, `lists/ipset-all.txt`, `utils/check_updates.enabled`).

- **Run Diagnostics** — полный порт `:service_diagnostics` на Python (18 проверок: BFE,
  прокси, TCP timestamps, Adguard, Killer, Intel Connectivity, Check Point, SmartByte,
  кириллица в пути, OneDrive, WinDivert, VPN, DoH, hosts, конфликты). Цвета
  `[+]`/`[?]`/`[X]` — как PrintGreen/PrintYellow/PrintRed. Как в оригинале, выключенные
  TCP timestamps диагностика включает сама (при правах админа); разрушающие фиксы
  (удаление WinDivert и конфликтных служб) — отдельная кнопка «Remove conflicts».
- **Run Tests** — пре-чеки (права админа, curl, служба zapret удалена), затем запуск
  оригинального `utils\test zapret.ps1` с ответами на его `Read-Host` через stdin;
  строки вывода идут в UI живьём, итог и «Best strategy» берутся из
  `utils/test results/test_results_*.txt`.

## Локализация (ru/en)

- **Словарь** — `i18n.py` (`STRINGS`: ключ → `{ru, en}`), вызовы `t("key", **переменные)`.
  Дефолт `ru`; `en` — дословно как в оригинальном `service.bat` / `test zapret.ps1`
  (маркеры `[+]`/`[?]`/`[X]` и тексты диагностик совпадают с оригиналом 1-в-1).
- **Хранение** — `%LOCALAPPDATA%\zapret-simple\ui_settings.json` (`{"lang": "ru"}`),
  читается при старте.
- **Переключатель** — кнопка `RU`/`EN` в шапке окна: сохраняет выбор и перестраивает
  интерфейс на месте (пункты меню, диалоги, вывод, сообщения ядра — всё через `t()`).

## Тесты и качество кода

```bat
python -m unittest discover -s tests -v   # 272 теста: ядро, i18n, UI/tray (offscreen), DoH, звуки, автозапуск
python test_verify.py                     # офлайн-проверки структуры без запуска окна
python -m ruff check .                    # линт (конфиг в ruff.toml) — 0 ошибок
python -m mypy                            # типизация (mypy.ini) — 0 ошибок
python -m coverage report                 # покрытие кода > 90%
```

Команды выше должны выполняться **интерпретатором с установленными зависимостями**
(`pip install -r requirements-dev.txt`): голый PATH-`python` без пакетов упадёт на импортах.
Если PATH-питон не тот — подставь свой: `C:\...\pythoncore-3.15-64\python.exe -m ruff check .`
(тот же принцип — в `.bat`-скриптах и хуке `hooks/pre-commit`: внешняя переменная `PYTHON`/`PY` →
локальный путь → `py -3.15` → `python`).

Сигнатуры всех функций `zapret_core` типизированы (аннотации параметров и возвратов).

**Живой smoke** (нужны права администратора, см. `SMOKE.md`): `smoke_live.bat` —
end-to-end применение стратегии (служба Running + реальный winws.exe + binPath + `.strategy`),
`smoke_live.bat --tests` — реальный запуск `utils\test zapret.ps1` по схеме оригинала
Remove Services → Run Tests с применением Best strategy после; визуальная часть
(трей / RU-EN / UAC) — по чек-листу в `SMOKE.md`.

## Сборка одиночного exe

```bat
pip install pyinstaller   # один раз, только для сборки
build_exe.bat             # или: python build_exe.py
```

Результат — `dist\zapret-simple.exe` (onefile, windowed, ~39 МБ): конечному пользователю
не нужны Python и pip. Выбранная стратегия хранится в `%LOCALAPPDATA%\zapret-simple\.strategy`
(каталог приложения может быть read-only; для старых версий — fallback на файл рядом с exe).
PyInstaller-артефакты (`dist/`, `build/`, `*.spec`) в `.gitignore`.

## Права безопасности в коде

- `subprocess` всегда с `CREATE_NO_WINDOW` и явной обработкой кодировки (OEM/CP866).
- Запись в `lists/` — только базовые имена `list-*.txt` / `ipset-*.txt`, с проверкой
  `commonpath` (защита от path traversal).
- `replace_fakes` копирует выбранный fake поверх `ACTIVE_*.bin` с бэкапом `.bak`,
  ничего не удаляет без выбора пользователя.
