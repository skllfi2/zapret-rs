# REVIEW.md — код-ревью zapret-simple (28.10.2026)

Метод: два параллельных ревью (ядро `zapret_core` + SCManager/pywin32; UI/i18n/скрипты/тесты)
+ ручная верификация каждой находки. Статус гейтов на момент ревью: ruff — 0, mypy — 0 (18 файлов),
188 тестов — OK, coverage 93%.

Как читать: **уверенность** — подтверждено ли находка; **проверено** — чем именно:
*интросп.* (реальная сигнатура установленного pywin32), *эмпирич.* (прогон на этой машине),
*код* (чтение кода и вызывающих мест).

---

## A. Критично

### A1. `apply_strategy` всегда падает: `ChangeServiceConfig()` вызывается не с теми аргументами
`zapret_core/strategies.py:110`

Сигнатура pywin32 312: `ChangeServiceConfig(pythonClassString, serviceName, startType=None, ...,
exeName=None, ..., exeArgs=None, description=None)`. Код зовёт
`ChangeServiceConfig(SERVICE_NAME, exeName=exe, exeArgs=..., ...)` — имя службы уходит в
`pythonClassString`, обязательного `serviceName` нет → **`TypeError: missing 1 required positional
argument: 'serviceName'`**.

Сценарий: служба установлена и работает (как сейчас) → код сначала **останавливает** службу
(`:102-109`), потом падает на TypeError → возвращает `ok=False`. Итог: DPI-bypass выключен,
новая конфигурация не применена, `.strategy` не записан. Это ровно то, что должен был поймать
живой smoke (шаг 1).

- Проверено: **интросп.** (запуск `inspect.signature`), код.
- Уверенность: **высокая**. Тесты не ловят: `mock.patch("win32serviceutil.ChangeServiceConfig")`.
- Исправление: `ChangeServiceConfig(None, SERVICE_NAME, exeName=exe, exeArgs=exe_args,
  startType=..., description=...)` — первый аргумент `pythonClassString` (None → no-op).

### A2. `InstallService()` ставит службу не на winws.exe
`zapret_core/strategies.py:114`

Сигнатура: `InstallService(pythonClassString, serviceName, displayName, ..., exeName=None, ...,
exeArgs=None, ...)`. Код: `InstallService(exe, SERVICE_NAME, SERVICE_DISPLAY, ...)` — путь к winws
уходит в `pythonClassString`, а `exeName` не задан → внутри `LocatePythonServiceExe(None)`:
в frozen-exe вернёт `sys.executable` (сам `zapret-simple.exe` с аргументами winws), в dev —
`pythonservice.exe`. Плюс в реестр запишется мусорный `Services\zapret\PythonClass = ...\winws.exe`.
Первая установка службы → не стартует (1053).

- Проверено: **интросп.**, код.
- Уверенность: **высокая**.
- Исправление: `InstallService(None, SERVICE_NAME, SERVICE_DISPLAY, exeName=exe,
  startType=..., exeArgs=exe_args, description=...)`.

### A3. Кнопка «Повысить права» не работает: elevated-копия всегда упирается в мьютекс
`zapret_pyside.py:803-813, 821`; `zapret_core/router.py:83-86`

Мьютекс `Local\zapret-simple-ui` держится весь срок процесса. `run_action("relaunch_admin")` зовёт
`relaunch_as_admin()` **не отпуская мьютекс и не завершаясь**. Дочерний процесс на старте получает
`ERROR_ALREADY_EXISTS` → «zapret-simple уже запущено» → `return 1`.
Сценарий: UAC «Да» → напечатан `[OK] Перезапуск с правами администратора`, а прав нет и окна нет.
Дополнительно гонка в startup-пути: мьютекс отпускается на `:811` **после** `ShellExecuteW` (`:810`)
— если ребёнок успевает раньше, не остаётся ни одного окна.

