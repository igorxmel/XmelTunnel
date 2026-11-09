"""Main window, tray icon and notifications. All work happens in core.Engine."""

from __future__ import annotations

import os
import sys
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea,
                             QSystemTrayIcon, QVBoxLayout, QWidget)

from xmeltunnel import APP_NAME, __version__, core, i18n
from xmeltunnel.i18n import tr
from xmeltunnel.ui import theme
from xmeltunnel.ui.dialogs import ProfileDialog, SettingsDialog
from xmeltunnel.ui.frameless import FramelessWindow, confirm
from xmeltunnel.ui.widgets import KeyValue, Pill, StatusRing, Toggle, app_icon, card, country_name, divider, flag_pixmap

INSTANCE_KEY = "xmeltunnel-single-instance"


def ago(ts: float | None) -> str:
    if not ts:
        return ""
    s = int(time.time() - ts)
    if s < 60:
        return tr("{n} s ago", n=s)
    if s < 3600:
        return tr("{n} min ago", n=s // 60)
    return tr("{h} h {m} min ago", h=s // 3600, m=s % 3600 // 60)


def headline(cfg: dict, level: str, problems: list) -> str:
    keys = {k for k, _ in problems}
    for key, text in (("setup", "Server is not set up yet"), ("vpn", "VPN is off"),
                      ("tunnel", "No connection to the server"), ("exit", "Exit is not your server")):
        if key in keys:
            return tr(text)
    if any(k.startswith(("leak", "off")) for k in keys):
        return tr("Something goes around the tunnel")
    if not core.enabled_profiles(cfg):
        return tr("No profiles turned on")
    if level == "ok":
        return tr("Everything goes through your server")
    return tr("Checking the exit…")


def app_state(a: dict | None, enabled: bool) -> tuple[str, str]:
    """Label and level for one watched app."""
    if not a or not a["pids"]:
        return tr("not running"), "unknown"
    n = tr(" · {n} processes", n=len(a["pids"])) if len(a["pids"]) > 1 else ""
    if a["direct"] and not enabled:
        return tr("goes direct · profile is off") + n, "warn"
    if a["direct"]:
        return (tr("goes direct, around the tunnel") if not a["via"] else tr("partly direct, around the tunnel")) + n, "down"
    if a["via"]:
        return tr("through the tunnel") + n, "ok"
    if not enabled:
        return tr("running · profile is off") + n, "unknown"
    return tr("running · no connections yet") + n, "unknown"


class ProfileRow(QWidget):
    """One profile: name, domain count, edit link, on/off switch, and its watched apps."""

    def __init__(self, win: "MainWindow", profile: dict):
        super().__init__()
        self.win, self.pid = win, profile["id"]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.name = QLabel(objectName="appName")
        col.addWidget(self.name)
        sub = QHBoxLayout()
        sub.setSpacing(10)
        self.count = QLabel(objectName="note")
        sub.addWidget(self.count)
        edit = QPushButton(tr("Edit…"), objectName="link")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(lambda: win.edit_profile(self.pid))
        sub.addWidget(edit)
        sub.addStretch()
        col.addLayout(sub)
        top.addLayout(col, 1)
        self.toggle = Toggle()
        self.toggle.toggled.connect(lambda on: win.engine.set_profile_enabled(self.pid, on))
        top.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(top)
        self.pills = []
        for app in profile["apps"]:
            r = QHBoxLayout()
            r.setContentsMargins(12, 0, 0, 0)
            lbl = QLabel(app["name"], objectName="kvKey")
            lbl.setFixedWidth(150)
            pill = Pill("…")
            r.addWidget(lbl)
            r.addWidget(pill, 1)
            lay.addLayout(r)
            self.pills.append(pill)
        self.update_from(profile, {})

    def update_from(self, profile: dict, apps: dict) -> None:
        self.name.setText(profile["name"])
        self.count.setText(tr("{n} domains", n=len(profile["domains"])))
        self.toggle.set_quiet(profile["enabled"])
        for i, pill in enumerate(self.pills):
            pill.set_state(*app_state(apps.get((self.pid, i)), profile["enabled"]))


class MainWindow(FramelessWindow):
    def __init__(self, engine: core.Engine):
        super().__init__(APP_NAME, app_icon())
        self.engine = engine
        self.quitting = False
        self.rows: dict[str, ProfileRow] = {}
        self._profile_sig = None
        self.titlebar.maximize.hide()
        self.resize(900, 680)
        self.setMinimumSize(780, 600)

        page = QWidget(objectName="page")
        root = QVBoxLayout(self.body)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(page)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(14)

        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(QLabel(tr("Overview"), objectName="title"))
        head.addWidget(QLabel(tr("Chosen sites and apps go through your server, everything else stays as is"),
                              objectName="subtitle"))
        lay.addLayout(head)

        # hero
        hero, hl = card()
        hl.setContentsMargins(22, 16, 22, 16)
        row = QHBoxLayout()
        row.setSpacing(22)
        self.ring = StatusRing()
        self.ring.clicked.connect(self.engine.check_now)
        row.addWidget(self.ring)
        info = QVBoxLayout()
        info.setSpacing(6)
        info.addStretch()
        self.h_title = QLabel(objectName="heroTitle")
        info.addWidget(self.h_title)
        line = QHBoxLayout()
        line.setSpacing(8)
        self.h_flag = QLabel()
        self.h_line = QLabel(objectName="heroLine")
        line.addWidget(self.h_flag)
        line.addWidget(self.h_line)
        line.addStretch()
        info.addLayout(line)
        self.h_sub = QLabel(objectName="muted")
        info.addWidget(self.h_sub)
        info.addStretch()
        row.addLayout(info, 1)
        btns = QVBoxLayout()
        btns.setSpacing(8)
        btns.addStretch()
        self.b_main = QPushButton(objectName="primary")
        self.b_main.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_main.clicked.connect(self.main_action)
        self.b_re = QPushButton(tr("Reconnect"))
        self.b_re.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_re.clicked.connect(self.engine.reconnect)
        for b in (self.b_main, self.b_re):
            b.setFixedWidth(180)
            btns.addWidget(b)
        btns.addStretch()
        row.addLayout(btns)
        hl.addLayout(row)
        lay.addWidget(hero)

        # problems banner
        self.banner, bl = card()
        self.banner.setObjectName("banner")
        self.banner_text = QLabel(objectName="bannerText")
        self.banner_text.setWordWrap(True)
        bl.addWidget(self.banner_text)
        self.banner.hide()
        lay.addWidget(self.banner)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        st, sl = card(tr("Status"))
        self.kv = {k: KeyValue(tr(t)) for k, t in (("vpn", "VPN"), ("tunnel", "SSH tunnel"),
                                                   ("proxy", "Proxy on server"), ("pac", "PAC file"))}
        for w in self.kv.values():
            sl.addWidget(w)
        sl.addStretch()
        sl.addWidget(divider())
        r = QHBoxLayout()
        r.addWidget(QLabel(tr("Start with Windows")), 1)
        self.t_auto = Toggle()
        self.t_auto.toggled.connect(self.engine.set_autostart)
        r.addWidget(self.t_auto)
        sl.addLayout(r)
        grid.addWidget(st, 0, 0)

        pc = QFrame(objectName="card")
        pl = QVBoxLayout(pc)
        pl.setContentsMargins(16, 14, 8, 14)
        pl.setSpacing(8)
        ph = QHBoxLayout()
        ph.addWidget(QLabel(tr("Profiles").upper(), objectName="section"), 1)
        add = QPushButton(tr("Add profile…"), objectName="link")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(lambda: self.edit_profile(None))
        ph.addWidget(add)
        ph.addSpacing(8)
        pl.addLayout(ph)
        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(10)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 8, 0)
        il.addLayout(self.list_box)
        il.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        pl.addWidget(scroll, 1)
        self.p_note = QLabel(objectName="note")
        self.p_note.setWordWrap(True)
        pl.addWidget(self.p_note)
        grid.addWidget(pc, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid, 1)

        foot = QHBoxLayout()
        for text, fn in ((tr("Settings…"), self.open_settings), (tr("Log"), self.open_log)):
            b = QPushButton(text, objectName="link")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            foot.addWidget(b)
            foot.addSpacing(14)
        foot.addStretch()
        self.f_server = QLabel(objectName="muted")
        foot.addWidget(self.f_server)
        lay.addLayout(foot)
        self.refresh()

    # --- actions ---

    def main_action(self) -> None:
        if not self.engine.cfg["server"]:
            self.open_settings()
        else:
            self.engine.check_now()

    def open_settings(self) -> None:
        lang = self.engine.cfg["language"]
        dlg = SettingsDialog(self, self.engine)
        dlg.exec()
        if dlg.removed:
            return self.remove_from_pc()
        if self.engine.cfg["language"] != lang:
            from xmeltunnel.ui.frameless import info
            i18n.set_language(self.engine.cfg["language"])
            info(self, APP_NAME, "Restart XmelTunnel to switch the language.\n\n"
                                 "Перезапусти XmelTunnel, чтобы сменить язык.")
        self.refresh()

    def remove_from_pc(self) -> None:
        from xmeltunnel.ui.frameless import info
        self.engine.stop()
        time.sleep(0.5)  # let ssh exit before its log/config folder goes away
        done = core.remove_from_pc(self.engine.cfg)
        info(self, APP_NAME, tr("Done. XmelTunnel has removed its traces and will close now. "
                                "Delete XmelTunnel.exe yourself.") + f"

({', '.join(done) or '—'})")
        self.quitting = True
        QApplication.instance().quit()

    def edit_profile(self, pid: str | None) -> None:
        p = next((x for x in self.engine.cfg["profiles"] if x["id"] == pid), None) if pid else None
        ProfileDialog(self, self.engine, p).exec()
        self.refresh()

    def open_log(self) -> None:
        if not os.path.exists(core.log_path()):
            core.log("log created")
        os.startfile(core.log_path())  # noqa: S606

    # --- refresh ---

    def rebuild_profiles(self) -> None:
        while self.list_box.count():
            w = self.list_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.rows.clear()
        for i, p in enumerate(self.engine.cfg["profiles"]):
            if i:
                self.list_box.addWidget(divider())
            row = ProfileRow(self, p)
            self.rows[p["id"]] = row
            self.list_box.addWidget(row)

    def refresh(self) -> None:
        cfg = self.engine.cfg
        sig = [(p["id"], p["name"], len(p["apps"])) for p in cfg["profiles"]]
        if sig != self._profile_sig:
            self._profile_sig = sig
            self.rebuild_profiles()
        s, level, problems = self.engine.snapshot()

        self.ring.set_level(level, busy=s["checking"] or (s["tunnel"] and s["exit_ok"] is None))
        self.h_title.setText(headline(cfg, level, problems))
        if s["exit_ok"]:
            self.h_flag.setPixmap(flag_pixmap(s["exit_loc"]))
            self.h_flag.show()
            self.h_line.setText(f"{s['exit_ip']}  ·  {country_name(s['exit_loc'])}  ·  {s['exit_ms']} " + tr("ms"))
        else:
            self.h_flag.hide()
            self.h_line.setText(tr("expected exit: {ip}", ip=self.engine.ip) if self.engine.ip else "")
        sub = []
        if s["since"]:
            sub.append(tr("tunnel up {ago}", ago=ago(s["since"])))
        if s["checking"]:
            sub.append(tr("checking…"))
        elif s["exit_at"]:
            sub.append(tr("checked {ago}", ago=ago(s["exit_at"])))
        self.h_sub.setText("  ·  ".join(sub) or ("" if not cfg["server"] else tr("tunnel is down")))
        setup = not cfg["server"]
        self.b_main.setText(tr("Set up the server") if setup else tr("Check exit"))
        self.b_main.setEnabled(setup or (s["tunnel"] and not s["checking"]))
        self.b_re.setVisible(not setup)

        self.banner.setVisible(bool(problems) and not setup)
        soft = all(k.startswith("off") for k, _ in problems)
        if self.banner.property("soft") != soft:
            for w in (self.banner, self.banner_text):
                w.setProperty("soft", soft)
                w.style().unpolish(w)
                w.style().polish(w)
        self.banner_text.setText("\n".join(t for _, t in problems))

        self.kv["vpn"].setVisible(cfg["require_vpn"])
        self.kv["vpn"].set(tr("on ({name})", name=s["vpn"]) if s["vpn"] else tr("not found — turn your VPN on"),
                           "ok" if s["vpn"] else "down")
        if setup:
            self.kv["tunnel"].set("—", "unknown")
        else:
            self.kv["tunnel"].set(tr("connected") if s["tunnel"] else tr("no connection, retrying…"),
                                  "ok" if s["tunnel"] else "down")
        if not s["tunnel"]:
            self.kv["proxy"].set("—", "unknown")
        elif s["exit_ok"] is None:
            self.kv["proxy"].set(tr("checking…"), "warn")
        elif s["exit_ok"]:
            self.kv["proxy"].set(tr("answers on :{port}", port=cfg["remote_proxy_port"]), "ok")
        else:
            self.kv["proxy"].set(tr("error: {err}", err=s["exit_ip"]), "down")
        if not core.enabled_profiles(cfg):
            self.kv["pac"].set(tr("no profiles on"), "unknown")
        elif not s["pac"]:
            self.kv["pac"].set(tr("off in Windows"), "warn")
        else:
            up = core.port_open(cfg["pac_port"])
            self.kv["pac"].set(tr("served on :{port}", port=cfg["pac_port"]) if up else tr("port does not answer"),
                               "ok" if up else "down")
        self.t_auto.set_quiet(s["autostart"])

        for p in cfg["profiles"]:
            if p["id"] in self.rows:
                self.rows[p["id"]].update_from(p, s["apps"])
        note = tr("Turn a profile on to send its sites through your server.")
        if any(a["method"] == "claude_code" for p in cfg["profiles"] for a in p["apps"]):
            note += " " + tr("Claude Code picks the change up in new sessions.")
        self.p_note.setText(note)
        self.f_server.setText(f"{cfg['server'] or '—'}  ·  127.0.0.1:{cfg['local_proxy_port']}  ·  v{__version__}")

    # --- window ---

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):  # noqa: N802 — the close box hides to tray
        if self.quitting:
            e.accept()
            return
        e.ignore()
        self.hide()


class Tray:
    def __init__(self, app: QApplication, engine: core.Engine, win: MainWindow):
        self.app, self.engine, self.win = app, engine, win
        self.icon = QSystemTrayIcon(app_icon("unknown"))
        self.icon.setToolTip(APP_NAME)
        self.menu = QMenu()
        self.icon.setContextMenu(self.menu)
        self.menu.aboutToShow.connect(self.build_menu)
        self.icon.activated.connect(self.on_activated)
        self.icon.messageClicked.connect(win.show_window)
        self._level = None
        self.build_menu()
        self.icon.show()

    def build_menu(self) -> None:
        m = self.menu
        m.clear()
        s, level, problems = self.engine.snapshot()
        m.addAction(QAction(tr("Open"), m, triggered=self.win.show_window))
        m.addSeparator()
        head = QAction(headline(self.engine.cfg, level, problems), m)
        head.setEnabled(False)
        m.addAction(head)
        if s["exit_ok"]:
            a = QAction(f"{s['exit_ip']} · {country_name(s['exit_loc'])} · {s['exit_ms']} " + tr("ms"), m)
            a.setEnabled(False)
            m.addAction(a)
        m.addSeparator()
        for p in self.engine.cfg["profiles"]:
            a = QAction(tr("Profile «{name}»", name=p["name"]), m, checkable=True)
            a.setChecked(p["enabled"])
            a.triggered.connect(lambda on, pid=p["id"]: self.engine.set_profile_enabled(pid, on))
            m.addAction(a)
        m.addSeparator()
        m.addAction(QAction(tr("Check exit"), m, triggered=self.engine.check_now))
        m.addAction(QAction(tr("Reconnect"), m, triggered=self.engine.reconnect))
        m.addSeparator()
        m.addAction(QAction(tr("Quit"), m, triggered=self.quit))

    def on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.win.show_window()

    def update(self) -> None:
        s, level, problems = self.engine.snapshot()
        if level != self._level:
            self.icon.setIcon(app_icon(level))
            self._level = level
        tip = headline(self.engine.cfg, level, problems)
        if s["exit_ok"]:
            tip += f"\n{s['exit_ip']} · {country_name(s['exit_loc'])} · {s['exit_ms']} " + tr("ms")
        self.icon.setToolTip(tip[:120])
        for title, text in self.engine.take_notes():
            self.icon.showMessage(title, text, QSystemTrayIcon.MessageIcon.Warning, 10000)

    def quit(self) -> None:
        s, _, _ = self.engine.snapshot()
        if s["pac"] and not confirm(self.win if self.win.isVisible() else None, tr("Quit"),
                                    tr("While XmelTunnel is closed, nobody serves the PAC file and Windows sends apps "
                                       "directly, around your server.\n\nQuit anyway?"), yes=tr("Quit")):
            return
        self.engine.stop()
        self.win.quitting = True
        self.icon.hide()
        self.app.quit()


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    if "--uninstall" in sys.argv:  # for scripts: same as Settings -> Remove from this PC
        print(", ".join(core.remove_from_pc(core.load_config())) or "nothing to undo")
        return 0

    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):  # already running: show its window
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(INSTANCE_KEY)
    server = QLocalServer()
    server.listen(INSTANCE_KEY)

    cfg = core.load_config()
    i18n.set_language(cfg["language"])
    engine = core.Engine(cfg)
    theme.apply(theme.system_is_light())
    app.setStyleSheet(theme.stylesheet())
    app.setWindowIcon(app_icon())

    engine.start()
    win = MainWindow(engine)
    tray = Tray(app, engine, win)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.show_window()))

    timer = QTimer(interval=1000)
    timer.timeout.connect(lambda: (tray.update(), win.isVisible() and win.refresh()))
    timer.start()
    tray.update()
    if "--hidden" not in sys.argv or not engine.cfg["server"]:
        win.show()
    if not engine.cfg["server"]:
        QTimer.singleShot(400, win.open_settings)
    return app.exec()
