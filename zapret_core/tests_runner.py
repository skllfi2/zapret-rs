# tests_runner.py — порт :run_tests -> utils\test zapret.ps1
# Оригинал просто открывает PowerShell-окно. Здесь: пре-чеки те же, что в ps1,
# запуск того же скрипта, ответы на его Read-Host (тип теста, режим) пишутся в stdin,
# строки вывода отдаются колбэку on_line для живого показа в UI.
import os
import shutil
import subprocess
import time
from collections.abc import Callable

import win32serviceutil

from i18n import t

from .misc import is_admin
from .paths import ORIG_DIR, SERVICE_NAME
from .strategies import list_strategies

# === ТЕСТЫ (порт :run_tests -> utils\test zapret.ps1) ===
# Оригинал просто открывает PowerShell-окно. Здесь: пре-чеки те же, что в ps1,
# запуск того же скрипта, ответы на его Read-Host (тип теста, режим) пишутся в stdin,
# строки вывода отдаются колбэку on_line для живого показа в UI.

def tests_prerequisites() -> list[str]:
    """Пре-чеки test zapret.ps1 — те же условия, но заранее."""
    problems = []
    if not is_admin():
        problems.append(t("tests.need_admin"))
    if not shutil.which("curl"):
        problems.append(t("tests.need_curl"))
    try:
        win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        problems.append(t("tests.service_installed"))
    except Exception:
        pass  # службы нет — это и есть требуемое состояние
    ps1 = os.path.join(ORIG_DIR, "utils", "test zapret.ps1")
    if not os.path.isfile(ps1):
        problems.append(t("tests.script_missing", p=ps1))
    return problems

def _latest_test_result() -> str | None:
    """Последний файл utils/test results/test_results_*.txt (там итог и Best strategy)."""
    d = os.path.join(ORIG_DIR, "utils", "test results")
    try:
        files = [os.path.join(d, f) for f in os.listdir(d)
                 if f.startswith("test_results_") and f.endswith(".txt")]
        return max(files, key=os.path.getmtime) if files else None
    except OSError:
        return None

def run_tests(on_line: Callable | None = None, test_type: int = 1, mode: int = 1,
              selection: list[str] | None = None, timeout: int = 1800) -> dict:
    """Запуск оригинального utils\test zapret.ps1.
    test_type: 1=Standard (HTTP/ping), 2=DPI checkers; mode: 1=All configs, 2=Selected;
    selection — номер конфига при mode=2 (третий Read-Host в оригинале).
    on_line(str) — колбэк на каждую строку вывода (живой прогресс в UI)."""
    problems = tests_prerequisites()
    if problems:
        return {"ok": False, "service": t("tests.not_started", p=" | ".join(problems)),
                "problems": problems}
    ps1 = os.path.join(ORIG_DIR, "utils", "test zapret.ps1")
    started = time.time()
    lines = []
    try:
        p = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1],
            cwd=ORIG_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, errors="replace",
            creationflags=0x08000000)
    except Exception as e:
        return {"ok": False, "service": t("tests.ps_fail", e=e)}
    # Ответы на Read-Host скрипта: тип теста, режим; при Selected — ещё и номер конфига.
    # Пишем сразу — буфер stdin сохранится до чтения скриптом.
    answers = f"{test_type}\n{mode}\n"
    if mode == 2:
        answers += f"{selection or 1}\n"
    try:
        p.stdin.write(answers)
        p.stdin.flush()
    except (BrokenPipeError, OSError):
        pass
    deadline = started + timeout
    try:
        for raw in p.stdout:
            if time.time() > deadline:
                p.kill()
                lines.append(t("tests.timeout"))
                break
            line = raw.rstrip("\r\n")
            lines.append(line)
            if on_line:
                try:
                    on_line(line)
                except Exception:
                    pass
    finally:
        try:
            p.stdin.close()
        except Exception:
            pass
        try:
            p.wait(timeout=15)
        except Exception:
            p.kill()
    # Итог из последнего файла результатов (Best strategy и аналитика)
    tail = ""
    res_file = _latest_test_result()
    if res_file and os.path.getmtime(res_file) >= started - 5:
        try:
            with open(res_file, encoding="utf-8", errors="replace") as f:
                rdata = f.read()
            best = next((ln.strip() for ln in rdata.splitlines()
                         if ln.strip().startswith("Best strategy:")), "")
            tail = f" | {best or t('tests.results_saved')} ({os.path.basename(res_file)})"
        except OSError:
            pass
    joined = "\n".join(lines)
    has_error = "[ERROR]" in joined
    summary = (t("tests.done", t=int(time.time() - started), tail=tail)
               if not has_error else t("tests.aborted"))
    return {"ok": not has_error, "service": summary, "stdout": lines[-60:],
            "results_file": res_file}

def best_strategy() -> dict:
    """Лучшая стратегия из последнего файла результатов тестов (строка
    'Best strategy: X.bat'), приведённая к имени без расширения (как list_strategies)."""
    res_file = _latest_test_result()
    if not res_file:
        return {"ok": False, "strategy": None, "reason": t("tests.best_none")}
    try:
        with open(res_file, encoding="utf-8", errors="replace") as f:
            line = next((ln.strip() for ln in f
                         if ln.strip().startswith("Best strategy:")), "")
    except OSError as e:
        return {"ok": False, "strategy": None, "reason": str(e)}
    if not line:
        return {"ok": False, "strategy": None, "reason": t("tests.best_none")}
    name = line.split(":", 1)[1].strip()
    if name.lower().endswith(".bat"):
        name = name[:-4]
    if name not in list_strategies():
        # Файл от старой версии/чужой копии — не предлагаем несуществующее
        return {"ok": False, "strategy": None, "reason": name,
                "file": os.path.basename(res_file)}
    return {"ok": True, "strategy": name, "file": os.path.basename(res_file)}