- Проверено: код (порядок строк), отсутствие тестов на взаимодействие (тест мокает саму функцию).
- Уверенность: **высокая**. Заявлено работающим в README и SMOKE.md.
- Исправление: при ручном relaunch — освободить мьютекс и выйти из текущего экземпляра (как в
  `main`), либо отдельный признак для elevated-копии; в `main` — отпускать мьютекс до
  `ShellExecuteW`.

### A4. Диагностика конфликтов врёт на русской Windows: `sc query` парсится по `SERVICE_NAME:`
`zapret_core/diagnostics.py:28-40` (потребители `:126+`, `remove_conflicts :287-301`)

`_sc_service_names()` ищет строки, начинающиеся с `SERVICE_NAME:`. На русской локали `sc query`
печатает `Имя_службы: ...` (и ещё декодируется как UTF-8 — см. B6) → совпадений **0**
(эмпирически на этой машине). Следствия: проверки Killer / Intel Connectivity / Check Point /
SmartByte / VPN / WinDivert-conflict / Conflicting bypasses **всегда `ok`** (ложное «конфликтов
нет»), а `remove_conflicts()` получает пустой список → возвращает `ok=True` и **ничего не удаляет**
(хорошо, что это не удаляет ничего — но и не удаляет заявленное).

- Проверено: **эмпирич.** (`sc query` → 0 совпадений), код.
- Уверенность: **высокая**. Оригинал (`service.bat`) делал `sc query | findstr /I "Killer"` —
  поиск по подстроке, локаль не мешала; это регрессия против оригинала.
- Исправление: имена служб через `win32service.EnumServicesStatus()` (pywin32) либо искать имя
  в любой строке вывода, как `findstr`.

## B. Средние

### B1. UI не гасит кнопки во время фоновых операций; guard тестов ставится слишком поздно
`zapret_pyside.py:622-646, 516-527, 563-565, 259`

`_tests_running` проверяется в `:623`, ставится в `:639` **после modal-диалога**;
`_tests_prereq_done` флаг не перепроверяет. Два быстрых клика → два prereq-воркера → вложенные
`dlg.exec()` (queued-сигналы доставляются внутри modal loop) → **два параллельных
`test zapret.ps1`**. Аналогично: двойной клик на Установить/Стоп/Удалить → параллельные
SCM-вызовы; две быстрые смены комбобокса → два параллельных `apply_strategy` (перетирают binPath
и `.strategy` друг другу).

- Проверено: код; тест `test_run_tests_guard_when_running` сам выставляет флаг, дыру не видит.
- Уверенность: высокая (дыры), средняя/высокая (сценарий).
- Исправление: ставить `_tests_running=True` до отправки prereq (снимать при отказе), перепроверять
  в `_tests_prereq_done`; гасить кнопки на время любого `submit`, включать в `_done`.

### B2. Выход из приложения во время фоновой операции → зависший процесс
`zapret_pyside.py:786-793, 820-822`

`pool.waitForDone(2000)` — результат **игнорируется**, воркеры не отменяются; после `app.exec()`
queued-сигналы `finished` больше не доставятся (`_done`/`_tests_done` не выполнятся). Воспроизведено
агентом: закрытие окна при 10-сек воркере → процесс завершился через 10.3 с +
`RuntimeError: Signal source has been deleted`. Выход из трея во время тестов → виснет на минуты.

- Проверено: код, эмпирич. (PySide6 offscreen).
- Уверенность: высокая.
- Исправление: отменяемая операция (флаг + kill powershell), при выходе — не закрываться, пока
  критический воркер не отменён, либо честный таймаут с сообщением.

### B3. Таймаут `run_tests` не срабатывает при «молчащем» зависании ps1
`zapret_core/tests_runner.py:85-104`

