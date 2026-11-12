"""Frameless window that keeps native Windows behaviour (snap, resize, shadow).

The system styles are restored and WM_NCCALCSIZE removes the non-client area, so we draw
everything ourselves while dragging and resizing are still handled by Windows."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from xmeltunnel.i18n import tr
from PyQt6.QtCore import QUrl, QEvent, QSize, Qt, QTimer
from PyQt6.QtGui import QDesktopServices, QFont, QFontDatabase, QPainter
from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QStyle, QStyleOption,
                             QVBoxLayout, QWidget)

WINDOWS = sys.platform == "win32"
TITLEBAR_HEIGHT = 40
GRIP = 5

GLYPH_MINIMIZE, GLYPH_MAXIMIZE, GLYPH_RESTORE, GLYPH_CLOSE = chr(0xE921), chr(0xE922), chr(0xE923), chr(0xE8BB)
ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
FALLBACK = {GLYPH_MINIMIZE: "—", GLYPH_MAXIMIZE: "□", GLYPH_RESTORE: "❐", GLYPH_CLOSE: "✕"}

if WINDOWS:
    GWL_STYLE = -16
    WS_CAPTION, WS_THICKFRAME, WS_MAXIMIZEBOX, WS_MINIMIZEBOX = 0x00C00000, 0x00040000, 0x00010000, 0x00020000
    WM_NCCALCSIZE, WM_GETMINMAXINFO = 0x0083, 0x0024
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_FRAMECHANGED = 1, 2, 4, 32
    SM_CXSIZEFRAME, SM_CXPADDEDBORDER = 32, 92

    class _NcCalcSizeParams(ctypes.Structure):
        _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

    class _MinMaxInfo(ctypes.Structure):
        _fields_ = [("ptReserved", wintypes.POINT), ("ptMaxSize", wintypes.POINT), ("ptMaxPosition", wintypes.POINT),
                    ("ptMinTrackSize", wintypes.POINT), ("ptMaxTrackSize", wintypes.POINT)]

    def _long_funcs():
        u = ctypes.windll.user32
        get = getattr(u, "GetWindowLongPtrW", None) or u.GetWindowLongW
        put = getattr(u, "SetWindowLongPtrW", None) or u.SetWindowLongW
        get.restype = put.restype = ctypes.c_ssize_t
        get.argtypes = [wintypes.HWND, ctypes.c_int]
        put.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        return get, put

    def enable_native_frame(handle: int) -> None:
        get, put = _long_funcs()
        put(handle, GWL_STYLE, get(handle, GWL_STYLE) | WS_CAPTION | WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX)
        ctypes.windll.user32.SetWindowPos(handle, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)

    def frame_border() -> int:
        m = ctypes.windll.user32.GetSystemMetrics
        return m(SM_CXSIZEFRAME) + m(SM_CXPADDEDBORDER)


def icon_font(size: int = 10) -> QFont | None:
    fams = QFontDatabase.families()
    for name in ICON_FONTS:
        if name in fams:
            f = QFont(name)
            f.setPointSize(size)
            return f
    return None



LINKS = (("GITHUB", "https://github.com/igorxmel/XmelTunnel"),)

class CaptionButton(QPushButton):
    def __init__(self, glyph: str, tip: str):
        super().__init__()
        self.setObjectName("CaptionButton")
        self.setFixedSize(QSize(46, TITLEBAR_HEIGHT))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(tip)
        self._font = icon_font()
        if self._font:
            self.setFont(self._font)
        self.set_glyph(glyph)

    def set_glyph(self, g: str) -> None:
        self.setText(g if self._font else FALLBACK.get(g, g))


class TitleBar(QWidget):
    """Title bar: icon, caption, a slot for tabs, window buttons. Empty space drags the window."""

    def __init__(self, window: QWidget, title: str, icon=None, compact: bool = False):
        super().__init__(window)
        self.win = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(12, 0, 0, 0)
        self.row.setSpacing(8)
        if icon is not None:
            ic = QLabel()
            ic.setPixmap(icon.pixmap(18, 18))
            self.row.addWidget(ic)
        self.caption = QLabel(title, objectName="TitleCaption")
        self.row.addWidget(self.caption)
        if not compact:
            from xmeltunnel import __version__

            self.version = QLabel(f"v{__version__}", objectName="TitleVersion")
            self.row.addWidget(self.version)
        self.slot = QHBoxLayout()  # the main window may put tabs here
        self.slot.setContentsMargins(10, 0, 0, 0)
        self.row.addLayout(self.slot)
        self.row.addStretch(1)
        self.maximize: CaptionButton | None = None
        if not compact:
            # links out live in the title bar: reachable from anywhere, apart from the window buttons
            for text, url in LINKS:
                link = QPushButton(text, objectName="TitleLink")
                link.setCursor(Qt.CursorShape.PointingHandCursor)
                link.setToolTip(url)
                link.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
                self.row.addWidget(link)
            sep = QWidget(objectName="TitleSeparator")
            sep.setFixedSize(1, 16)
            self.row.addSpacing(4)
            self.row.addWidget(sep, 0, Qt.AlignmentFlag.AlignVCenter)
            self.row.addSpacing(4)
            mn = CaptionButton(GLYPH_MINIMIZE, tr("Minimize"))
            mn.clicked.connect(window.showMinimized)
            self.row.addWidget(mn)
            self.maximize = CaptionButton(GLYPH_MAXIMIZE, tr("Maximize"))
            self.maximize.clicked.connect(self.toggle_maximize)
            self.row.addWidget(self.maximize)
        close = CaptionButton(GLYPH_CLOSE, tr("Close"))
        close.setProperty("close", True)
        close.clicked.connect(window.close)
        self.row.addWidget(close)

    def toggle_maximize(self) -> None:
        if self.maximize is not None:
            self.win.showNormal() if self.win.isMaximized() else self.win.showMaximized()

    def sync_state(self) -> None:
        if self.maximize is not None:
            m = self.win.isMaximized()
            self.maximize.set_glyph(GLYPH_RESTORE if m else GLYPH_MAXIMIZE)
            self.maximize.setToolTip(tr("Restore") if m else tr("Maximize"))

    def paintEvent(self, _):  # noqa: N802 — QWidget subclasses must paint the QSS background themselves
        opt = QStyleOption()
        opt.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, QPainter(self), self)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.win.windowHandle():
            self.win.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, _):  # noqa: N802
        self.toggle_maximize()


class _Grip(QWidget):
    def __init__(self, parent: QWidget, edges, cursor):
        super().__init__(parent)
        self.edges = edges
        self.setCursor(cursor)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemResize(self.edges)


class FramelessWindow(QWidget):
    """Main window: custom title bar, content goes into `self.body`."""

    def __init__(self, title: str, icon=None):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.Window)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(title)
        if icon is not None:
            self.setWindowIcon(icon)
        self._native = False
        shell = QVBoxLayout(self)
        # No margin: the window's own (light) background would show through as a white outline.
        # WindowFrame draws the border.
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.frame = QFrame(objectName="WindowFrame")
        shell.addWidget(self.frame)
        inner = QVBoxLayout(self.frame)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        self.titlebar = TitleBar(self, title, icon)
        inner.addWidget(self.titlebar)
        self.body = QWidget()
        inner.addWidget(self.body, 1)
        E, C = Qt.Edge, Qt.CursorShape
        self.grips = [_Grip(self, e, c) for e, c in (
            (E.TopEdge, C.SizeVerCursor), (E.BottomEdge, C.SizeVerCursor), (E.LeftEdge, C.SizeHorCursor),
            (E.RightEdge, C.SizeHorCursor), (E.TopEdge | E.LeftEdge, C.SizeFDiagCursor),
            (E.BottomEdge | E.RightEdge, C.SizeFDiagCursor), (E.TopEdge | E.RightEdge, C.SizeBDiagCursor),
            (E.BottomEdge | E.LeftEdge, C.SizeBDiagCursor))]

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if WINDOWS and not self._native:
            enable_native_frame(int(self.winId()))
            self._native = True
        for g in self.grips:
            g.raise_()

    def nativeEvent(self, kind, message):  # noqa: N802
        if not self._native or kind != b"windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_GETMINMAXINFO:
            r = self.devicePixelRatioF()
            lim = _MinMaxInfo.from_address(msg.lParam)
            lim.ptMinTrackSize.x = int(self.minimumWidth() * r)
            lim.ptMinTrackSize.y = int(self.minimumHeight() * r)
            return True, 0
        if msg.message != WM_NCCALCSIZE:
            return False, 0
        # A maximized window overflows the screen by the frame width — trim it. Ask Windows, not Qt,
        # whether it is maximized: when un-snapping by drag Qt learns about it later.
        # The handle comes from the message itself: winId() may still be empty while Qt recreates the window.
        if msg.wParam and ctypes.windll.user32.IsZoomed(int(msg.hWnd or 0)):
            b = frame_border()
            rc = _NcCalcSizeParams.from_address(msg.lParam).rgrc[0]
            rc.left += b
            rc.top += b
            rc.right -= b
            rc.bottom -= b
        return True, 0

    def event(self, e):
        # A recreated native window needs the system frame styles again.
        if e.type() == QEvent.Type.WinIdChange and WINDOWS and self._native:
            QTimer.singleShot(0, self._reapply_frame)  # after Qt finishes recreating it
        return super().event(e)

    def _reapply_frame(self) -> None:
        wh = self.windowHandle()
        if wh is not None and wh.winId():
            enable_native_frame(int(wh.winId()))

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._place_grips()

    def changeEvent(self, e):  # noqa: N802
        super().changeEvent(e)
        if e.type() == QEvent.Type.WindowStateChange:
            self._place_grips()
            self.titlebar.sync_state()
            m = self.isMaximized()
            self.frame.setProperty("flat", m)
            self.frame.style().unpolish(self.frame)
            self.frame.style().polish(self.frame)

    def _place_grips(self) -> None:
        if self.isMaximized():
            for g in self.grips:
                g.hide()
            return
        w, h, t = self.width(), self.height(), GRIP
        geo = ((t, 0, w - 2 * t, t), (t, h - t, w - 2 * t, t), (0, t, t, h - 2 * t), (w - t, t, t, h - 2 * t),
               (0, 0, t, t), (w - t, h - t, t, t), (w - t, 0, t, t), (0, h - t, t, t))
        for g, r in zip(self.grips, geo):
            g.setGeometry(*r)
            g.show()


class FramelessDialog(QDialog):
    """Dialog in the same style: compact title bar with a close button, content in `body`."""

    def __init__(self, parent: QWidget | None, title: str):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(title)
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(objectName="WindowFrame")
        shell.addWidget(frame)
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        self.titlebar = TitleBar(self, title, compact=True)
        inner.addWidget(self.titlebar)
        self.body = QWidget()
        inner.addWidget(self.body, 1)


def _message(parent, title: str, text: str, buttons: list[tuple[str, bool, bool]], danger: bool = False) -> bool:
    """buttons: (label, primary, result). Returns the pressed button's result (close box = False).

    danger: the primary button is red (removing, deleting)."""
    d = FramelessDialog(parent, title)
    d.setMinimumWidth(420)
    lay = QVBoxLayout(d.body)
    lay.setContentsMargins(24, 18, 24, 18)
    lay.setSpacing(16)
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lay.addWidget(lbl)
    row = QHBoxLayout()
    row.addStretch()
    result = {"v": False}
    for label, primary, value in buttons:
        b = QPushButton(label, objectName=("danger" if danger else "primary") if primary else "")
        b.clicked.connect(lambda _=False, v=value: (result.update(v=v), d.accept()))
        if primary:
            b.setDefault(True)
        row.addWidget(b)
    lay.addLayout(row)
    d.exec()
    return result["v"]


def info(parent, title: str, text: str) -> None:
    _message(parent, title, text, [(tr("OK"), True, True)])


def confirm(parent, title: str, text: str, yes: str = "OK", no: str = "", danger: bool = False) -> bool:
    return _message(parent, title, text, [(no or tr("Cancel"), False, False), (yes, True, True)], danger)


def ask_text(parent, title: str, label: str, value: str = "") -> str | None:
    d = FramelessDialog(parent, title)
    d.setMinimumWidth(400)
    lay = QVBoxLayout(d.body)
    lay.setContentsMargins(24, 18, 24, 18)
    lay.setSpacing(12)
    lay.addWidget(QLabel(label, objectName="dim"))
    edit = QLineEdit(value)
    edit.selectAll()
    lay.addWidget(edit)
    row = QHBoxLayout()
    row.addStretch()
    cancel = QPushButton(tr("Cancel"))
    ok = QPushButton(tr("Save"), objectName="primary")
    ok.setDefault(True)
    cancel.clicked.connect(d.reject)
    ok.clicked.connect(d.accept)
    row.addWidget(cancel)
    row.addWidget(ok)
    lay.addLayout(row)
    return edit.text() if d.exec() else None
