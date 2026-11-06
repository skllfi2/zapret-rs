# zapret-rs (Windows Fluent Desktop)

[![Rust](https://img.shields.io/badge/Rust-2021%20Edition-orange.svg)](https://www.rust-lang.org/)
[![UI Framework](https://img.shields.io/badge/UI-Slint%201.8%2B-blue.svg)](https://slint.dev/)
[![Design](https://img.shields.io/badge/Design-Windows%2011%20Fluent%20Mica-0078d4.svg)]()
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-blue.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Высокопроизводительное, легковесное нативное Windows-приложение на **Rust + Slint UI** с интерфейсом **Windows 11 Fluent Design** для управления службой и обхода замедлений YouTube и Discord на базе [zapret](https://github.com/Flowseal/zapret-discord-youtube) (`winws.exe` / `WinDivert`).

---

## ✨ Ключевые возможности

* **Нативный движок на Rust + Slint UI:**
  * Потребление памяти: всего ~15 МБ RAM.
  * Мгновенный холодный запуск (< 25 мс).
  * Автономный бинарник без сторонних рантаймов (без Python, WebView2, Electron или Qt).
* **Современный интерфейс Windows 11 Fluent Design:**
  * Бесшовное frameless-окно с кастомным заголовком, поддержкой перетаскивания за неклиентскую область и встроенными кнопками управления окном.
  * Автоопределение системной темы (Светлая / Тёмная / Системная) и языка интерфейса (Русский / English / Автоопределение).
  * Интуитивная группировка параметров: отсутствие горизонтального переполнения карточек, раздельные кнопки прямого выбора (сегментированные переключатели вместо циклического перебора).
* **Быстрое параллельное тестирование стратегий:**
  * Автоматический тест 22 конфигураций с параллельным опросом `HTTP 1.1`, `TLS 1.2`, `TLS 1.3` и `ICMP Ping` через `std::thread::scope`.
  * Автоскролл терминала вывода и генерация подробного отчета.
* **Сетевой файл Hosts и Fake Payloads:**
  * Автоматическое скачивание и безопасная установка оптимизированных адресов YouTube и голосовых серверов Discord с созданием `hosts.bak`.
  * Интерактивный селектор фейковых пакетов маскировки DPI (`tls_clienthello_*.bin`, `quic_initial_*.bin`).
* **Безопасность и интеграция с Windows:**
  * Прямая работа со службами через нативный Windows Service Control Manager (Win32 SCM API).
  * Управление DNS over HTTPS (DoH) на уровне ОС (Cloudflare, Google, Quad9, AdGuard).
  * Сворачивание в системный трей с динамическим индикатором статуса службы.
  * Чистая архитектура хранения данных: рабочие файлы, логи и отчеты изолированы в `%LOCALAPPDATA%\zapret-rs\`.

---

## 📁 Структура проекта

```
zapret-simple/
├── zapret-slint/            # Нативное приложение на Rust + Slint
│   ├── assets/              # Встроенные иконки (app.ico, app.png)
│   ├── src/                 # Модули Rust (SCM, пути, тесты, DoH, трей, i18n, тема)
│   │   ├── main.rs          # Точка входа, Win32-хэндлы, биндинги Slint
│   │   ├── scm.rs           # Windows Service Control Manager (Win32 API)
│   │   ├── paths.rs         # Поиск и миграция ядра zapret
│   │   ├── tests_runner.rs  # Параллельный бенчмарк стратегий (thread::scope)
│   │   ├── diagnostics.rs   # Комплексная диагностика (18 системных проверок)
│   │   ├── fakes.rs         # Управление бинарными фейками
│   │   ├── updates.rs       # Атомарное обновление движка и баз
│   │   └── tray.rs          # Системный трей Windows
│   └── ui/
│       └── appwindow.slint  # Декларативная разметка Fluent UI
├── zapret_core/             # [Legacy] Python-модули
├── zapret_pyside.py         # [Legacy] Интерфейс PySide6
└── README.md
```

---

## 🛠️ Сборка из исходников

### Требования
* 64-битная Windows 10/11
* [Rust](https://rustup.rs/) (версия 1.80+ stable)
* Visual Studio Build Tools (C++ x64)

### Компиляция Release-бинарника
```cmd
cd zapret-slint
cargo build --release
```

Готовый файл будет расположен в:
`zapret-slint\target\release\zapret-rs.exe`

---

## 📄 Лицензия

Проект распространяется под лицензией [MIT](LICENSE).
Использует оригинальные наработки движка [zapret](https://github.com/bol-van/zapret) и форка [Flowseal/zapret-discord-youtube](https://github.com/Flowseal/zapret-discord-youtube).