`deadline` проверяется **внутри** `for raw in stdout`, а `readline()` блокируется до новой строки.
Зависший `test zapret.ps1` без вывода (сеть/Read-Host) → воркер QThreadPool виснет навсегда →
`_tests_running` остаётся `True` → перезапуск тестов невозможен до рестарта приложения;
`timeout=1800` из docstring фактически не обеспечен. При выходе (B2) powershell остаётся сиротой.

- Проверено: код.
- Уверенность: высокая (механика), средняя (частота зависаний).
- Исправление: чтение stdout в отдельном потоке + убийство процесса по deadline; сбрасывать
  `_tests_running` в `finally`.

### B4. `uninstall_service` не останавливает службу и всегда сообщает успех
`zapret_core/scm.py:29-34`

Исходник `RemoveService` (проверено): только `DeleteService` + чистка реестра, **без** `StopService`.
Для Running-службы `DeleteService` лишь помечает удалением → функция возвращает `True`, а
`QueryServiceStatus("zapret")` продолжает работать → `tests_prerequisites:31-35` видит «служба
установлена» → **тесты блокируются с ошибкой, хотя UI только что доложил «служба удалена»**.
(Прямо бьётся с шагом 2 живого smoke: Remove Services → Run Tests.)

- Проверено: интросп./исходник `RemoveService`, код.
- Уверенность: высокая.
- Исправление: перед `RemoveService` — `StopService` + ожидание `Stopped`, после — реальная
  проверка `QueryServiceStatus`.

### B5. Пункт «Установить службу» не может выполниться никогда
`zapret_core/paths.py:27-29` + `zapret_core/scm.py:18-20` + `router.py:19`

`install_service()` без аргументов (так его и зовёт кнопка UI) берёт `get_bin_path()` →
`service.bat`, дальше безусловный отказ «.bat нельзя указывать как binPath». Действие всегда
`ok=False`; `service.bat` из UI тоже не запускается. Противоречит README («без service.bat») и
`router.py:17` («заменяет service.bat полностью»). Рабочая установка — только ветка A2.

- Проверено: код; тест закрепляет отказ, но не альтернативу.
- Уверенность: высокая.
- Исправление: `install_service(os.path.join(BIN_DIR, "winws.exe"))` (или убрать пункт /
  перенаправить на `apply_strategy` после починки A2).

### B6. Вывод `sc`/`netsh`/`net` (OEM, cp866) декодируется как UTF-8 → каша в сообщениях UI
`zapret_core/scm.py:23-24, 77`; `zapret_core/diagnostics.py:31, 44, 65, 98, 293`

Python 3.15 = UTF-8 mode по умолчанию → `text=True, errors="replace"` декодирует cp866-вывод как
UTF-8. Эмпирически: `sc query BFE` в коде выглядит как `'���_�㦡�: BFE '` (должно быть
`Имя_службы: BFE`). Эти строки возвращаются в UI (`install_service`, `set_autostart`). В `winws.py:13-17`
это сделано правильно (байты) — внутри проекта непоследовательность.

- Проверено: **эмпирич.** (сырые байты vs `text=True`).
- Уверенность: высокая.
- Исправление: байты (как в winws.py) либо `encoding="cp866"`/`"oem"` для консольных утилит.

### B7. TCP timestamps: подстрока `timestamp` не находится в русском netsh → авто-включение при каждом запуске
`zapret_core/diagnostics.py:96-116`

`ts_line = next((ln for ln in out.splitlines() if "timestamp" in ln), "")`. На этой машине netsh
печатает `Метки времени RFC 1323 : enabled` → подстроки нет → `ts_line = ""` → ветка «выключены»:
при правах админа **каждый** прогон диагностики выполняет `netsh int tcp set global
timestamps=enabled` и печатает «были выключены → включили», хотя они включены. Нарушен условный
характер из docstring.

- Проверено: **эмпирич.** (вывод netsh через тот же код), код.
- Уверенность: высокая.
- Исправление: состояние по значению после `:` на строке с меткой, не завязываясь на английское
  слово; `set` только при реальном `disabled`.

