# Проверка zapret-simple без запуска окна (максимально просто)
import os, sys

ORIG = r"C:\Users\dexox\Pictures\zapret-discord-youtube"
SIMPLE = r"F:\Development\Dev\mydev\zapret-simple"

errors = []

def check(p, msg):
    if not p: errors.append(msg)
    else: print("  OK:", msg)

print("=== Структура zapret-simple ===")
for f in ["main.py", "index.html", "start.bat", "update.bat"]:
    check(os.path.isfile(os.path.join(SIMPLE, f)), f"{f} есть")

print("\n=== Оригинал доступен ===")
check(os.path.isfile(os.path.join(ORIG, "service.bat")), "service.bat в оригинале")
check(os.path.isfile(os.path.join(ORIG, "general.bat")), "general.bat в оригинале")

print("\n=== Python 3.15+ ===")
import subprocess
res = subprocess.run([r"C:\Users\dexox\AppData\Local\Python\pythoncore-3.15-64\python.exe", "--version"], capture_output=True, text=True)
check(res.stdout.strip().startswith("Python 3.15"), f"Python 3.15.x (получено: {res.stdout.strip()})")

print("\n=== Синтаксис main.py ===")
try:
    compile(open(os.path.join(SIMPLE,"main.py")).read(), "main.py", "exec")
    check(True, "main.py синтаксически верен")
except Exception as e:
    check(False, f"main.py ошибка: {e}")

print("\n=== Конечные точки (endpoints) ===")
content = open(os.path.join(SIMPLE,"main.py"), encoding="utf-8").read()
for ep in ["/api/update", "/api/status", "/api/start", "/api/stop", "/api/diag", "/api/lists"]:
    check(f'"{ep}"' in content, f"endpoint {ep}")

print("\n=== Мутирующие эндпоинты защищены CSRF ===")
check('X-Zapret-Token' in content, "проверка X-Zapret-Token")
check('methods=["POST"]' in content, "мутирующие — только POST")

print("\n=== HTML ссылается на /api/update ===")
html = open(os.path.join(SIMPLE,"index.html"), encoding="utf-8").read()
check("post('api/update')" in html, "post('api/update') в HTML")
check("api/update" in html, "api/update в HTML")

print("\n=== start.bat указывает на Python 3.15 ===")
bat = open(os.path.join(SIMPLE, "start.bat")).read()
check("pythoncore-3.15-64" in bat, "start.bat ссылается на pythoncore-3.15-64")

print("\n=== Итог ===")
if errors:
    for e in errors: print("  ОШИБКА:", e)
    sys.exit(1)
else:
    print("  ВСЕ ПРОВЕРКИ ПРОШЛИ — готово без запуска окна.")
