"""Monochrome palette; colour only marks state.

Green works, yellow needs attention, red is broken, grey is off."""

from __future__ import annotations

DARK = {
    "bg": "#0b0b0c", "surface": "#141416", "surface_hover": "#1b1b1e", "elevated": "#202024",
    "border": "#282830", "border_strong": "#3a3a44",
    "text": "#f2f2f3", "text_dim": "#9f9fa6", "text_muted": "#68686f", "text_inverted": "#0b0b0c",
    "success": "#4cc38a", "danger": "#f0616d", "warning": "#d9a441", "info": "#6a6a72",
    "accent": "#f2f2f3", "accent_hover": "#ffffff", "bar": "#0e0e10",
    "danger_bg": "#2a1215", "knob": "#f2f2f3",
}

LIGHT = {
    "bg": "#e8eaee", "surface": "#ffffff", "surface_hover": "#f0f1f5", "elevated": "#ffffff",
    "border": "#d2d6de", "border_strong": "#a8adb8",
    "text": "#16161a", "text_dim": "#55555f", "text_muted": "#85858f", "text_inverted": "#ffffff",
    "success": "#118a52", "danger": "#c02632", "warning": "#8a5a08", "info": "#9a9aa3",
    "accent": "#16161a", "accent_hover": "#000000", "bar": "#dfe2e8",
    "danger_bg": "#fbe9eb", "knob": "#ffffff",
}

C: dict[str, str] = dict(DARK)

LEVEL_COLOR = {"ok": "success", "warn": "warning", "down": "danger", "unknown": "info"}


def system_is_light() -> bool:
    try:
        import winreg

        path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return bool(winreg.QueryValueEx(key, "AppsUseLightTheme")[0])
    except (ImportError, OSError):
        return False


def apply(light: bool) -> None:
    C.clear()
    C.update(LIGHT if light else DARK)


def level_color(level: str) -> str:
    return C[LEVEL_COLOR.get(level, "info")]


def stylesheet() -> str:
    c = C
    return f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 10pt; color: {c['text']}; }}
QWidget#page, QDialog {{ background: {c['bg']}; }}
QToolTip {{ background: {c['elevated']}; color: {c['text']}; border: 1px solid {c['border_strong']}; padding: 4px 6px; }}

QFrame#WindowFrame {{ background: {c['bg']}; border: 1px solid {c['border_strong']}; }}
QFrame#WindowFrame[flat="true"] {{ border: none; }}
#TitleBar {{ background: {c['bar']}; border-bottom: 1px solid {c['border_strong']}; }}
QLabel#TitleCaption {{ color: {c['text_dim']}; font-weight: 600; }}
QPushButton#CaptionButton {{ background: transparent; border: none; border-radius: 0; padding: 0; color: {c['text_dim']}; font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets"; font-size: 10px; }}
QPushButton#CaptionButton:hover {{ background: {c['elevated']}; color: {c['text']}; }}
QPushButton#CaptionButton:pressed {{ background: {c['surface_hover']}; }}
QPushButton#CaptionButton[close="true"]:hover {{ background: {c['danger']}; color: #ffffff; }}

#title {{ font-size: 15pt; font-weight: 600; }}
#subtitle, #muted {{ color: {c['text_muted']}; }}
#dim {{ color: {c['text_dim']}; }}
#heroTitle {{ font-size: 16pt; font-weight: 600; }}
#heroLine {{ color: {c['text']}; font-size: 10.5pt; }}

#card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; }}
#section {{ color: {c['text_muted']}; font-size: 8.5pt; font-weight: 600; letter-spacing: 1px; }}
#kvKey {{ color: {c['text_dim']}; }}
#appName {{ font-size: 10.5pt; font-weight: 600; }}
#note {{ color: {c['text_muted']}; font-size: 9pt; }}
#divider {{ background: {c['border']}; max-height: 1px; min-height: 1px; border: none; }}
#banner {{ background: {c['danger_bg']}; border: 1px solid {c['danger']}; border-radius: 8px; }}
#bannerText {{ color: {c['danger']}; }}
#banner[soft="true"] {{ background: {c['surface']}; border-color: {c['warning']}; }}
#bannerText[soft="true"] {{ color: {c['warning']}; }}

QPushButton {{ background: {c['elevated']}; border: 1px solid {c['border_strong']}; border-radius: 6px; padding: 7px 16px; }}
QPushButton:hover {{ background: {c['surface_hover']}; border-color: {c['text_muted']}; }}
QPushButton:disabled {{ color: {c['text_muted']}; border-color: {c['border']}; }}
QPushButton:focus {{ outline: none; }}
QPushButton#primary {{ background: {c['accent']}; color: {c['text_inverted']}; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#primary:disabled {{ background: {c['border_strong']}; color: {c['text_muted']}; }}
QPushButton#link {{ background: transparent; border: none; padding: 2px 0; color: {c['text_dim']}; }}
QPushButton#link:hover {{ color: {c['text']}; text-decoration: underline; }}

QLineEdit {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: 6px; padding: 6px 8px; selection-background-color: {c['border_strong']}; }}
QLineEdit:focus {{ border-color: {c['text_dim']}; }}
QLabel#formLabel {{ color: {c['text_dim']}; }}
QLabel#error {{ color: {c['danger']}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['text_muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QPlainTextEdit {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: 6px; padding: 4px; }}
QComboBox {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: 6px; padding: 6px 8px; }}
QComboBox QAbstractItemView {{ background: {c['elevated']}; border: 1px solid {c['border_strong']}; selection-background-color: {c['surface_hover']}; }}
QCheckBox {{ spacing: 8px; }}
QMenu {{ background: {c['elevated']}; border: 1px solid {c['border_strong']}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c['surface_hover']}; }}
QMenu::item:disabled {{ color: {c['text_dim']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 6px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 2px; }}
"""
