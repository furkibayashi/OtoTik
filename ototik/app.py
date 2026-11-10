"""OtoTık arayüzü."""
import os
import queue
import sys
import time
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk

from . import engine, themes
from .config import (APP_NAME, CONFIG_DIR, MACRO_DIR, VERSION, Config)
from .i18n import LANGUAGES, T, detect_language, set_language

REPO_URL = "https://github.com/furkibayashi/OtoTik"

PAGES = [
    ("clicker", "◉"),
    ("keys", "⌨"),
    ("typer", "✎"),
    ("macro", "⏺"),
    ("trigger", "◎"),
    ("cpstest", "⚡"),
    ("settings", "⚙"),
]
TASK_NAMES = ("clicker", "keys", "typer", "macro", "trigger")
HOTKEY_ACTIONS = ("clicker", "keys", "typer", "macro_play", "macro_record", "trigger",
                  "add_point", "stop_all", "hide")
LAST_MACRO = os.path.join(MACRO_DIR, "last_recording.json")


class Seg(ctk.CTkFrame):
    """Tema renklerine tam uyumlu segment seçici."""

    def __init__(self, master, app, options, value, command=None, height=30):
        super().__init__(master, fg_color=app.p["card2"], corner_radius=9)
        self.app, self.command, self.value = app, command, value
        self.btns = {}
        for i, (val, label) in enumerate(options):
            b = ctk.CTkButton(self, text=label, height=height, width=20, corner_radius=7,
                              font=app.font(12, "bold"), command=lambda v=val: self.select(v, True))
            b.grid(row=0, column=i, padx=3, pady=3, sticky="ew")
            self.grid_columnconfigure(i, weight=1, uniform="seg")
            self.btns[val] = b
        self.select(value)

    def select(self, v, user=False):
        p = self.app.p
        self.value = v
        for val, b in self.btns.items():
            on = val == v
            b.configure(fg_color=p["accent"] if on else "transparent",
                        text_color=p["accent_text"] if on else p["text"],
                        hover_color=p["accent_hover"] if on else p["hover"])
        if user and self.command:
            self.command(v)


class NavItem(ctk.CTkFrame):
    """Yan menü öğesi: simge + metin + çalışma durumu noktası."""

    def __init__(self, master, app, icon, text, command):
        super().__init__(master, fg_color=app.p["side"], corner_radius=8)
        self.app, self.active, self.hover = app, False, False
        self.icon = ctk.CTkLabel(self, text=icon, width=26, font=app.font(15))
        self.icon.pack(side="left", padx=(12, 6), pady=5)
        self.text = ctk.CTkLabel(self, text=text, font=app.font(13, "bold"), anchor="w")
        self.text.pack(side="left", fill="x", expand=True, pady=5)
        self.dot = ctk.CTkLabel(self, text="", width=16, font=app.font(12))
        self.dot.pack(side="right", padx=(0, 10))
        for w in (self, self.icon, self.text, self.dot):
            w.bind("<Button-1>", lambda e=None: command())
            w.bind("<Enter>", lambda e=None: self._set_hover(True))
            w.bind("<Leave>", lambda e=None: self.after(15, self._check_leave))
        self._dot_color = None
        self._paint()

    def _check_leave(self):
        try:
            x, y = self.winfo_pointerxy()
            inside = (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width() and
                      self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height())
        except Exception:
            inside = False
        if not inside:
            self._set_hover(False)

    def _set_hover(self, v):
        if v != self.hover:
            self.hover = v
            self._paint()

    def set_active(self, v):
        self.active = v
        self._paint()

    def set_dot(self, color):
        if color == self._dot_color:
            return
        self._dot_color = color
        self.dot.configure(text="●" if color else "", text_color=color or self.app.p["sub"])

    def _paint(self):
        p = self.app.p
        bg = p["accent_soft"] if self.active else (p["hover"] if self.hover else p["side"])
        fg = p["accent"] if self.active else p["text"]
        self.configure(fg_color=bg)
        self.icon.configure(text_color=fg)
        self.text.configure(text_color=fg)


