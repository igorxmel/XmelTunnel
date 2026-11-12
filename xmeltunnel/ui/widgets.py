"""Widgets: status pill, toggle switch, status ring, flags, app icon."""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QAbstractButton, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from xmeltunnel.i18n import language, tr
from xmeltunnel.ui import theme

COUNTRY_RU = {
    "FI": "Финляндия", "RO": "Румыния", "DE": "Германия", "NL": "Нидерланды", "FR": "Франция", "SE": "Швеция",
    "PL": "Польша", "LV": "Латвия", "LT": "Литва", "EE": "Эстония", "GB": "Великобритания", "US": "США",
    "TR": "Турция", "KZ": "Казахстан", "AM": "Армения", "GE": "Грузия", "RS": "Сербия", "RU": "Россия",
    "CH": "Швейцария", "AT": "Австрия", "CZ": "Чехия", "NO": "Норвегия", "JP": "Япония", "SG": "Сингапур",
}


COUNTRY_EN = {
    "FI": "Finland", "RO": "Romania", "DE": "Germany", "NL": "Netherlands", "FR": "France", "SE": "Sweden",
    "PL": "Poland", "LV": "Latvia", "LT": "Lithuania", "EE": "Estonia", "GB": "United Kingdom", "US": "USA",
    "TR": "Türkiye", "KZ": "Kazakhstan", "AM": "Armenia", "GE": "Georgia", "RS": "Serbia", "RU": "Russia",
    "CH": "Switzerland", "AT": "Austria", "CZ": "Czechia", "NO": "Norway", "JP": "Japan", "SG": "Singapore",
}


def country_name(code: str | None) -> str:
    if not code:
        return ""
    names = COUNTRY_RU if language() == "ru" else COUNTRY_EN
    return names.get(code.upper(), code.upper())


def assets_dir() -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets")


def _blend(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


class Pill(QWidget):
    """Status dot with a label. Colour fades so polling every few seconds does not blink."""

    def __init__(self, text: str = "", level: str = "unknown"):
        super().__init__()
        self._text, self._level = text, level
        self._color = self._from = self._to = QColor(theme.level_color(level))
        self._t = 1.0
        self._anim = QPropertyAnimation(self, b"t", self)
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(20)

    def set_state(self, text: str, level: str, flag: str | None = None) -> None:
        self._text, self._level = text, level
        self._flag = flag_pixmap(flag, 18, 13) if flag and len(flag) == 2 else None
        to = QColor(theme.level_color(level))
        if to != self._to:
            self._from, self._to = QColor(self._color), to
            self._anim.stop()
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        self.setToolTip(text)
        self.updateGeometry()
        self.update()

    def _get_t(self) -> float:
        return self._t

    def _set_t(self, v: float) -> None:
        self._t = v
        self._color = _blend(self._from, self._to, v)
        self.update()

    t = pyqtProperty(float, fget=_get_t, fset=_set_t)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.fontMetrics().horizontalAdvance(self._text) + 22 + (24 if getattr(self, "_flag", None) else 0), 20)

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r, cy = 4.0, self.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(QRectF(1, cy - r, r * 2, r * 2))
        p.setPen(QColor(theme.C["text"]))
        x = r * 2 + 9
        flag = getattr(self, "_flag", None)
        if flag is not None:
            fh = flag.height() / flag.devicePixelRatio()
            p.drawPixmap(int(x), int(cy - fh / 2), flag)
            x += flag.width() / flag.devicePixelRatio() + 6
        rect = QRectF(x, 0, self.width() - x, self.height())
        text = self.fontMetrics().elidedText(self._text, Qt.TextElideMode.ElideRight, int(rect.width()))
        p.drawText(rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)


