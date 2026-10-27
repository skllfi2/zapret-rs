# zapret-simple

Десктопный интерфейс для управления [zapret](https://github.com/Flowseal/zapret-discord-youtube)
(DPI-bypass через `winws.exe`) — **без** интерактивного `service.bat`.

Единственный вариант программы: **настольное приложение на PySide6**.

## Как это устроено

| Файл / каталог | Роль |
|---|---|
| `zapret_core/` | **Ядро** (бывший `service_manager.py`, разбитый на модули): `paths` (автоопределение каталога zapret), `scm` (служба Windows через pywin32), `winws` (процессы и fake-payload), `lists` (ipset/user-списки/hosts), `settings` (тумблеры `utils/*`), `updates` (проверка обновлений), `strategies` (разбор и применение стратегий), `menu` (шапка меню), `diagnostics` (18 проверок), `tests_runner` (запуск `test zapret.ps1`), `misc` (права/скрытые команды/перезапуск UAC), `router` (маршрутизатор действий), `applog` (лог-файл и перехват крашей). |
| `service_manager.py` | **Публичный фасад**: реэкспорт всего API ядра — импорты `from service_manager import X` работают как раньше и служат точкой патчинга для тестов. |
| `zapret_pyside.py` | **Единственный UI (PySide6 6.12, Qt 6).** Структура меню как в оригинальном `service.bat` (секции `:: SERVICE/SETTINGS/UPDATES/TOOLS`, пункты, статусы в `[]`), тёмная тема, фоновые потоки `QThreadPool`, живой вывод тестов через сигнал, трей. |
| `i18n.py` | Словарь локализации ru/en для ядра и UI + хранение выбора языка. |
| `build_exe.py` / `.bat` | Сборка одиночного portable-exe (см. ниже). |
| `ruff.toml` | Конфиг линта (pyflakes, bugbear, isort, `E4/E7/E9`). |

Каталог с самим zapret (`bin/winws.exe`, `lists/`, `service.bat`) определяется автоматически:
переменная окружения `ZAPRET_DIR` → `%LOCALAPPDATA%\AppWatch\Apps\zapret-discord-youtube`
→ `~/Pictures\zapret-discord-youtube`.

Удалены (оставлен только PySide6): веб-вариант (`main.py`, `index.html`, `start.bat`,
Flask) и tkinter-вариант (`zapret-tkinter.py`).

## Запуск

```bat
start-gui.bat             # десктопный UI на PySide6 (единственный вариант)
python zapret_pyside.py   # то же самое напрямую
dist\zapret-simple.exe    # portable-exe без Python (после сборки, см. ниже)
update.bat                # проверка обновлений (service_manager.check_updates)
```

Зависимости: `pip install -r requirements.txt` (pywin32, PySide6-Essentials).
PySide6 ставится только `Essentials` (~215 МБ) — метапакет с `Addons` (~100 МБ) в проекте
не нужен.

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

- **Копировать / Сохранить… / Очистить** — кнопки над панелью вывода диагностик и тестов.
- **Применить лучшую стратегию** — читает строку `Best strategy: X.bat` из последнего
  `utils/test results/test_results_*.txt`, выбирает стратегию в списке и применяет её
  тем же фоновым путём, что и кнопка Apply.

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
python -m unittest discover -s tests -v   # 78 тестов: ядро, i18n, UI/tray (offscreen)
python test_verify.py                     # офлайн-проверки структуры без запуска окна
python -m ruff check .                    # линт (конфиг в ruff.toml) — 0 ошибок
```

Сигнатуры всех функций `zapret_core` типизированы (аннотации параметров и возвратов).

## Сборка одиночного exe

```bat
pip install pyinstaller   # один раз, только для сборки
build_exe.bat             # или: python build_exe.py
```

Результат — `dist\zapret-simple.exe` (onefile, windowed, ~39 МБ): конечному пользователю
не нужны Python и pip. В frozen-режиме `.strategy` хранится рядом с exe (каталог
определяется через `sys.executable`, а не временный `_MEIPASS`). PyInstaller-артефакты
(`dist/`, `build/`, `*.spec`) в `.gitignore`.

## Права безопасности в коде

- `subprocess` всегда с `CREATE_NO_WINDOW` и явной обработкой кодировки (OEM/CP866).
- Запись в `lists/` — только базовые имена `list-*.txt` / `ipset-*.txt`, с проверкой
  `commonpath` (защита от path traversal).
- `replace_fakes` копирует выбранный fake поверх `ACTIVE_*.bin` с бэкапом `.bak`,
  ничего не удаляет без выбора пользователя.
