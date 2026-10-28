# smoke_live.py — живой e2e-smoke zapret-simple (то, что нельзя проверить офлайн-тестами)
#
# Шаг 1. Живое применение стратегии end-to-end: разбор *.bat -> binPath службы ->
#        служба Running -> процесс winws.exe реально запущен -> .strategy записан.
# Шаг 2 (--tests). Реальный запуск оригинального utils\test zapret.ps1 по схеме
#        оригинала Remove Services -> Run Tests, с ответами на его Read-Host через stdin,
#        затем применение Best strategy (или прежней стратегии) обратно.
#
# Запуск:
#   python smoke_live.py                       # шаг 1 (при нехватке прав сам спросит UAC)
#   python smoke_live.py --strategy "general (ALT)"
#   python smoke_live.py --tests               # шаги 1+2; шаг 2 УДАЛИТ службу zapret
#   python smoke_live.py --tests --yes --mode 2 --selection 3
#   python smoke_live.py --dry-run             # без прав: только пре-чеки, ничего не меняет
import argparse
import ctypes
import os
import shutil
import sys
import time

import win32serviceutil

from zapret_core.misc import is_admin
from zapret_core.paths import BIN_DIR, ORIG_DIR, SERVICE_NAME
from zapret_core.scm import query_status, uninstall_service
from zapret_core.strategies import apply_strategy, current_strategy, list_strategies, parse_strategy_args
from zapret_core.tests_runner import best_strategy, run_tests, tests_prerequisites
from zapret_core.winws import winws_is_running

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    """Один пункт smoke-отчёта: печатает PASS/FAIL и запоминает для итога."""
    RESULTS.append((bool(ok), name))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def service_installed() -> bool:
    try:
        win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        return True
    except Exception:
        return False


def _relaunch_elevated() -> bool:
    """Перезапуск себя же с правами администратора (UAC). Абсолютные пути: дочерний
    процесс стартует с рабочим каталогом system32, если каталог не задан явно."""
    argv = [os.path.abspath(sys.argv[0]), *sys.argv[1:], "--no-elevate"]
    args = " ".join(f'"{a}"' if " " in a else a for a in argv)
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        h = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, here, 1)
        return h > 32
    except Exception:
        return False


def default_strategy() -> str:
    """Стратегия по умолчанию: последняя применённая, иначе general, иначе первая."""
    known = list_strategies()
    prev = current_strategy()
    if prev in known:
        return prev
    if "general" in known:
        return "general"
    return known[0] if known else ""


def preflight(args: argparse.Namespace) -> str:
    """Пре-чеки среды; возвращает id выбранной стратегии."""
    print("=== Пре-чеки ===")
    admin = is_admin()
    if args.dry_run and not admin:
        print("  [SKIP] права администратора — понадобятся для шагов 1/2 (UAC)")
    else:
        check(admin, "права администратора", "есть" if admin else "нужен UAC")
    check(os.path.isfile(os.path.join(BIN_DIR, "winws.exe")), "winws.exe найден", BIN_DIR)
    ps1 = os.path.join(ORIG_DIR, "utils", "test zapret.ps1")
    check(os.path.isfile(ps1), "test zapret.ps1 найден", ps1)
    check(bool(shutil.which("curl")), "curl в PATH (нужен тестам)")
    strategies = list_strategies()
    check(bool(strategies), "стратегии найдены", f"{len(strategies)} шт.")
    sid = args.strategy or default_strategy()
    parsed, err = parse_strategy_args(sid)
    if err is not None or not parsed:
        check(False, "разбор стратегии", err or "в .bat нет строки winws.exe")
    else:
        check(True, "разбор стратегии", f"{len(parsed)} аргументов winws")
    installed = service_installed()
    print(f"  [INFO] служба zapret: {'установлена' if installed else 'не установлена'},"
          f" статус: {query_status()}")
    return sid


def step_apply(sid: str, dry: bool) -> None:
    """Шаг 1: живое применение стратегии + проверка, что она реально заработала."""
    print(f"\n=== Шаг 1: применение стратегии '{sid}' end-to-end ===")
    if dry:
        print("  [SKIP] --dry-run: служба и winws не трогаются")
        return
    if not is_admin():
        check(False, "применение стратегии", "нет прав администратора (UAC отклонён?)")
        return
    r = apply_strategy(sid, restart=True)
    check(bool(r.get("ok")), "apply_strategy()", str(r.get("service"))[:200])
    if not r.get("ok"):
        return
    running = winws = False
    for _ in range(30):  # ждём старта службы и winws до 15 с
        time.sleep(0.5)
        running, winws = query_status() == "Running", winws_is_running()
        if running and winws:
            break
    check(running, "служба в состоянии Running", query_status())
    check(winws, "процесс winws.exe запущен")
    try:
        binpath = win32serviceutil.QueryServiceConfig(SERVICE_NAME)[3]
    except Exception as e:
        binpath = f"<error: {e}>"
    check("winws.exe" in str(binpath).lower(), "binPath службы указывает на winws.exe",
          str(binpath)[:160])
    saved = current_strategy()
    check(saved == sid, "файл .strategy записан", f"'{saved}'")


