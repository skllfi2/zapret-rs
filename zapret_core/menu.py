# menu.py — шапка меню одним запросом (версия + стратегия + три тумблера)
from .lists import ipset_status
from .misc import is_admin
from .settings import check_updates_flag, game_filter_label, local_version
from .strategies import current_strategy


def menu_status():
    """Все статусы шапки оригинального меню одним запросом."""
    return {"ok": True, "version": local_version(), "strategy": current_strategy(),
            "game_filter": game_filter_label(), "ipset": ipset_status(),
            "check_updates": check_updates_flag(), "admin": is_admin()}
