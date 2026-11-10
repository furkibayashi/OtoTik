"""Renk temaları ve CustomTkinter tema sözlüğü üreticisi."""
import customtkinter as ctk

# Her tema: mode, bg (pencere), side (yan menü), card (kartlar), card2 (iç alan),
# entry, border, text, sub (ikincil metin), accent, accent_text, ok, warn, err
THEMES = {
    "midnight": dict(mode="dark", bg="#0f1420", side="#0b0f19", card="#161d2d", card2="#1d2639",
                     entry="#111827", border="#2a3550", text="#e6ebf5", sub="#8b97b0",
                     accent="#4f8cff", accent_text="#ffffff", ok="#2ecc71", warn="#f5a524", err="#ff5c6c"),
    "light": dict(mode="light", bg="#f3f5f9", side="#e6eaf1", card="#ffffff", card2="#f0f3f8",
                  entry="#ffffff", border="#d3d9e4", text="#1b2333", sub="#5d6a80",
                  accent="#2f6fed", accent_text="#ffffff", ok="#1f9d55", warn="#d98b00", err="#e0384b"),
    "neon": dict(mode="dark", bg="#0a0a12", side="#07070d", card="#12121f", card2="#191930",
                 entry="#0d0d18", border="#2d2d55", text="#f0f0ff", sub="#9a9ac8",
                 accent="#ff2bd6", accent_text="#ffffff", ok="#21f5c1", warn="#ffd23f", err="#ff3b6b"),
    "ocean": dict(mode="dark", bg="#0b1a22", side="#08141a", card="#10242f", card2="#153140",
                  entry="#0b1c25", border="#1f4557", text="#e2f3f8", sub="#86aab8",
                  accent="#1ec8c8", accent_text="#04222a", ok="#3ddc97", warn="#ffb547", err="#ff6b6b"),
    "forest": dict(mode="dark", bg="#0f1712", side="#0b120e", card="#16211a", card2="#1c2b21",
                   entry="#111a14", border="#2b3f31", text="#e6f2e8", sub="#8fa995",
                   accent="#4cc26a", accent_text="#06210f", ok="#7bd88f", warn="#e9b949", err="#ef6a5b"),
    "sunset": dict(mode="dark", bg="#1a1012", side="#140b0d", card="#24161a", card2="#2e1c21",
                   entry="#1c1114", border="#4a2a31", text="#fbe9e4", sub="#c49a92",
                   accent="#ff7a3d", accent_text="#2a0e02", ok="#6fd08c", warn="#ffc04d", err="#ff4f6d"),
    "vampire": dict(mode="dark", bg="#16111f", side="#110d18", card="#1f182b", card2="#281f37",
                    entry="#18121f", border="#3b2e52", text="#eee6fb", sub="#a596bf",
                    accent="#bd7bff", accent_text="#1b0b2e", ok="#57e3a0", warn="#ffc66d", err="#ff5f87"),
    "terminal": dict(mode="dark", bg="#050805", side="#030503", card="#0a120a", card2="#0f1a0f",
                     entry="#060a06", border="#1d3a1d", text="#b6ffb6", sub="#5fae5f",
                     accent="#33ff66", accent_text="#022008", ok="#33ff66", warn="#e6ff4d", err="#ff4d4d"),
    "sakura": dict(mode="light", bg="#fff5f8", side="#fde6ee", card="#ffffff", card2="#fff0f5",
                   entry="#ffffff", border="#f3c9d8", text="#3a1f2b", sub="#8f6475",
                   accent="#e8578a", accent_text="#ffffff", ok="#2fa36b", warn="#d68a00", err="#d93a4b"),
    "coffee": dict(mode="light", bg="#f5efe7", side="#ebe1d4", card="#fffaf4", card2="#f4ebe0",
                   entry="#fffdf9", border="#dccbb6", text="#3b2a1e", sub="#7d6551",
                   accent="#a0643a", accent_text="#ffffff", ok="#4f8a3c", warn="#c7811a", err="#c2413b"),
    "mono": dict(mode="dark", bg="#141414", side="#0e0e0e", card="#1c1c1c", card2="#242424",
                 entry="#121212", border="#363636", text="#ededed", sub="#9a9a9a",
                 accent="#e0e0e0", accent_text="#111111", ok="#9be39b", warn="#e3cf7a", err="#ef8a8a"),
    "arctic": dict(mode="light", bg="#eef4f8", side="#dfe9f0", card="#ffffff", card2="#eaf2f7",
                   entry="#ffffff", border="#c8d8e4", text="#16303f", sub="#5a7486",
                   accent="#0e9bd8", accent_text="#ffffff", ok="#17a673", warn="#d39200", err="#d6455d"),
}

THEME_ORDER = list(THEMES.keys())


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def mix(c1, c2, t):
    """c1 ile c2 arasında t oranında karışım."""
    a, b = _hex_to_rgb(c1), _hex_to_rgb(c2)
    return _rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def readable_text(bg):
    r, g, b = _hex_to_rgb(bg)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#111111" if lum > 150 else "#ffffff"


