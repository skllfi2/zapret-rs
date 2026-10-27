# test_verify.py — офлайн-проверки zapret-simple без запуска окна (структура «только PySide6»)
import os
import subprocess
import sys

ORIG = r"C:\Users\dexox\Pictures\zapret-discord-youtube"
SIMPLE = r"F:\Development\Dev\mydev\zapret-simple"

errors = []

def check(p, msg):
    if not p:
        errors.append(msg)
    else:
        print("  OK:", msg)

print("=== Состав zapret-simple ===")
for f in ["zapret_pyside.py", "service_manager.py", "i18n.py", "update.bat",
          "start-gui.bat", "build_exe.py", "ruff.toml"]:
    check(os.path.isfile(os.path.join(SIMPLE, f)), f"{f} существует")
for f in ["main.py", "index.html", "zapret-tkinter.py", "start.bat"]:
    check(not os.path.isfile(os.path.join(SIMPLE, f)), f"{f} удалён (оставлен только PySide6)")
# Ядро разбито на пакет zapret_core (service_manager.py — публичный фасад)
check(os.path.isdir(os.path.join(SIMPLE, "zapret_core")), "пакет zapret_core/ существует")
for f in ["paths.py", "scm.py", "winws.py", "lists.py", "settings.py", "updates.py",
          "strategies.py", "menu.py", "diagnostics.py", "tests_runner.py", "misc.py",
          "router.py", "applog.py"]:
    check(os.path.isfile(os.path.join(SIMPLE, "zapret_core", f)), f"zapret_core/{f} существует")

print("\n=== Оригинальная копия zapret ===")
check(os.path.isfile(os.path.join(ORIG, "service.bat")), "service.bat есть в оригинальной копии")
check(os.path.isfile(os.path.join(ORIG, "general.bat")), "general.bat есть в оригинальной копии")

print("\n=== Python 3.15+ ===")
res = subprocess.run([r"C:\Users\dexox\AppData\Local\Python\pythoncore-3.15-64\python.exe", "--version"], capture_output=True, text=True, check=False)
check(res.stdout.strip().startswith("Python 3.15"), f"Python 3.15.x (фактически: {res.stdout.strip()})")

print("\n=== Синтаксис исходников ===")
for f in ["zapret_pyside.py", "service_manager.py", "i18n.py"] + [
        f"zapret_core\\{f}" for f in ("paths.py", "scm.py", "winws.py", "lists.py", "settings.py",
                                      "updates.py", "strategies.py", "menu.py", "diagnostics.py",
                                      "tests_runner.py", "misc.py", "router.py", "applog.py")]:
    with open(os.path.join(SIMPLE, f), encoding="utf-8") as fh:
        src_text = fh.read()
    try:
        compile(src_text, f, "exec")
        check(True, f"{f} синтаксически верен")
    except Exception as e:
        check(False, f"{f} ошибка: {e}")

print("\n=== Действия меню вызываются в UI ===")
src = open(os.path.join(SIMPLE, "zapret_pyside.py"), encoding="utf-8").read()
for a in ["service_status", "service_install", "service_remove", "toggle_ipset",
          "toggle_check_updates", "check_updates", "set_game_filter", "menu_status",
          "clear_discord", "restore_payloads", "ipset_update", "update_hosts",
          "remove_conflicts", "relaunch_admin", "tests_prereq"]:
    check(f'"{a}"' in src, f"действие {a}")

print("\n=== Фоновая работа без блокировки UI ===")
check("QThreadPool" in src, "QThreadPool для фоновых операций")
check("Signal(" in src, "результаты через сигналы Qt")
check("root.after(0" not in src, "нет остатков tkinter-подхода")

print("\n=== Локализация i18n ===")
i18n_src = open(os.path.join(SIMPLE, "i18n.py"), encoding="utf-8").read()
check("STRINGS" in i18n_src, "словарь STRINGS объявлен")
check('from i18n import t' in src, "UI подключён к словарю")
check("i18n.save" in src, "переключатель языка сохраняет выбор")

print("\n=== Безопасность ===")
check(os.path.isfile(os.path.join(SIMPLE, "requirements.txt")), "requirements.txt есть")
req = open(os.path.join(SIMPLE, "requirements.txt"), encoding="utf-8").read()
check("PySide6-Essentials" in req, "PySide6-Essentials в зависимостях")
check("flask" not in req.lower().replace("#", ""), "flask удалён (веб-вариант не нужен)")

print("\n=== Итог ===")
if errors:
    for e in errors:
        print("  ОШИБКА:", e)
    sys.exit(1)
else:
    print("  ВСЕ ПРОВЕРКИ ПРОШЛИ — готово без запуска окна.")
