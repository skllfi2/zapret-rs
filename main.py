# Zapret Simple — вне браузера, из нуля, как оригинал
# Запуск: double-click start.bat -> http://127.0.0.1:8765/
#
# Безопасность: мутирующие эндпоинты принимают только POST + заголовок
# X-Zapret-Token (токен отдаётся в index.html). Это закрывает CSRF —
# раньше любая веб-страница могла остановить службу тегом <img>.
from flask import Flask, jsonify, request, abort
import hmac, os
import service_manager
from service_manager import run_service_action  # полная замена service.bat

app = Flask(__name__)
# Каталог zapret определяется автоматически в service_manager (ZAPRET_DIR / AppWatch / Pictures)
ORIG_DIR = service_manager.ORIG_DIR
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSRF_TOKEN = os.urandom(24).hex()  # живёт только до перезапуска сервера
ALLOWED_HOSTS = {"127.0.0.1:8765", "localhost:8765", "127.0.0.1", "localhost"}

@app.before_request
def _guard_host():
    # Защита от DNS rebinding: чужой Host не должен ходить по API, иначе токен читается
    if request.host not in ALLOWED_HOSTS:
        abort(403, description="Host not allowed")

def _check_csrf():
    """Мутирующие запросы: только POST + валидный токен."""
    if request.method != "POST":
        return jsonify({"ok": False, "msg": "Используй POST (CSRF protection)"}), 405
    if not hmac.compare_digest(request.headers.get("X-Zapret-Token", ""), CSRF_TOKEN):
        return jsonify({"ok": False, "msg": "Bad or missing X-Zapret-Token"}), 403
    return None

@app.route("/csrf-token")
def csrf_token():
    # Для Tkinter/скриптов: GET-эндпоинт без side effects
    return jsonify({"token": CSRF_TOKEN})

@app.route("/")
def index():
    with open(os.path.join(BASE_DIR, "index.html"), encoding="utf-8") as f:
        html = f.read()
    # Токен инлайнится в страницу — браузерный JS подставит его в заголовки
    return html.replace("__CSRF_TOKEN__", CSRF_TOKEN)

@app.route("/api/status")
def status():
    try:
        pl = service_manager.payloads_status()
        return jsonify({"running": service_manager.is_running(),
                        "service": service_manager.query_status(),
                        "winws": service_manager.winws_is_running(),
                        "admin": service_manager.is_admin(),
                        "payloads_ok": pl["ok"],
                        "payloads_missing": len(pl["missing"]),
                        "payloads_total": pl["total"],
                        "strategy": service_manager.current_strategy(),
                        "dir": ORIG_DIR})
    except Exception as e:
        return jsonify({"running": False, "service": f"ERR:{e}"})

# === READ-ONLY ===
@app.route("/api/diag")
def diag(): return jsonify(run_service_action("service_diagnostics"))

@app.route("/api/test")
def test_r():
    # GET без запуска: только проверка условий (запуск — POST /api/run_tests,
    # тесты идут минуты и требуют админа)
    return jsonify(run_service_action("tests_prereq"))

# Состояние фонового запуска тестов: веб поллит /api/tests_state
_TESTS = {"running": False, "lines": [], "result": None}

@app.route("/api/run_tests", methods=["POST"])
def run_tests_endpoint():
    if _check_csrf(): return _check_csrf()
    if _TESTS["running"]:
        return jsonify({"ok": False, "msg": "Тесты уже выполняются", "running": True})
    _TESTS.update(running=True, lines=[], result=None)

    def _worker():
        def _on_line(line):
            _TESTS["lines"].append(line)
            if len(_TESTS["lines"]) > 500:
                del _TESTS["lines"][:200]
        try:
            r = run_service_action("run_tests", on_line=_on_line)
        except Exception as e:
            r = {"ok": False, "service": str(e)}
        _TESTS.update(running=False, result=r)

    import threading
    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"ok": True, "running": True,
                    "msg": "Тесты запущены в фоне — полли /api/tests_state"})

@app.route("/api/tests_state")
def tests_state():
    return jsonify(_TESTS)

