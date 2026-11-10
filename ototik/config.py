"""Ayar yönetimi: yükleme, kaydetme, profiller ve eski sürümden aktarma."""
import copy
import json
import os
import re
import sys
import threading

APP_NAME = "OtoTık"
APP_ID = "OtoTik"
VERSION = "2.0.0"


def _config_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_ID)
    os.makedirs(path, exist_ok=True)
    return path


CONFIG_DIR = _config_dir()
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")
PROFILE_DIR = os.path.join(CONFIG_DIR, "profiles")
MACRO_DIR = os.path.join(CONFIG_DIR, "macros")
os.makedirs(PROFILE_DIR, exist_ok=True)
os.makedirs(MACRO_DIR, exist_ok=True)


def app_dir():
    """Exe ya da betiğin bulunduğu klasör."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Profil ile kaydedilen bölümler (dil/tema/kısayol gibi genel ayarlar hariç)
PROFILE_SECTIONS = ("clicker", "keys", "typer", "macro", "trigger")

DEFAULTS = {
    "app": {
        "language": "",          # boş = sistem dilinden algıla
        "theme": "midnight",
        "accent": "",            # boş = temanın kendi vurgu rengi
        "topmost": True,
        "opacity": 1.0,
        "sound": True,
        "osd": True,
        "failsafe": True,        # fare sol üst köşeye giderse her şeyi durdur
        "compact": False,
        "geometry": "",
        "profile": "Varsayılan",
        "page": "clicker",
        "ui_scale": 1.0,
    },
    "hotkeys": {
        "clicker": "f8",
        "keys": "f7",
        "typer": "ctrl+f7",
        "macro_play": "f9",
        "macro_record": "f11",
        "trigger": "ctrl+f8",
        "add_point": "f6",
        "stop_all": "f12",
        "hide": "f10",
    },
    "clicker": {
        "button": "left",        # left / right / middle
        "click_type": "single",  # single / double / triple / hold
        "min_ms": 80,
        "max_ms": 160,
        "hold_ms": 20,
        "position": "cursor",    # cursor / points / area
        "points": [],            # [[x, y], ...]
        "jitter": 0,
        "return_cursor": False,
        "stop_on_move": False,
        "limit_clicks": 0,
        "limit_seconds": 0,
        "start_delay": 0,
        "hold_to_run": False,    # kısayola basılı tuttukça çalış
        "schedule": "",          # "HH:MM" -> o saatte otomatik başlat
    },
    "keys": {
        "key": "space",
        "min_ms": 500,
        "max_ms": 500,
        "hold_ms": 30,
        "limit": 0,
        "start_delay": 0,
    },
    "typer": {
        "text": "",
        "char_ms": 30,
        "repeat": 1,
        "between_ms": 1000,
        "press_enter": True,
        "start_delay": 3,
    },
    "macro": {
        "repeat": 1,             # 0 = sonsuz
        "speed": 1.0,
        "loop_delay_ms": 0,
        "record_moves": True,
        "current": "",
    },
    "trigger": {
        "x": "",
        "y": "",
        "color": "#00FF00",
        "tolerance": 10,
        "mode": "match",         # match / change
        "action": "click",       # click / key
        "button": "left",
        "key": "space",
        "click_at": "point",     # point / cursor
        "cooldown_ms": 500,
        "once": False,
    },
    "stats": {
        "total_clicks": 0,
        "total_keys": 0,
        "total_seconds": 0,
        "best_cps": 0.0,
        "launches": 0,
    },
}


def _merge(base, extra):
    """extra içindeki geçerli anahtarları base'in üzerine yazar (tip kontrolüyle)."""
    for key, val in extra.items():
        if key not in base:
            continue
        if isinstance(base[key], dict) and isinstance(val, dict):
            _merge(base[key], val)
        elif isinstance(base[key], bool):
            base[key] = bool(val)
        elif isinstance(base[key], (int, float)) and not isinstance(val, bool) and isinstance(val, (int, float)):
            base[key] = type(base[key])(val) if isinstance(base[key], int) and float(val).is_integer() else val
        elif isinstance(base[key], type(val)) or base[key] in ("", None) or isinstance(base[key], list):
            base[key] = val
    return base