class Toggle(QAbstractButton):
    """Windows 11 style toggle switch."""

    def __init__(self, tip: str = ""):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(42, 22)
        self.setToolTip(tip)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def set_quiet(self, on: bool) -> None:
        """Set without a signal or animation (used when polling)."""
        if on != self.isChecked():
            self.blockSignals(True)
            self.setChecked(on)
            self.blockSignals(False)
            self._pos = 1.0 if on else 0.0
            self.update()

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get_pos(self) -> float:
        return self._pos

    def _set_pos(self, v: float) -> None:
        self._pos = v
        self.update()

    pos = pyqtProperty(float, fget=_get_pos, fset=_set_pos)

    def paintEvent(self, _):  # noqa: N802
        c = theme.C
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        track = QRectF(1, 1, self.width() - 2, self.height() - 2)
        if on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c["accent"]))
        else:
            p.setPen(QPen(QColor(c["text_dim"]), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        d = 12 if (on or self.underMouse()) else 10
        x = 6 + (self.width() - 12 - 12) * self._pos
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c["text_inverted"] if on else c["text_dim"]))
        p.drawEllipse(QRectF(x + (12 - d) / 2, (self.height() - d) / 2, d, d))

    def enterEvent(self, e):  # noqa: N802
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        self.update()
        super().leaveEvent(e)


def draw_icon(p: QPainter, kind: str, r: QRectF, color: QColor, width: float = 2.0) -> None:
    """Line icons drawn in code (no image files): server, shield (VPN), direct (arrow)."""
    p.save()
    p.setPen(QPen(color, width, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    if kind == "server":  # two stacked units with status dots
        uh = h * 0.40
        for top in (y + h * 0.06, y + h * 0.54):
            p.drawRoundedRect(QRectF(x + w * 0.08, top, w * 0.84, uh), w * 0.08, w * 0.08)
            p.setBrush(color)
            p.drawEllipse(QPointF(x + w * 0.74, top + uh / 2), width * 0.7, width * 0.7)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(QPointF(x + w * 0.24, top + uh / 2), QPointF(x + w * 0.48, top + uh / 2))
    elif kind == "shield":
        path = QPainterPath(QPointF(x + w * 0.5, y + h * 0.04))
        path.lineTo(x + w * 0.88, y + h * 0.18)
        path.cubicTo(x + w * 0.88, y + h * 0.62, x + w * 0.70, y + h * 0.84, x + w * 0.5, y + h * 0.96)
        path.cubicTo(x + w * 0.30, y + h * 0.84, x + w * 0.12, y + h * 0.62, x + w * 0.12, y + h * 0.18)
        path.closeSubpath()
        p.drawPath(path)
        tick = QPainterPath(QPointF(x + w * 0.34, y + h * 0.50))
        tick.lineTo(x + w * 0.46, y + h * 0.62)
        tick.lineTo(x + w * 0.67, y + h * 0.38)
        p.drawPath(tick)
    elif kind == "pencil":
        body = QPainterPath(QPointF(x + w * 0.20, y + h * 0.80))
        body.lineTo(x + w * 0.24, y + h * 0.62)
        body.lineTo(x + w * 0.66, y + h * 0.20)
        body.lineTo(x + w * 0.80, y + h * 0.34)
        body.lineTo(x + w * 0.38, y + h * 0.76)
        body.closeSubpath()
        p.drawPath(body)
        p.drawLine(QPointF(x + w * 0.58, y + h * 0.28), QPointF(x + w * 0.72, y + h * 0.42))
    else:  # direct: an arrow straight ahead
        p.drawLine(QPointF(x + w * 0.10, y + h * 0.5), QPointF(x + w * 0.88, y + h * 0.5))
        head = QPainterPath(QPointF(x + w * 0.58, y + h * 0.20))
        head.lineTo(x + w * 0.88, y + h * 0.5)
        head.lineTo(x + w * 0.58, y + h * 0.80)
        p.drawPath(head)
    p.restore()


TARGET_ICON = {"server": "server", "vpn": "shield", "direct": "direct"}


class IconButton(QAbstractButton):
    """A small round button with a line icon (edit…)."""

    def __init__(self, icon: str, tip: str, size: int = 28):
        super().__init__()
        self.icon = icon
        self.setFixedSize(size, size)
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _):  # noqa: N802
        c = theme.C
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hover = self.underMouse()
        if hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c["surface_hover"]))
            p.drawEllipse(QRectF(0, 0, self.width(), self.height()))
        s = self.width() * 0.56
        o = (self.width() - s) / 2
        draw_icon(p, self.icon, QRectF(o, o, s, s), QColor(c["text"] if hover else c["text_dim"]), 1.5)

    def enterEvent(self, e):  # noqa: N802
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        self.update()
        super().leaveEvent(e)