def palette(name, accent_override=""):
    p = dict(THEMES.get(name, THEMES["midnight"]))
    if accent_override:
        try:
            _hex_to_rgb(accent_override)
            p["accent"] = accent_override
            p["accent_text"] = readable_text(accent_override)
        except Exception:
            pass
    dark = p["mode"] == "dark"
    p["accent_hover"] = mix(p["accent"], "#000000" if not dark else "#ffffff", 0.18)
    p["accent_soft"] = mix(p["card"], p["accent"], 0.18)
    p["hover"] = mix(p["card2"], p["text"], 0.08)
    p["muted"] = mix(p["card2"], p["text"], 0.18)
    return p


def build_ctk_theme(p):
    """Paletten CustomTkinter tema sözlüğü üretir (yeni oluşturulan widget'lar bunu kullanır)."""
    def two(c):
        return [c, c]

    font_family = "Segoe UI"
    return {
        "CTk": {"fg_color": two(p["bg"])},
        "CTkToplevel": {"fg_color": two(p["bg"])},
        "CTkFrame": {"corner_radius": 10, "border_width": 0, "fg_color": two(p["card"]),
                     "top_fg_color": two(p["card2"]), "border_color": two(p["border"])},
        "CTkButton": {"corner_radius": 8, "border_width": 0, "fg_color": two(p["accent"]),
                      "hover_color": two(p["accent_hover"]), "border_color": two(p["border"]),
                      "text_color": two(p["accent_text"]), "text_color_disabled": two(p["sub"])},
        "CTkLabel": {"corner_radius": 0, "border_width": 0, "fg_color": "transparent",
                     "border_color": two(p["border"]), "text_color": two(p["text"])},
        "CTkEntry": {"corner_radius": 7, "border_width": 1, "fg_color": two(p["entry"]),
                     "border_color": two(p["border"]), "text_color": two(p["text"]),
                     "placeholder_text_color": two(p["sub"])},
        "CTkCheckBox": {"corner_radius": 5, "border_width": 2, "fg_color": two(p["accent"]),
                        "border_color": two(p["border"]), "hover_color": two(p["accent_hover"]),
                        "checkmark_color": two(p["accent_text"]), "text_color": two(p["text"]),
                        "text_color_disabled": two(p["sub"])},
        "CTkSwitch": {"corner_radius": 1000, "border_width": 3, "button_length": 0,
                      "fg_color": two(p["muted"]), "progress_color": two(p["accent"]),
                      "button_color": two("#ffffff" if p["mode"] == "dark" else "#ffffff"),
                      "button_hover_color": two("#f0f0f0"), "text_color": two(p["text"]),
                      "text_color_disabled": two(p["sub"])},
        "CTkRadioButton": {"corner_radius": 1000, "border_width_checked": 6, "border_width_unchecked": 2,
                           "fg_color": two(p["accent"]), "border_color": two(p["border"]),
                           "hover_color": two(p["accent_hover"]), "text_color": two(p["text"]),
                           "text_color_disabled": two(p["sub"])},
        "CTkProgressBar": {"corner_radius": 1000, "border_width": 0, "fg_color": two(p["card2"]),
                           "progress_color": two(p["accent"]), "border_color": two(p["border"])},
        "CTkSlider": {"corner_radius": 1000, "button_corner_radius": 1000, "border_width": 6,
                      "button_length": 0, "fg_color": two(p["muted"]), "progress_color": two(p["accent"]),
                      "button_color": two(p["accent"]), "button_hover_color": two(p["accent_hover"])},
        "CTkOptionMenu": {"corner_radius": 7, "fg_color": two(p["card2"]), "button_color": two(p["muted"]),
                          "button_hover_color": two(p["accent"]), "text_color": two(p["text"]),
                          "text_color_disabled": two(p["sub"])},
        "CTkComboBox": {"corner_radius": 7, "border_width": 1, "fg_color": two(p["entry"]),
                        "border_color": two(p["border"]), "button_color": two(p["border"]),
                        "button_hover_color": two(p["accent"]), "text_color": two(p["text"]),
                        "text_color_disabled": two(p["sub"])},
        "CTkScrollbar": {"corner_radius": 1000, "border_spacing": 4, "fg_color": "transparent",
                         "button_color": two(p["muted"]), "button_hover_color": two(p["accent"])},
        "CTkSegmentedButton": {"corner_radius": 8, "border_width": 2, "fg_color": two(p["card2"]),
                               "selected_color": two(p["accent"]), "selected_hover_color": two(p["accent_hover"]),
                               "unselected_color": two(p["card2"]), "unselected_hover_color": two(p["hover"]),
                               "text_color": two(p["text"]), "text_color_disabled": two(p["sub"])},
        "CTkTextbox": {"corner_radius": 8, "border_width": 1, "fg_color": two(p["entry"]),
                       "border_color": two(p["border"]), "text_color": two(p["text"]),
                       "scrollbar_button_color": two(p["muted"]), "scrollbar_button_hover_color": two(p["accent"])},
        "CTkScrollableFrame": {"label_fg_color": two(p["card2"])},
        "DropdownMenu": {"fg_color": two(p["card2"]), "hover_color": two(p["accent_soft"]),
                         "text_color": two(p["text"])},
        "CTkFont": {"family": font_family, "size": 13, "weight": "normal"},
    }


def apply(name, accent_override=""):
    p = palette(name, accent_override)
    ctk.set_appearance_mode(p["mode"])
    ctk.ThemeManager.theme = build_ctk_theme(p)
    return p
