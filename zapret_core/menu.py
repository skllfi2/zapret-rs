# menu.py — шапка меню одним запросом (версия + стратегия + три тумблера)
from .settings import local_version, game_filter_label, check_updates_flag
from .lists import ipset_status
from .strategies import current_strategy
from .misc import is_admin

def menu_status():
    """Все статусы шапки оригинального меню одним запросом."""
    return {"ok": True, "version": local_version(), "strategy": current_strategy(),
            "game_filter": game_filter_label(), "ipset": ipset_status(),
            "check_updates": check_updates_flag(), "admin": is_admin()}
