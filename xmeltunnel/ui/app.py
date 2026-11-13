"""Main window, tray icon and notifications. All work happens in core.Engine."""

from __future__ import annotations

import os
import sys
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QSizePolicy, QStackedWidget, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea,
                             QSystemTrayIcon, QVBoxLayout, QWidget)

from xmeltunnel import APP_NAME, __version__, core, i18n, profiles, updater
from xmeltunnel.i18n import tr
from xmeltunnel.ui import theme
from xmeltunnel.ui.dialogs import TARGET_SHORT, TARGET_TITLES, ProfileDialog, SettingsPanel
from xmeltunnel.ui.frameless import FramelessWindow, confirm
from xmeltunnel.ui.widgets import (IconButton, KeyValue, Pill, StatusDot, StatusRing, TargetChip, Toggle, app_icon,
                                   card, country_name, divider, flag_pixmap)

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
    """Title of the «Your server» card: the state of the connection to it."""
    keys = {k for k, _ in problems}
    if core.has_server(cfg) and not cfg.get("server_enabled", True):
        return tr("Server is disconnected")
    if "vpn" in keys:
        return tr("Waiting for the VPN")
    if not core.has_server(cfg):
        return tr("Profiles need your server") if "setup" in keys else tr("Server is not set up")
    for key, text in (("vpn", "VPN is off"), ("tunnel", "No connection to the server"),
                      ("exit", "Exit is not your server")):
        if key in keys:
            return tr(text)
    if any(k.startswith("leak") for k in keys):
        return tr("Something goes around your server")
    if level in ("ok", "warn") and not any(k in keys for k in ("tunnel", "exit")):
        return tr("Server is connected") if level == "ok" or not core.pac_profiles(cfg) or \
            any(k.startswith("off") for k in keys) else tr("Checking the exit…")
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
        self.chev = QPushButton(objectName="chevron")
        self.chev.setFixedWidth(16)
        self.chev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chev.clicked.connect(self.toggle_open)
        self.has_apps = bool(profile["apps"])
        self.chev.setEnabled(self.has_apps)  # keeps its place, so names line up
        top.addWidget(self.chev, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(3)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self.chip = TargetChip()
        name_row.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignVCenter)
        self.name = QLabel(objectName="appName")
        name_row.addWidget(self.name)
        self.dot = StatusDot()  # red: an app of this profile goes around it; yellow: goes direct, profile is off
        self.dot.set_level(None)
        name_row.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        name_row.addStretch()
        col.addLayout(name_row)
        sub = QHBoxLayout()
        sub.setSpacing(10)
        self.count = QLabel(objectName="note")
        sub.addWidget(self.count)
        sub.addStretch()
        col.addLayout(sub)
        top.addLayout(col, 1)
        edit = IconButton("pencil", tr("Edit…"))
        edit.clicked.connect(lambda: win.edit_profile(self.pid))
        top.addWidget(edit, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addSpacing(4)
        self.toggle = Toggle()
        self.toggle.toggled.connect(lambda on: win.engine.set_profile_enabled(self.pid, on))
        top.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(top)
        self.pills = []
        self.apps_box = QWidget()
        apps_lay = QVBoxLayout(self.apps_box)
        apps_lay.setContentsMargins(0, 0, 0, 0)
        apps_lay.setSpacing(4)
        lay.addWidget(self.apps_box)
        for app in profile["apps"]:
            r = QHBoxLayout()
            r.setContentsMargins(38, 0, 0, 0)
            lbl = QLabel(app["name"], objectName="kvKey")
            lbl.setFixedWidth(150)
            pill = Pill("…")
            r.addWidget(lbl)
            r.addWidget(pill, 1)
            apps_lay.addLayout(r)
            self.pills.append(pill)
        self.set_open(profile["id"] in win.engine.cfg.get("expanded_profiles", []))
        self.update_from(profile, {})

    def set_open(self, on: bool) -> None:
        self.apps_box.setVisible(on)
        self.chev.setText(("▾" if on else "▸") if self.has_apps else "")
        self.chev.setToolTip(tr("Hide apps") if on else tr("Show apps"))

    def toggle_open(self) -> None:
        on = not self.apps_box.isVisible()
        self.set_open(on)
        with self.win.engine.cfg_lock:
            ids = [i for i in self.win.engine.cfg.get("expanded_profiles", []) if i != self.pid]
            self.win.engine.cfg["expanded_profiles"] = ids + ([self.pid] if on else [])
            self.win.engine.save()

    def update_from(self, profile: dict, apps: dict, problems: list | None = None) -> None:
        self.name.setText(profile["name"])
        mine = [(k, t) for k, t in (problems or []) if k.split(":")[1:2] == [self.pid]]
        if any(k.startswith("leak") for k, _ in mine):
            self.dot.set_level("down", "\n".join(t for _, t in mine))
        elif mine:
            self.dot.set_level("warn", "\n".join(t for _, t in mine))
        else:
            self.dot.set_level(None)
        c = profiles.counts(profile)
        self.chip.set_target(profile["target"], dict((k, tr(t)) for k, t in TARGET_SHORT)[profile["target"]])
        parts = []
        if c["sites"]:
            parts.append(tr("sites: {n}", n=c["sites"]))
        if c["apps"]:
            parts.append(tr("programs: {n}", n=c["apps"]))
        if c["nets"]:
            parts.append(tr("subnets: {n}", n=c["nets"]))
        self.count.setText(" · ".join(parts))
        needs = profiles.needs_routing(profile) and not self.win.engine.cfg["route_enabled"]
        self.count.setToolTip(tr("Part of this profile works only while the VPN is connected.") if needs else "")
        self.count.setObjectName("warnNote" if needs and profile["enabled"] else "note")
        self.count.style().unpolish(self.count)
        self.count.style().polish(self.count)
        self.toggle.set_quiet(profile["enabled"])
        for i, pill in enumerate(self.pills):
            pill.set_state(*app_state(apps.get((self.pid, i)), profile["enabled"]))


def route_path_text(check) -> tuple[str, str, str | None]:
    if not check:
        return "—", "unknown", None
    ip, loc = check
    if loc is None:
        return tr("no answer ({err})", err=ip), "down", None
    return f"{ip} · {country_name(loc)}", "ok", loc


class VpnCard(QFrame):
    """«VPN»: where it goes (your VPN client or a subscription server) and a Connect button.

    Connected = the whole PC goes by the profiles (sing-box with a virtual adapter, admin rights).
    Disconnected = only the sites of «through your server» profiles go through your server (PAC, no admin rights).
    What each path exits as is shown in «Status» (self.paths_box is placed there by the main window)."""

    def __init__(self, win: "MainWindow"):
        super().__init__(objectName="card")
        self.win = win
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(18)
        self.ring = StatusRing("shield", 84)
        self.ring.clicked.connect(win.engine.check_route)
        lay.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(6)
        col.addWidget(QLabel(tr("VPN").upper(), objectName="section"))
        top = QHBoxLayout()
        self.title = QLabel(objectName="cardTitle")
        top.addWidget(self.title, 1)
        col.addLayout(top)
        self.sub = QLabel(objectName="note")
        self.sub.setWordWrap(True)
        col.addWidget(self.sub)
        # where the «through the VPN» path goes: a VPN client already running, or a server of a subscription
        col.addWidget(QLabel(tr("VPN goes through"), objectName="kvKey"))
        src = QHBoxLayout()
        src.setSpacing(0)
        self.seg = {}
        self.seg_group = QButtonGroup(self)
        self.seg_group.setExclusive(True)  # clicking the chosen one again keeps it chosen
        for key, text in (("adapter", tr("Your VPN client")), ("servers", tr("Server from a subscription"))):
            b = QPushButton(text, objectName="segment")
            b.setCheckable(True)
            self.seg_group.addButton(b)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty("pos", "left" if key == "adapter" else "right")
            b.clicked.connect(lambda _=False, k=key: (win.engine.set_vpn_source(k), win.refresh()))
            b.setMinimumWidth(b.sizeHint().width() + 8)  # never squeezed into a cut-off label
            src.addWidget(b, 1)
            self.seg[key] = b
        col.addLayout(src)
        self.picker = QPushButton(objectName="picker")  # looks like a drop-down: the chosen server
        self.picker.setCursor(Qt.CursorShape.PointingHandCursor)
        self.picker.clicked.connect(self.open_servers)
        col.addWidget(self.picker)
        self.server_line = QLabel(objectName="note")
        col.addWidget(self.server_line)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.b_connect = QPushButton(objectName="primary")
        self.b_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_connect.setMinimumWidth(150)
        self.b_connect.clicked.connect(lambda: win.engine.set_route_enabled(not win.engine.cfg["route_enabled"]))
        btns.addWidget(self.b_connect)
        self.b_retry_route = QPushButton(tr("Retry"), objectName="small")
        self.b_retry_route.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_retry_route.clicked.connect(win.engine.retry_route)
        btns.addWidget(self.b_retry_route)
        btns.addStretch()
        col.addLayout(btns)
        lay.addLayout(col, 1)

        # what each path exits as: shown in the «Status» card
        self.paths_box = QWidget()
        pl = QVBoxLayout(self.paths_box)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(QLabel(tr("Paths").upper(), objectName="section"), 1)
        self.b_check_route = QPushButton(tr("Check"), objectName="small")
        self.b_check_route.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_check_route.clicked.connect(win.engine.check_route)
        head.addWidget(self.b_check_route)
        pl.addLayout(head)
        self.pills = {}
        for key in ("direct", "vpn", "server"):
            r = QHBoxLayout()
            r.setSpacing(8)
            chip = TargetChip(key, dict((k, tr(t)) for k, t in TARGET_SHORT)[key])
            chip.setFixedWidth(110)
            r.addWidget(chip)
            p = Pill("—")
            r.addWidget(p, 1)
            pl.addLayout(r)
            self.pills[key] = p
        self.paths_note = QLabel(tr("Shown while the VPN is connected."), objectName="note")
        pl.addWidget(self.paths_note)

    def open_servers(self) -> None:
        from xmeltunnel.ui.servers_dialog import ServersDialog

        ServersDialog(self.win, self.win.engine).exec()
        self.win.refresh()

    def picker_state(self, cfg: dict) -> tuple[str, str]:
        """(text, country code for the flag) of the server picker."""
        from xmeltunnel.servers import display_name

        pick = cfg.get("vpn_server") or "auto"
        all_servers = list(cfg.get("servers") or [])
        if not all_servers:
            return tr("Add a subscription or server links…"), ""
        if pick.startswith("auto"):
            from xmeltunnel.routing import chosen_servers

            checks = cfg.get("server_checks") or {}
            ranked = sorted((checks[s["id"]]["ms"], s) for s in chosen_servers(cfg)
                            if (checks.get(s["id"]) or {}).get("ms"))
            where = tr("the fastest in {country}", country=country_name(pick[5:])) if ":" in pick \
                else tr("the fastest of {n}", n=len(all_servers))
            if not ranked:
                return tr("Automatically: {where}", where=where) + " · " + tr("ping not checked yet"), pick[5:]
            ms, best = ranked[0]
            return (tr("Automatically: {where}", where=where) + f" — {display_name(best['name'])} · {ms} " + tr("ms"),
                    best.get("country") or checks[best["id"]].get("exit_loc", ""))
        s = next((x for x in all_servers if x["id"] == pick), None)
        if not s:
            return tr("Choose a server…"), ""
        chk = (cfg.get("server_checks") or {}).get(pick) or {}
        ms = f"  ·  {chk['ms']} " + tr("ms") if chk.get("ms") else ""
        return display_name(s["name"]) + ms, s.get("country") or chk.get("exit_loc", "")

    def update_from(self, cfg: dict, r: dict, adapter: str | None = None) -> None:
        source = cfg.get("vpn_source", "adapter")
        for key, b in self.seg.items():
            b.setChecked(key == source)
        builtin = source == "servers"
        self.picker.setVisible(builtin)
        if builtin:
            text, cc = self.picker_state(cfg)
            self.picker.setText(text + "   ▾")
            self.picker.setIcon(QIcon(flag_pixmap(cc, 18, 13)) if cc else QIcon())
            self.server_line.setText("")
        else:
            self.server_line.setText(tr("Adapter: {name}", name=adapter) if adapter else
                                     tr("No VPN client adapter found — turn your VPN client on."))
        self.server_line.setVisible(not builtin)
        status = r["status"]
        checks = r["checks"]
        failed = [k for k, v in checks.items() if v and v[1] is None]
        external = cfg.get("vpn_source", "adapter") != "servers"
        if status == "running":
            level = "ok" if checks and not failed else ("down" if checks and len(failed) == len(checks) else "warn")
            title = (tr("Profiles are applied") if external else tr("VPN is connected")) if not failed \
                else tr("Connected, but not every path answers")
            where = {"direct": tr("direct"), "vpn": tr("through the VPN"),
                     "server": tr("through your server")}[cfg.get("route_default", "direct")]
            text = tr("Profiles decide, everything else goes {where}.", where=where)
        elif status in ("downloading", "starting", "restarting"):
            level, title = "unknown", tr("Connecting…")
            text = {"downloading": tr("Downloading sing-box… {pct}%", pct=r["progress"]),
                    "restarting": tr("Restarting with the new settings…"),
                    "starting": tr("Starting… confirm the admin rights request")}[status]
        elif status == "error":
            level, title, text = "down", tr("The VPN did not connect"), r["error"]
        elif external:
            # the VPN itself is the other client's business; here only «apply the profiles on top of it» is off
            vpn_on = bool(adapter)  # the VPN client's adapter, as the monitor sees it right now
            level = "ok" if vpn_on else "unknown"
            title = tr("Your VPN client is on") if vpn_on else tr("Your VPN client is off")
            text = (r["error"] + " " if r["error"] else "") + tr(
                "XmelTunnel does not touch its traffic now. Apply the profiles to send games direct, chosen sites "
                "through your server and so on, on top of that client.")
        else:
            level, title = "unknown", tr("VPN is disconnected")
            text = (r["error"] + " " if r["error"] else "") + tr(
                "Connect to route the whole PC by the profiles. While disconnected, only the sites of «through your "
                "server» profiles go through your server.")
        busy = status in ("downloading", "starting", "restarting") or (status == "running" and r["checking"])
        self.ring.set_level(level, busy=busy)
        self.title.setText(title)
        self.sub.setText(text)
        self.sub.setObjectName("error" if status == "error" else "note")
        self.sub.style().unpolish(self.sub)
        self.sub.style().polish(self.sub)
        if external:
            self.b_connect.setText(tr("Stop applying profiles") if cfg["route_enabled"] else tr("Apply profiles"))
        else:
            self.b_connect.setText(tr("Disconnect") if cfg["route_enabled"] else tr("Connect"))
        self.b_connect.setObjectName("" if cfg["route_enabled"] else "primary")
        self.b_connect.style().unpolish(self.b_connect)
        self.b_connect.style().polish(self.b_connect)
        self.b_retry_route.setVisible(cfg["route_enabled"] and status in ("error", "off"))
        self.b_check_route.setVisible(status == "running")
        self.paths_note.setVisible(status != "running")
        for key, pill in self.pills.items():
            if status != "running":
                pill.set_state("—", "unknown")
            elif r["checking"] and key not in checks:
                pill.set_state(tr("checking…"), "warn")
            elif key == "server" and not cfg.get("ss_key") and not core.link_server(cfg):
                pill.set_state(tr("not installed"), "unknown")
            else:
                text, lvl, flag = route_path_text(checks.get(key))
                used = (cfg.get("traffic") or {}).get(key, 0)
                if used:
                    from xmeltunnel.sharing import fmt_bytes

                    text += f"  ·  {fmt_bytes(used)}"
                pill.set_state(text, lvl, flag)


class MainWindow(FramelessWindow):
    def __init__(self, engine: core.Engine):
        super().__init__(APP_NAME, app_icon())
        self.engine = engine
        self.quitting = False
        self.rows: dict[str, ProfileRow] = {}
        self.on_update_ready = None  # set by main(): install and quit
        self.tray = None
        self._profile_sig = None
        self.setMinimumSize(1160, 760)  # the left menu takes ~200 px; the two cards on top need the rest
        w = engine.cfg.get("window") or []
        self.resize(*(w[:2] if len(w) >= 2 and w[0] >= 1160 else (1260, 840)))
        self._start_maximized = len(w) >= 3 and bool(w[2])

        # a left menu with pages, like ZapretXmel
        root = QHBoxLayout(self.body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        side = QFrame(objectName="Sidebar")
        side.setFixedWidth(196)
        sl_ = QVBoxLayout(side)
        sl_.setContentsMargins(10, 16, 10, 14)
        sl_.setSpacing(4)
        self.stack = QStackedWidget()
        self.nav: dict[str, QPushButton] = {}
        self.nav_group = QButtonGroup(self)
        for key, title in (("overview", tr("Overview")), ("settings", tr("Settings")), ("log", tr("Log")),
                           ("updates", tr("Updates"))):
            b = QPushButton(title, objectName="navItem")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.select(k))
            self.nav_group.addButton(b)
            sl_.addWidget(b)
            self.nav[key] = b
        sl_.addStretch()  # the version is in the title bar, the update state on the «Updates» page
        root.addWidget(side)
        root.addWidget(self.stack, 1)

        page = QWidget(objectName="page")
        self.pages = {"overview": page}
        self.stack.addWidget(page)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(14)

        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(QLabel(tr("Overview"), objectName="title"))
        head.addWidget(QLabel(tr("Profiles decide what goes through your server, the VPN or direct"),
                              objectName="subtitle"))
        lay.addLayout(head)

        self.route = VpnCard(self)  # created first: its paths go into the «Status» card below
        # two hero cards: your server and the VPN
        heroes = QHBoxLayout()
        heroes.setSpacing(14)
        hero = QFrame(objectName="card")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.setSpacing(18)
        self.ring = StatusRing("server", 84)
        self.ring.clicked.connect(self.engine.check_now)
        hl.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(6)
        self.h_caption = QLabel(tr("Your server").upper(), objectName="section")
        info.addWidget(self.h_caption)
        self.h_title = QLabel(objectName="cardTitle")
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
        self.h_sub.setWordWrap(True)
        info.addWidget(self.h_sub)
        info.addStretch()
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.b_main = QPushButton(objectName="small")
        self.b_main.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_main.clicked.connect(self.main_action)
        self.b_main.setToolTip(tr("Checks right now that sites go out through your server: asks Cloudflare which "
                                  "IP and country it sees, and how long that takes."))
        self.b_re = QPushButton(objectName="small")
        self.b_re.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_re.clicked.connect(lambda: self.engine.set_server_enabled(not self.engine.cfg.get("server_enabled", True)))
        self.b_friends = QPushButton(tr("Share…"), objectName="small")
        self.b_friends.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_friends.setToolTip(tr("Share your server: personal links, traffic, limits"))
        self.b_friends.clicked.connect(self.open_sharing)
        for b in (self.b_main, self.b_re, self.b_friends):
            b.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)  # never cut: the card grows
            btns.addWidget(b)
        btns.addStretch()
        info.addLayout(btns)
        hl.addLayout(info, 1)
        heroes.addWidget(hero, 1)
        heroes.addWidget(self.route, 1)
        lay.addLayout(heroes)

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
        sl.addSpacing(6)
        sl.addWidget(divider())
        sl.addWidget(self.route.paths_box)
        sl.addStretch()
        grid.addWidget(st, 0, 0)

        pc = QFrame(objectName="card")
        pl = QVBoxLayout(pc)
        pl.setContentsMargins(16, 14, 8, 14)
        pl.setSpacing(8)
        ph = QHBoxLayout()
        ph.addWidget(QLabel(tr("Profiles").upper(), objectName="section"), 1)
        add = QPushButton(tr("Add profile…"), objectName="small")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(lambda: self.edit_profile(None))
        ph.addWidget(add)
        ph.addSpacing(8)
        pl.addLayout(ph)
        rest = QHBoxLayout()
        rest.setSpacing(8)
        rest.addWidget(QLabel(tr("Everything not in a profile"), objectName="kvKey"))
        rest.addWidget(QLabel("→", objectName="kvKey"))
        self.default = QComboBox()
        for key, title in TARGET_TITLES:
            self.default.addItem(tr(title), key)
        self.default.setCurrentIndex(max(0, self.default.findData(engine.cfg.get("route_default", "direct"))))
        self.default.currentIndexChanged.connect(lambda: engine.set_route_default(self.default.currentData()))
        rest.addWidget(self.default)
        rest.addStretch()
        rest.addSpacing(8)
        pl.addLayout(rest)
        self.rest_note = QLabel(tr("Works while the VPN is connected; otherwise the rest goes as Windows decides."), objectName="note")
        self.rest_note.setWordWrap(True)
        pl.addWidget(self.rest_note)
        pl.addWidget(divider())
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
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 3)
        lay.addLayout(grid, 1)

        from xmeltunnel.ui.pages import LogPage, UpdatesPage

        self.settings_host = QWidget(objectName="page")
        shl = QVBoxLayout(self.settings_host)
        shl.setContentsMargins(24, 20, 24, 16)
        shl.setSpacing(12)
        shl.addWidget(QLabel(tr("Settings"), objectName="title"))
        self.settings_slot = QVBoxLayout()
        shl.addLayout(self.settings_slot, 1)
        self.settings_panel = None
        self.log_page = LogPage()
        self.updates_page = UpdatesPage(self)
        for key, w in (("settings", self.settings_host), ("log", self.log_page), ("updates", self.updates_page)):
            self.pages[key] = w
            self.stack.addWidget(w)
        self.select("overview")
        self.refresh()

    def select(self, key: str) -> None:
        if key == "settings":
            self.build_settings()
        elif key == "log":
            self.log_page.load()
        self.nav[key].setChecked(True)
        self.stack.setCurrentWidget(self.pages[key])
        self.refresh()

    def build_settings(self) -> None:
        """A fresh settings panel with the current values (also after «Undo changes»)."""
        if self.settings_panel is not None:
            self.settings_slot.removeWidget(self.settings_panel)
            self.settings_panel.deleteLater()
        self._before = {k: self.engine.cfg[k] for k in ("language", "theme", "ui_scale")}
        self.settings_panel = SettingsPanel(self.engine)
        self.settings_panel.saved.connect(self.on_settings_saved)
        self.settings_panel.reset_requested.connect(self.build_settings)
        self.settings_panel.remove_requested.connect(self.remove_from_pc)
        self.settings_slot.addWidget(self.settings_panel)

    # --- actions ---

    def main_action(self) -> None:
        if not core.has_server(self.engine.cfg):
            self.open_settings()
        else:
            self.engine.check_now()

    def open_sharing(self) -> None:
        from xmeltunnel.ui.sharing_dialog import SharingDialog

        SharingDialog(self, self.engine).exec()
        self.refresh()

    def welcome(self) -> None:
        from xmeltunnel.ui.dialogs import WelcomeDialog
        dlg = WelcomeDialog(self)
        dlg.exec()
        if dlg.choice == "server":
            self.open_settings()
        elif dlg.choice == "routing":
            self.edit_profile(None)
        elif dlg.choice == "subscription":
            self.engine.set_vpn_source("servers")
            self.route.open_servers()
        self.refresh()

    def update_action(self) -> None:
        u = self.engine.snapshot()[0]["update"]
        if u["status"] in ("downloading", "ready", "checking"):
            return
        if not u["version"]:
            return self.engine.check_updates_now()
        extra = tr("Connecting the VPN will ask for admin rights again after the restart.") \
            if self.engine.cfg["route_enabled"] else ""
        if confirm(self, tr("Update"), tr("Update XmelTunnel to {v}? It downloads from GitHub, checks the "
                                          "checksum and restarts.", v=u["version"]) + ("\n\n" + extra if extra else ""),
                   yes=tr("Update")):
            self.engine.download_update()

    def update_text(self, u: dict) -> tuple[str, bool]:
        """Footer link text and whether it is visible."""
        if u["kind"] == "source":
            return "", False
        st = u["status"]
        if st == "downloading":
            return tr("Downloading the update… {pct}%", pct=u["progress"]), True
        if st == "ready":
            return tr("Installing the update…"), True
        if u["version"]:
            return tr("Update to {v}", v=u["version"]), True
        if st == "checking":
            return tr("Checking for updates…"), True
        return tr("Check for updates"), True

    def open_settings(self) -> None:
        self.select("settings")

    def on_settings_saved(self) -> None:
        before = getattr(self, "_before", {})
        cfg = self.engine.cfg
        self._before = {k: cfg[k] for k in ("language", "theme", "ui_scale")}
        if cfg["theme"] != before.get("theme"):
            apply_theme(cfg)
            for w in QApplication.topLevelWidgets():
                w.update()
        if cfg["language"] != before.get("language") or cfg["ui_scale"] != before.get("ui_scale"):
            from xmeltunnel.ui.frameless import info
            info(self, APP_NAME, "Restart XmelTunnel to apply the language and scale.\n\n"
                                 "Перезапустите XmelTunnel, чтобы применились язык и масштаб.")
        self.refresh()

    def remove_from_pc(self) -> None:
        from xmeltunnel.ui.frameless import info
        self.engine.stop()
        time.sleep(0.5)  # let ssh exit before its log/config folder goes away
        done = core.remove_from_pc(self.engine.cfg)
        info(self, APP_NAME, tr("Done. XmelTunnel has removed its traces and will close now. "
                                "Delete XmelTunnel.exe yourself.") + "\n\n(" + (", ".join(done) or "—") + ")")
        self.quitting = True
        QApplication.instance().quit()

    def edit_profile(self, pid: str | None) -> None:
        p = next((x for x in self.engine.cfg["profiles"] if x["id"] == pid), None) if pid else None
        ProfileDialog(self, self.engine, p).exec()
        self.refresh()

    def open_log(self) -> None:
        self.select("log")

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

        self.ring.set_level(level if core.has_server(cfg) else "unknown",
                            busy=s["checking"] or (s["tunnel"] and s["exit_ok"] is None))
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
        setup = not core.has_server(cfg)
        enabled = cfg.get("server_enabled", True)
        link = cfg.get("server_mode") == "link"
        if setup:
            idle = tr("Sites of «through your server» profiles go through it. The VPN works without it.")
        elif not enabled:
            idle = tr("Sites of «through your server» profiles go direct until you connect it again.")
        else:
            idle = tr("tunnel is down")
        self.h_sub.setText("  ·  ".join(sub) or idle)
        self.rest_note.setVisible(not cfg["route_enabled"])
        self.b_main.setText(tr("Set up the server") if setup else tr("Check the connection"))
        self.b_main.setVisible(setup or enabled)
        self.b_main.setEnabled(setup or (s["tunnel"] and not s["checking"]))
        self.b_re.setVisible(not setup)
        self.b_re.setText(tr("Disconnect") if enabled else tr("Connect"))
        self.b_friends.setVisible(not setup and not link)  # sharing needs SSH to your own server
        self.kv["tunnel"].key_label.setText(tr("Link proxy") if link else tr("SSH tunnel"))
        self.kv["proxy"].setVisible(not link)

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
        keys = {k for k, _ in problems}
        if setup:
            self.kv["tunnel"].set("—", "unknown")
        elif not cfg.get("server_enabled", True):
            self.kv["tunnel"].set(tr("disconnected by you"), "unknown")
        elif "vpn" in keys:
            self.kv["tunnel"].set(tr("waits for the VPN"), "warn")
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
        if not cfg.get("server_enabled", True):
            self.kv["pac"].set(tr("off while the server is disconnected"), "unknown")
        elif not core.pac_profiles(cfg):
            self.kv["pac"].set(tr("no profiles on"), "unknown")
        elif not s["pac"]:
            self.kv["pac"].set(tr("off in Windows"), "warn")
        else:
            up = core.port_open(cfg["pac_port"])
            self.kv["pac"].set(tr("served on :{port}", port=cfg["pac_port"]) if up else tr("port does not answer"),
                               "ok" if up else "down")
        self.route.update_from(cfg, s["route"], s["vpn"])

        for p in cfg["profiles"]:
            if p["id"] in self.rows:
                self.rows[p["id"]].update_from(p, s["apps"], problems)
        note = tr("A profile that is on sends its sites and programs where it says.")
        if any(a["method"] == "claude_code" for p in cfg["profiles"] for a in p["apps"]):
            note += " " + tr("Claude Code picks the change up in new sessions.")
        self.p_note.setText(note)
        u = s["update"]
        self.updates_page.update_from(u)
        self.nav["updates"].setText(tr("Updates") + ("  •" if u["version"] else ""))
        if u["status"] == "ready" and self.on_update_ready:
            cb, self.on_update_ready = self.on_update_ready, None
            cb()


    # --- window ---

    def show_window(self) -> None:
        if self.isMaximized() or (not self.isVisible() and self._start_maximized):
            self.showMaximized()
        else:
            self.showNormal()
        self._start_maximized = False
        self.raise_()
        self.activateWindow()

    def remember_geometry(self) -> None:
        maxed = self.isMaximized()
        size = self.normalGeometry().size() if maxed else self.size()
        with self.engine.cfg_lock:
            self.engine.cfg["window"] = [size.width(), size.height(), maxed]
            self.engine.save()

    def closeEvent(self, e):  # noqa: N802 — the close box hides to tray (or quits, per settings)
        self.remember_geometry()
        if self.quitting:
            e.accept()
            return
        e.ignore()
        if self.engine.cfg.get("close_to_tray", True):
            self.hide()
        elif self.tray is not None:
            self.tray.quit()


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
        a = QAction(tr("VPN connected"), m, checkable=True)
        a.setChecked(self.engine.cfg["route_enabled"])
        a.triggered.connect(self.engine.set_route_enabled)
        m.addAction(a)
        m.addSeparator()
        if s["update"]["version"]:
            m.addAction(QAction(tr("Update to {v}", v=s["update"]["version"]), m,
                                triggered=lambda: (self.win.show_window(), self.win.update_action())))
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
            if not self.engine.cfg.get("notifications", True):
                continue
            self.icon.showMessage(title, text, QSystemTrayIcon.MessageIcon.Warning, 10000)

    def quit_for_update(self) -> None:
        args = [] if self.win.isVisible() else ["--hidden"]
        try:
            self.engine.install_update(args)
        except Exception as e:  # noqa: BLE001
            core.log(f"update install failed: {e!r}")
            self.engine._update_set(status="error", error=tr("Could not install the update: {err}", err=str(e)))
            return
        self.engine.stop()
        self.win.quitting = True
        self.icon.hide()
        self.app.quit()

    def quit(self) -> None:
        s, _, _ = self.engine.snapshot()
        if s["route"]["status"] == "running" and not s["pac"] and not confirm(
                self.win if self.win.isVisible() else None, tr("Quit"),
                tr("The VPN disconnects together with XmelTunnel.\n\nQuit anyway?"), yes=tr("Quit")):
            return
        if s["pac"] and not confirm(self.win if self.win.isVisible() else None, tr("Quit"),
                                    tr("While XmelTunnel is closed, nobody serves the PAC file and Windows sends apps "
                                       "directly, around your server.\n\nQuit anyway?"), yes=tr("Quit")):
            return
        self.win.remember_geometry()
        self.engine.stop()
        self.win.quitting = True
        self.icon.hide()
        self.app.quit()


