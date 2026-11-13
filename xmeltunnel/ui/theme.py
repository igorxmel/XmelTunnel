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
    # where a profile goes: your server, the VPN, direct
    "t_server": "#6ea8ff", "t_vpn": "#b38cff", "t_direct": "#a3a3ab",
}

LIGHT = {
    "bg": "#e8eaee", "surface": "#ffffff", "surface_hover": "#f0f1f5", "elevated": "#ffffff",
    "border": "#d2d6de", "border_strong": "#a8adb8",
    "text": "#16161a", "text_dim": "#55555f", "text_muted": "#85858f", "text_inverted": "#ffffff",
    "success": "#118a52", "danger": "#c02632", "warning": "#8a5a08", "info": "#9a9aa3",
    "accent": "#16161a", "accent_hover": "#000000", "bar": "#dfe2e8",
    "danger_bg": "#fbe9eb", "knob": "#ffffff",
    "t_server": "#2563eb", "t_vpn": "#7c3aed", "t_direct": "#5c5c66",
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


def arrow_icon(color: str) -> str:
    """A small chevron as an SVG file for the combo box arrow (QSS needs a file path, not inline data)."""
    import os
    import tempfile

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
           f'<path d="M1.5 3.5 L5 7 L8.5 3.5" fill="none" stroke="{color}" stroke-width="1.6" '
           f'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    path = os.path.join(tempfile.gettempdir(), f"xmeltunnel-arrow-{color.lstrip('#')}.svg")
    if not os.path.exists(path):
        try:
            with open(path, "w", encoding="ascii") as f:
                f.write(svg)
        except OSError:
            return ""
    return path.replace("\\", "/")


def check_icon(color: str) -> str:
    """A tick for checked boxes, as an SVG file (QSS takes a path)."""
    import os
    import tempfile

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
           f'<path d="M2.5 6.3 L5 8.8 L9.6 3.6" fill="none" stroke="{color}" stroke-width="1.8" '
           f'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    path = os.path.join(tempfile.gettempdir(), f"xmeltunnel-check-{color.lstrip('#')}.svg")
    if not os.path.exists(path):
        try:
            with open(path, "w", encoding="ascii") as f:
                f.write(svg)
        except OSError:
            return ""
    return path.replace("\\", "/")


def stylesheet() -> str:
    c = C
    arrow = arrow_icon(c['text_dim'])
    check = check_icon(c['text_inverted'])
    return f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 10pt; color: {c['text']}; }}
QWidget#page, QDialog {{ background: {c['bg']}; }}
QToolTip {{ background: {c['elevated']}; color: {c['text']}; border: 1px solid {c['border_strong']}; padding: 4px 6px; }}

QFrame#WindowFrame {{ background: {c['bg']}; border: 1px solid {c['border_strong']}; }}
QFrame#WindowFrame[flat="true"] {{ border: none; }}
#TitleBar {{ background: {c['bar']}; border-bottom: 1px solid {c['border_strong']}; }}
QLabel#TitleVersion {{ color: {c['text_muted']}; font-size: 8.5pt; }}
QPushButton#TitleLink {{ background: transparent; border: none; color: {c['text_muted']}; font-size: 8.5pt;
                        font-weight: 600; letter-spacing: 1px; padding: 4px 8px; }}
QPushButton#TitleLink:hover {{ color: {c['text']}; }}
QWidget#TitleSeparator {{ background: {c['border_strong']}; }}
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
QPushButton#danger {{ background: {c['danger']}; color: #ffffff; border: none; font-weight: 600; }}
QPushButton#danger:hover {{ background: {c['danger']}; border: 1px solid {c['text']}; }}
QPushButton#dangerSmall {{ background: transparent; color: {c['danger']}; border: 1px solid {c['danger']};
                          border-radius: 6px; padding: 4px 12px; font-size: 9pt; }}
QPushButton#dangerSmall:hover {{ background: {c['danger_bg']}; }}
QPushButton#chevron {{ background: transparent; border: none; padding: 0; color: {c['text_dim']}; font-size: 12pt; }}
QPushButton#chevron:hover {{ color: {c['text']}; }}
QPushButton#footerLink {{ background: transparent; border: none; padding: 2px 0; color: {c['text_muted']}; }}
QPushButton#footerLink:hover {{ color: {c['text']}; text-decoration: underline; }}
QPushButton#segment {{ background: {c['surface']}; color: {c['text_dim']}; border: 1px solid {c['border_strong']};
                       padding: 5px 14px; font-size: 9pt; border-radius: 0; }}
