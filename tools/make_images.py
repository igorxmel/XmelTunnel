"""Render README banner and social preview images from the app's own icon and a screenshot.

    .venv\\Scripts\\python tools\\make_images.py

Writes media/banner.png (1280x420), media/social.png and media/social-ru.png (1280x640, GitHub social preview).
"""


from __future__ import annotations
import os as _os, tempfile as _tf
# Never touch the real %APPDATA%\XmelTunnel: these tools build fake engines that may save.
_tmp = _tf.mkdtemp(prefix="xt-tools-")
_os.environ["APPDATA"] = _os.path.join(_tmp, "appdata")
_os.environ["USERPROFILE"] = _os.path.join(_tmp, "home")

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PyQt6.QtGui import (QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen,  # noqa: E402
                         QRadialGradient)
from PyQt6.QtWidgets import QApplication  # noqa: E402

from xmeltunnel import profiles  # noqa: E402
from xmeltunnel.ui.widgets import app_icon  # noqa: E402

BG = QColor("#0b0b0c")
TEXT = QColor("#f2f2f3")
DIM = QColor("#9f9fa6")
MUTED = QColor("#68686f")
BORDER = QColor("#3a3a44")
GREEN = QColor("#4cc38a")

TEXTS = {
    "en": ("Your server for chosen sites and apps.",
           "Everything else stays on your normal connection.",
           "SSH tunnel · per-app routing · leak watching · Windows"),
    "ru": ("Твой сервер для выбранных сайтов и приложений.",
           "Остальной интернет — как обычно.",
           "SSH-туннель · отдельные приложения · контроль утечек · Windows"),
}


def font(size: float, weight=QFont.Weight.Normal, family="Segoe UI Variable Display") -> QFont:
    f = QFont(family)
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def background(p: QPainter, w: int, h: int) -> None:
    p.fillRect(0, 0, w, h, BG)
    glow = QRadialGradient(QPointF(w * 0.78, h * 0.15), w * 0.6)
    glow.setColorAt(0, QColor(76, 195, 138, 38))
    glow.setColorAt(1, QColor(76, 195, 138, 0))
    p.fillRect(0, 0, w, h, glow)
    p.setPen(QPen(QColor(255, 255, 255, 10), 1))  # faint grid
    for x in range(0, w, 40):
        p.drawLine(x, 0, x, h)
    for y in range(0, h, 40):
        p.drawLine(0, y, w, y)


def screenshot(p: QPainter, img: QImage, x: float, y: float, width: float) -> None:
    scale = width / img.width()
    rect = QRectF(x, y, width, img.height() * scale)
    for i in range(18, 0, -3):  # soft shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 10))
        p.drawRoundedRect(rect.adjusted(-i, -i + 8, i, i + 8), 14 + i, 14 + i)
    clip = QPainterPath()
    clip.addRoundedRect(rect, 12, 12)
    p.save()
    p.setClipPath(clip)
    p.drawImage(rect, img)
    p.restore()
    p.setPen(QPen(BORDER, 1.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(rect, 12, 12)


def chips(p: QPainter, x: float, y: float, names: list[str], max_x: float) -> float:
    p.setFont(font(10.5, QFont.Weight.DemiBold, "Segoe UI Variable Text"))
    fm = p.fontMetrics()
    cx, cy = x, y
    for n in names:
        tw = fm.horizontalAdvance(n) + 26
        if cx + tw > max_x:
            cx, cy = x, cy + 36
        r = QRectF(cx, cy, tw, 28)
        p.setPen(QPen(BORDER, 1))
        p.setBrush(QColor("#141416"))
        p.drawRoundedRect(r, 14, 14)
        p.setPen(DIM)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, n)
        cx += tw + 8
    return cy + 28


def logo(p: QPainter, x: float, y: float, size: int) -> None:
    p.drawPixmap(int(x), int(y), app_icon("ok", size * 2).pixmap(size * 2, size * 2).scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


def render(w: int, h: int, lang: str, shot: QImage, compact: bool) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    background(p, w, h)
    title, sub, foot = TEXTS[lang]
    left = 64
    text_w = 620 if compact else 600
    top = 56 if compact else 110
    logo(p, left, top, 64)
    p.setPen(TEXT)
    p.setFont(font(34 if compact else 40, QFont.Weight.Bold))
    p.drawText(QRectF(left + 82, top - 6, text_w, 76), Qt.AlignmentFlag.AlignVCenter, "XmelTunnel")
    y = top + 100
    p.setFont(font(17 if compact else 20, QFont.Weight.DemiBold))
    r = p.boundingRect(QRectF(left, y, text_w, 200), Qt.TextFlag.TextWordWrap, title)
    p.drawText(r, Qt.TextFlag.TextWordWrap, title)
    y = r.bottom() + 8
    p.setPen(DIM)
    p.setFont(font(13 if compact else 14.5, family="Segoe UI Variable Text"))
    r = p.boundingRect(QRectF(left, y, text_w, 200), Qt.TextFlag.TextWordWrap, sub)
    p.drawText(r, Qt.TextFlag.TextWordWrap, sub)
    y = r.bottom() + 22
    names = [x["name"] for x in profiles.PRESETS if x["id"] != "custom"]
    y = chips(p, left, y, names, left + text_w)
    if not compact:
        p.setPen(MUTED)
        p.setFont(font(11, family="Segoe UI Variable Text"))
        p.drawText(QRectF(left, h - 70, text_w, 24), Qt.AlignmentFlag.AlignVCenter, foot)
    sw = min(560 if compact else 600, (h - 64) * shot.width() / shot.height())  # keep it inside the frame
    screenshot(p, shot, w - sw - 48, (h - shot.height() * sw / shot.width()) / 2, sw)
    p.end()
    return img


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841 — must stay alive while painting
    media = os.path.join(ROOT, "media")
    shots = {lang: QImage(os.path.join(media, "overview.png" if lang == "en" else "overview-ru.png"))
             for lang in TEXTS}
    render(1280, 420, "en", shots["en"], compact=True).save(os.path.join(media, "banner.png"))
    render(1280, 420, "ru", shots["ru"], compact=True).save(os.path.join(media, "banner-ru.png"))
    render(1280, 640, "en", shots["en"], compact=False).save(os.path.join(media, "social.png"))
    render(1280, 640, "ru", shots["ru"], compact=False).save(os.path.join(media, "social-ru.png"))
    print("written to", media)


if __name__ == "__main__":
    main()