def step_tests(args: argparse.Namespace, sid: str) -> None:
    """Шаг 2: Remove Services -> реальный test zapret.ps1 -> Best strategy -> применить."""
    print("\n=== Шаг 2: реальный запуск utils\\test zapret.ps1 ===")
    if args.dry_run:
        print("  [SKIP] --dry-run: служба не удаляется, тесты не запускаются")
        return
    if not is_admin():
        check(False, "запуск тестов", "нужны права администратора")
        return
    # Как в оригинале: тесты требуют отсутствия службы (Remove Services -> Run Tests)
    if service_installed():
        try:
            answer = input("  Служба zapret установлена — удалить перед тестами? [y/N]: ")
        except EOFError:  # stdin не консоль (перенаправлен) — без ручного подтверждения не трогаем
            answer = ""
        yes = args.yes or answer.strip().lower() in ("y", "yes", "д", "да")
        if not yes:
            check(False, "удаление службы перед тестами", "отменено пользователем")
            return
        ok, msg = uninstall_service()
        check(ok, "служба удалена (Remove Services)", str(msg)[:120])
        if not ok:
            return
    problems = tests_prerequisites()
    check(not problems, "пре-чеки test zapret.ps1", " | ".join(problems) if problems else "все ок")
    if problems:
        return

    def on_line(line: str) -> None:
        print("   |", line)

    r = run_tests(on_line=on_line, test_type=args.test_type, mode=args.mode,
                  selection=args.selection, timeout=args.timeout)
    # строки уже напечатаны живьём через on_line — здесь только итог
    check(bool(r.get("ok")), "test zapret.ps1 завершился", str(r.get("service"))[:300])
    if r.get("results_file"):
        print("  [INFO] результаты:", r["results_file"])
    # Возврат в рабочее состояние: Best strategy (или прежняя), как после тестов в оригинале
    best = best_strategy()
    target = best.get("strategy") if best.get("ok") else sid
    if best.get("ok"):
        print("  [INFO] Best strategy:", best.get("strategy"), f"(файл {best.get('file')})")
    elif sid:
        print("  [INFO] Best strategy не найден, возвращаю прежнюю:", best.get("reason"))
    if not target:
        return
    if args.no_apply:
        print(f"  [SKIP] применение '{target}' — --no-apply")
        return
    r2 = apply_strategy(target, restart=True)
    check(bool(r2.get("ok")), f"после тестов применена стратегия '{target}'",
          str(r2.get("service"))[:200])


def summary() -> int:
    fails = [name for ok, name in RESULTS if not ok]
    print("\n=== ИТОГ ЖИВОГО SMOKE ===")
    print(f"  пройдено: {len(RESULTS) - len(fails)} / {len(RESULTS)}")
    for name in fails:
        print("   FAIL:", name)
    if not fails:
        print("  Остался только визуальный чек-лист: SMOKE.md (трей / RU-EN / UAC).")
    return 1 if fails else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Живой e2e-smoke zapret-simple (от администратора)")
    p.add_argument("--strategy", default="", help="id стратегии (имя .bat без расширения)")
    p.add_argument("--tests", action="store_true", help="шаг 2: реальный test zapret.ps1")
    p.add_argument("--yes", "-y", action="store_true", help="не спрашивать подтверждений")
    p.add_argument("--test-type", type=int, default=1, choices=(1, 2), help="1=Standard, 2=DPI")
    p.add_argument("--mode", type=int, default=1, choices=(1, 2), help="1=All configs, 2=Selected")
    p.add_argument("--selection", type=int, default=1, help="номер конфига при --mode 2")
    p.add_argument("--timeout", type=int, default=1800, help="таймаут тестов, с")
    p.add_argument("--no-apply", action="store_true", help="не применять стратегию после тестов")
    p.add_argument("--dry-run", action="store_true", help="только пре-чеки, без изменения системы")
    p.add_argument("--no-elevate", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not args.dry_run and not args.no_elevate and not is_admin():
        print("Нет прав администратора — запрашиваю UAC (откроется новое окно)...")
        if _relaunch_elevated():
            return 0
        print("Повышение прав отклонено — продолжаю, пункты, требующие админа, будут FAIL.")
    sid = preflight(args)
    if not sid:
        check(False, "выбор стратегии", "в каталоге zapret нет .bat со стратегией")
        return summary()
    step_apply(sid, args.dry_run)
    if args.tests:
        step_tests(args, sid)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