QPushButton#segment[pos="left"] {{ border-top-left-radius: 6px; border-bottom-left-radius: 6px; border-right: none; }}
QPushButton#segment[pos="right"] {{ border-top-right-radius: 6px; border-bottom-right-radius: 6px; }}
QPushButton#segment:checked {{ background: {c['accent']}; color: {c['text_inverted']}; border-color: {c['accent']};
                               font-weight: 600; }}
QPushButton#segment:hover:!checked {{ color: {c['text']}; }}
QPushButton#picker {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: 6px;
                     padding: 6px 10px; text-align: left; }}
QPushButton#picker:hover {{ border-color: {c['text_muted']}; }}
QFrame#Sidebar {{ background: {c['bar']}; border-right: 1px solid {c['border']}; }}
QPushButton#navItem {{ background: transparent; border: none; border-radius: 8px; padding: 9px 14px;
                      text-align: left; color: {c['text_dim']}; font-size: 10.5pt; }}
QPushButton#navItem:hover {{ background: {c['surface_hover']}; color: {c['text']}; }}
QPushButton#navItem:checked {{ background: {c['elevated']}; color: {c['text']}; font-weight: 600; }}
QPushButton#small {{ padding: 4px 12px; border-radius: 6px; font-size: 9pt; }}
QPushButton#small[accent="true"] {{ background: {c['accent']}; color: {c['text_inverted']}; border: none; font-weight: 600; }}
QPushButton#small[accent="true"]:hover {{ background: {c['accent_hover']}; }}

QLineEdit {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: 6px; padding: 6px 8px; selection-background-color: {c['border_strong']}; }}
QLineEdit:focus {{ border-color: {c['text_dim']}; }}
QLabel#formLabel {{ color: {c['text_dim']}; }}
QLabel#error {{ color: {c['danger']}; }}
QLabel#cardTitle {{ font-size: 13.5pt; font-weight: 600; }}
QLabel#warnNote {{ color: {c['warning']}; font-size: 9pt; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['text_muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QPlainTextEdit {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: 6px; padding: 4px; }}
QComboBox {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: 6px; padding: 6px 8px; }}
QComboBox::drop-down {{ border: none; width: 26px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({arrow}); width: 10px; height: 10px; }}
QComboBox::down-arrow:on {{ top: 1px; }}
QComboBox:hover {{ border-color: {c['text_muted']}; }}
QComboBox QAbstractItemView {{ background: {c['elevated']}; border: 1px solid {c['border_strong']}; selection-background-color: {c['surface_hover']}; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {c['border_strong']}; border-radius: 5px;
                       background: {c['surface']}; }}
QCheckBox::indicator:hover {{ border-color: {c['text_muted']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; image: url({check}); }}
QCheckBox::indicator:disabled {{ background: {c['bar']}; border-color: {c['border']}; }}
QComboBox QAbstractItemView {{ padding: 4px; outline: 0; border-radius: 8px; }}
QComboBox QAbstractItemView::item {{ min-height: 26px; padding: 2px 8px; border-radius: 5px; }}
QComboBox QAbstractItemView::item:selected {{ background: {c['surface_hover']}; color: {c['text']}; }}
QTableWidget, QListWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px;
                            selection-background-color: {c['surface_hover']}; selection-color: {c['text']};
                            outline: none; }}
QTableWidget::item, QListWidget::item {{ padding: 4px 6px; border: none; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: {c['elevated']}; }}
QHeaderView::section {{ background: {c['surface']}; color: {c['text_dim']}; border: none;
                       border-bottom: 1px solid {c['border']}; padding: 6px; font-weight: 600; }}
QTableCornerButton::section {{ background: {c['surface']}; border: none; }}
QLineEdit {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: 6px; padding: 6px 8px; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {c['border']}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {c['text_dim']}; padding: 8px 14px; margin-right: 4px;
               border: none; border-bottom: 2px solid transparent; }}
QTabBar::tab:hover {{ color: {c['text']}; }}
QTabBar::tab:selected {{ color: {c['text']}; border-bottom: 2px solid {c['accent']}; font-weight: 600; }}
QMenu {{ background: {c['elevated']}; border: 1px solid {c['border_strong']}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c['surface_hover']}; }}
QMenu::item:disabled {{ color: {c['text_dim']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 6px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 2px; }}
"""
