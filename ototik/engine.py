"""Çalışma motoru: giriş simülasyonu, kısayol yöneticisi ve görev iş parçacıkları.

Bu modüldeki hiçbir kod Tkinter'a dokunmaz; arayüze yalnızca `post(event)` ile
mesaj gönderir. (Eski sürümdeki "arka plandan arayüz güncelleme" çökme hatası
böyle giderildi.)
"""
import ctypes
import json
import os
import random
import sys
import threading
import time

import keyboard
import mouse

IS_WIN = sys.platform.startswith("win")

# ---------------------------------------------------------------------------
# Düşük seviye giriş (Windows'ta doğrudan user32, diğerlerinde `mouse` kütüphanesi)
# ---------------------------------------------------------------------------
if IS_WIN:
    _user32 = ctypes.windll.user32
    _gdi32 = ctypes.windll.gdi32

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    _FLAGS = {
        "left": (0x0002, 0x0004),
        "right": (0x0008, 0x0010),
        "middle": (0x0020, 0x0040),
    }
    _user32.GetDC.restype = ctypes.c_void_p
    _user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _gdi32.GetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    _gdi32.GetPixel.restype = ctypes.c_uint32


def get_pos():
    if IS_WIN:
        pt = _POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    return mouse.get_position()


def move_to(x, y):
    if IS_WIN:
        _user32.SetCursorPos(int(x), int(y))
    else:
        mouse.move(int(x), int(y))


def mouse_down(button="left"):
    if IS_WIN:
        _user32.mouse_event(_FLAGS[button][0], 0, 0, 0, 0)
    else:
        mouse.press(button)


def mouse_up(button="left"):
    if IS_WIN:
        _user32.mouse_event(_FLAGS[button][1], 0, 0, 0, 0)
    else:
        mouse.release(button)


def get_pixel(x, y):
    """(r, g, b) ya da okunamazsa None."""
    if IS_WIN:
        hdc = _user32.GetDC(None)
        try:
            c = _gdi32.GetPixel(hdc, int(x), int(y))
        finally:
            _user32.ReleaseDC(None, hdc)
        if c == 0xFFFFFFFF:
            return None
        return c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF
    try:
        from PIL import ImageGrab
        return ImageGrab.grab(bbox=(x, y, x + 1, y + 1), all_screens=True).getpixel((0, 0))[:3]
    except Exception:
        return None


def virtual_screen():
    """Tüm monitörleri kapsayan sanal ekran (x, y, w, h)."""
    if IS_WIN:
        return (_user32.GetSystemMetrics(76), _user32.GetSystemMetrics(77),
                _user32.GetSystemMetrics(78), _user32.GetSystemMetrics(79))
    return 0, 0, 1920, 1080


