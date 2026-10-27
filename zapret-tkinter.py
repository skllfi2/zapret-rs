#!/usr/bin/env python3
# zapret-tkinter — ZuiV2-style native GUI for zapret-simple (replaces .bat fully)
# Portable: uses only service_manager.py (pywin32 + stdlib), no pywebview, no .bat
import sys, os, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import service_manager
import i18n
from i18n import t

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
except ImportError:
    print("ERROR: tkinter not available. Python installation missing tkinter.")
    sys.exit(1)

# ZuiV2 palette: dark elegant, subtle borders, rounded buttons, clean spacing
COLORS = {
    "bg_main": "#181825",
    "bg_card": "#202030",
    "bg_header": "#141420",
    "text_primary": "#f0f0f5",
    "text_secondary": "#a0a0b0",
    "text_muted": "#707078",
    "accent": "#d4afff",
    "accent_hover": "#bfa0f0",
    "danger": "#e86060",
    "success": "#5ee87f",
    "border": "#2a2a3a",
    "border_hover": "#3a3a4a",
    "button_bg": "#23233a",
    "button_bg_hover": "#2e2e45",
}

class ZapretApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(t("ui.tk_root_title"))
        self.root.geometry("760x580")
        self.root.minsize(600, 480)
        self.root.configure(bg=COLORS["bg_main"])
        # Center
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w // 2) - 380
        y = (screen_h // 2) - 290
        self.root.geometry(f"760x580+{x}+{y}")

        # Header
        header = tk.Frame(self.root, bg=COLORS["bg_header"], height=72)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)
        tk.Label(header, text="Zapret", font=("Segoe UI", 26, "bold"), fg=COLORS["text_primary"], bg=COLORS["bg_header"]).pack(side="left", padx=20, pady=14)
        # Переключатель языка ru/en (как в вебе и PySide — выбор сохраняется)
        lang_btn = tk.Button(header, text=i18n.LANG.upper(), command=self._switch_lang,
                             bg=COLORS["button_bg"], fg=COLORS["text_primary"],
                             activebackground=COLORS["button_bg_hover"],
                             font=("Segoe UI", 9, "bold"), width=4,
                             relief="flat", bd=1, highlightthickness=1,
                             highlightbackground=COLORS["border"], highlightcolor=COLORS["border_hover"])
        lang_btn.pack(side="left", padx=(0, 14), pady=16)
        # Status pill
        status_pill_frame = tk.Frame(header, bg=COLORS["bg_main"])
        status_pill_frame.pack(side="right", padx=20, pady=16)
        self.dot = tk.Canvas(status_pill_frame, width=14, height=14, bg=COLORS["bg_main"], highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        self.status_text = tk.Label(status_pill_frame, text=t("ui.status_unknown"), font=("Segoe UI", 10, "bold"), fg=COLORS["text_secondary"], bg=COLORS["bg_main"])
        self.status_text.pack(side="left")
        self.payload_warn = tk.Label(status_pill_frame, text="", font=("Segoe UI", 9, "bold"),
                                     fg=COLORS["danger"], bg=COLORS["bg_main"], cursor="hand2")
        self.payload_warn.pack(side="left", padx=(10, 0))
        self.payload_warn.bind("<Button-1>", lambda e: self.run_action("restore_payloads"))

        # Main content card
        content = tk.Frame(self.root, bg=COLORS["bg_card"], bd=0)
        content.pack(fill="both", expand=True, padx=16, pady=14)

        # Section label
        tk.Label(content, text=t("ui.sec_control_tk"), font=("Segoe UI", 9, "bold"), fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 10))

        # Стратегии: реальные .bat из каталога zapret (как в вебе)
        strat_frame = tk.Frame(content, bg=COLORS["bg_card"])
        strat_frame.pack(fill="x", pady=(0, 6))
        tk.Label(strat_frame, text=t("ui.strategy"), font=("Segoe UI", 9, "bold"),
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(side="left", padx=(2, 8))
        self.strat_var = tk.StringVar(value=service_manager.current_strategy() or "")
        self.strat_box = ttk.Combobox(strat_frame, textvariable=self.strat_var, state="readonly",
                                      font=("Segoe UI", 9), width=30)
        self.strat_box.pack(side="left", fill="x", expand=True)
        self.strat_box.bind("<<ComboboxSelected>>", lambda e: self.apply_strategy())
        apply_btn = tk.Button(strat_frame, text=t("ui.apply"), command=self.apply_strategy,
                              bg=COLORS["button_bg"], fg=COLORS["text_primary"],
                              activebackground=COLORS["button_bg_hover"], font=("Segoe UI", 9, "bold"),
                              relief="flat", bd=1, highlightthickness=1,
                              highlightbackground=COLORS["border"], highlightcolor=COLORS["border_hover"])
        apply_btn.pack(side="left", padx=(8, 2))
        try:
            strats = service_manager.list_strategies()
            self.strat_box["values"] = strats
            if not self.strat_var.get() and strats:
                self.strat_var.set("general" if "general" in strats else strats[0])
        except Exception:
            self.strat_box["values"] = []

        # Buttons grid: 4 columns, clean rounded buttons
        btn_defs = [
            (t("ui.tk_status"), lambda: self.run_action("service_status")),
            (t("ui.admin_rights"), lambda: self.run_action("relaunch_admin")),
            (t("ui.tk_install"), lambda: self.run_action("service_install")),
            (t("ui.tk_uninstall"), lambda: self.run_action("service_remove")),
            (t("ui.tk_start"), lambda: self.run_action("start")),
            (t("ui.tk_stop"), lambda: self.run_action("stop")),
            (t("ui.tk_diag"), lambda: self.run_action("service_diagnostics")),
            (t("ui.tk_test"), lambda: self.run_action("test")),
            (t("ui.tk_update"), lambda: self.run_action("check_updates")),
            (t("ui.tk_gamefilter"), lambda: self.run_action("load_game_filter")),
            (t("ui.tk_discord"), lambda: self.run_action("clear_discord")),
            (t("ui.tk_fakes"), lambda: self.show_fakes()),
            (t("ui.tk_restore"), lambda: self.run_action("restore_payloads")),
            (t("ui.tk_ipset"), lambda: self.run_action("ipset_update")),
        ]
        grid_frame = tk.Frame(content, bg=COLORS["bg_card"])
        grid_frame.pack(fill="x", pady=2)
        for i, (label, cmd) in enumerate(btn_defs):
            row, col = i // 2, (i % 2) * 2
            btn = tk.Button(grid_frame, text=label, command=cmd,
                bg=COLORS["button_bg"], fg=COLORS["text_primary"],
                activebackground=COLORS["button_bg_hover"],
                activeforeground=COLORS["text_primary"],
                font=("Segoe UI", 9, "bold"), width=18, height=2,
                relief="flat", bd=1, highlightthickness=1,
                highlightbackground=COLORS["border"], highlightcolor=COLORS["border_hover"])
            btn.grid(row=row, column=col, padx=6, pady=4, sticky="nsew")
        for c in range(4):
            grid_frame.grid_columnconfigure(c, weight=1, minsize=140)

        # Output area
        tk.Label(content, text=t("ui.output"), font=("Segoe UI", 9, "bold"), fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(14, 4))
        self.output = tk.Text(content, bg="#12121a", fg="#e8e8e8",
                              font=("Consolas", 9), height=12,
                              wrap="word", bd=0, highlightthickness=1,
                              highlightbackground=COLORS["border"], highlightcolor=COLORS["border_hover"])
        self.output.pack(fill="both", expand=True, pady=(0, 8))
        self.output.insert("end", t("ui.tk_ready") + "\n")
        self.output.config(state="disabled")

        # Footer
        foot = tk.Label(content, text=t("ui.footer_tk"), bg=COLORS["bg_card"], fg=COLORS["text_muted"], font=("Segoe UI", 7))
        foot.pack(side="bottom", pady=6)

        # Auto-refresh status
        self.refresh()
        self.root.mainloop()

    def _switch_lang(self):
        """Переключатель ru/en: сохраняет выбор и пересоздаёт окно."""
        i18n.save("en" if i18n.LANG == "ru" else "ru")
        self._restart = True
        self.root.destroy()

    def refresh(self):
        """Обновление статуса + планирование следующего опроса (ровно один цикл)."""
        self.update_status()
        self.root.after(3000, self.refresh)

    def update_status(self):
        # Отдельно от refresh: кнопки вызывают только это, чтобы не плодить таймеры
        try:
            s = service_manager.query_status()
            running = service_manager.is_running()
            self.status_text.config(text=s, fg=COLORS["success"] if running else COLORS["danger"])
            # Draw dot
            self.dot.delete("all")
            self.dot.create_oval(2, 2, 12, 12, fill=COLORS["success"] if running else COLORS["danger"], outline="")
        except Exception as e:
            self.status_text.config(text=f"ERR: {str(e)[:30]}", fg=COLORS["danger"])
            self.dot.delete("all")
            self.dot.create_oval(2, 2, 12, 12, fill=COLORS["danger"], outline="")
        # Предупреждение о недостающих payload-файлах (клик = восстановить)
        try:
            pl = service_manager.payloads_status()
            if pl["ok"]:
                self.payload_warn.config(text="")
            else:
                self.payload_warn.config(text=t("ui.payload_warn_tk", n=len(pl['missing'])))
        except Exception:
            self.payload_warn.config(text="")

    def append_output(self, text):
        self.output.config(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.config(state="disabled")

    def show_fakes(self):
        """Список fake-файлов + выбор для замены (аналог :replace_active_fakes в service.bat)."""
        import tkinter.simpledialog
        r = service_manager.run_service_action("list_fakes")
        items = r.get("stdout") or []
        if not items:
            self.append_output(t("ui.no_bins"))
            return
        lines = []
        num = 0
        for f in items:
            mark = "[ACTIVE]" if f.get("active") else ""
            if not f.get("active"):
                num += 1
                lines.append(f"  {num}. {f['name']}  {f['sha256']}{mark}")
            else:
                lines.append(f"  *  {f['name']}  {f['sha256']}{mark}")
        self.append_output(t("ui.fakes_list") + "\n" + "\n".join(lines))
        choice = tkinter.simpledialog.askstring(
            t("ui.fake_dialog_title"),
            t("ui.tk_fake_prompt") + "\n\n" + "\n".join(lines),
            parent=self.root)
        if not choice:
            return
        parts = choice.split()
        if len(parts) != 2:
            self.append_output(t("ui.tk_format_err"))
            return
        rr = service_manager.run_service_action("replace_active_fakes",
                                                fake_type=parts[0], number=parts[1])
        self.append_output(f"[{'OK' if rr.get('ok') else 'ERR'}] {rr.get('stdout') or rr.get('stderr')}")

    def apply_strategy(self):
        """Применение выбранной стратегии в фоне (перезапуск службы — долго, UI не должен виснуть)."""
        sid = self.strat_var.get()
        if not sid:
            self.append_output(t("ui.tk_strategy_err"))
            return
        if not service_manager.is_admin():
            self.append_output(t("ui.tk_need_admin"))
            return
        self.append_output(t("ui.tk_applying", s=sid))
        threading.Thread(target=self._apply_strategy_worker, args=(sid,), daemon=True).start()

    def _apply_strategy_worker(self, sid):
        r = service_manager.apply_strategy(sid)
        # Вывод в Tkinter только через mainloop — планируем в главный поток
        msg = f"[{'OK' if r.get('ok') else 'ERR'}] {r.get('service')}"
        self.root.after(0, lambda: self.append_output(msg))
        self.root.after(0, self.update_status)

    def run_action(self, action):
        self.append_output(t("ui.tk_running", a=action))
        # В фоне: sc/netsh/ipset могут занимать секунды — не блокируем UI
        threading.Thread(target=self._run_action_worker, args=(action,), daemon=True).start()

    def _run_action_worker(self, action):
        extra = []
        try:
            r = service_manager.run_service_action(action)
            if isinstance(r, tuple):
                ok, msg = r
                result = f"[{'OK' if ok else 'ERR'}] {msg}"
            elif isinstance(r, dict):
                if r.get("checks"):
                    # Диагностика: чек-лист, как PrintGreen/PrintYellow/PrintRed
                    for ch in r["checks"]:
                        mark = {"ok": "[+]", "warn": "[?]", "bad": "[X]"}.get(ch.get("level"), "   ")
                        extra.append(f"{mark} {ch.get('name')}: {ch.get('msg')}")
                        if ch.get("url"):
                            extra.append(f"      {ch['url']}")
                ok = r.get("ok", False)
                msg = r.get("service", r.get("stdout", r.get("stderr", "")))
                if isinstance(msg, bytes):
                    msg = msg.decode("utf-8", errors="replace")
                if isinstance(msg, list):
                    msg = "; ".join(str(m) for m in msg[:10])
                result = f"[{'OK' if ok else 'ERR'}] {str(msg)[:300]}"
            else:
                result = str(r)[:200]
        except Exception as e:
            result = f"{t('ui.tk_error')} {str(e)[:200]}"
        # Вывод — только в главном потоке mainloop
        self.root.after(0, lambda: [self.append_output(x) for x in extra])
        self.root.after(0, lambda: self.append_output(result))
        self.root.after(0, self.update_status)  # не refresh() — иначе каждый клик добавлял бы новый таймер

if __name__ == "__main__":
    # Пересоздание окна после смены языка (i18n.save -> destroy -> новый цикл)
    while True:
        app = ZapretApp()
        if not getattr(app, "_restart", False):
            break
