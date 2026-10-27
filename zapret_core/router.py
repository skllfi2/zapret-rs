# router.py — основной маршрутизатор действий UI (замена service.bat полностью)
from i18n import t

from .diagnostics import remove_conflicts, run_diagnostics
from .lists import ipset_update, load_user_lists, toggle_ipset, update_hosts
from .menu import menu_status
from .misc import admin_use, clear_discord, relaunch_as_admin
from .scm import install_service, query_status, start_service, stop_service, uninstall_service
from .settings import game_filter_status, set_game_filter, toggle_check_updates
from .strategies import apply_strategy
from .tests_runner import best_strategy, run_tests, tests_prerequisites
from .updates import check_updates
from .winws import list_fakes, payloads_status, replace_fakes, restore_payloads, winws_is_running


def run_service_action(action: str = "status_zapret", arg: str = "", **kwargs) -> dict:
    """Основной маршрутизатор — заменяет service.bat полностью.
    kwargs пробрасываются в функцию (например, fake_type/number для replace_active_fakes)."""
    if action == "service_install":
        r = install_service()
        return {"ok": r[0], "service": r[1]}
    if action == "service_remove":
        r = uninstall_service()
        return {"ok": r[0], "service": r[1]}
    if action == "service_status":
        return {"ok": True, "service": query_status()}
    if action == "start":
        r = start_service()
        return {"ok": r[0], "service": r[1]}
    if action == "stop":
        r = stop_service()
        return {"ok": r[0], "service": r[1]}
    if action == "load_game_filter":
        return game_filter_status()
    if action == "load_user_lists":
        return load_user_lists()
    if action == "service_diagnostics" or action == "diagnostics":
        return run_diagnostics()
    if action == "remove_conflicts":
        return remove_conflicts()
    if action == "tests_prereq" or action == "tests_precheck":
        probs = tests_prerequisites()
        return {"ok": not probs, "problems": probs,
                "service": t("tests.prereq_ok") if not probs
                else t("tests.wont_start", p=" | ".join(probs))}
    if action == "run_tests" or action == "test":
        return run_tests(on_line=kwargs.get("on_line"),
                         test_type=kwargs.get("test_type", 1),
                         mode=kwargs.get("mode", 1),
                         selection=kwargs.get("selection"))
    if action == "payloads_status":
        return payloads_status()
    if action == "restore_payloads":
        return restore_payloads(**kwargs)
    if action == "status_zapret":
        return {"ok": True, "service": f"winws.exe running={winws_is_running()}, service={query_status()}"}
    if action == "replace_active_fakes":
        return replace_fakes(**kwargs)
    if action == "list_fakes":
        return list_fakes()
    if action == "check_updates":
        return check_updates()
    if action in ("ipset_update", "update_ipset", "8"):
        return ipset_update()
    if action in ("update_hosts", "hosts_update", "9"):
        return update_hosts()
    if action == "clear_discord":
        return clear_discord()
    if action in ("admin", "admin_use"):
        return admin_use()
    if action == "menu_status":
        return menu_status()
    if action == "set_game_filter":
        return set_game_filter(kwargs.get("mode", "disabled"),
                               kwargs.get("tcp", "1024-65535"),
                               kwargs.get("udp", "1024-65535"))
    if action == "toggle_check_updates":
        return toggle_check_updates(kwargs.get("enable"))
    if action == "toggle_ipset":
        return toggle_ipset(kwargs.get("mode"))
    if action == "apply_strategy":
        return apply_strategy(kwargs.get("strategy") or arg)
    if action == "relaunch_admin":
        ok = relaunch_as_admin()
        return {"ok": ok, "service": t("sm.relaunch_ok") if ok
                else t("sm.relaunch_fail")}
    if action == "best_strategy":
        return best_strategy()
    return {"ok": False, "service": f"Unknown action: {action}"}