class StatusDot(QWidget):
    """A small coloured dot with a tooltip: something is wrong with this row."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(12, 12)
        self.level = None

    def set_level(self, level: str | None, tip: str = "") -> None:
        self.level = level
        self.setToolTip(tip)
        self.setVisible(level is not None)
        self.update()

    def paintEvent(self, _):  # noqa: N802
        if not self.level:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.level_color(self.level)))
        p.drawEllipse(QRectF(1, 1, 10, 10))


class TargetChip(QWidget):
    """Coloured label with an icon: where a profile goes."""

    def __init__(self, target: str = "server", text: str = ""):
        super().__init__()
        self.target, self.text = target, text
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_target(self, target: str, text: str) -> None:
        self.target, self.text = target, text
        self.setToolTip(text)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        f = self.font()
        f.setPointSizeF(max(7.5, f.pointSizeF() - 1.5))
        from PyQt6.QtGui import QFontMetrics

        return QSize(QFontMetrics(f).horizontalAdvance(self.text) + 34, 20)

    def paintEvent(self, _):  # noqa: N802
        color = QColor(theme.C["t_" + self.target])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(color)
        bg.setAlphaF(0.16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 10, 10)
        draw_icon(p, TARGET_ICON[self.target], QRectF(8, 4, 12, 12), color, 1.4)
        f = self.font()
        f.setPointSizeF(max(7.5, f.pointSizeF() - 1.5))
        f.setBold(True)
        p.setFont(f)
        p.setPen(color)
        p.drawText(QRectF(25, 0, self.width() - 28, self.height()),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.text)


class StatusRing(QAbstractButton):
    """Big ring on the overview: colour is the state, an icon (or a glyph) inside. Click = check now."""

    def __init__(self, icon: str | None = None, size: int = 104):
        super().__init__()
        self.icon = icon
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("Check now"))
        self.level, self.busy = "unknown", True
        self._color = QColor(theme.level_color("unknown"))
        self._from = self._to = QColor(self._color)
        self._t = 1.0
        self._anim = QPropertyAnimation(self, b"t", self)
        self._anim.setDuration(300)

    def set_level(self, level: str, busy: bool = False) -> None:
        """busy: a check is running, show an ellipsis instead of the glyph."""
        self.level, self.busy = level, busy
        to = QColor(theme.level_color(level))
        if to != self._to:
            self._from, self._to = QColor(self._color), to
            self._anim.stop()
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        self.update()

    def _get_t(self) -> float:
        return self._t

    def _set_t(self, v: float) -> None:
        self._t = v
        self._color = _blend(self._from, self._to, v)
        self.update()

    t = pyqtProperty(float, fget=_get_t, fset=_set_t)

    def paintEvent(self, _):  # noqa: N802
        c = theme.C
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k = self.width() / 104  # everything below is laid out for 104 px
        p.scale(k, k)
        hover = self.underMouse()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c["surface_hover"] if hover else c["elevated"]))
        p.drawEllipse(QRectF(6, 6, 92, 92))
        p.setPen(QPen(self._color, 3.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(6, 6, 92, 92))
        if self.icon and not self.busy:
            draw_icon(p, self.icon, QRectF(34, 34, 36, 36), self._color, 3.0)
            p.end()
            return
        pen = QPen(self._color, 4.5, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if self.busy or self.level == "unknown":   # ellipsis: checking
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._color)
            for x in (38, 52, 66):
                p.drawEllipse(QPointF(x, 52), 3.5, 3.5)
        elif self.level == "ok":                    # check mark
            path = QPainterPath(QPointF(36, 53))
            path.lineTo(47, 64)
            path.lineTo(69, 41)
            p.drawPath(path)
        elif self.level == "down":                  # cross
            p.drawLine(QPointF(40, 40), QPointF(64, 64))
            p.drawLine(QPointF(64, 40), QPointF(40, 64))
        else:                                       # exclamation mark: needs attention
            p.drawLine(QPointF(52, 36), QPointF(52, 56))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._color)
            p.drawEllipse(QPointF(52, 67), 3.2, 3.2)

    def enterEvent(self, e):  # noqa: N802
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        self.update()
        super().leaveEvent(e)


_FLAGS: dict = {}


def flag_pixmap(code: str | None, w: int = 24, h: int = 18, dpr: float = 2.0) -> QPixmap:
    """Rendered once per size: a table of hundreds of servers asks for the same flags again and again."""
    key = ((code or "").lower(), w, h, dpr, theme.C.get("elevated"), theme.C.get("text"))
    if key not in _FLAGS:
        _FLAGS[key] = _render_flag(code, w, h, dpr)
    return _FLAGS[key]


def _render_flag(code: str | None, w: int, h: int, dpr: float) -> QPixmap:
    from PyQt6.QtSvg import QSvgRenderer

    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, w * dpr, h * dpr), 3 * dpr, 3 * dpr)
    p.setClipPath(clip)
    path = os.path.join(assets_dir(), "flags", f"{(code or '').lower()}.svg")
    if code and os.path.exists(path):
        QSvgRenderer(path).render(p, QRectF(0, 0, w * dpr, h * dpr))
    else:
        p.fillRect(0, 0, int(w * dpr), int(h * dpr), QColor(theme.C["elevated"]))
    p.setClipping(False)
    edge = QColor(theme.C["text"])
    edge.setAlphaF(0.22)  # white flags (Japan, Finland…) would melt into a light background
    p.setPen(QPen(edge, 1.0 * dpr))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(0.5 * dpr, 0.5 * dpr, (w - 1) * dpr, (h - 1) * dpr), 3 * dpr, 3 * dpr)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame(objectName="card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    if title:
        lay.addWidget(QLabel(title.upper(), objectName="section"))
    return f, lay


def divider() -> QFrame:
    return QFrame(objectName="divider")


class KeyValue(QWidget):
    """Row: name on the left, status pill on the right."""

    def __init__(self, key: str):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        k = QLabel(key, objectName="kvKey")
        k.setFixedWidth(140)
        self.key_label = k
        self.pill = Pill("…")
        lay.addWidget(k)
        lay.addWidget(self.pill, 1)

    def set(self, text: str, level: str) -> None:
        self.pill.set_state(text, level)


def app_icon(level: str | None = None, size: int = 64) -> QIcon:
    """App icon: an X made of two paths on a dark tile.

    The white path is your normal connection, the coloured one goes through your server. Without
    level it is brand green; with level (tray) the coloured path shows the state instead of a dot.
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    s = size / 64
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#202024"))
    p.drawRoundedRect(QRectF(4 * s, 4 * s, 56 * s, 56 * s), 14 * s, 14 * s)
    p.setPen(QPen(QColor("#f2f2f3"), 7 * s, cap=Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(18 * s, 46 * s), QPointF(46 * s, 18 * s))
    route = QColor(BRAND_GREEN) if level is None else QColor(DARK_LEVEL.get(level, DARK_LEVEL["unknown"]))
    p.setPen(QPen(route, 7 * s, cap=Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(18 * s, 18 * s), QPointF(46 * s, 46 * s))
    p.end()
    return QIcon(pm)


BRAND_GREEN = "#4cc38a"
# The icon tile is always dark, so it uses the dark-theme state colours whatever the Windows theme is.
DARK_LEVEL = {"ok": "#4cc38a", "warn": "#d9a441", "down": "#f0616d", "unknown": "#8a8a92"}
