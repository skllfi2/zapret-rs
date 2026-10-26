#!/usr/bin/env python3
# zapret-tkinter — ZuiV2-style native GUI for zapret-simple (replaces .bat fully)
# Portable: uses only service_manager.py (pywin32 + stdlib), no pywebview, no .bat
import sys, os, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import service_manager

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
        self.root.title("Zapret — DPI Bypass")
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
        # Status pill
        status_pill_frame = tk.Frame(header, bg=COLORS["bg_main"])
        status_pill_frame.pack(side="right", padx=20, pady=16)
        self.dot = tk.Canvas(status_pill_frame, width=14, height=14, bg=COLORS["bg_main"], highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        self.status_text = tk.Label(status_pill_frame, text="Неизвестно", font=("Segoe UI", 10, "bold"), fg=COLORS["text_secondary"], bg=COLORS["bg_main"])
        self.status_text.pack(side="left")

        # Main content card
        content = tk.Frame(self.root, bg=COLORS["bg_card"], bd=0)
        content.pack(fill="both", expand=True, padx=16, pady=14)

        # Section label
        tk.Label(content, text="УПРАВЛЕНИЕ СЕРВИСОМ (SCM — без .bat)", font=("Segoe UI", 9, "bold"), fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 10))

        # Buttons grid: 4 columns, clean rounded buttons
        btn_defs = [
            ("Status", lambda: self.run_action("service_status")),
            ("Install Svc", lambda: self.run_action("service_install")),
            ("Uninstall", lambda: self.run_action("service_remove")),
            ("Start", lambda: self.run_action("start")),
            ("Stop", lambda: self.run_action("stop")),
            ("Diag", lambda: self.run_action("service_diagnostics")),
            ("Test", lambda: self.run_action("test")),
            ("Update", lambda: self.run_action("check_updates")),
            ("GameFilter", lambda: self.run_action("load_game_filter")),
            ("Clear Discord", lambda: self.run_action("clear_discord")),
            ("List Fakes", lambda: self.show_fakes()),
            ("IPSet Update", lambda: self.run_action("ipset_update")),
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
        tk.Label(content, text="ВЫВОД", font=("Segoe UI", 9, "bold"), fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(14, 4))
        self.output = tk.Text(content, bg="#12121a", fg="#e8e8e8",
                              font=("Consolas", 9), height=12,
                              wrap="word", bd=0, highlightthickness=1,
                              highlightbackground=COLORS["border"], highlightcolor=COLORS["border_hover"])
        self.output.pack(fill="both", expand=True, pady=(0, 8))
        self.output.insert("end", "Готово. Нажми любую кнопку.\nВсе функции работают через service_manager (без .bat).\n")
        self.output.config(state="disabled")

        # Footer
        foot = tk.Label(content, text="zapret-simple — native SCM (pywin32) | без service.bat | Python 3.15+", bg=COLORS["bg_card"], fg=COLORS["text_muted"], font=("Segoe UI", 7))
        foot.pack(side="bottom", pady=6)

        # Auto-refresh status
        self.refresh()
        self.root.mainloop()

    def refresh(self):
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
        self.root.after(3000, self.refresh)

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
            self.append_output("[ERR] Нет .bin файлов в bin/")
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
        self.append_output("Fake-файлы:\n" + "\n".join(lines))
        choice = tkinter.simpledialog.askstring(
            "Replace Active Fake",
            "Введите: тип (1=Discord UDP, 2=GameFilter UDP) и номер fake-файла\n"
            "Например: 1 3\n\n" + "\n".join(lines),
            parent=self.root)
        if not choice:
            return
        parts = choice.split()
        if len(parts) != 2:
            self.append_output("[ERR] Формат: <тип> <номер>, например 1 3")
            return
        rr = service_manager.run_service_action("replace_active_fakes",
                                                fake_type=parts[0], number=parts[1])
        self.append_output(f"[{'OK' if rr.get('ok') else 'ERR'}] {rr.get('stdout') or rr.get('stderr')}")

    def run_action(self, action):
        self.append_output(f">>> Выполняется: {action}")
        self.root.update()
        try:
            r = service_manager.run_service_action(action)
            if isinstance(r, tuple):
                ok, msg = r
                result = f"[{'OK' if ok else 'ERR'}] {msg}"
            elif isinstance(r, dict):
                ok = r.get("ok", False)
                msg = r.get("service", r.get("stdout", r.get("stderr", "")))
                if isinstance(msg, bytes):
                    msg = msg.decode("utf-8", errors="replace")
                result = f"[{'OK' if ok else 'ERR'}] {str(msg)[:200]}"
            else:
                result = str(r)[:200]
            self.append_output(result)
        except Exception as e:
            self.append_output(f"[ОШИБКА] {str(e)[:200]}")
        self.refresh()

if __name__ == "__main__":
    ZapretApp()
