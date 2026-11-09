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

    def set_state(self, text: str, level: str) -> None:
        self._text, self._level = text, level
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
        return QSize(self.fontMetrics().horizontalAdvance(self._text) + 22, 20)

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r, cy = 4.0, self.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(QRectF(1, cy - r, r * 2, r * 2))
        p.setPen(QColor(theme.C["text"]))
        rect = QRectF(r * 2 + 9, 0, self.width() - r * 2 - 9, self.height())
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


class StatusRing(QAbstractButton):
    """Big ring on the overview: colour is the overall state, a glyph inside. Click = check now."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(104, 104)
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
        hover = self.underMouse()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c["surface_hover"] if hover else c["elevated"]))
        p.drawEllipse(QRectF(6, 6, 92, 92))
        p.setPen(QPen(self._color, 3.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(6, 6, 92, 92))
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


def flag_pixmap(code: str | None, w: int = 24, h: int = 18, dpr: float = 2.0) -> QPixmap:
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
        self.pill = Pill("…")
        lay.addWidget(k)
        lay.addWidget(self.pill, 1)

    def set(self, text: str, level: str) -> None:
        self.pill.set_state(text, level)


def app_icon(level: str | None = None, size: int = 64) -> QIcon:
    """App icon: dark tile with an arc. With level, adds a status dot (tray)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    s = size / 64
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#202024"))
    p.drawRoundedRect(QRectF(4 * s, 4 * s, 56 * s, 56 * s), 14 * s, 14 * s)
    pen = QPen(QColor("#f2f2f3"), 7 * s, cap=Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawArc(QRectF(15 * s, 15 * s, 34 * s, 34 * s), 45 * 16, 270 * 16)
    if level:
        p.setPen(QPen(QColor("#202024"), 3 * s))
        p.setBrush(QColor(theme.level_color(level)))
        p.drawEllipse(QRectF(38 * s, 38 * s, 24 * s, 24 * s))
    p.end()
    return QIcon(pm)