class App:
    def __init__(self):
        self.cfg = Config()
        self.cfg["stats"]["launches"] += 1
        if not self.cfg["app"]["language"]:
            self.cfg["app"]["language"] = detect_language()
        set_language(self.cfg["app"]["language"])

        self.q = queue.Queue()
        self.post = self.q.put
        self.p = themes.apply(self.cfg["app"]["theme"], self.cfg["app"]["accent"])
        ctk.set_widget_scaling(self.cfg["app"]["ui_scale"])

        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} {VERSION}")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self._set_icon()

        self.hub = engine.InputHub(self.post)
        self.tasks = {
            "clicker": engine.Clicker(self),
            "keys": engine.KeyPresser(self),
            "typer": engine.Typer(self),
            "macro": engine.MacroPlayer(self),
            "trigger": engine.PixelTrigger(self),
        }
        self.recorder = None
        self.macro_name = ""
        self.logs = []
        self.updaters = []
        self.visible = True
        self.capturing = None
        self.cps_state = None
        self._schedule_fired = ""
        self._osd_win = None
        self._page_frame = None
        self._load_last_macro()
        self.apply_bindings()

        self.build()
        geo = self.cfg["app"]["geometry"]
        if geo and not self.cfg["app"]["compact"]:
            try:
                self.root.geometry(geo)
            except Exception:
                pass
        self.apply_window_attrs()
        self.log(T("log_ready", v=VERSION))
        if not engine.is_admin():
            self.log(T("log_not_admin"))
        self.root.after(100, self.tick)

    # ------------------------------------------------------------------ yardımcılar
    def font(self, size=13, weight="normal"):
        return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)

    def _set_icon(self):
        for base in (getattr(sys, "_MEIPASS", ""), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
            ico = os.path.join(base, "assets", "icon.ico")
            if base and os.path.exists(ico):
                try:
                    self.root.iconbitmap(ico)
                    self.root.after(250, lambda i=ico: self.root.iconbitmap(i))
                except Exception:
                    pass
                return

    def apply_window_attrs(self):
        try:
            self.root.attributes("-topmost", bool(self.cfg["app"]["topmost"]))
            self.root.attributes("-alpha", max(0.3, min(1.0, float(self.cfg["app"]["opacity"]))))
        except Exception:
            pass

    def apply_bindings(self):
        hold = ["clicker"] if self.cfg["clicker"]["hold_to_run"] else []
        self.hub.set_bindings(self.cfg["hotkeys"], hold)

    def hk(self, action):
        return engine.pretty_combo(self.cfg["hotkeys"].get(action, ""))

    def log(self, msg):
        stamp = time.strftime("%H:%M:%S")
        self.logs.append(f"[{stamp}] {msg}")
        del self.logs[:-300]
        self._last_status = msg
        try:
            self.w_status.configure(text=msg)
        except Exception:
            pass
        try:
            if self.w_log.winfo_exists():
                self.w_log.configure(state="normal")
                self.w_log.insert("end", f"[{stamp}] {msg}\n")
                self.w_log.see("end")
                self.w_log.configure(state="disabled")
        except Exception:
            pass

    def sound(self, kind):
        engine.beep(kind, self.cfg["app"]["sound"])

    def osd(self, text, color=None):
        """Ekranın üst ortasında kısa bildirim (pencere gizliyken de görünür)."""
        if not self.cfg["app"].get("osd", True):
            return
        try:
            if self._osd_win is not None:
                self._osd_win.destroy()
        except Exception:
            pass
        p = self.p
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        try:
            w.attributes("-alpha", 0.92)
        except Exception:
            pass
        w.configure(bg=color or p["accent"])
        tk.Label(w, text=text, bg=p["card"], fg=p["text"], font=("Segoe UI", 12, "bold"),
                 padx=18, pady=8).pack(padx=2, pady=2)
        w.update_idletasks()
        sw = w.winfo_screenwidth()
        w.geometry(f"+{(sw - w.winfo_reqwidth()) // 2}+{40}")
        self._osd_win = w
        w.after(1300, lambda: w.destroy() if w.winfo_exists() else None)

    # ------------------------------------------------------------------ inşa
    def build(self):
        for child in self.root.winfo_children():
            child.destroy()
        self.updaters = []
        self.root.configure(fg_color=self.p["bg"])
        if self.cfg["app"]["compact"]:
            self.build_compact()
        else:
            self.build_full()

    def rebuild(self):
        self.p = themes.apply(self.cfg["app"]["theme"], self.cfg["app"]["accent"])
        ctk.set_widget_scaling(self.cfg["app"]["ui_scale"])
        set_language(self.cfg["app"]["language"])
        self._last_status = ""
        self.build()

    def build_full(self):
        p = self.p
        self.root.resizable(True, True)
        self.root.minsize(820, 560)
        if not self.cfg["app"]["geometry"]:
            self.root.geometry("940x660")

        side = ctk.CTkFrame(self.root, fg_color=p["side"], corner_radius=0, width=200)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        logo = ctk.CTkFrame(side, fg_color="transparent")
        logo.pack(fill="x", padx=18, pady=(20, 18))
        ctk.CTkLabel(logo, text="●", text_color=p["accent"], font=self.font(26, "bold")).pack(side="left")
        ctk.CTkLabel(logo, text=" " + APP_NAME, font=self.font(22, "bold")).pack(side="left")

        self.nav_btns = {}
        for key, icon in PAGES:
            item = NavItem(side, self, icon, T("nav_" + key), lambda k=key: self.show_page(k))
            item.pack(fill="x", padx=10, pady=2)
            self.nav_btns[key] = item

        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=10, pady=12)
        ctk.CTkButton(bottom, text="⇲  " + T("mini_mode"), height=32, fg_color=p["card"],
                      hover_color=p["hover"], text_color=p["text"], font=self.font(12),
                      command=self.toggle_compact).pack(fill="x", pady=(0, 6))
        ctk.CTkButton(bottom, text="■  " + T("stop_all") + f"  ({self.hk('stop_all')})", height=34,
                      fg_color=p["err"], hover_color=themes.mix(p["err"], "#000000", 0.2),
                      text_color="#ffffff", font=self.font(12, "bold"),
                      command=self.stop_all).pack(fill="x")
        ctk.CTkLabel(bottom, text=f"v{VERSION}", text_color=p["sub"], font=self.font(11)).pack(pady=(8, 0))

        main = ctk.CTkFrame(self.root, fg_color=p["bg"], corner_radius=0)
        main.pack(side="left", fill="both", expand=True)

        status = ctk.CTkFrame(main, fg_color=p["side"], corner_radius=0, height=34)
        status.pack(side="bottom", fill="x")
        status.pack_propagate(False)
        self.w_status = ctk.CTkLabel(status, text=getattr(self, "_last_status", ""), anchor="w",
                                     text_color=p["sub"], font=self.font(12))
        self.w_status.pack(side="left", fill="x", expand=True, padx=14)
        self.w_admin = ctk.CTkLabel(status, text=("🛡 " + T("admin")) if engine.is_admin() else "",
                                    text_color=p["ok"], font=self.font(11))
        self.w_admin.pack(side="right", padx=12)

        self.content = ctk.CTkFrame(main, fg_color="transparent")
        self.content.pack(fill="both", expand=True)
        self.show_page(self.cfg["app"]["page"] if self.cfg["app"]["page"] in dict(PAGES) else "clicker")

    def show_page(self, key):
        p = self.p
        self.cfg["app"]["page"] = key
        if self.cps_state and key != "cpstest":
            self.cps_state = None
        for k, b in self.nav_btns.items():
            b.set_active(k == key)
        for child in self.content.winfo_children():
            child.destroy()
        self.updaters = [u for u in self.updaters if getattr(u, "_global", False)]
        self.w_log = None

        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 6))
        txt = ctk.CTkFrame(header, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(txt, text=T("nav_" + key), font=self.font(24, "bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(txt, text=T("desc_" + key), text_color=p["sub"], font=self.font(12), anchor="w",
                     justify="left", wraplength=480).pack(anchor="w")
        if key in TASK_NAMES:
            self.start_button(header, key).pack(side="right")

        body = ctk.CTkScrollableFrame(self.content, fg_color="transparent",
                                      scrollbar_button_color=p["muted"],
                                      scrollbar_button_hover_color=p["accent"])
        body.pack(fill="both", expand=True, padx=12, pady=(4, 8))
        getattr(self, "page_" + key)(body)

    # --- ortak bileşenler ---
    def card(self, parent, title=None, hint=None):
        p = self.p
        outer = ctk.CTkFrame(parent, fg_color=p["card"], corner_radius=12, border_width=1,
                             border_color=p["border"])
        outer.pack(fill="x", padx=12, pady=7)
        if title:
            ctk.CTkLabel(outer, text=title, font=self.font(14, "bold"), anchor="w").pack(
                anchor="w", padx=16, pady=(12, 0))
        if hint:
            ctk.CTkLabel(outer, text=hint, font=self.font(11), text_color=p["sub"], anchor="w",
                         justify="left", wraplength=560).pack(anchor="w", padx=16)
        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(8, 14))
        return inner

    def row(self, parent, pady=4):
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", pady=pady)
        return r

    def lbl(self, parent, text, sub=False, size=13, bold=False, **kw):
        return ctk.CTkLabel(parent, text=text, font=self.font(size, "bold" if bold else "normal"),
                            text_color=self.p["sub"] if sub else self.p["text"], **kw)

    def num(self, parent, sec, key, width=80, kind=int, lo=0, hi=None, on_change=None, allow_empty=False):
        var = tk.StringVar(value=str(self.cfg[sec][key]))
        ent = ctk.CTkEntry(parent, textvariable=var, width=width, justify="center")

        def changed(*_):
            s = var.get().strip().replace(",", ".")
            try:
                if allow_empty and s == "":
                    val = ""
                else:
                    val = kind(float(s)) if kind is int else kind(s)
                    if lo is not None and val < lo:
                        raise ValueError
                    if hi is not None and val > hi:
                        raise ValueError
                self.cfg[sec][key] = val
                self.cfg.save_later()
                ent.configure(border_color=self.p["border"])
                if on_change:
                    on_change(val)
            except (ValueError, TypeError):
                ent.configure(border_color=self.p["err"])
        var.trace_add("write", changed)
        ent._var = var
        return ent

    def text_entry(self, parent, sec, key, width=160, on_change=None, placeholder=""):
        var = tk.StringVar(value=str(self.cfg[sec][key]))

        def changed(*_):
            self.cfg[sec][key] = var.get()
            self.cfg.save_later()
            if on_change:
                on_change(var.get())
        var.trace_add("write", changed)
        ent = ctk.CTkEntry(parent, textvariable=var, width=width, placeholder_text=placeholder)
        ent._var = var
        return ent

    def switch(self, parent, text, sec, key, on_change=None):
        var = tk.BooleanVar(value=bool(self.cfg[sec][key]))

        def changed():
            self.cfg[sec][key] = bool(var.get())
            self.cfg.save_later()
            if on_change:
                on_change(bool(var.get()))
        sw = ctk.CTkSwitch(parent, text=text, variable=var, onvalue=True, offvalue=False,
                           command=changed, font=self.font(13))
        return sw

    def seg(self, parent, sec, key, options, on_change=None):
        def changed(v):
            self.cfg[sec][key] = v
            self.cfg.save_later()
            if on_change:
                on_change(v)
        return Seg(parent, self, options, self.cfg[sec][key], changed)

    def field(self, parent, label, widget_factory, hint=None):
        """Etiket + widget satırı."""
        r = self.row(parent)
        self.lbl(r, label, width=190, anchor="w").pack(side="left")
        w = widget_factory(r)
        w.pack(side="left")
        if hint:
            self.lbl(r, hint, sub=True, size=11).pack(side="left", padx=8)
        return w

    def start_button(self, parent, task):
        p = self.p
        b = ctk.CTkButton(parent, height=44, width=190, corner_radius=10, font=self.font(14, "bold"),
                          command=lambda: self.toggle_task(task))
        hk = {"macro": "macro_play"}.get(task, task)

        def upd():
            t = self.tasks[task]
            if t.running:
                state = T("btn_stop")
                b.configure(text=f"■  {state}   {self.hk(hk)}", fg_color=p["err"],
                            hover_color=themes.mix(p["err"], "#000000", 0.2), text_color="#ffffff")
            else:
                b.configure(text=f"▶  {T('btn_start')}   {self.hk(hk)}", fg_color=p["ok"],
                            hover_color=themes.mix(p["ok"], "#000000", 0.2),
                            text_color=themes.readable_text(p["ok"]))
        upd()
        self.updaters.append(upd)
        return b

    def stat_tiles(self, parent, items):
        """items: [(başlık, değer_fonksiyonu)]"""
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", padx=12, pady=(4, 6))
        labels = []
        for i, (title, fn) in enumerate(items):
            f = ctk.CTkFrame(r, fg_color=self.p["card"], corner_radius=12, border_width=1,
                             border_color=self.p["border"])
            f.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            r.grid_columnconfigure(i, weight=1, uniform="tiles")
            self.lbl(f, title, sub=True, size=11).pack(anchor="w", padx=14, pady=(10, 0))
            v = ctk.CTkLabel(f, text="0", font=self.font(22, "bold"), text_color=self.p["accent"])
            v.pack(anchor="w", padx=14, pady=(0, 10))
            labels.append((v, fn))

        def upd():
            for v, fn in labels:
                v.configure(text=fn())
        upd()
        self.updaters.append(upd)

    @staticmethod
    def fmt_time(sec):
        sec = int(sec)
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def task_elapsed(self, t):
        if t.running and t.state == "running":
            return time.time() - t.started_at
        if t.running and t.state == "waiting":
            return 0
        return getattr(t, "_last_elapsed", 0)

    def countdown_pick(self, button, seconds, done):
        """Butonda geri sayım yapıp imleç konumunu döndürür."""
        orig = button.cget("text")

        def step(n):
            try:
                if not button.winfo_exists():
                    return
            except Exception:
                return
            if n > 0:
                button.configure(text=T("pick_in", n=n))
                self.root.after(1000, lambda: step(n - 1))
            else:
                button.configure(text=orig)
                x, y = engine.get_pos()
                self.sound("point")
                done(x, y)
        step(seconds)

    # ------------------------------------------------------------------ SAYFA: Tıklayıcı
    def page_clicker(self, body):
        c = self.cfg["clicker"]
        t = self.tasks["clicker"]
        self.stat_tiles(body, [
            (T("stat_clicks"), lambda: f"{t.count:,}".replace(",", ".")),
            (T("stat_time"), lambda: self.fmt_time(self.task_elapsed(t))),
            (T("stat_cps"), lambda: self._real_cps(t)),
            (T("stat_status"), lambda: self._state_text(t)),
        ])

        # Hız
        k = self.card(body, T("card_speed"), T("hint_speed"))
        r = self.row(k)
        self.lbl(r, T("min_ms")).pack(side="left")
        e_min = self.num(r, "clicker", "min_ms", 90, int, 1, on_change=lambda v: upd_cps())
        e_min.pack(side="left", padx=(6, 14))
        self.lbl(r, T("max_ms")).pack(side="left")
        e_max = self.num(r, "clicker", "max_ms", 90, int, 1, on_change=lambda v: upd_cps())
        e_max.pack(side="left", padx=6)
        cps_lbl = self.lbl(r, "", sub=True)
        cps_lbl.pack(side="left", padx=12)

        def upd_cps():
            try:
                avg = (float(c["min_ms"]) + float(c["max_ms"])) / 2
                cps_lbl.configure(text=f"≈ {1000 / max(avg, 1):.1f} CPS")
            except Exception:
                cps_lbl.configure(text="")
        upd_cps()

        r = self.row(k)
        self.lbl(r, T("presets"), sub=True, size=12).pack(side="left", padx=(0, 8))
        for cps in (1, 5, 10, 15, 20, 50, 100):
            def setp(cps=cps):
                base = 1000.0 / cps
                e_min._var.set(str(max(1, int(base * 0.9))))
                e_max._var.set(str(max(1, int(base * 1.1))))
            ctk.CTkButton(r, text=f"{cps}", width=44, height=28, fg_color=self.p["card2"],
                          hover_color=self.p["accent_soft"], text_color=self.p["text"],
                          font=self.font(12, "bold"), command=setp).pack(side="left", padx=2)
        self.lbl(r, "CPS", sub=True, size=12).pack(side="left", padx=6)

        # Tıklama türü
        k = self.card(body, T("card_click"))
        r = self.row(k)
        self.lbl(r, T("mouse_button"), width=150, anchor="w").pack(side="left")
        self.seg(r, "clicker", "button", [("left", T("btn_left")), ("right", T("btn_right")),
                                          ("middle", T("btn_middle"))]).pack(side="left", fill="x", expand=True)
        r = self.row(k)
        self.lbl(r, T("click_type"), width=150, anchor="w").pack(side="left")
        self.seg(r, "clicker", "click_type", [("single", T("ct_single")), ("double", T("ct_double")),
                                              ("triple", T("ct_triple")), ("hold", T("ct_hold"))]
                 ).pack(side="left", fill="x", expand=True)
        r = self.row(k)
        self.lbl(r, T("hold_ms"), width=150, anchor="w").pack(side="left")
        self.num(r, "clicker", "hold_ms", 80, int, 0, 5000).pack(side="left")
        self.lbl(r, T("hint_hold_ms"), sub=True, size=11).pack(side="left", padx=8)

        # Konum
        k = self.card(body, T("card_position"))
        pts_frame = ctk.CTkFrame(k, fg_color="transparent")

        def pos_changed(v):
            render_points()
        self.seg(k, "clicker", "position", [("cursor", T("pos_cursor")), ("points", T("pos_points")),
                                            ("area", T("pos_area"))], on_change=pos_changed).pack(fill="x")
        pos_hint = self.lbl(k, "", sub=True, size=11, justify="left", anchor="w", wraplength=560)
        pos_hint.pack(anchor="w", pady=(6, 2))
        pts_frame.pack(fill="x")

        def render_points():
            for ch in pts_frame.winfo_children():
                ch.destroy()
            mode = c["position"]
            pos_hint.configure(text={"cursor": T("hint_pos_cursor"), "points": T("hint_pos_points"),
                                     "area": T("hint_pos_area")}[mode].format(k=self.hk("add_point")))
            if mode == "cursor":
                return
            pts = c["points"]
            for i, pt in enumerate(pts):
                rr = ctk.CTkFrame(pts_frame, fg_color=self.p["card2"], corner_radius=8)
                rr.pack(fill="x", pady=2)
                ctk.CTkLabel(rr, text=f"#{i + 1}", width=36, font=self.font(12, "bold"),
                             text_color=self.p["accent"]).pack(side="left", padx=(8, 4))
                for axis in (0, 1):
                    self.lbl(rr, "XY"[axis], sub=True).pack(side="left", padx=(6, 2))
                    var = tk.StringVar(value=str(pt[axis]))
                    ent = ctk.CTkEntry(rr, textvariable=var, width=74, height=26, justify="center")
                    ent.pack(side="left", pady=4)

                    def ch(*_, i=i, axis=axis, var=var, ent=ent):
                        try:
                            c["points"][i][axis] = int(var.get())
                            ent.configure(border_color=self.p["border"])
                            self.cfg.save_later()
                        except (ValueError, IndexError):
                            ent.configure(border_color=self.p["err"])
                    var.trace_add("write", ch)

                def rm(i=i):
                    del c["points"][i]
                    self.cfg.save_later()
                    render_points()
                ctk.CTkButton(rr, text="✕", width=28, height=26, fg_color="transparent",
                              hover_color=self.p["err"], text_color=self.p["sub"],
                              command=rm).pack(side="right", padx=6)
                if i > 0:
                    def up(i=i):
                        c["points"][i - 1], c["points"][i] = c["points"][i], c["points"][i - 1]
                        render_points()
                    ctk.CTkButton(rr, text="↑", width=28, height=26, fg_color="transparent",
                                  hover_color=self.p["hover"], text_color=self.p["sub"],
                                  command=up).pack(side="right")
            br = ctk.CTkFrame(pts_frame, fg_color="transparent")
            br.pack(fill="x", pady=(6, 0))
            add_btn = ctk.CTkButton(br, text="+ " + T("add_point_btn"), width=150, height=30)
            add_btn.configure(command=lambda: self.countdown_pick(add_btn, 3, lambda x, y: self.add_point(x, y)))
            add_btn.pack(side="left")
            ctk.CTkButton(br, text="◎ " + T("show_points"), width=130, height=30, fg_color=self.p["card2"],
                          text_color=self.p["text"], hover_color=self.p["hover"],
                          command=self.show_points).pack(side="left", padx=6)
            if pts:
                ctk.CTkButton(br, text=T("clear"), width=80, height=30, fg_color="transparent",
                              border_width=1, border_color=self.p["border"], text_color=self.p["sub"],
                              hover_color=self.p["hover"], command=clear_pts).pack(side="left")

        def clear_pts():
            c["points"] = []
            self.cfg.save_later()
            render_points()
        self._render_points = render_points
        render_points()

        r = self.row(k, pady=(10, 2))
        self.lbl(r, T("jitter"), width=150, anchor="w").pack(side="left")
        self.num(r, "clicker", "jitter", 70, int, 0, 500).pack(side="left")
        self.lbl(r, T("hint_jitter"), sub=True, size=11).pack(side="left", padx=8)
        r = self.row(k)
        self.switch(r, T("return_cursor"), "clicker", "return_cursor").pack(side="left")

        # Limitler & zamanlama
        k = self.card(body, T("card_limits"))
        g = ctk.CTkFrame(k, fg_color="transparent")
        g.pack(fill="x")
        items = [("limit_clicks", T("limit_clicks"), T("zero_unlimited")),
                 ("limit_seconds", T("limit_seconds"), T("zero_unlimited")),
                 ("start_delay", T("start_delay"), T("seconds"))]
        for i, (key, label, hint) in enumerate(items):
            self.lbl(g, label, anchor="w").grid(row=i, column=0, sticky="w", pady=3)
            self.num(g, "clicker", key, 90, int if key != "start_delay" else float, 0).grid(
                row=i, column=1, padx=10, pady=3)
            self.lbl(g, hint, sub=True, size=11).grid(row=i, column=2, sticky="w")
        self.lbl(g, T("schedule"), anchor="w").grid(row=3, column=0, sticky="w", pady=3)
        sch = self.text_entry(g, "clicker", "schedule", 90, placeholder="HH:MM")
        sch.configure(justify="center")
        sch.grid(row=3, column=1, padx=10, pady=3)
        self.lbl(g, T("hint_schedule"), sub=True, size=11).grid(row=3, column=2, sticky="w")
        r = self.row(k, pady=(8, 2))
        self.switch(r, T("stop_on_move"), "clicker", "stop_on_move").pack(side="left")
        r = self.row(k)
        self.switch(r, T("hold_to_run", k=self.hk("clicker")), "clicker", "hold_to_run",
                    on_change=lambda v: self.apply_bindings()).pack(side="left")
        self.tip(body, T("tip_clicker", start=self.hk("clicker"), stop=self.hk("stop_all"),
                         hide=self.hk("hide")))

    def tip(self, body, text):
        f = ctk.CTkFrame(body, fg_color=self.p["accent_soft"], corner_radius=10)
        f.pack(fill="x", padx=12, pady=(6, 12))
        ctk.CTkLabel(f, text="💡  " + text, justify="left", anchor="w", wraplength=600,
                     font=self.font(12), text_color=self.p["text"]).pack(anchor="w", padx=14, pady=10)

    def _real_cps(self, t):
        el = self.task_elapsed(t)
        if el < 0.5:
            return "0.0"
        return f"{t.count / el:.1f}"

    def _state_text(self, t):
        if t.running:
            if t.state == "waiting":
                left = max(0, t.wait_until - time.time())
                return T("st_waiting") + f" {left:.0f}s"
            return T("st_running")
        return T("st_idle")

    def add_point(self, x, y):
        c = self.cfg["clicker"]
        c["points"].append([int(x), int(y)])
        if c["position"] == "cursor":
            c["position"] = "points"
        self.cfg.save_later()
        self.log(T("log_point", n=len(c["points"]), x=x, y=y))
        if self.cfg["app"]["page"] == "clicker" and not self.cfg["app"]["compact"]:
            self.show_page("clicker")

    def show_points(self):
        pts = self.cfg["clicker"]["points"]
        if not pts:
            return
        wins = []
        for i, (x, y) in enumerate(pts):
            w = tk.Toplevel(self.root)
            w.overrideredirect(True)
            w.attributes("-topmost", True)
            w.configure(bg=self.p["accent"])
            tk.Label(w, text=str(i + 1), bg=self.p["accent"], fg=self.p["accent_text"],
                     font=("Segoe UI", 10, "bold")).pack(expand=True, fill="both")
            w.geometry(f"26x26+{int(x) - 13}+{int(y) - 13}")
            wins.append(w)
        self.root.after(2500, lambda: [w.destroy() for w in wins if w.winfo_exists()])

    # ------------------------------------------------------------------ SAYFA: Tuş basıcı
    def page_keys(self, body):
        t = self.tasks["keys"]
        self.stat_tiles(body, [
            (T("stat_presses"), lambda: str(t.count)),
            (T("stat_time"), lambda: self.fmt_time(self.task_elapsed(t))),
            (T("stat_status"), lambda: self._state_text(t)),
        ])
        k = self.card(body, T("card_key"), T("hint_key"))
        r = self.row(k)
        self.lbl(r, T("key_to_press"), width=170, anchor="w").pack(side="left")
        ent = self.text_entry(r, "keys", "key", 160)
        ent.pack(side="left")
        cap = ctk.CTkButton(r, text="⌨ " + T("capture"), width=110, height=28, fg_color=self.p["card2"],
                            text_color=self.p["text"], hover_color=self.p["hover"])

        def do_capture():
            cap.configure(text=T("press_key"))

            def got(combo):
                self.post(("call", lambda: (ent._var.set(combo) if combo else None,
                                            cap.configure(text="⌨ " + T("capture")) if cap.winfo_exists() else None)))
            self.hub.start_capture(got)
        cap.configure(command=do_capture)
        cap.pack(side="left", padx=8)
        r = self.row(k)
        self.lbl(r, T("examples"), sub=True, size=11).pack(side="left")
        for ex in ("space", "e", "enter", "ctrl+c", "shift+f", "up"):
            ctk.CTkButton(r, text=ex, width=20, height=24, fg_color=self.p["card2"], text_color=self.p["text"],
                          hover_color=self.p["accent_soft"], font=self.font(11),
                          command=lambda ex=ex: ent._var.set(ex)).pack(side="left", padx=2)

        k = self.card(body, T("card_timing"))
        r = self.row(k)
        self.lbl(r, T("min_ms")).pack(side="left")
        self.num(r, "keys", "min_ms", 90, int, 1).pack(side="left", padx=(6, 14))
        self.lbl(r, T("max_ms")).pack(side="left")
        self.num(r, "keys", "max_ms", 90, int, 1).pack(side="left", padx=6)
        self.field(k, T("hold_ms"), lambda p_: self.num(p_, "keys", "hold_ms", 90, int, 0, 10000),
                   T("hint_key_hold"))
        self.field(k, T("limit_presses"), lambda p_: self.num(p_, "keys", "limit", 90, int, 0),
                   T("zero_unlimited"))
        self.field(k, T("start_delay"), lambda p_: self.num(p_, "keys", "start_delay", 90, float, 0),
                   T("seconds"))
        self.tip(body, T("tip_keys"))

    # ------------------------------------------------------------------ SAYFA: Otomatik yazıcı
    def page_typer(self, body):
        t = self.tasks["typer"]
        ty = self.cfg["typer"]
        k = self.card(body, T("card_text"), T("hint_text"))
        box = ctk.CTkTextbox(k, height=150, font=self.font(13), wrap="word")
        box.pack(fill="x")
        box.insert("1.0", ty["text"])

        def on_text(*_):
            ty["text"] = box.get("1.0", "end-1c")
            self.cfg.save_later()
        box.bind("<KeyRelease>", on_text)
        box.bind("<FocusOut>", on_text)
        box.bind("<<Paste>>", lambda e: self.root.after(10, on_text))
        cnt = self.lbl(k, "", sub=True, size=11)
        cnt.pack(anchor="e")
        self.updaters.append(lambda: cnt.configure(text=T("chars", n=len(ty["text"]))))

        k = self.card(body, T("card_options"))
        self.field(k, T("char_ms"), lambda p_: self.num(p_, "typer", "char_ms", 90, int, 0, 5000),
                   T("hint_char_ms"))
        self.field(k, T("repeat"), lambda p_: self.num(p_, "typer", "repeat", 90, int, 0),
                   T("zero_infinite"))
        self.field(k, T("between_ms"), lambda p_: self.num(p_, "typer", "between_ms", 90, int, 0))
        self.field(k, T("start_delay"), lambda p_: self.num(p_, "typer", "start_delay", 90, float, 0),
                   T("hint_typer_delay"))
        r = self.row(k, pady=(8, 2))
        self.switch(r, T("press_enter"), "typer", "press_enter").pack(side="left")
        prog = ctk.CTkLabel(k, text="", text_color=self.p["accent"], font=self.font(12, "bold"))
        prog.pack(anchor="w", pady=(6, 0))
        self.updaters.append(lambda: prog.configure(
            text=(self._state_text(t) + f" · {T('done_count', n=t.count)}") if t.running else ""))
        self.tip(body, T("tip_typer"))

    # ------------------------------------------------------------------ SAYFA: Makro
    def page_macro(self, body):
        p = self.p
        t = self.tasks["macro"]
        m = self.cfg["macro"]

        def status_text():
            if self.recorder:
                return T("mac_recording", n=len(self.recorder.events))
            ev = t.events
            if not ev:
                return T("mac_empty")
            name = self.macro_name or T("mac_unsaved")
            return T("mac_ready", name=name, n=len(ev), s=f"{engine.macro_duration(ev):.1f}")

        self.stat_tiles(body, [
            (T("stat_events"), lambda: str(len(self.recorder.events) if self.recorder else len(t.events))),
            (T("stat_length"), lambda: f"{engine.macro_duration(t.events):.1f}s"),
            (T("stat_loop"), lambda: str(t.count)),
            (T("stat_status"), lambda: (T("st_recording") if self.recorder else self._state_text(t))),
        ])
        k = self.card(body, T("card_recorder"))
        st = ctk.CTkLabel(k, text="", font=self.font(13, "bold"), anchor="w", text_color=p["accent"])
        st.pack(anchor="w", pady=(0, 8))
        r = self.row(k)
        rec_btn = ctk.CTkButton(r, height=38, width=200, font=self.font(13, "bold"),
                                command=lambda: self.toggle_record(from_gui=True))
        rec_btn.pack(side="left")
        ctk.CTkButton(r, text="💾 " + T("save"), height=38, width=110, fg_color=p["card2"], text_color=p["text"],
                      hover_color=p["hover"], command=self.save_macro_dialog).pack(side="left", padx=6)
        ctk.CTkButton(r, text="📂 " + T("open"), height=38, width=110, fg_color=p["card2"], text_color=p["text"],
                      hover_color=p["hover"], command=self.load_macro_dialog).pack(side="left")
        ctk.CTkButton(r, text=T("clear"), height=38, width=80, fg_color="transparent", border_width=1,
                      border_color=p["border"], text_color=p["sub"], hover_color=p["hover"],
                      command=self.clear_macro).pack(side="left", padx=6)

        def upd():
            st.configure(text=status_text())
            if self.recorder:
                rec_btn.configure(text=f"■  {T('rec_stop')}   {self.hk('macro_record')}", fg_color=p["err"],
                                  hover_color=themes.mix(p["err"], "#000000", 0.2), text_color="#ffffff")
            else:
                rec_btn.configure(text=f"⏺  {T('rec_start')}   {self.hk('macro_record')}", fg_color=p["accent"],
                                  hover_color=p["accent_hover"], text_color=p["accent_text"])
        upd()
        self.updaters.append(upd)
        r = self.row(k, pady=(10, 0))
        self.switch(r, T("record_moves"), "macro", "record_moves").pack(side="left")

        k = self.card(body, T("card_playback"))
        self.field(k, T("repeat"), lambda p_: self.num(p_, "macro", "repeat", 90, int, 0), T("zero_infinite"))
        self.field(k, T("loop_delay"), lambda p_: self.num(p_, "macro", "loop_delay_ms", 90, int, 0))
        r = self.row(k)
        self.lbl(r, T("speed"), width=190, anchor="w").pack(side="left")
        speeds = [("0.5", "0.5×"), ("1.0", "1×"), ("1.5", "1.5×"), ("2.0", "2×"), ("4.0", "4×"), ("10.0", "10×")]
        cur = f"{float(m['speed']):.1f}"
        Seg(r, self, speeds, cur if cur in dict(speeds) else "1.0",
            lambda v: (m.__setitem__("speed", float(v)), self.cfg.save_later())).pack(side="left", fill="x",
                                                                                      expand=True)

        k = self.card(body, T("card_library"), T("hint_library"))
        files = sorted([f for f in os.listdir(MACRO_DIR) if f.endswith(".json")], key=str.lower)
        if not files:
            self.lbl(k, T("lib_empty"), sub=True, size=12).pack(anchor="w")
        for fname in files:
            path = os.path.join(MACRO_DIR, fname)
            rr = ctk.CTkFrame(k, fg_color=p["card2"], corner_radius=8)
            rr.pack(fill="x", pady=2)
            label = os.path.splitext(fname)[0]
            if fname == os.path.basename(LAST_MACRO):
                label = T("last_recording")
            self.lbl(rr, "⏺  " + label, anchor="w").pack(side="left", padx=10, pady=6)
            ctk.CTkButton(rr, text="✕", width=28, height=26, fg_color="transparent", hover_color=p["err"],
                          text_color=p["sub"], command=lambda pa=path: self.delete_macro(pa)).pack(side="right", padx=6)
            ctk.CTkButton(rr, text=T("load"), width=70, height=26,
                          command=lambda pa=path: self.load_macro(pa)).pack(side="right")
        ctk.CTkButton(k, text="📁 " + T("open_folder"), width=150, height=28, fg_color="transparent",
                      border_width=1, border_color=p["border"], text_color=p["sub"], hover_color=p["hover"],
                      command=lambda: os.startfile(MACRO_DIR)).pack(anchor="w", pady=(8, 0))
        self.tip(body, T("tip_macro", rec=self.hk("macro_record"), play=self.hk("macro_play"),
                         stop=self.hk("stop_all")))

    def toggle_record(self, from_gui=False):
        if self.recorder:
            events = self.recorder.finish(from_gui=from_gui)
            self.hub.recorder = None
            self.recorder = None
            self.tasks["macro"].events = events
            self.macro_name = ""
            if events:
                try:
                    engine.save_macro(LAST_MACRO, events)
                    self.cfg["macro"]["current"] = LAST_MACRO
                except Exception:
                    pass
            self.log(T("log_rec_done", n=len(events), s=f"{engine.macro_duration(events):.1f}"))
            self.osd("⏹  " + T("log_rec_done", n=len(events), s=f"{engine.macro_duration(events):.1f}"))
            self.sound("stop")
            if self.cfg["app"]["page"] == "macro" and not self.cfg["app"]["compact"]:
                self.show_page("macro")
        else:
            if self.tasks["macro"].running:
                self.tasks["macro"].stop()
            self.recorder = engine.MacroRecorder(self.hub, self.cfg["macro"]["record_moves"])
            self.hub.recorder = self.recorder
            self.log(T("log_rec_start", k=self.hk("macro_record")))
            self.osd("⏺  " + T("st_recording"), self.p["err"])
            self.sound("rec")

    def _load_last_macro(self):
        path = self.cfg["macro"]["current"] or LAST_MACRO
        if os.path.exists(path):
            try:
                self.tasks["macro"].events = engine.load_macro(path)
                if path != LAST_MACRO:
                    self.macro_name = os.path.splitext(os.path.basename(path))[0]
            except Exception:
                pass

    def load_macro(self, path):
        try:
            self.tasks["macro"].events = engine.load_macro(path)
            self.macro_name = os.path.splitext(os.path.basename(path))[0]
            if path == LAST_MACRO:
                self.macro_name = ""
            self.cfg["macro"]["current"] = path
            self.cfg.save_later()
            self.log(T("log_macro_loaded", name=os.path.basename(path)))
        except Exception as ex:
            messagebox.showerror(APP_NAME, T("err_macro_load") + f"\n{ex}")
        if self.cfg["app"]["page"] == "macro":
            self.show_page("macro")

    def save_macro_dialog(self):
        ev = self.tasks["macro"].events
        if not ev:
            messagebox.showinfo(APP_NAME, T("mac_empty"))
            return
        path = filedialog.asksaveasfilename(initialdir=MACRO_DIR, defaultextension=".json",
                                            initialfile=(self.macro_name or "makro") + ".json",
                                            filetypes=[(T("macro_files"), "*.json")])
        if not path:
            return
        engine.save_macro(path, ev)
        self.macro_name = os.path.splitext(os.path.basename(path))[0]
        self.cfg["macro"]["current"] = path
        self.log(T("log_macro_saved", name=os.path.basename(path)))
        self.show_page("macro")

    def load_macro_dialog(self):
        path = filedialog.askopenfilename(initialdir=MACRO_DIR, filetypes=[(T("macro_files"), "*.json")])
        if path:
            self.load_macro(path)

    def delete_macro(self, path):
        if not messagebox.askyesno(APP_NAME, T("confirm_delete", name=os.path.basename(path))):
            return
        try:
            os.remove(path)
        except Exception:
            pass
        if self.cfg["macro"]["current"] == path:
            self.cfg["macro"]["current"] = ""
        self.show_page("macro")

    def clear_macro(self):
        if self.tasks["macro"].running:
            self.tasks["macro"].stop()
        self.tasks["macro"].events = []
        self.macro_name = ""
        self.cfg["macro"]["current"] = ""
        self.log(T("log_macro_cleared"))
        self.show_page("macro")

    # ------------------------------------------------------------------ SAYFA: Renk tetikleyici
    def page_trigger(self, body):
        p = self.p
        tr = self.cfg["trigger"]
        t = self.tasks["trigger"]
        self.stat_tiles(body, [
            (T("stat_triggers"), lambda: str(t.count)),
            (T("stat_time"), lambda: self.fmt_time(self.task_elapsed(t))),
            (T("stat_status"), lambda: self._state_text(t)),
        ])
        k = self.card(body, T("card_watch"), T("hint_watch"))
        r = self.row(k)
        self.lbl(r, "X").pack(side="left")
        ex = self.num(r, "trigger", "x", 80, int, None, allow_empty=True)
        ex.pack(side="left", padx=(4, 12))
        self.lbl(r, "Y").pack(side="left")
        ey = self.num(r, "trigger", "y", 80, int, None, allow_empty=True)
        ey.pack(side="left", padx=4)
        pick = ctk.CTkButton(r, text="◎ " + T("pick_point_color"), width=200, height=28)

        def picked(x, y):
            ex._var.set(str(x))
            ey._var.set(str(y))
            px = engine.get_pixel(x, y)
            if px:
                ec._var.set(engine.rgb_to_hex(px))
        pick.configure(command=lambda: self.countdown_pick(pick, 3, picked))
        pick.pack(side="left", padx=10)

        r = self.row(k, pady=(8, 4))
        self.lbl(r, T("target_color")).pack(side="left")
        ec = self.text_entry(r, "trigger", "color", 100)
        ec.configure(justify="center")
        ec.pack(side="left", padx=8)
        sw_target = ctk.CTkFrame(r, width=28, height=28, corner_radius=6, border_width=1, border_color=p["border"])
        sw_target.pack(side="left")

        def choose():
            res = colorchooser.askcolor(color=tr["color"] if self._valid_hex(tr["color"]) else None)
            if res and res[1]:
                ec._var.set(res[1].upper())
        ctk.CTkButton(r, text="🎨", width=34, height=28, fg_color=p["card2"], hover_color=p["hover"],
                      text_color=p["text"], command=choose).pack(side="left", padx=6)
        self.lbl(r, T("live_color"), sub=True).pack(side="left", padx=(16, 6))
        sw_live = ctk.CTkFrame(r, width=28, height=28, corner_radius=6, border_width=1, border_color=p["border"])
        sw_live.pack(side="left")
        live_lbl = self.lbl(r, "", sub=True, size=11)
        live_lbl.pack(side="left", padx=6)

        def upd():
            if self._valid_hex(tr["color"]):
                sw_target.configure(fg_color=tr["color"])
            try:
                px = engine.get_pixel(int(tr["x"]), int(tr["y"]))
            except (TypeError, ValueError):
                px = None
            if px:
                hx = engine.rgb_to_hex(px)
                sw_live.configure(fg_color=hx)
                d = engine.color_distance(px, engine.hex_to_rgb(tr["color"])) if self._valid_hex(tr["color"]) else 255
                live_lbl.configure(text=f"{hx}  Δ{d}", text_color=p["ok"] if d <= int(tr["tolerance"]) else p["sub"])
            else:
                live_lbl.configure(text="—")
        self.updaters.append(upd)

        r = self.row(k, pady=(8, 2))
        self.lbl(r, T("tolerance"), width=150, anchor="w").pack(side="left")
        tol_lbl = self.lbl(r, str(tr["tolerance"]), width=40)
        sl = ctk.CTkSlider(r, from_=0, to=120, number_of_steps=120, width=260,
                           command=lambda v: (tr.__setitem__("tolerance", int(v)), tol_lbl.configure(text=str(int(v))),
                                              self.cfg.save_later()))
        sl.set(int(tr["tolerance"]))
        sl.pack(side="left")
        tol_lbl.pack(side="left", padx=6)
        r = self.row(k)
        self.lbl(r, T("trigger_when"), width=150, anchor="w").pack(side="left")
        self.seg(r, "trigger", "mode", [("match", T("tm_match")), ("change", T("tm_change"))]).pack(
            side="left", fill="x", expand=True)

        k = self.card(body, T("card_action"))
        act_box = ctk.CTkFrame(k, fg_color="transparent")

        def render_action(v=None):
            for ch in act_box.winfo_children():
                ch.destroy()
            if tr["action"] == "click":
                rr = self.row(act_box)
                self.lbl(rr, T("mouse_button"), width=150, anchor="w").pack(side="left")
                self.seg(rr, "trigger", "button", [("left", T("btn_left")), ("right", T("btn_right")),
                                                  ("middle", T("btn_middle"))]).pack(side="left", fill="x", expand=True)
                rr = self.row(act_box)
                self.lbl(rr, T("click_where"), width=150, anchor="w").pack(side="left")
                self.seg(rr, "trigger", "click_at", [("point", T("at_point")), ("cursor", T("at_cursor"))]).pack(
                    side="left", fill="x", expand=True)
            else:
                rr = self.row(act_box)
                self.lbl(rr, T("key_to_press"), width=150, anchor="w").pack(side="left")
                self.text_entry(rr, "trigger", "key", 140).pack(side="left")
        self.seg(k, "trigger", "action", [("click", T("act_click")), ("key", T("act_key"))],
                 on_change=render_action).pack(fill="x")
        act_box.pack(fill="x", pady=(6, 0))
        render_action()
        self.field(k, T("cooldown"), lambda p_: self.num(p_, "trigger", "cooldown_ms", 90, int, 0))
        r = self.row(k, pady=(6, 2))
        self.switch(r, T("trigger_once"), "trigger", "once").pack(side="left")
        self.tip(body, T("tip_trigger"))

    @staticmethod
    def _valid_hex(h):
        try:
            engine.hex_to_rgb(h)
            return len(h.strip().lstrip("#")) in (3, 6)
        except Exception:
            return False

    # ------------------------------------------------------------------ SAYFA: CPS testi
    def page_cpstest(self, body):
        p = self.p
        st = self.cfg["stats"]
        self.cps_duration = getattr(self, "cps_duration", 5)
        k = self.card(body, T("card_cps"), T("hint_cps"))
        r = self.row(k)
        self.lbl(r, T("duration"), width=120, anchor="w").pack(side="left")
        Seg(r, self, [(5, "5 s"), (10, "10 s"), (30, "30 s"), (60, "60 s")], self.cps_duration,
            lambda v: setattr(self, "cps_duration", v)).pack(side="left", fill="x", expand=True)

        area = ctk.CTkLabel(k, text=T("cps_click_to_start"), height=230, corner_radius=14,
                            fg_color=p["card2"], font=self.font(20, "bold"), text_color=p["text"])
        area.pack(fill="x", pady=(12, 6))
        info = self.lbl(k, "", sub=True)
        info.pack()
        best = self.lbl(k, "", size=14, bold=True)
        best.pack(pady=(4, 0))

        def show_best():
            best.configure(text=T("cps_best", v=f"{st['best_cps']:.2f}"), text_color=p["accent"])
        show_best()

        def press(_e=None):
            s = self.cps_state
            now = time.perf_counter()
            if s is None or s.get("done"):
                if s and s.get("done") and now - s["end"] < 1.0:
                    return  # bitişten hemen sonraki yanlış tıklamaları yut
                self.cps_state = {"start": now, "clicks": 1, "dur": self.cps_duration, "done": False}
                area.configure(fg_color=p["accent_soft"])
                return
            s["clicks"] += 1

        def upd():
            s = self.cps_state
            if not s or s.get("done"):
                return
            el = time.perf_counter() - s["start"]
            if el >= s["dur"]:
                s["done"], s["end"] = True, time.perf_counter()
                cps = s["clicks"] / s["dur"]
                record = cps > st["best_cps"]
                if record:
                    st["best_cps"] = round(cps, 2)
                    self.cfg.save_later()
                    self.sound("done")
                area.configure(text=f"{cps:.2f} CPS" + ("  🏆" if record else ""), fg_color=p["card2"])
                info.configure(text=T("cps_result", n=s["clicks"], s=s["dur"]) + "  ·  " + T("cps_again"))
                show_best()
                return
            area.configure(text=f"{s['clicks']}  ·  {s['clicks'] / max(el, 0.001):.1f} CPS")
            info.configure(text=T("cps_left", s=f"{s['dur'] - el:.1f}"))
        area.bind("<Button-1>", press)
        self.updaters.append(upd)
        self.tip(body, T("tip_cps", k=self.hk("clicker")))

    # ------------------------------------------------------------------ SAYFA: Ayarlar
    def page_settings(self, body):
        p = self.p
        a = self.cfg["app"]

        # Görünüm
        k = self.card(body, T("card_appearance"))
        r = self.row(k)
        self.lbl(r, T("language"), width=170, anchor="w").pack(side="left")
        names = [n for _, n in LANGUAGES]
        cur = dict(LANGUAGES).get(a["language"], "English")

        def set_lang(name):
            code = {n: c for c, n in LANGUAGES}[name]
            a["language"] = code
            self.cfg.save_later()
            self.rebuild()
        ctk.CTkOptionMenu(r, values=names, command=set_lang, width=200,
                          dynamic_resizing=False).pack(side="left")
        r.winfo_children()[-1].set(cur)

        self.lbl(k, T("theme"), anchor="w").pack(anchor="w", pady=(10, 4))
        grid = ctk.CTkFrame(k, fg_color="transparent")
        grid.pack(fill="x")
        cols = 4
        for i, name in enumerate(themes.THEME_ORDER):
            tp = themes.palette(name)
            on = name == a["theme"]
            b = ctk.CTkButton(grid, text=("✓ " if on else "") + T("theme_" + name), height=46,
                              fg_color=tp["card"], hover_color=tp["card2"], text_color=tp["text"],
                              border_width=3 if on else 2, border_color=tp["accent"], corner_radius=10,
                              font=self.font(12, "bold"),
                              command=lambda n=name: self.set_theme(n))
            b.grid(row=i // cols, column=i % cols, padx=4, pady=4, sticky="ew")
            grid.grid_columnconfigure(i % cols, weight=1, uniform="th")

        r = self.row(k, pady=(10, 4))
        self.lbl(r, T("accent_color"), width=170, anchor="w").pack(side="left")
        ctk.CTkButton(r, text="", width=34, height=28, fg_color=p["accent"], hover_color=p["accent_hover"],
                      border_width=2, border_color=p["border"], command=self.pick_accent).pack(side="left")
        ctk.CTkButton(r, text="🎨 " + T("choose"), width=100, height=28, fg_color=p["card2"],
                      text_color=p["text"], hover_color=p["hover"], command=self.pick_accent).pack(side="left", padx=6)
        if a["accent"]:
            ctk.CTkButton(r, text=T("reset"), width=80, height=28, fg_color="transparent", border_width=1,
                          border_color=p["border"], text_color=p["sub"], hover_color=p["hover"],
                          command=lambda: self.set_accent("")).pack(side="left")

        r = self.row(k)
        self.lbl(r, T("ui_scale"), width=170, anchor="w").pack(side="left")
        scales = [("0.9", "90%"), ("1.0", "100%"), ("1.1", "110%"), ("1.25", "125%")]
        cur_s = str(float(a["ui_scale"])).rstrip("0").rstrip(".") if a["ui_scale"] != 1.25 else "1.25"
        cur_s = {"0.9": "0.9", "1": "1.0", "1.1": "1.1", "1.25": "1.25"}.get(cur_s, "1.0")

        def set_scale(v):
            a["ui_scale"] = float(v)
            self.cfg.save_later()
            self.rebuild()
        Seg(r, self, scales, cur_s, set_scale).pack(side="left", fill="x", expand=True)

        r = self.row(k)
        self.lbl(r, T("opacity"), width=170, anchor="w").pack(side="left")
        op = ctk.CTkSlider(r, from_=0.3, to=1.0, width=240,
                           command=lambda v: (a.__setitem__("opacity", round(float(v), 2)), self.apply_window_attrs(),
                                              self.cfg.save_later()))
        op.set(float(a["opacity"]))
        op.pack(side="left")
        r = self.row(k)
        self.switch(r, T("topmost"), "app", "topmost", lambda v: self.apply_window_attrs()).pack(side="left")
        r = self.row(k)
        self.switch(r, T("osd"), "app", "osd").pack(side="left")

        # Kısayollar
        k = self.card(body, T("card_hotkeys"), T("hint_hotkeys"))
        for action in HOTKEY_ACTIONS:
            rr = ctk.CTkFrame(k, fg_color=p["card2"], corner_radius=8)
            rr.pack(fill="x", pady=2)
            self.lbl(rr, T("hk_" + action), anchor="w").pack(side="left", padx=12, pady=6)
            ctk.CTkButton(rr, text="✕", width=28, height=26, fg_color="transparent", hover_color=p["err"],
                          text_color=p["sub"], command=lambda ac=action: self.set_hotkey(ac, "")).pack(
                side="right", padx=(0, 8))
            hb = ctk.CTkButton(rr, text=self.hk(action), width=150, height=28, font=self.font(12, "bold"),
                               fg_color=p["bg"], text_color=p["accent"], hover_color=p["hover"],
                               border_width=1, border_color=p["border"])
            hb.configure(command=lambda ac=action, b=hb: self.capture_hotkey(ac, b))
            hb.pack(side="right", padx=6)
        ctk.CTkButton(k, text=T("reset_hotkeys"), width=160, height=28, fg_color="transparent", border_width=1,
                      border_color=p["border"], text_color=p["sub"], hover_color=p["hover"],
                      command=self.reset_hotkeys).pack(anchor="w", pady=(8, 0))

        # Profiller
        k = self.card(body, T("card_profiles"), T("hint_profiles"))
        r = self.row(k)
        profiles = self.cfg.list_profiles()
        prof_menu = ctk.CTkOptionMenu(r, values=profiles or ["—"], width=200, dynamic_resizing=False)
        prof_menu.set(a["profile"] if a["profile"] in profiles else (profiles[0] if profiles else "—"))
        prof_menu.pack(side="left")

        def load_p():
            name = prof_menu.get()
            if name in profiles:
                self.stop_all(quiet=True)
                self.cfg.load_profile(name)
                self.apply_bindings()
                self.log(T("log_profile_loaded", name=name))
                self.show_page("settings")

        def save_p():
            d = ctk.CTkInputDialog(text=T("profile_name"), title=APP_NAME)
            name = d.get_input()
            if name and name.strip():
                saved = self.cfg.save_profile(name.strip())
                self.log(T("log_profile_saved", name=saved))
                self.show_page("settings")

        def del_p():
            name = prof_menu.get()
            if name in profiles and messagebox.askyesno(APP_NAME, T("confirm_delete", name=name)):
                self.cfg.delete_profile(name)
                self.show_page("settings")
        for txt, cmd, prim in ((T("load"), load_p, True), (T("save_as"), save_p, False), (T("delete"), del_p, False)):
            ctk.CTkButton(r, text=txt, width=100, height=28, command=cmd,
                          **({} if prim else dict(fg_color=p["card2"], text_color=p["text"], hover_color=p["hover"]))
                          ).pack(side="left", padx=(6, 0))
        r = self.row(k, pady=(8, 0))
        ctk.CTkButton(r, text="⬆ " + T("export"), width=150, height=28, fg_color="transparent", border_width=1,
                      border_color=p["border"], text_color=p["text"], hover_color=p["hover"],
                      command=self.export_settings).pack(side="left")
        ctk.CTkButton(r, text="⬇ " + T("import"), width=150, height=28, fg_color="transparent", border_width=1,
                      border_color=p["border"], text_color=p["text"], hover_color=p["hover"],
                      command=self.import_settings).pack(side="left", padx=6)

        # Genel
        k = self.card(body, T("card_general"))
        r = self.row(k)
        self.switch(r, T("sounds"), "app", "sound").pack(side="left")
        r = self.row(k)
        self.switch(r, T("failsafe"), "app", "failsafe").pack(side="left")
        r = self.row(k, pady=(8, 0))
        if not engine.is_admin() and engine.IS_WIN:
            ctk.CTkButton(r, text="🛡 " + T("run_admin"), width=200, height=30, fg_color=p["warn"],
                          hover_color=themes.mix(p["warn"], "#000000", 0.2), text_color="#1a1a1a",
                          command=self.run_as_admin).pack(side="left")
        ctk.CTkButton(r, text="📁 " + T("open_config"), width=170, height=30, fg_color=p["card2"],
                      text_color=p["text"], hover_color=p["hover"],
                      command=lambda: os.startfile(CONFIG_DIR)).pack(side="left", padx=6)
        self.lbl(k, T("hint_admin"), sub=True, size=11, justify="left", wraplength=560).pack(anchor="w", pady=(6, 0))

        # İstatistikler
        st = self.cfg["stats"]
        k = self.card(body, T("card_stats"))
        g = ctk.CTkFrame(k, fg_color="transparent")
        g.pack(fill="x")
        vals = [(T("st_total_clicks"), lambda: f"{st['total_clicks']:,}".replace(",", ".")),
                (T("st_total_keys"), lambda: f"{st['total_keys']:,}".replace(",", ".")),
                (T("st_total_time"), lambda: self.fmt_time(st["total_seconds"])),
                (T("st_best_cps"), lambda: f"{st['best_cps']:.2f}"),
                (T("st_launches"), lambda: str(st["launches"]))]
        labels = []
        for i, (n, fn) in enumerate(vals):
            f = ctk.CTkFrame(g, fg_color=p["card2"], corner_radius=10)
            f.grid(row=0, column=i, padx=(0 if i == 0 else 6, 0), sticky="ew")
            g.grid_columnconfigure(i, weight=1, uniform="st")
            self.lbl(f, n, sub=True, size=11).pack(padx=10, pady=(8, 0))
            v = ctk.CTkLabel(f, text=fn(), font=self.font(16, "bold"), text_color=p["accent"])
            v.pack(padx=10, pady=(0, 8))
            labels.append((v, fn))
        self.updaters.append(lambda: [v.configure(text=fn()) for v, fn in labels])

        def reset_stats():
            if messagebox.askyesno(APP_NAME, T("confirm_reset_stats")):
                for kk in ("total_clicks", "total_keys", "total_seconds", "best_cps"):
                    st[kk] = 0 if kk != "best_cps" else 0.0
                self.cfg.save_later()
        ctk.CTkButton(k, text=T("reset_stats"), width=160, height=28, fg_color="transparent", border_width=1,
                      border_color=p["border"], text_color=p["sub"], hover_color=p["hover"],
                      command=reset_stats).pack(anchor="w", pady=(8, 0))

        # Günlük
        k = self.card(body, T("card_log"))
        self.w_log = ctk.CTkTextbox(k, height=150, font=ctk.CTkFont(family="Consolas", size=11))
        self.w_log.pack(fill="x")
        self.w_log.insert("end", "\n".join(self.logs) + ("\n" if self.logs else ""))
        self.w_log.see("end")
        self.w_log.configure(state="disabled")

        # Hakkında
        k = self.card(body, T("card_about"))
        self.lbl(k, f"{APP_NAME} v{VERSION}", bold=True, size=14).pack(anchor="w")
        self.lbl(k, T("about_text"), sub=True, size=12, justify="left", wraplength=560).pack(anchor="w", pady=(2, 6))
        import webbrowser
        ctk.CTkButton(k, text="★ GitHub", width=120, height=28,
                      command=lambda: webbrowser.open(REPO_URL)).pack(anchor="w")

    def set_theme(self, name):
        self.cfg["app"]["theme"] = name
        self.cfg["app"]["accent"] = ""
        self.cfg.save_later()
        self.rebuild()

    def set_accent(self, color):
        self.cfg["app"]["accent"] = color
        self.cfg.save_later()
        self.rebuild()

    def pick_accent(self):
        res = colorchooser.askcolor(color=self.p["accent"], title=T("accent_color"))
        if res and res[1]:
            self.set_accent(res[1])

    def capture_hotkey(self, action, button):
        if self.capturing:
            return
        self.capturing = action
        button.configure(text=T("press_key"), text_color=self.p["warn"])
        self.hub.enabled = False

        def got(combo):
            self.post(("captured", action, combo))
        self.hub.start_capture(got)

    def set_hotkey(self, action, combo):
        hk = self.cfg["hotkeys"]
        if combo:
            for other, c in hk.items():
                if other != action and c == combo:
                    hk[other] = ""
                    self.log(T("log_hotkey_conflict", a=T("hk_" + other)))
        hk[action] = combo or ""
        self.cfg.save_later()
        self.apply_bindings()
        self.show_page(self.cfg["app"]["page"])

    def reset_hotkeys(self):
        self.cfg.reset_section("hotkeys")
        self.apply_bindings()
        self.show_page("settings")

    def export_settings(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile="ototik-ayarlar.json",
                                            filetypes=[("JSON", "*.json")])
        if path:
            self.cfg.export_to(path)
            self.log(T("log_exported"))

    def import_settings(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            self.cfg.import_from(path)
            self.apply_bindings()
            self.rebuild()
            self.log(T("log_imported"))
        except Exception as ex:
            messagebox.showerror(APP_NAME, str(ex))

    def run_as_admin(self):
        release_single_instance()
        if engine.relaunch_as_admin():
            self.quit()
        else:
            ensure_single_instance()

    # ------------------------------------------------------------------ Mini mod
    def build_compact(self):
        p = self.p
        self.root.minsize(300, 100)
        self.root.resizable(False, False)
        self.root.geometry("330x206")
        top = ctk.CTkFrame(self.root, fg_color=p["side"], corner_radius=0, height=34)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="● ", text_color=p["accent"], font=self.font(14, "bold")).pack(side="left", padx=(10, 0))
        ctk.CTkLabel(top, text=APP_NAME, font=self.font(13, "bold")).pack(side="left")
        ctk.CTkButton(top, text="⇱", width=30, height=26, fg_color="transparent", hover_color=p["hover"],
                      text_color=p["text"], command=self.toggle_compact).pack(side="right", padx=6)
        ctk.CTkButton(top, text="■", width=30, height=26, fg_color="transparent", hover_color=p["err"],
                      text_color=p["err"], command=self.stop_all).pack(side="right")
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=6)
        for name in ("clicker", "keys", "macro", "trigger"):
            t = self.tasks[name]
            r = ctk.CTkFrame(body, fg_color=p["card"], corner_radius=8)
            r.pack(fill="x", pady=2)
            dot = ctk.CTkLabel(r, text="●", width=16, text_color=p["sub"])
            dot.pack(side="left", padx=(8, 2))
            ctk.CTkLabel(r, text=T("nav_" + name), font=self.font(12, "bold"), anchor="w", width=110).pack(side="left")
            info = ctk.CTkLabel(r, text="", text_color=p["sub"], font=self.font(11), anchor="w")
            info.pack(side="left", fill="x", expand=True)
            b = ctk.CTkButton(r, text="▶", width=34, height=24, command=lambda n=name: self.toggle_task(n))
            b.pack(side="right", padx=6, pady=3)

            def upd(t=t, dot=dot, info=info, b=b, name=name):
                running = t.running
                dot.configure(text_color=(p["warn"] if t.state == "waiting" else p["ok"]) if running else p["sub"])
                if running:
                    extra = f" · {self._real_cps(t)} CPS" if name == "clicker" else ""
                    info.configure(text=f"{t.count}{extra}")
                    b.configure(text="■", fg_color=p["err"], hover_color=themes.mix(p["err"], "#000000", 0.2),
                                text_color="#ffffff")
                else:
                    info.configure(text=self.hk({"macro": "macro_play"}.get(name, name)))
                    b.configure(text="▶", fg_color=p["accent"], hover_color=p["accent_hover"], text_color=p["accent_text"])
            upd()
            self.updaters.append(upd)

    def toggle_compact(self):
        a = self.cfg["app"]
        if not a["compact"]:
            a["geometry"] = self.root.geometry()
        a["compact"] = not a["compact"]
        self.cfg.save_later()
        self.build()
        if not a["compact"] and a["geometry"]:
            self.root.geometry(a["geometry"])

    # ------------------------------------------------------------------ görev kontrolü
    def toggle_task(self, name):
        t = self.tasks[name]
        if t.running:
            t.stop()
            return
        if name == "macro" and self.recorder:
            self.toggle_record()
        if name == "macro" and not t.events:
            self.log(T("log_no_macro"))
            self.sound("error")
            return
        t.start()

    def stop_all(self, quiet=False):
        any_running = False
        for t in self.tasks.values():
            if t.running:
                any_running = True
                t.stop()
        if self.recorder:
            self.toggle_record()
            any_running = True
        if any_running and not quiet:
            self.log(T("log_stop_all"))

    def on_hotkey(self, action, phase):
        if self.capturing:
            return
        if action == "clicker" and self.cfg["clicker"]["hold_to_run"]:
            t = self.tasks["clicker"]
            if phase == "down" and not t.running:
                t.start()
            elif phase == "up" and t.running:
                t.stop()
            return
        if phase != "down":
            return
        if action in ("clicker", "keys", "typer", "trigger"):
            self.toggle_task(action)
        elif action == "macro_play":
            self.toggle_task("macro")
        elif action == "macro_record":
            self.toggle_record()
        elif action == "add_point":
            x, y = engine.get_pos()
            self.sound("point")
            self.add_point(x, y)
            self.osd(T("log_point", n=len(self.cfg["clicker"]["points"]), x=x, y=y))
        elif action == "stop_all":
            self.stop_all()
        elif action == "hide":
            self.visible = not self.visible
            if self.visible:
                self.root.deiconify()
                self.root.lift()
            else:
                self.root.withdraw()

    def on_task_event(self, name, what):
        t = self.tasks[name]
        label = T("nav_" + name)
        if what == "start":
            self.sound("start")
            self.osd("▶  " + T("osd_started", t=label), self.p["ok"])
            self.log(T("log_started", t=label))
            return
        el = (time.time() - t.started_at) if t.started_at else 0
        t._last_elapsed = el if t.state != "waiting" else 0
        st = self.cfg["stats"]
        st["total_seconds"] += int(el)
        if name == "clicker":
            st["total_clicks"] += t.count
        elif name == "keys":
            st["total_keys"] += t.count
        self.cfg.save_later()
        self.sound("done" if what in ("done", "limit") else ("error" if what == "error" else "stop"))
        self.osd("■  " + T("osd_stopped", t=label), self.p["err"])
        self.log(T("log_finished_" + what, t=label, n=t.count) if ("log_finished_" + what) in _known()
                 else T("log_finished_stopped", t=label, n=t.count))

    def check_schedule(self):
        s = (self.cfg["clicker"]["schedule"] or "").strip()
        if len(s) < 4 or ":" not in s:
            return
        now = time.strftime("%H:%M")
        try:
            hh, mm = s.split(":")
            target = f"{int(hh):02d}:{int(mm):02d}"
        except ValueError:
            return
        key = time.strftime("%Y-%m-%d ") + target
        if now == target and self._schedule_fired != key:
            self._schedule_fired = key
            if not self.tasks["clicker"].running:
                self.log(T("log_schedule", t=target))
                self.tasks["clicker"].start()

    # ------------------------------------------------------------------ ana döngü
    def tick(self):
        try:
            while True:
                ev = self.q.get_nowait()
                kind = ev[0]
                if kind == "hotkey":
                    self.on_hotkey(ev[1], ev[2])
                elif kind == "task":
                    self.on_task_event(ev[1], ev[2])
                elif kind == "log":
                    self.log(T(ev[1], **ev[2]))
                elif kind == "failsafe":
                    self.stop_all(quiet=True)
                    self.log(T("log_failsafe"))
                elif kind == "captured":
                    self.capturing = None
                    self.hub.enabled = True
                    if ev[2]:
                        self.set_hotkey(ev[1], ev[2])
                    else:
                        self.show_page(self.cfg["app"]["page"])
                elif kind == "call":
                    ev[1]()
        except queue.Empty:
            pass
        except Exception as ex:
            self.log(f"UI: {ex}")

        if not self.cfg["app"]["compact"]:
            p = self.p
            for k, item in getattr(self, "nav_btns", {}).items():
                if k not in self.tasks:
                    continue
                try:
                    t = self.tasks[k]
                    if k == "macro" and self.recorder:
                        item.set_dot(p["err"])
                    elif t.running:
                        item.set_dot(p["warn"] if t.state == "waiting" else p["ok"])
                    else:
                        item.set_dot(None)
                except Exception:
                    pass
        for u in list(self.updaters):
            try:
                u()
            except Exception:
                pass
        self.check_schedule()
        self.root.after(100, self.tick)

    def quit(self):
        try:
            self.stop_all(quiet=True)
            if not self.cfg["app"]["compact"]:
                self.cfg["app"]["geometry"] = self.root.geometry()
            self.cfg.save()
            self.hub.close()
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


def _known():
    from .i18n import STRINGS
    return STRINGS["en"]


_mutex = None


def release_single_instance():
    global _mutex
    if _mutex and engine.IS_WIN:
        import ctypes
        ctypes.windll.kernel32.CloseHandle(_mutex)
        _mutex = None


def ensure_single_instance(wait=0.0):
    """Aynı anda iki OtoTık çalışırsa kısayollar iki kez tetiklenir; bunu engeller."""
    if not engine.IS_WIN:
        return True
    import ctypes
    kernel32 = ctypes.windll.kernel32
    global _mutex
    deadline = time.time() + wait
    while True:
        _mutex = kernel32.CreateMutexW(None, False, "Local\\OtoTik_SingleInstance")
        already = kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
        if not already or time.time() >= deadline:
            break
        kernel32.CloseHandle(_mutex)
        _mutex = None
        time.sleep(0.25)
    if already:
        hwnd = ctypes.windll.user32.FindWindowW(None, f"{APP_NAME} {VERSION}")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        return False
    return True


def main():
    if not ensure_single_instance(wait=6.0 if "--elevated" in sys.argv else 0.0):
        return
    App().run()