class Config:
    def __init__(self):
        self.data = copy.deepcopy(DEFAULTS)
        self._lock = threading.RLock()
        self._save_timer = None
        self.first_run = not os.path.exists(CONFIG_FILE)
        self.load()

    # --- erişim ---
    def __getitem__(self, section):
        return self.data[section]

    def get(self, section, key):
        return self.data[section][key]

    def set(self, section, key, value):
        self.data[section][key] = value
        self.save_later()

    # --- disk ---
    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    _merge(self.data, json.load(f))
            except Exception:
                pass
        else:
            self._migrate_old()

    def save(self):
        with self._lock:
            tmp = CONFIG_FILE + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, CONFIG_FILE)
            except Exception:
                pass

    def save_later(self, delay=1.0):
        """Sık değişikliklerde diski yormamak için gecikmeli kayıt."""
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(delay, self.save)
        self._save_timer.daemon = True
        self._save_timer.start()

    # --- eski sürümden aktarma ---
    def _migrate_old(self):
        names = ["clicker_ultimate_ayarlar.json", "clicker_premium_ayarlar.json", "clicker_ayarlar.json"]
        for folder in (app_dir(), os.getcwd()):
            for name in names:
                path = os.path.join(folder, name)
                if not os.path.exists(path):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        old = json.load(f)
                except Exception:
                    continue
                c = self.data["clicker"]
                try:
                    c["min_ms"] = int(float(old.get("min_w", 0.08)) * 1000)
                    c["max_ms"] = int(float(old.get("max_w", 0.16)) * 1000)
                    c["hold_ms"] = int(float(old.get("hold_t", 0.02)) * 1000)
                    c["jitter"] = int(old.get("jitter", 0))
                    c["button"] = {"Sağ Tık": "right", "Orta Tık": "middle"}.get(old.get("tus"), "left")
                    c["click_type"] = "double" if old.get("tip") == "Çift Tık" else "single"
                    c["stop_on_move"] = bool(old.get("sensor"))
                    c["hold_to_run"] = bool(old.get("hold_mode"))
                    c["limit_clicks"] = int(old.get("limit_click", 0))
                    c["limit_seconds"] = int(old.get("limit_time", 0))
                    c["start_delay"] = int(old.get("delay_start", 0))
                    pts = []
                    for a, b in (("t_x1", "t_y1"), ("t_x2", "t_y2")):
                        if str(old.get(a, "")).strip() and str(old.get(b, "")).strip():
                            pts.append([int(old[a]), int(old[b])])
                    c["points"] = pts if old.get("pingpong") else pts[:1]
                    if old.get("mod") == "Sabit" and pts:
                        c["position"] = "points"
                    hk = self.data["hotkeys"]
                    for action, old_key in (("clicker", "k_start"), ("hide", "k_boss")):
                        new = str(old.get(old_key) or "").lower().strip()
                        if not new or hk[action] == new:
                            continue
                        # eski tuş başka bir eylemde kullanılıyorsa ikisini yer değiştir
                        for other, combo in hk.items():
                            if other != action and combo == new:
                                hk[other] = hk[action]
                        hk[action] = new
                    self.data["app"]["sound"] = bool(old.get("sound", True))
                    self.data["app"]["topmost"] = bool(old.get("topmost", True))
                    self.data["app"]["opacity"] = max(0.3, min(1.0, float(old.get("opacity", 1.0))))
                except Exception:
                    pass
                return

    # --- profiller ---
    @staticmethod
    def _safe(name):
        return re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "profil"

    def list_profiles(self):
        names = [os.path.splitext(n)[0] for n in os.listdir(PROFILE_DIR) if n.endswith(".json")]
        return sorted(names, key=str.lower)

    def save_profile(self, name):
        name = self._safe(name)
        payload = {s: self.data[s] for s in PROFILE_SECTIONS}
        with open(os.path.join(PROFILE_DIR, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self.data["app"]["profile"] = name
        self.save_later()
        return name

    def load_profile(self, name):
        path = os.path.join(PROFILE_DIR, self._safe(name) + ".json")
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        for s in PROFILE_SECTIONS:
            self.data[s] = copy.deepcopy(DEFAULTS[s])
            if isinstance(payload.get(s), dict):
                _merge(self.data[s], payload[s])
        self.data["app"]["profile"] = name
        self.save_later()

    def delete_profile(self, name):
        path = os.path.join(PROFILE_DIR, self._safe(name) + ".json")
        if os.path.exists(path):
            os.remove(path)

    def export_to(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def import_from(self, path):
        with open(path, "r", encoding="utf-8") as f:
            _merge(self.data, json.load(f))
        self.save()

    def reset_section(self, section):
        self.data[section] = copy.deepcopy(DEFAULTS[section])
        self.save_later()