### B8. `.strategy` рядом с exe → молча теряется в Program Files
`zapret_core/paths.py:34-37` + `zapret_core/strategies.py:122-126`

Для frozen-exe `APP_DIR` = каталог exe; запись обёрнута в `except OSError: pass`. exe в Program
Files → стратегия реально применяется (админ), файл не сохраняется → после рестарта комбобокс
молча показывает `general`, хотя служба крутит другое. (i18n/applog уже пишут в `%LOCALAPPDATA%`.)

- Проверено: код.
- Уверенность: высокая (механика), средняя (частота).
- Исправление: хранить `.strategy` в `%LOCALAPPDATA%\zapret-simple\` (как `ui_settings.json`)
  или репортить ошибку записи.

### B9. Ложная уверенность тестов UI
`tests/test_pyside_ui.py:132-140, 142-147, 371-374`

- `test_status_updates_via_threadpool` — финальный assert `assertNotEqual(text, "")`, а исходный
  текст «Неизвестно» никогда не пустой. Доказано: при полностью отключённом `refresh` тест проходит.
- `test_no_widget_access_from_worker_threads` — grep подстрок в тексте файла: пройдёт даже при
  `label.setText(...)` из воркера.
- `test_emit_line_crosses_to_ui` — `_emit_line` вызывается из главного потока: кросс-поточная
  (queued) доставка не проверяется.

- Проверено: код, эмпирич. (мутация `refresh`).
- Уверенность: высокая. Продакшн-код при этом потокобезопасен (WorkerSignals в главном потоке →
  queued) — риск в ложной уверенности, не в баге.
- Исправление: сравнивать с начальным текстом/мокать `_read_status` и ждать конкретное значение;
  эмитить из реального фонового потока.

## C. Инфраструктура и воспроизводимость

### C1. Захардкоженный путь к Python в скриптах и хуке
`hooks/pre-commit:4`, `start-gui.bat:4`, `update.bat:4`, `build_exe.bat:4`

`C:\Users\dexox\AppData\Local\Python\pythoncore-3.15-64\python.exe` без фолбэка (в `smoke_live.bat:9`
фолбэк есть — противоречие внутри же репо). На другой машине/после переезда: `.bat` → «cannot find
the path» + `pause`; хук → код 1 → **все коммиты блокируются**. Все `.bat` закоммичены с LF
(`git ls-files --eol`: i/lf, w/lf).

Плюс README говорит `python -m unittest/ruff/mypy`, а на этой машине PATH-`python` — голый
интерпретатор без пакетов: команды из README дают 67 ошибок импорта (работает только с явным
интерпретатором).

- Проверено: код, `git ls-files --eol`, запуск.
- Уверенность: высокая.
- Исправление: цепочка «захардкоженный → `py -3.15` → `python`» (как в smoke_live.bat), в хуке
  `PY="${PY:-python}"`; пересохранить `.bat` с CRLF; в README указать рабочий интерпретатор.

### C2. `test_verify.py` проверяет не ту копию zapret
`test_verify.py:6, 30-32`

`ORIG = C:\Users\dexox\Pictures\zapret-discord-youtube`, а приложение через `zapret_core/paths.py`
использует `%LOCALAPPDATA%\AppWatch\Apps\zapret-discord-youtube`. Копии разошлись: 43 vs 58 файлов
(в AppWatch есть 16 fake-payload `bin\*.bin`, которых нет в Pictures; в Pictures есть лишний
`lists\TRAVERSAL2.txt`). Проверка «оригинальная копия цела» смотрит не туда и не проверяет самое
хрупкое — наличие payload-файлов. Плюс захардкожены `SIMPLE` и путь к python.

- Проверено: эмпирич. (сравнение дерева файлов).
- Уверенность: высокая.
- Исправление: брать `ORIG_DIR` из `zapret_core.paths`, проверять `bin/winws.exe` и `bin/*.bin`.

### C3. Нет dev-зависимостей
`requirements.txt` — только runtime (`pywin32` вообще без пина, `PySide6-Essentials==6.12.0`).
`ruff`/`mypy`/`coverage`/`pyinstaller` не перечислены нигде → чистое окружение не воспроизводимо
(гейты просто не запускаются).

- Проверено: чтение requirements/README, состояние PATH-питона.
- Исправление: `requirements-dev.txt` (ruff, mypy, coverage, pyinstaller) + упоминание в README,
  пин на pywin32.

## D. Низкие

| # | Место | Суть | Проверено |
|---|-------|------|-----------|
| D1 | `zapret_core/misc.py:36` | `taskkill` — единственный вызов без `CREATE_NO_WINDOW`: в `--windowed`-exe троекратное мигание консолей при «Очистить Discord» | код |
| D2 | `zapret_core/strategies.py:101-119` | `except Exception: pass` на `StopService`; при неостановке за 10 с `StartService` падает с 1052/1056 → UI «ошибка», хотя конфиг уже изменён; `.strategy` не пишется → статус расходится с реальностью | код |
| D3 | `zapret_pyside.py:441, 449` | `QMenu(self)` создаётся заново при каждом переключении RU/EN (старые копятся потомками окна); `setIcon` сбрасывает иконку трея в серый до ближайшего refresh (≤3 с) | код |
| D4 | `i18n.py:407` | Мёртвый ключ `ui.best_fail` нигде не вызывается (`_best_done` печатает `r.get('reason')`) | grep |
| D5 | `smoke_live.py` (было) | Двойная печать строк тестов; `input()` без `EOFError` | исправлено в этом же цикле |

## E. Проверено и чисто (в отчёт не вынесено)

- **Qt-потоки в продакшене**: `WorkerSignals` создаётся в главном потоке → `finished`/`line_signal`
  queued; обращений к виджетам из воркеров нет; `mousePressEvent`/`closeEvent` — легитимные
  переопределения.
- **i18n**: 161 использование — все ключи есть в словаре (кроме `no.such.key` из теста);
  плейсхолдеры ru/en совпадают; kwargs всех 190 вызовов `t(...)` совпадают с плейсхолдерами.
- **Сборка exe**: pywin32 действительно попадает в бандл (`pywintypes315.dll`, `win32service.pyd`,
  `pyi_rth_pywintypes` в Analysis-00.toc); PySide6 подхвачен хуками; критичных пропусков нет.
- **sc-формат**: `sc create ... "binPath= " + path` (одиночный токен с пробелом) sc принимает.
- **Парсер стратегий**: `shlex.split(posix=False)` + `join(" ")` байт-в-байт восстанавливает
  командную строку, `CommandLineToArgvW` даёт корректные argv (в т.ч. пути с пробелами);
  плейсхолдеры `%BIN%/%LISTS%/%GameFilterTCP/%UDP%/%~dp0` совпадают с реальными 22 `.bat`.
- **Кодировки .bat**: Python 3.15 = UTF-8 mode по умолчанию (`sys.flags.utf8_mode == 1`);
  кириллица в `.bat` только в `rem` — метасимволов cmd не задевает.
- **BFE-проверка**: `"RUNNING" in out` устойчива к локали (латиница в значении).
- Тесты ядра мокают внешний API, но проверяют реальную логику внутри; существенных «ложных»
  тестов, кроме B9, не найдено.

## Приоритетный план исправлений (предложение)

1. **Перед живым smoke**: A1, A2 (иначе шаг 1 смока упадёт по построению), A4+B6+B7 (чтобы
   диагностика не врала), B4 (иначе шаг 2 «Remove Services → Run Tests» блокируется).
2. **Следом**: A3 (кнопка UAC), B1, B2, B3 (стабильность UI), B5, B8.
3. **Затем**: B9 (честные тесты), C1-C3 (воспроизводимость), D1-D5.
