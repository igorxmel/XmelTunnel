"""Render README banner and social preview images from the app's own icon and its main window.

    .venv\\Scripts\\python tools\\make_images.py

Writes media/banner.png (1280x744, drawn at 2x), media/social.png and media/social-ru.png (1280x640, GitHub social preview).
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
    "en": ("Profiles for your whole PC: through a VPN, your own server or direct.",
           "Built-in VPN client with subscriptions, your server over SSH, sharing it with friends.",
           "sing-box · per-app and per-site routing · honest ping · Windows"),
    "ru": ("Профили для всего компьютера: через VPN, ваш сервер или напрямую.",
           "Встроенный VPN-клиент с подписками, ваш сервер по SSH, доступ для друзей.",
           "sing-box · программы и сайты по профилям · честный пинг · Windows"),
}
# what the built-in VPN client speaks
PROTOCOL_CHIPS = ["VLESS · Reality", "VMess", "Trojan", "Shadowsocks", "Hysteria2", "TUIC", "AnyTLS", "Naive",
                  "WireGuard"]


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


# pieces of the main window (its own 1x pixels, 1260x840): every card that shows what the app does
SERVER_CARD = QRectF(221, 122, 500, 196)
VPN_CARD = QRectF(735, 122, 500, 196)
STATUS = QRectF(222, 331, 398, 281)         # «Status» with the three paths and their traffic
PROFILES = QRectF(636, 331, 585, 281)       # «Profiles», «everything else →», the first rows


def card(p: QPainter, img: QImage, src: QRectF, x: float, y: float, scale: float = 1.0) -> float:
    """One card cut out of the window at (nearly) full size, floating with a shadow. Returns its bottom.
    The whole window shrunk into a banner was unreadable: GitHub shows the banner at ~2/3 size anyway."""
    k = img.width() / 1260  # the screenshot is rendered at 2x
    rect = QRectF(x, y, src.width() * scale, src.height() * scale)
    for i in range(20, 0, -4):  # soft shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 16))
        p.drawRoundedRect(rect.adjusted(-i, -i + 10, i, i + 10), 12 + i, 12 + i)
    clip = QPainterPath()
    clip.addRoundedRect(rect, 12, 12)
    p.save()
    p.setClipPath(clip)
    p.fillRect(rect, QColor("#111113"))
    p.drawImage(rect, img, QRectF(src.x() * k, src.y() * k, src.width() * k, src.height() * k))
    p.restore()
    p.setPen(QPen(BORDER, 1.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(rect, 12, 12)
    return rect.bottom()


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


SCALE = 2  # every picture is drawn at 2x: sharp on high-DPI screens and when GitHub scales it
GAP = 22


def render(w: int, h: int, lang: str, shot: QImage, k: float) -> QImage:
    """Name and protocols on top, then the window's four cards in two rows at scale k.
    The whole window shrunk into a strip was unreadable, and any one or two cards left out what matters."""
    img = QImage(w * SCALE, h * SCALE, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.scale(SCALE, SCALE)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    background(p, w, h)
    title, sub, _ = TEXTS[lang]
    row1 = (SERVER_CARD.width() + VPN_CARD.width()) * k + GAP
    left = (w - row1) / 2
    top = 34
    logo(p, left, top, 48)
    p.setPen(TEXT)
    p.setFont(font(26, QFont.Weight.Bold))
    p.drawText(QRectF(left + 62, top - 8, 400, 64), Qt.AlignmentFlag.AlignVCenter, "XmelTunnel")
    y = top + 62
    p.setFont(font(15, QFont.Weight.DemiBold))
    r = p.boundingRect(QRectF(left, y, row1, 100), Qt.TextFlag.TextWordWrap, title)
    p.drawText(r, Qt.TextFlag.TextWordWrap, title)
    y = r.bottom() + 4
    p.setPen(DIM)
    p.setFont(font(11.5, family="Segoe UI Variable Text"))
    r = p.boundingRect(QRectF(left, y, row1, 100), Qt.TextFlag.TextWordWrap, sub)
    p.drawText(r, Qt.TextFlag.TextWordWrap, sub)
    y = chips(p, left, r.bottom() + 14, PROTOCOL_CHIPS, left + row1) + 26
    # row 1: your server, the VPN; row 2: status with the paths, the profiles
    x = left
    card(p, shot, SERVER_CARD, x, y, k)
    card(p, shot, VPN_CARD, x + SERVER_CARD.width() * k + GAP, y, k)
    y += max(SERVER_CARD.height(), VPN_CARD.height()) * k + GAP
    row2 = (STATUS.width() + PROFILES.width()) * k + GAP
    x = left + (row1 - row2) / 2
    card(p, shot, STATUS, x, y, k)
    card(p, shot, PROFILES, x + STATUS.width() * k + GAP, y, k)
    p.end()
    return img


def hires_shots() -> dict:
    """The main window rendered at 2x by screenshot_main.py, in a temporary folder."""
    import subprocess
    import tempfile

    out, shots = tempfile.mkdtemp(prefix="xt-shots-"), {}
    env = dict(os.environ, QT_SCALE_FACTOR="2", XT_BUILTIN="1")
    for lang in TEXTS:
        path = os.path.join(out, f"overview-{lang}.png")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "screenshot_main.py"), lang, "ok", path],
                       env=env, check=True)
        shots[lang] = QImage(path)
    return shots


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841 — must stay alive while painting
    media = os.path.join(ROOT, "media")
    shots = hires_shots()
    for lang, banner, social in (("en", "banner.png", "social.png"), ("ru", "banner-ru.png", "social-ru.png")):
        render(1280, 744, lang, shots[lang], 1.0).save(os.path.join(media, banner))
        # GitHub's social preview: 1280x640 is what it asks for (and under 1 MB)
        render(1280, 640, lang, shots[lang], 0.66).scaled(
            1280, 640, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation).save(os.path.join(media, social))
    print("written to", media)


if __name__ == "__main__":
    main()