def apply_theme(cfg: dict) -> None:
    t = cfg.get("theme", "system")
    theme.apply(theme.system_is_light() if t == "system" else t == "light")
    QApplication.instance().setStyleSheet(theme.stylesheet())


def apply_ui_scale() -> None:
    """Interface scale on top of Windows'. Qt reads it once, before QApplication exists."""
    try:
        scale = float(core.load_config().get("ui_scale") or 0)
    except (TypeError, ValueError):
        scale = 0
    if 0.5 <= scale <= 3 and "QT_SCALE_FACTOR" not in os.environ:
        os.environ["QT_SCALE_FACTOR"] = str(scale)


_mutex = None


def hold_app_mutex() -> None:
    """Named mutex the installer looks for (AppMutex) to ask the user to close XmelTunnel first."""
    global _mutex
    try:
        import ctypes

        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "XmelTunnelAppMutex")
    except Exception:  # noqa: BLE001 — not Windows: nothing to do
        pass


def install_excepthook() -> None:
    """PyQt6 aborts the whole program on an exception that escapes a slot, unless sys.excepthook is ours.
    Log it and keep running: one broken click must not take the tunnel and the routing mode down."""
    import traceback

    def hook(kind, value, tb):
        core.log("unexpected error:\n" + "".join(traceback.format_exception(kind, value, tb)))

    sys.excepthook = hook


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    if "--uninstall" not in sys.argv:
        apply_ui_scale()
    app = QApplication(sys.argv)
    # One look on Windows 10 and 11: the native style draws check boxes and drop-down lists the old way on 10
    app.setStyle("Fusion")
    install_excepthook()
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    if updater.RESTART_FLAG in sys.argv:  # started by an update: let the old instance finish quitting
        updater.wait_for_previous()
    updater.cleanup()

    if "--uninstall" in sys.argv:  # uninstaller and scripts: same as Settings -> Remove from this PC
        # Runs hidden from the uninstaller: never show dialogs, never touch stdout (a windowed exe has none).
        try:
            cfg = core.load_config()
            core.kill_stale_tunnels(cfg)
            done = core.remove_from_pc(cfg)
            if sys.stdout:
                print(", ".join(done) or "nothing to undo")
        except Exception:  # noqa: BLE001 — cleanup is best effort, the uninstaller must not hang
            return 1
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
    hold_app_mutex()

    cfg = core.load_config()
    i18n.set_language(cfg["language"])
    engine = core.Engine(cfg)
    apply_theme(cfg)
    app.setWindowIcon(app_icon())

    engine.start()
    win = MainWindow(engine)
    tray = Tray(app, engine, win)
    win.on_update_ready = tray.quit_for_update
    win.tray = tray
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.show_window()))

    timer = QTimer(interval=1000)
    timer.timeout.connect(lambda: (tray.update(), win.refresh() if win.isVisible() or
                                   engine.state["update"]["status"] == "ready" else None))
    timer.start()
    tray.update()
    hidden = "--hidden" in sys.argv or (engine.cfg["start_minimized"] and updater.RESTART_FLAG not in sys.argv)
    if not hidden or engine.cfg.get("_first_run"):
        win.show_window()
    if engine.cfg.get("_first_run"):
        QTimer.singleShot(400, win.welcome)
    return app.exec()
