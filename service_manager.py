# service_manager.py — публичный фасад ядра zapret-simple.
# Реальный код живёт в пакете zapret_core/ (paths, scm, winws, lists, settings,
# updates, strategies, menu, diagnostics, tests_runner, misc, router); сюда
# переэкспортируются все публичные имена, поэтому импорты вида
# `from service_manager import X` (zapret_pyside.py, тесты) работают как раньше.
#
# Строки import ниже — не мёртвый код, а точка патчинга для тестов:
# mock.patch("service_manager.subprocess.run") резолвится в этот атрибут и
# патчит общий модуль subprocess для всех модулей zapret_core.
import os               # noqa: F401
import subprocess       # noqa: F401
import win32serviceutil  # noqa: F401

from zapret_core.paths import (ORIG_DIR, BIN_DIR, LISTS_DIR, SERVICE_NAME,
                               SERVICE_DISPLAY, APP_DIR, STRATEGY_FILE,
                               LEGACY_STRATEGY_FILE, get_bin_path, _detect_orig_dir)
from zapret_core.scm import (install_service, uninstall_service, start_service,
                             stop_service, set_autostart, SERVICE_STATES,
                             query_status, is_running)
from zapret_core.winws import (winws_is_running, replace_fakes, list_fakes,
                               payloads_status, find_payload_source,
                               restore_payloads)
from zapret_core.lists import (ipset_update, ipset_status, toggle_ipset,
                               load_user_lists, update_hosts)
from zapret_core.settings import (game_filter_status, game_filter_label,
                                  set_game_filter, check_updates_flag,
                                  toggle_check_updates, local_version)
from zapret_core.updates import apply_zapret_update, check_updates
from zapret_core.selfupdate import (APP_VERSION, SELF_UPDATE_REPO, check_app_update,
                                    update_app)
from zapret_core.strategies import (list_strategies, parse_strategy_args,
                                    apply_strategy, current_strategy,
                                    default_strategy, format_exe_args,
                                    _game_filter_ranges)
from zapret_core.menu import menu_status
from zapret_core.diagnostics import (tcp_timestamps, run_diagnostics,
                                     remove_conflicts)
from zapret_core.tests_runner import (tests_prerequisites, run_tests,
                                      _latest_test_result, best_strategy)
from zapret_core.misc import (is_admin, admin_use, hidden_cmd, clear_discord,
                              relaunch_as_admin, decode_output)
from zapret_core.router import run_service_action

__all__ = [n for n in dir() if not n.startswith("__")]