@app.route("/api/fakes")
def fakes(): return jsonify(run_service_action("list_fakes"))

@app.route("/api/payloads")
def payloads(): return jsonify(run_service_action("payloads_status"))

@app.route("/api/restore_payloads", methods=["POST"])
def restore_payloads():
    if _check_csrf(): return _check_csrf()
    return jsonify(run_service_action("restore_payloads"))

@app.route("/api/game_filter")
def game_filter(): return jsonify(run_service_action("load_game_filter"))

@app.route("/api/menu_status")
def menu_status_ep(): return jsonify(run_service_action("menu_status"))

@app.route("/api/set_game_filter", methods=["POST"])
def set_game_filter_ep():
    if _check_csrf(): return _check_csrf()
    g = lambda k, d: request.form.get(k) or request.args.get(k, d)
    return jsonify(run_service_action("set_game_filter",
                                      mode=g("mode", "disabled"),
                                      tcp=g("tcp", "1024-65535"),
                                      udp=g("udp", "1024-65535")))

@app.route("/api/toggle_check_updates", methods=["POST"])
def toggle_check_updates_ep():
    if _check_csrf(): return _check_csrf()
    en = request.form.get("enable") or request.args.get("enable")
    return jsonify(run_service_action("toggle_check_updates",
                                      enable=None if en is None else en in ("1", "true", "enabled")))

@app.route("/api/toggle_ipset", methods=["POST"])
def toggle_ipset_ep():
    if _check_csrf(): return _check_csrf()
    mode = request.form.get("mode") or request.args.get("mode")
    return jsonify(run_service_action("toggle_ipset", mode=mode))

@app.route("/api/remove_conflicts", methods=["POST"])
def remove_conflicts_ep():
    if _check_csrf(): return _check_csrf()
    return jsonify(run_service_action("remove_conflicts"))

@app.route("/api/hosts_check")
def hosts_check(): return jsonify(run_service_action("update_hosts"))

@app.route("/api/strategies")
def strategies():
    ids = service_manager.list_strategies()
    return jsonify({"strategies": [{"id": i, "name": i} for i in ids]})

@app.route("/api/lists")
def lists():
    d = os.path.join(ORIG_DIR, "lists")
    try: files = sorted(os.listdir(d))
    except OSError: files = []
    return jsonify({"files": files, "dir": d})

@app.route("/api/lists_get")
def lists_get():
    name = os.path.basename((request.args.get("name") or "").replace("\\", "/"))
    if not (name.startswith("list-") or name.startswith("ipset-")) or not name.endswith(".txt"):
        return jsonify({"ok": False, "msg": "Invalid list file"})
    p = os.path.join(ORIG_DIR, "lists", name)
    if os.path.commonpath([os.path.abspath(p), os.path.abspath(os.path.join(ORIG_DIR, "lists"))]) \
            != os.path.abspath(os.path.join(ORIG_DIR, "lists")):
        return jsonify({"ok": False, "msg": "Path escapes lists dir"})
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return jsonify({"ok": True, "file": name, "content": f.read()})
    except OSError as e:
        return jsonify({"ok": False, "msg": str(e)})

# === MUTATING (POST + CSRF) ===
@app.route("/api/start", methods=["POST"])
def start():
    if _check_csrf(): return _check_csrf()
    ok, msg = service_manager.start_service()
    return jsonify({"ok": ok, "service": msg})

@app.route("/api/stop", methods=["POST"])
def stop():
    if _check_csrf(): return _check_csrf()
    ok, msg = service_manager.stop_service()
    return jsonify({"ok": ok, "service": msg})

@app.route("/api/service_install", methods=["POST"])
def svc_install():
    if _check_csrf(): return _check_csrf()
    ok, msg = service_manager.install_service()
    return jsonify({"ok": ok, "service": msg})

@app.route("/api/service_uninstall", methods=["POST"])
def svc_uninstall():
    if _check_csrf(): return _check_csrf()
    ok, msg = service_manager.uninstall_service()
    return jsonify({"ok": ok, "service": msg})