def hex_to_rgb(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02X%02X%02X" % tuple(rgb)


def color_distance(a, b):
    return max(abs(a[i] - b[i]) for i in range(3))


def beep(kind, enabled=True):
    if not enabled or not IS_WIN:
        return
    tones = {"start": [(880, 70), (1320, 90)], "stop": [(990, 70), (520, 110)],
             "point": [(1200, 60)], "rec": [(700, 80), (700, 80)], "error": [(300, 200)],
             "done": [(784, 80), (988, 80), (1318, 120)]}

    def run():
        try:
            import winsound
            for f, d in tones.get(kind, []):
                winsound.Beep(f, d)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def interruptible_sleep(stop_event, seconds):
    """stop_event set edilirse erken döner. True = uyku tamamlandı."""
    if seconds <= 0:
        return not stop_event.is_set()
    return not stop_event.wait(seconds)


def _num(v, default=0.0, lo=None, hi=None):
    try:
        v = float(v)
    except (TypeError, ValueError):
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


# ---------------------------------------------------------------------------
# Kısayol yöneticisi
# ---------------------------------------------------------------------------
MODIFIERS = {"ctrl", "shift", "alt", "alt gr", "windows"}


def normalize_key(name):
    if not name:
        return ""
    n = name.lower()
    for pre in ("left ", "right "):
        if n.startswith(pre) and n[len(pre):] in ("ctrl", "shift", "alt", "windows"):
            n = n[len(pre):]
    return {"control": "ctrl", "win": "windows", "cmd": "windows", "escape": "esc",
            "return": "enter", "spacebar": "space"}.get(n, n)


def parse_combo(combo):
    """"ctrl+f8" -> (frozenset({'ctrl'}), 'f8'); fare: "mouse:x" -> (frozenset(), 'mouse:x')."""
    combo = (combo or "").strip().lower()
    if not combo:
        return None
    if combo.startswith("mouse:"):
        return frozenset(), combo
    parts = [normalize_key(p.strip()) for p in combo.split("+") if p.strip()]
    if not parts:
        return None
    return frozenset(parts[:-1]), parts[-1]


def pretty_combo(combo):
    if not combo:
        return "—"
    if combo.startswith("mouse:"):
        return {"mouse:x": "Mouse 4", "mouse:x2": "Mouse 5", "mouse:middle": "Mouse 3"}.get(combo, combo)
    return " + ".join(p.strip().upper() if len(p.strip()) <= 3 else p.strip().title() for p in combo.split("+"))


class InputHub:
    """Tek bir klavye + fare kancası: kısayollar, kısayol yakalama ve makro kaydı burada."""

    def __init__(self, post):
        self.post = post
        self.pressed = set()
        self.bindings = {}          # action -> (mods, key)
        self.hold_actions = set()   # basılı tutma modunda çalışan eylemler
        self.capture_cb = None
        self.recorder = None
        self.enabled = True
        self._kb_hook = keyboard.hook(self._on_key)
        mouse.hook(self._on_mouse)

    def close(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        try:
            mouse.unhook_all()
        except Exception:
            pass

    def set_bindings(self, hotkeys, hold_actions=()):
        b = {}
        for action, combo in hotkeys.items():
            parsed = parse_combo(combo)
            if parsed:
                b[action] = parsed
        self.bindings = b
        self.hold_actions = set(hold_actions)

    def hotkey_keys(self):
        """Makro kaydından çıkarılacak tuş adları."""
        keys = set()
        for mods, key in self.bindings.values():
            keys.add(key)
        return keys

    def start_capture(self, callback):
        self.pressed.clear()
        self.capture_cb = callback

    def cancel_capture(self):
        self.capture_cb = None

    # --- olaylar ---
    def _on_key(self, e):
        try:
            name = normalize_key(e.name or "")
            if not name:
                return
            if self.recorder is not None:
                self.recorder.key_event(e, name)
            if e.event_type == keyboard.KEY_DOWN:
                repeat = name in self.pressed
                self.pressed.add(name)
                if repeat:
                    return
                if self.capture_cb is not None:
                    if name in MODIFIERS:
                        return
                    cb, self.capture_cb = self.capture_cb, None
                    if name == "esc":
                        cb(None)
                    else:
                        mods = sorted(m for m in self.pressed if m in MODIFIERS)
                        cb("+".join(mods + [name]))
                    return
                if not self.enabled:
                    return
                for action, (mods, key) in self.bindings.items():
                    if key == name and mods <= self.pressed and \
                            not ((self.pressed & MODIFIERS) - mods - {name}):
                        self.post(("hotkey", action, "down"))
            elif e.event_type == keyboard.KEY_UP:
                self.pressed.discard(name)
                if self.enabled:
                    for action in self.hold_actions:
                        b = self.bindings.get(action)
                        if b and b[1] == name:
                            self.post(("hotkey", action, "up"))
        except Exception:
            pass

    def _on_mouse(self, e):
        try:
            if self.recorder is not None:
                self.recorder.mouse_event(e)
            if isinstance(e, mouse.ButtonEvent) and e.button in ("x", "x2"):
                combo = "mouse:" + e.button
                if e.event_type in ("down", "double"):
                    if self.capture_cb is not None:
                        cb, self.capture_cb = self.capture_cb, None
                        cb(combo)
                        return
                    if not self.enabled:
                        return
                    for action, (mods, key) in self.bindings.items():
                        if key == combo:
                            self.post(("hotkey", action, "down"))
                elif e.event_type == "up" and self.enabled:
                    for action in self.hold_actions:
                        b = self.bindings.get(action)
                        if b and b[1] == combo:
                            self.post(("hotkey", action, "up"))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Görevler
# ---------------------------------------------------------------------------
class Task:
    name = "task"

    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.post = app.post
        self.stop_event = threading.Event()
        self.thread = None
        self.state = "idle"     # idle / waiting / running
        self.count = 0
        self.started_at = 0.0
        self.wait_until = 0.0

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        if self.running:
            return False
        self.stop_event = threading.Event()
        self.count = 0
        self.started_at = time.time()
        self.state = "waiting"
        self.thread = threading.Thread(target=self._wrap, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.stop_event.set()

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def _countdown(self, seconds):
        seconds = _num(seconds, 0, 0, 3600)
        if seconds > 0:
            self.state = "waiting"
            self.wait_until = time.time() + seconds
            self.post(("log", "log_delay", {"s": f"{seconds:g}"}))
            if not interruptible_sleep(self.stop_event, seconds):
                return False
        self.state = "running"
        self.started_at = time.time()
        return True

    def _wrap(self):
        self.post(("task", self.name, "start"))
        reason = "stopped"
        try:
            reason = self.run() or "stopped"
        except Exception as ex:  # görev hatası uygulamayı çökertmesin
            reason = "error"
            self.post(("log", "log_error", {"e": str(ex)}))
        finally:
            self.cleanup()
            self.state = "idle"
            self.post(("task", self.name, reason))

    def cleanup(self):
        pass

    def run(self):
        raise NotImplementedError

    def failsafe(self):
        """Fare sol üst köşeye götürülürse acil durdurma."""
        if self.cfg["app"]["failsafe"]:
            x, y = get_pos()
            vx, vy, _, _ = virtual_screen()
            if x <= vx + 1 and y <= vy + 1:
                self.post(("failsafe",))
                return True
        return False


class Clicker(Task):
    name = "clicker"

    def __init__(self, app):
        super().__init__(app)
        self.holding = None
        self.point_index = 0

    def cleanup(self):
        if self.holding:
            try:
                mouse_up(self.holding)
            except Exception:
                pass
            self.holding = None

    def _target(self, c):
        pos = c["position"]
        pts = [p for p in c["points"] if isinstance(p, (list, tuple)) and len(p) == 2]
        if pos == "points" and pts:
            p = pts[self.point_index % len(pts)]
            self.point_index += 1
            x, y = int(p[0]), int(p[1])
        elif pos == "area" and len(pts) >= 2:
            (x1, y1), (x2, y2) = pts[0], pts[1]
            x = random.randint(min(x1, x2), max(x1, x2))
            y = random.randint(min(y1, y2), max(y1, y2))
        else:
            return None
        j = int(_num(c["jitter"], 0, 0, 500))
        if j:
            x += random.randint(-j, j)
            y += random.randint(-j, j)
        return x, y

    def run(self):
        c = self.cfg["clicker"]
        if not self._countdown(c["start_delay"]):
            return "stopped"
        self.point_index = 0
        last_set = None   # imleci en son bizim koyduğumuz konum
        btn = c["button"] if c["button"] in ("left", "right", "middle") else "left"

        # Basılı tut modu: tuşu bas, durdurulana kadar bekle
        if c["click_type"] == "hold":
            target = self._target(c)
            if target:
                move_to(*target)
            mouse_down(btn)
            self.holding = btn
            self.count = 1
            limit_s = _num(c["limit_seconds"], 0, 0)
            while not self.stop_event.wait(0.05):
                if self.failsafe():
                    return "failsafe"
                if limit_s and time.time() - self.started_at >= limit_s:
                    return "limit"
            return "stopped"

        clicks_per = {"single": 1, "double": 2, "triple": 3}.get(c["click_type"], 1)
        next_time = time.perf_counter()
        while not self.stop_event.is_set():
            # ayarlar canlı okunur: çalışırken değiştirilebilir
            btn = c["button"] if c["button"] in ("left", "right", "middle") else "left"
            clicks_per = {"single": 1, "double": 2, "triple": 3}.get(c["click_type"], 1)
            lim_c = int(_num(c["limit_clicks"], 0, 0))
            lim_s = _num(c["limit_seconds"], 0, 0)
            if lim_c and self.count >= lim_c:
                return "limit"
            if lim_s and time.time() - self.started_at >= lim_s:
                return "limit"
            if self.failsafe():
                return "failsafe"

            cur = get_pos()
            if c["stop_on_move"] and last_set is not None:
                if abs(cur[0] - last_set[0]) > 15 or abs(cur[1] - last_set[1]) > 15:
                    self.post(("log", "log_moved", {}))
                    return "moved"

            target = self._target(c)
            hold = _num(c["hold_ms"], 20, 0, 5000) / 1000.0
            if target:
                move_to(*target)
                time.sleep(0.002)
            for i in range(clicks_per):
                mouse_down(btn)
                if hold:
                    time.sleep(hold)
                mouse_up(btn)
                if i < clicks_per - 1:
                    time.sleep(0.03)
            self.count += 1
            if target and c["return_cursor"]:
                move_to(*cur)
                last_set = cur
            else:
                last_set = get_pos()

            lo = _num(c["min_ms"], 100, 1, 3_600_000)
            hi = _num(c["max_ms"], lo, 1, 3_600_000)
            if hi < lo:
                lo, hi = hi, lo
            delay = random.uniform(lo, hi) / 1000.0
            next_time += delay
            now = time.perf_counter()
            if next_time < now - 0.25:      # çok gerideysek yetişmeye çalışma
                next_time = now
            wait = next_time - now
            if wait > 0.03:
                if self.stop_event.wait(wait - 0.02):
                    break
            # son milisaniyeler için hassas bekleme
            while not self.stop_event.is_set():
                rem = next_time - time.perf_counter()
                if rem <= 0:
                    break
                if rem > 0.002:
                    time.sleep(0.001)
        return "stopped"


class KeyPresser(Task):
    name = "keys"

    def run(self):
        k = self.cfg["keys"]
        key = (k["key"] or "").strip()
        if not key:
            self.post(("log", "log_no_key", {}))
            return "error"
        try:
            keyboard.parse_hotkey(key)
        except Exception:
            self.post(("log", "log_bad_key", {"k": key}))
            return "error"
        if not self._countdown(k["start_delay"]):
            return "stopped"
        while not self.stop_event.is_set():
            lim = int(_num(k["limit"], 0, 0))
            if lim and self.count >= lim:
                return "limit"
            if self.failsafe():
                return "failsafe"
            hold = _num(k["hold_ms"], 30, 0, 10000) / 1000.0
            try:
                keyboard.press(key)
                if hold:
                    time.sleep(hold)
            finally:
                keyboard.release(key)
            self.count += 1
            lo = _num(k["min_ms"], 500, 1)
            hi = _num(k["max_ms"], lo, 1)
            if hi < lo:
                lo, hi = hi, lo
            if not interruptible_sleep(self.stop_event, random.uniform(lo, hi) / 1000.0):
                break
        return "stopped"


class Typer(Task):
    name = "typer"

    def run(self):
        t = self.cfg["typer"]
        text = t["text"]
        if not text.strip():
            self.post(("log", "log_no_text", {}))
            return "error"
        if not self._countdown(t["start_delay"]):
            return "stopped"
        repeat = int(_num(t["repeat"], 1, 0))
        n = 0
        while not self.stop_event.is_set() and (repeat == 0 or n < repeat):
            delay = _num(t["char_ms"], 30, 0, 5000) / 1000.0
            for ch in text:
                if self.stop_event.is_set() or self.failsafe():
                    return "stopped"
                if ch == "\n":
                    keyboard.send("enter")
                elif ch == "\t":
                    keyboard.send("tab")
                else:
                    keyboard.write(ch)
                if delay:
                    time.sleep(delay)
            if t["press_enter"]:
                keyboard.send("enter")
            n += 1
            self.count = n
            if repeat == 0 or n < repeat:
                if not interruptible_sleep(self.stop_event, _num(t["between_ms"], 1000, 0) / 1000.0):
                    break
        return "done" if not self.stop_event.is_set() else "stopped"


# ---------------------------------------------------------------------------
# Makro
# ---------------------------------------------------------------------------
class MacroRecorder:
    def __init__(self, hub, record_moves=True):
        self.hub = hub
        self.record_moves = record_moves
        self.events = []
        self.t0 = time.perf_counter()
        self.skip_keys = hub.hotkey_keys()
        self._last_move = 0.0

    def _t(self):
        return round(time.perf_counter() - self.t0, 4)

    def key_event(self, e, name):
        if name in self.skip_keys:
            return
        self.events.append({"t": self._t(), "k": "key",
                            "e": "down" if e.event_type == keyboard.KEY_DOWN else "up",
                            "name": e.name, "sc": e.scan_code})

    def mouse_event(self, e):
        if isinstance(e, mouse.MoveEvent):
            if not self.record_moves:
                return
            now = time.perf_counter()
            if now - self._last_move < 0.008:   # ~120 Hz yeterli
                return
            self._last_move = now
            self.events.append({"t": self._t(), "k": "move", "x": e.x, "y": e.y})
        elif isinstance(e, mouse.ButtonEvent):
            if e.button in ("x", "x2") and any(k.startswith("mouse:") for k in self.skip_keys):
                return
            x, y = get_pos()
            et = "down" if e.event_type in ("down", "double") else "up"
            self.events.append({"t": self._t(), "k": "btn", "e": et, "b": e.button, "x": x, "y": y})
        elif isinstance(e, mouse.WheelEvent):
            self.events.append({"t": self._t(), "k": "wheel", "d": e.delta})

    def finish(self, from_gui=False):
        ev = self.events
        if from_gui:
            # Durdur butonuna yapılan son tıklamayı kayıttan çıkar
            for i in range(len(ev) - 1, -1, -1):
                if ev[i]["k"] == "btn" and ev[i]["e"] == "down":
                    ev = ev[:i]
                    break
        # bırakılmamış tuşları kapat
        down_keys, down_btns = {}, {}
        for e in ev:
            if e["k"] == "key":
                if e["e"] == "down":
                    down_keys[e["name"]] = e
                else:
                    down_keys.pop(e["name"], None)
            elif e["k"] == "btn":
                if e["e"] == "down":
                    down_btns[e["b"]] = e
                else:
                    down_btns.pop(e["b"], None)
        end = ev[-1]["t"] if ev else 0
        for e in down_keys.values():
            ev.append({**e, "e": "up", "t": end})
        for e in down_btns.values():
            ev.append({**e, "e": "up", "t": end})
        return ev


def macro_duration(events):
    return events[-1]["t"] if events else 0.0


def save_macro(path, events, meta=None):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"format": "ototik-macro", "version": 1, "meta": meta or {}, "events": events},
                  f, ensure_ascii=False)


def load_macro(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    events = data.get("events", data if isinstance(data, list) else [])
    if not isinstance(events, list):
        raise ValueError("invalid macro")
    return [e for e in events if isinstance(e, dict) and "t" in e and "k" in e]


class MacroPlayer(Task):
    name = "macro"

    def __init__(self, app):
        super().__init__(app)
        self.events = []
        self.loop = 0
        self._down_keys = set()
        self._down_btns = set()

    def cleanup(self):
        for k in list(self._down_keys):
            try:
                keyboard.release(k)
            except Exception:
                pass
        for b in list(self._down_btns):
            try:
                mouse.release(b)
            except Exception:
                pass
        self._down_keys.clear()
        self._down_btns.clear()

    @staticmethod
    def _key_ref(e):
        name = e.get("name") or ""
        if len(name) > 1:
            try:
                keyboard.key_to_scan_codes(name)
                return name
            except Exception:
                pass
        return e.get("sc") or name

    def run(self):
        m = self.cfg["macro"]
        events = list(self.events)
        if not events:
            self.post(("log", "log_no_macro", {}))
            return "error"
        repeat = int(_num(m["repeat"], 1, 0))
        self.state = "running"
        self.loop = 0
        while not self.stop_event.is_set() and (repeat == 0 or self.loop < repeat):
            speed = _num(m["speed"], 1.0, 0.1, 20.0)
            t0 = time.perf_counter()
            for e in events:
                target = t0 + e["t"] / speed
                while True:
                    left = target - time.perf_counter()
                    if left <= 0:
                        break
                    if self.stop_event.wait(min(left, 0.05)):
                        return "stopped"
                if self.failsafe():
                    return "failsafe"
                kind = e["k"]
                try:
                    if kind == "move":
                        move_to(e["x"], e["y"])
                    elif kind == "btn":
                        if "x" in e:
                            move_to(e["x"], e["y"])
                        if e["e"] == "down":
                            mouse.press(e["b"])
                            self._down_btns.add(e["b"])
                        else:
                            mouse.release(e["b"])
                            self._down_btns.discard(e["b"])
                    elif kind == "wheel":
                        mouse.wheel(e["d"])
                    elif kind == "key":
                        ref = self._key_ref(e)
                        if e["e"] == "down":
                            keyboard.press(ref)
                            self._down_keys.add(ref)
                        else:
                            keyboard.release(ref)
                            self._down_keys.discard(ref)
                except Exception:
                    pass
            self.loop += 1
            self.count = self.loop
            if repeat == 0 or self.loop < repeat:
                if not interruptible_sleep(self.stop_event, _num(m["loop_delay_ms"], 0, 0) / 1000.0):
                    break
        return "done" if not self.stop_event.is_set() else "stopped"


# ---------------------------------------------------------------------------
# Renk tetikleyici
# ---------------------------------------------------------------------------
class PixelTrigger(Task):
    name = "trigger"

    def run(self):
        t = self.cfg["trigger"]
        try:
            x, y = int(t["x"]), int(t["y"])
            target = hex_to_rgb(t["color"])
        except Exception:
            self.post(("log", "log_trigger_cfg", {}))
            return "error"
        self.state = "running"
        self.started_at = time.time()
        base = get_pixel(x, y)
        last_fire = 0.0
        armed = True
        while not self.stop_event.wait(0.03):
            if self.failsafe():
                return "failsafe"
            px = get_pixel(x, y)
            if px is None:
                continue
            tol = int(_num(t["tolerance"], 10, 0, 255))
            if t["mode"] == "change":
                hit = base is not None and color_distance(px, base) > tol
            else:
                hit = color_distance(px, target) <= tol
            if not hit:
                armed = True
                continue
            now = time.time()
            if not armed or now - last_fire < _num(t["cooldown_ms"], 500, 0) / 1000.0:
                continue
            armed = False   # tekrar tetiklemek için renk önce eşleşmeyi bırakmalı
            last_fire = now
            self._fire(t, x, y)
            self.count += 1
            self.post(("log", "log_triggered", {"c": rgb_to_hex(px)}))
            if t["mode"] == "change":
                base = px
            if t["once"]:
                return "done"
        return "stopped"

    def _fire(self, t, x, y):
        if t["action"] == "key":
            try:
                keyboard.send(t["key"])
            except Exception:
                pass
            return
        btn = t["button"] if t["button"] in ("left", "right", "middle") else "left"
        if t["click_at"] == "point":
            cur = get_pos()
            move_to(x, y)
            time.sleep(0.005)
            mouse_down(btn); time.sleep(0.02); mouse_up(btn)
            move_to(*cur)
        else:
            mouse_down(btn); time.sleep(0.02); mouse_up(btn)


def is_admin():
    if not IS_WIN:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    """Uygulamayı yönetici olarak yeniden başlatır (UAC penceresi açılır)."""
    if not IS_WIN:
        return False
    if getattr(sys, "frozen", False):
        exe, params, cwd = sys.executable, "--elevated", os.path.dirname(sys.executable)
    else:
        exe = sys.executable
        if exe.lower().endswith("python.exe"):
            pyw = exe[:-10] + "pythonw.exe"
            exe = pyw if os.path.exists(pyw) else exe
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        params = "-m ototik --elevated"
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, cwd, 1)
    return r > 32