@app.route("/api/update", methods=["POST"])
def update(): 
    if _check_csrf(): return _check_csrf()
    return jsonify(run_service_action("check_updates"))

@app.route("/api/update_ipset", methods=["POST"])
def update_ipset():
    if _check_csrf(): return _check_csrf()
    return jsonify(run_service_action("ipset_update"))

@app.route("/api/update_hosts", methods=["POST"])
def update_hosts():
    if _check_csrf(): return _check_csrf()
    return jsonify(run_service_action("update_hosts"))

@app.route("/api/replace_fakes", methods=["POST"])
def replace_fakes():
    if _check_csrf(): return _check_csrf()
    # type=1 (Discord) / 2 (GameFilter), number — позиция из /api/fakes
    return jsonify(run_service_action("replace_active_fakes",
                                      fake_type=request.form.get("type") or request.args.get("type"),
                                      number=request.form.get("number") or request.args.get("number")))

@app.route("/api/set_strategy", methods=["POST"])
def set_strat():
    if _check_csrf(): return _check_csrf()
    sid = request.form.get("id") or request.args.get("id", "general")
    # Реальное применение: разбор .bat -> binPath службы -> перезапуск (нужен админ)
    return jsonify(run_service_action("apply_strategy", strategy=sid))

@app.route("/api/elevate", methods=["POST"])
def elevate():
    if _check_csrf(): return _check_csrf()
    return jsonify(run_service_action("relaunch_admin"))

@app.route("/api/clear_discord", methods=["POST"])
def clear_discord():
    if _check_csrf(): return _check_csrf()
    return jsonify(run_service_action("clear_discord"))

@app.route("/api/tcp_timestamps", methods=["POST"])
def tcp_timestamps():
    if _check_csrf(): return _check_csrf()
    ok, msg = service_manager.tcp_timestamps()
    return jsonify({"ok": ok, "msg": msg})

@app.route("/api/admin_use", methods=["POST"])
def admin_use():
    if _check_csrf(): return _check_csrf()
    return jsonify(run_service_action("admin"))

@app.route("/api/lists_edit", methods=["POST"])
def lists_edit():
    if _check_csrf(): return _check_csrf()
    name = request.form.get("name") or request.args.get("name")
    content = request.form.get("content") or request.args.get("content")
    if name and content is not None:
        d = os.path.join(ORIG_DIR, "lists")
        # Только базовое имя без сепараторов — защита от path traversal
        name = os.path.basename(name.replace("\\", "/"))
        if not (name.startswith("list-") or name.startswith("ipset-")) or not name.endswith(".txt"):
            return jsonify({"ok": False, "msg": "Invalid list file"})
        p = os.path.join(d, name)
        if os.path.commonpath([os.path.abspath(p), os.path.abspath(d)]) != os.path.abspath(d):
            return jsonify({"ok": False, "msg": "Path escapes lists dir"})
        try:
            with open(p, "w", encoding="utf-8") as f: f.write(content)
            return jsonify({"ok": True, "file": name, "lines": len(content.splitlines())})
        except OSError as e:
            return jsonify({"ok": False, "msg": str(e)})
    return jsonify({"ok": False, "msg": "Invalid list file"})

@app.route("/api/autostart", methods=["POST"])
def autostart():
    if _check_csrf(): return _check_csrf()
    on = (request.form.get("enable") or request.args.get("enable", "true")) == "true"
    try:
        import winreg
        bat = os.path.join(BASE_DIR, "start.bat")
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")
        if on:
            # Python не умеет запускать .bat — оборачиваем в cmd /c
            winreg.SetValueEx(k, "ZapretSimple", 0, winreg.REG_SZ, f'cmd /c start "" "{bat}"')
        else:
            winreg.DeleteValue(k, "ZapretSimple")
        return jsonify({"ok": True, "autostart": on})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})

if __name__ == "__main__":
    # Чистый веб-сервер (без pywebview) — работает через браузер
    # Открыть: http://localhost:8765/
    print(f"Zapret Simple: http://127.0.0.1:8765/  (dir={ORIG_DIR})")
    app.run(host="127.0.0.1", port=8765, debug=False, threaded=True)
