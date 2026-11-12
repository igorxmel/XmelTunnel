"""Settings (server + setup) and profile editor dialogs."""

from __future__ import annotations

import copy
import re

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
                             QFrame, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from xmeltunnel import core, i18n, profiles, routing, server_setup
from xmeltunnel.i18n import tr
from xmeltunnel.ui.frameless import FramelessDialog, confirm


class _Job(QObject):
    done = pyqtSignal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as e:  # noqa: BLE001
            self.done.emit(e)


def run_bg(owner, fn, on_done) -> None:
    """Run fn in a thread, call on_done(result) in the UI thread. Keeps refs on owner."""
    th = QThread(owner)
    job = _Job(fn)
    job.moveToThread(th)
    th.started.connect(job.run)
    job.done.connect(on_done)
    job.done.connect(th.quit)
    th.finished.connect(lambda: owner.__dict__.setdefault("_jobs", []).remove((th, job)))
    owner.__dict__.setdefault("_jobs", []).append((th, job))
    th.start()


class SettingsPanel(QWidget):
    """The «Settings» page of the main window."""

    saved = pyqtSignal()
    reset_requested = pyqtSignal()
    remove_requested = pyqtSignal()

    FIELDS = (("server", "Server (IP, user@host or ~/.ssh/config alias)"), ("ssh_port", "SSH port"),
              ("ssh_key", "SSH key file"), ("remote_proxy_port", "Proxy port on the server"),
              ("local_proxy_port", "Proxy port on this PC"), ("pac_port", "PAC file port"))

    SCALES = ((0.0, "As in Windows"), (0.9, "90%"), (1.0, "100%"), (1.1, "110%"), (1.25, "125%"), (1.5, "150%"))
    THEMES = (("system", "As in Windows"), ("dark", "Dark"), ("light", "Light"))

    def __init__(self, engine: core.Engine):
        super().__init__()
        self.engine = engine
        cfg = engine.cfg
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._server_page(cfg), tr("Server"))
        self.tabs.addTab(self._app_page(cfg), tr("App"))
        lay.addWidget(self.tabs, 1)

        self.msg = QLabel(objectName="dim")
        self.msg.setWordWrap(True)
        self.msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.msg)

        row = QHBoxLayout()
        self.removed = False
        rm = QPushButton(tr("Remove from this PC…"), objectName="dangerSmall")
        rm.clicked.connect(self.on_remove)
        row.addWidget(rm)
        row.addStretch()
        cancel = QPushButton(tr("Undo changes"))
        cancel.clicked.connect(self.reset_requested.emit)
        ok = QPushButton(tr("Save"), objectName="primary")
        ok.clicked.connect(self.on_save)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def _server_page(self, cfg: dict) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 14, 4, 4)
        lay.setSpacing(10)

        # how «Your server» is reached: your own server over SSH, or a share link
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.mode_group = QButtonGroup(self)
        self.mode_btn = {}
        for key, text in (("ssh", tr("My own server (SSH key)")), ("link", tr("By a link"))):
            bt = QPushButton(text, objectName="segment")
            bt.setCheckable(True)
            bt.setProperty("pos", "left" if key == "ssh" else "right")
            bt.setMinimumWidth(bt.sizeHint().width() + 8)
            self.mode_group.addButton(bt)
            bt.clicked.connect(self.show_mode)
            seg.addWidget(bt, 1)
            self.mode_btn[key] = bt
        self.mode_btn["link" if cfg.get("server_mode") == "link" else "ssh"].setChecked(True)
        lay.addLayout(seg)

        # --- by a link ---
        self.link_box = QWidget()
        ll = QVBoxLayout(self.link_box)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(8)
        ln = QLabel(tr("Paste the link someone shared with you (or any ss://, vless://, trojan://… link). XmelTunnel "
                       "then uses that server as «Your server»: for the sites of «through your server» profiles, "
                       "Claude Code and the VPN's «server» path. No SSH and no admin rights needed."), objectName="note")
        ln.setWordWrap(True)
        ll.addWidget(ln)
        self.link = QLineEdit(cfg.get("server_link", ""))
        self.link.setPlaceholderText("ss://… · vless://… · trojan://…")
        self.link.textChanged.connect(self.show_link_info)
        ll.addWidget(self.link)
        self.link_info = QLabel(objectName="dim")
        ll.addWidget(self.link_info)
        lay.addWidget(self.link_box)

        # --- your own server over SSH ---
        self.ssh_box = QWidget()
        sl = QVBoxLayout(self.ssh_box)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(10)
        intro = QLabel(tr("XmelTunnel needs a Linux server you can reach over SSH with a key.") + "\n"
                       + tr("The proxy listens only inside the server, nothing new is opened to the internet."),
                       objectName="note")
        intro.setWordWrap(True)
        sl.addWidget(intro)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.edits = {}
        r = 0
        for key, label in self.FIELDS[:4]:
            grid.addWidget(QLabel(tr(label), objectName="formLabel"), r, 0)
            e = QLineEdit(str(cfg[key]))
            grid.addWidget(e, r, 1)
            self.edits[key] = e
            r += 1
        sl.addLayout(grid)
        row = QHBoxLayout()
        self.b_check = QPushButton(tr("Check connection"))
        self.b_check.clicked.connect(self.on_check)
        self.b_install = QPushButton(tr("Install proxy on the server"))
        self.b_install.clicked.connect(self.on_install)
        row.addWidget(self.b_check)
        row.addWidget(self.b_install)
        row.addStretch()
        sl.addLayout(row)
        sl.addSpacing(4)
        sl.addWidget(QLabel(tr("For the VPN").upper(), objectName="section"))
        ss_note = QLabel(tr("Programs, folders and subnets of «through your server» profiles go by Shadowsocks: "
                            "install it once. Sites work without it."), objectName="note")
        ss_note.setWordWrap(True)
        sl.addWidget(ss_note)
        ss = QHBoxLayout()
        ss.setSpacing(10)
        ss.addWidget(QLabel(tr("Shadowsocks port on the server"), objectName="formLabel"))
        self.ss_port = QLineEdit(str(cfg["ss_port"]))
        self.ss_port.setFixedWidth(80)
        ss.addWidget(self.ss_port)
        self.b_ss = QPushButton(tr("Install on the server"))
        self.b_ss.clicked.connect(self.on_install_ss)
        ss.addWidget(self.b_ss)
        self.ss_state = QLabel(objectName="dim")
        ss.addWidget(self.ss_state, 1)
        sl.addLayout(ss)
        lay.addWidget(self.ssh_box)

        # --- both modes ---
        lay.addSpacing(4)
        lay.addWidget(QLabel(tr("Connection").upper(), objectName="section"))
        grid2 = QGridLayout()
        grid2.setHorizontalSpacing(14)
        grid2.setVerticalSpacing(8)
        r = 0
        for key, label in self.FIELDS[4:]:
            grid2.addWidget(QLabel(tr(label), objectName="formLabel"), r, 0)
            e = QLineEdit(str(cfg[key]))
            grid2.addWidget(e, r, 1)
            self.edits[key] = e
            r += 1
        self.vpn = QCheckBox(tr("My server is reachable only through the VPN"))
        self.vpn.setChecked(cfg["require_vpn"])
        grid2.addWidget(self.vpn, r, 1)
        r += 1
        grid2.addWidget(QLabel(tr("VPN adapter"), objectName="formLabel"), r, 0)
        self.vpn_rx = QComboBox()
        self.vpn_rx.addItem(tr("Automatically (Happ, v2rayN, WireGuard, Amnezia…)"), core.DEFAULTS["vpn_adapter"])
        for name in core.network_adapters():
            self.vpn_rx.addItem(name, "^" + re.escape(name) + "$")
        current = cfg["vpn_adapter"]
        if self.vpn_rx.findData(current) < 0:
            self.vpn_rx.addItem(tr("Own rule: {rule}", rule=current), current)
        self.vpn_rx.setCurrentIndex(self.vpn_rx.findData(current))
        grid2.addWidget(self.vpn_rx, r, 1)
        r += 1
        vpn_note = QLabel(tr("Turn on if your server is blocked where you are: XmelTunnel then connects to it through "
                             "the VPN adapter and warns you when the VPN is off."), objectName="note")
        vpn_note.setWordWrap(True)
        grid2.addWidget(vpn_note, r, 1)
        grid2.setColumnStretch(1, 1)
        lay.addLayout(grid2)
        self.show_ss_state()
        self.show_link_info()
        self.show_mode()
        lay.addStretch()
        return page

    def link_mode(self) -> bool:
        return self.mode_btn["link"].isChecked()

    def show_mode(self) -> None:
        self.link_box.setVisible(self.link_mode())
        self.ssh_box.setVisible(not self.link_mode())

    def show_link_info(self) -> None:
        from xmeltunnel import servers as sv

        text = self.link.text().strip()
        if not text:
            self.link_info.setText("")
            return
        try:
            p = sv.parse_link(text)
            self.link_info.setText(tr("{proto} server {host}:{port} · «{name}»", proto=sv.PROTOCOLS.get(p["protocol"],
                                   p["protocol"]), host=p["host"], port=p["port"], name=sv.display_name(p["name"])))
        except Exception as e:  # noqa: BLE001
            self.link_info.setText(tr("Not a server link: {err}", err=e))

    def show_ss_state(self) -> None:
        self.ss_state.setText(tr("installed") if self.engine.cfg.get("ss_key") else tr("not installed"))

    def on_install_ss(self) -> None:
        t = self.ss_port.text().strip()
        if not (t.isdigit() and 1 <= int(t) <= 65535):
            return self.say(tr("{field}: a number from 1 to 65535.", field=tr("Shadowsocks port on the server")), False)
        cfg = self._trial_cfg()
        if not cfg:
            return
        port = int(t)
        self.b_ss.setEnabled(False)
        self.say(tr("Installing… (up to a few minutes)"), None)

        def done(res):
            self.b_ss.setEnabled(True)
            if isinstance(res, Exception):
                return self.say(tr("Install failed: {err}", err=res), False)
            ok, text, key = res
            self.say(text, ok)
            if ok:
                self.engine.set_server_ss(port, key)
                self.show_ss_state()

        run_bg(self, lambda: server_setup.install_ss(cfg, port), done)

    def _app_page(self, cfg: dict) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 14, 4, 4)
        lay.setSpacing(8)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)

        def combo(items, value, translate=True):
            c = QComboBox()
            for data, title in items:
                c.addItem(tr(title) if translate else title, data)
            c.setCurrentIndex(max(0, c.findData(value)))
            return c

        self.lang = combo([("", tr("As in Windows"))] + list(i18n.LANGS.items()), cfg["language"], translate=False)
        self.theme = combo(self.THEMES, cfg["theme"])
        self.scale = combo(self.SCALES, float(cfg["ui_scale"]))
        for r, (label, w) in enumerate(((tr("Language"), self.lang), (tr("Theme"), self.theme),
                                        (tr("Interface scale"), self.scale))):
            grid.addWidget(QLabel(label, objectName="formLabel"), r, 0)
            grid.addWidget(w, r, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        lay.addWidget(QLabel(tr("Language and scale apply after a restart."), objectName="note"))

        lay.addSpacing(6)
        lay.addWidget(QLabel(tr("Start and connection").upper(), objectName="section"))
        self.checks = {}
        for key, text in (("autostart", "Start with Windows"),
                          ("start_minimized", "Start minimized to the tray"),
                          ("route_on_start", "Connect the VPN at start if it was connected"),
                          ("close_to_tray", "The close button hides to the tray (otherwise it quits)"),
                          ("route_no_uac", "Do not ask for admin rights every time the VPN connects"),
                          ("notifications", "Show notifications"),
                          ("check_updates", "Check for updates automatically")):
            cb = QCheckBox(tr(text))
            cb.setChecked(core.autostart_enabled() if key == "autostart" else bool(cfg[key]))
            lay.addWidget(cb)
            self.checks[key] = cb
        uac = QLabel(tr("«Do not ask»: Windows asks once now and registers the «XmelTunnel Routing» task in the Task "
                        "Scheduler. Keep in mind that any program running as you can then connect the VPN "
                        "with admin rights too."), objectName="note")
        uac.setWordWrap(True)
        lay.addWidget(uac)
        if not routing.task_supported():
            self.checks["route_no_uac"].setEnabled(False)
        lay.addWidget(QLabel(tr("The SSH tunnel always connects by itself while XmelTunnel runs."), objectName="note"))
        lay.addStretch()
        return page

    def app_values(self) -> dict:
        out = {k: cb.isChecked() for k, cb in self.checks.items()}
        out.update(language=self.lang.currentData(), theme=self.theme.currentData(),
                   ui_scale=float(self.scale.currentData()))
        return out

    def on_remove(self) -> None:
        msg = tr(i18n.REMOVE_EN)
        if confirm(self, tr("Remove from this PC…"), msg, yes=tr("Remove"), danger=True):
            self.remove_requested.emit()

    def collect(self) -> dict | None:
        common = dict(require_vpn=self.vpn.isChecked(),
                      vpn_adapter=self.vpn_rx.currentData() or core.DEFAULTS["vpn_adapter"])
        if self.link_mode():
            from xmeltunnel import servers as sv

            errors, out = [], {"server_mode": "link", "server_link": self.link.text().strip()}
            try:
                sv.parse_link(out["server_link"])
            except Exception as e:  # noqa: BLE001
                errors.append(tr("Not a server link: {err}", err=e))
            for key, title in (("local_proxy_port", tr("Proxy port on this PC")), ("pac_port", tr("PAC file port"))):
                t = self.edits[key].text().strip()
                if t.isdigit() and 1 <= int(t) <= 65535:
                    out[key] = int(t)
                else:
                    errors.append(tr("{field}: a number from 1 to 65535.", field=title))
            if errors:
                self.say("\n".join(errors), False)
                return None
            out.update(common)
            return out
        out, errors = core.validate({k: e.text() for k, e in self.edits.items()})
        if errors:
            self.say("\n".join(errors), False)
            return None
        out.update(common, server_mode="ssh")
        return out

    def say(self, text: str, ok: bool | None) -> None:
        self.msg.setObjectName("dim" if ok is None else ("dim" if ok else "error"))
        self.msg.setStyleSheet("" if ok is not True else "color: %s;" % __import__(
            "xmeltunnel.ui.theme", fromlist=["C"]).C["success"])
        self.msg.style().unpolish(self.msg)
        self.msg.style().polish(self.msg)
        self.msg.setText(text)

    def busy(self, on: bool) -> None:
        for b in (self.b_check, self.b_install):
            b.setEnabled(not on)

    def _trial_cfg(self) -> dict | None:
        new = self.collect()
        if new is None:
            return None
        cfg = dict(self.engine.cfg)
        cfg.update(new)
        return cfg

    def on_check(self) -> None:
        cfg = self._trial_cfg()
        if not cfg:
            return
        self.busy(True)
        self.say(tr("Checking…"), None)

        def done(res):
            self.busy(False)
            if isinstance(res, Exception):
                return self.say(tr("SSH failed: {err}", err=res), False)
            ssh_ok, proxy_ok, msg = res
            self.say(msg, proxy_ok)
            self.b_install.setDefault(ssh_ok and not proxy_ok)

        run_bg(self, lambda: server_setup.check(cfg), done)

    def on_install(self) -> None:
        cfg = self._trial_cfg()
        if not cfg:
            return
        self.busy(True)
        self.say(tr("Installing…"), None)

        def done(res):
            self.busy(False)
            if isinstance(res, Exception):
                return self.say(tr("Install failed: {err}", err=res), False)
            ok, msg = res
            self.say(msg, ok)

        run_bg(self, lambda: server_setup.install(cfg), done)

    def on_save(self) -> None:
        new = self.collect()
        if new is None:
            self.tabs.setCurrentIndex(0)
            return
        values = self.app_values()
        if values["route_no_uac"] != bool(self.engine.cfg.get("route_no_uac")):
            self.say(tr("Waiting for the admin rights prompt…"), None)
            QApplication.processEvents()
            if not self.engine.set_no_uac(values["route_no_uac"]):
                return self.say(tr("Windows did not confirm the change (admin rights were not given?)."), False)
        try:
            self.engine.apply_app_settings(values)
            self.engine.apply_settings(new)
        except OSError as e:
            return self.say(str(e), False)
        self.say(tr("Saved."), True)
        self.saved.emit()


def running_programs() -> list[tuple[str, str]]:
    """(name.exe, full path) of running programs a user would pick: not Windows' own, one row per name."""
    import os

    import psutil

    windir = (os.environ.get("SystemRoot") or r"C:\Windows").lower()
    seen: dict[str, tuple[str, str]] = {}
    for p in psutil.process_iter(["name", "exe"]):
        exe = p.info.get("exe") or ""
        if exe and not exe.lower().startswith(windir) and p.info["name"].lower() not in seen:
            seen[p.info["name"].lower()] = (p.info["name"], exe)
    return sorted(seen.values(), key=lambda x: x[0].lower())


TARGET_TITLES = (("server", "Through your server"), ("vpn", "Through the VPN"), ("direct", "Direct"))
TARGET_SHORT = (("server", "Server"), ("vpn", "VPN"), ("direct", "Direct"))


class ProfileDialog(FramelessDialog):
    """Create a profile (from a preset or empty) or edit one: name, where it goes, what it holds."""

    def __init__(self, parent, engine: core.Engine, profile: dict | None = None):
        super().__init__(parent, tr("Profile") if profile else tr("New profile"))
        self.engine = engine
        self.is_new = profile is None
        self.profile = copy.deepcopy(profile) if profile else profiles.normalize(profiles.preset("custom"))
        self.deleted = False
        self.setMinimumSize(640, 640)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        r = 0
        if self.is_new:
            grid.addWidget(QLabel(tr("Start from a preset"), objectName="formLabel"), r, 0)
            self.preset = QComboBox()
            shown = [(tr(p["name"]) if p["id"] in ("custom", "blocked") else p["name"], p["id"]) for p in profiles.PRESETS]
            custom = [x for x in shown if x[1] == "custom"]
            for title, pid in custom + sorted((x for x in shown if x[1] != "custom"), key=lambda x: x[0].lower()):
                self.preset.addItem(title, pid)
            self.preset.setCurrentIndex(self.preset.findData("custom"))
            self.preset.currentIndexChanged.connect(self.load_preset)
            grid.addWidget(self.preset, r, 1)
            r += 1
        grid.addWidget(QLabel(tr("Name"), objectName="formLabel"), r, 0)
        self.name = QLineEdit()
        grid.addWidget(self.name, r, 1)
        r += 1
        grid.addWidget(QLabel(tr("Goes"), objectName="formLabel"), r, 0)
        self.target = QComboBox()
        for key, title in TARGET_TITLES:
            self.target.addItem(tr(title), key)
        self.target.currentIndexChanged.connect(self.show_hint)
        grid.addWidget(self.target, r, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        lay.addWidget(QLabel(tr("What goes"), objectName="formLabel"))
        hint = QLabel(tr("One entry per line: a site (subdomains included), a program (name.exe), a folder "
                         "(every program inside it) or an IP/subnet. # starts a comment."), objectName="note")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.entries = QPlainTextEdit()
        self.entries.setStyleSheet("QPlainTextEdit { font-family: Consolas, monospace; }")
        self.entries.setMinimumHeight(200)
        self.entries.textChanged.connect(self.show_hint)
        lay.addWidget(self.entries, 1)
        adds = QHBoxLayout()
        adds.setSpacing(8)
        for text, fn in ((tr("+ Program…"), self.add_program), (tr("+ Folder…"), self.add_folder),
                         (tr("+ Running…"), self.add_running)):
            b = QPushButton(text, objectName="small")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            adds.addWidget(b)
        adds.addStretch()
        lay.addLayout(adds)
        self.mode_hint = QLabel(objectName="note")
        self.mode_hint.setWordWrap(True)
        lay.addWidget(self.mode_hint)

        lay.addWidget(QLabel(tr("Watched apps"), objectName="formLabel"))
        self.apps = QLabel(objectName="dim")
        self.apps.setWordWrap(True)
        lay.addWidget(self.apps)
        self.err = QLabel(objectName="error")
        self.err.setWordWrap(True)
        lay.addWidget(self.err)

        row = QHBoxLayout()
        if not self.is_new:
            rm = QPushButton(tr("Delete"), objectName="dangerSmall")
            rm.clicked.connect(self.on_delete)
            row.addWidget(rm)
        row.addStretch()
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)
        ok = QPushButton(tr("Save"), objectName="primary")
        ok.setDefault(True)
        ok.clicked.connect(self.on_save)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self.show_profile()

    def load_preset(self) -> None:
        self.profile = profiles.normalize(profiles.preset(self.preset.currentData()))
        if self.profile["id"] in ("custom", "blocked"):
            self.profile["name"] = tr(self.profile["name"])
        self.show_profile()

    def show_profile(self) -> None:
        self.name.setText(self.profile["name"])
        self.target.setCurrentIndex(max(0, self.target.findData(self.profile["target"])))
        self.entries.setPlainText("\n".join(self.profile["entries"]))
        names = [a["name"] for a in self.profile["apps"]]
        self.apps.setText(", ".join(names) if names else tr("none — leaks are not checked for this profile"))
        self.show_hint()

    def show_hint(self) -> None:
        target = self.target.currentData()
        parsed = routing.parse_list(self.entries.toPlainText().splitlines())
        if target != "server":
            text = tr("Works while the VPN is connected.")
        elif parsed["procs"] or parsed["folders"] or parsed["cidrs"]:
            text = tr("Sites go through your server always; programs, folders and subnets — while the VPN is connected.")
        else:
            text = tr("Sites go through your server always, no admin rights needed.")
        self.mode_hint.setText(text)

    # --- adding entries ---

    def _append(self, line: str) -> None:
        lines = self.entries.toPlainText().splitlines()
        if line.lower() in (ln.split("#", 1)[0].strip().lower() for ln in lines):
            return
        while lines and not lines[-1].strip():
            lines.pop()
        self.entries.setPlainText("\n".join(lines + [line]))
        self.entries.moveCursor(self.entries.textCursor().MoveOperation.End)

    def add_program(self) -> None:
        import os

        path, _ = QFileDialog.getOpenFileName(self, tr("Choose a program"), "", tr("Programs (*.exe)"))
        if path:
            self._append(os.path.basename(path))

    def add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("Choose a folder: every program inside it"))
        if path:
            self._append(path.replace("/", "\\").rstrip("\\") + "\\")

    def add_running(self) -> None:
        menu = QMenu(self)
        progs = running_programs()
        if not progs:
            a = QAction(tr("nothing found"), menu)
            a.setEnabled(False)
            menu.addAction(a)
        for name, exe in progs:
            a = QAction(name, menu)
            a.setToolTip(exe)
            a.triggered.connect(lambda _=False, n=name: self._append(n))
            menu.addAction(a)
        menu.setToolTipsVisible(True)
        menu.exec(QCursor.pos())

    # --- save / delete ---

    def on_save(self) -> None:
        lines = [ln.rstrip() for ln in self.entries.toPlainText().splitlines()]
        parsed = routing.parse_list(lines)
        if parsed["bad"]:
            return self.err.setText(tr("Not understood: {items}", items=", ".join(parsed["bad"][:5])))
        if not routing.has_items(lines):
            return self.err.setText(tr("Add at least one site, program or folder."))
        p = self.profile
        p["name"] = self.name.text().strip() or p["name"]
        p["target"] = self.target.currentData()
        p["entries"] = lines
        if self.is_new:
            taken = {x["id"] for x in self.engine.cfg["profiles"]}
            base, n, pid = p["id"], 2, p["id"]
            while pid in taken:
                pid, n = f"{base}-{n}", n + 1
            p["id"] = pid
            p["enabled"] = True
        self.engine.upsert_profile(profiles.normalize(p))
        self.accept()

    def on_delete(self) -> None:
        if confirm(self, tr("Delete"), tr("Delete profile «{name}»?", name=self.profile["name"]), yes=tr("Delete"),
                   danger=True):
            self.engine.delete_profile(self.profile["id"])
            self.deleted = True
            self.accept()


class WelcomeDialog(FramelessDialog):
    """First start: what XmelTunnel can do and where to begin. Everything can be changed later."""

    CHOICES = (
        ("subscription", "VPN from a subscription",
         "Paste a subscription link or server links (VLESS, VMess, Trojan, Shadowsocks, Hysteria2, TUIC). "
         "XmelTunnel checks every server for real and picks the fastest."),
        ("routing", "Rules on top of your VPN",
         "Happ, v2rayN or another VPN client stays on. Profiles decide what goes through the VPN, what direct, "
         "and what through your server: games direct, YouTube through the VPN, and so on."),
        ("server", "Your own server",
         "Chosen sites and apps (Claude, ChatGPT…) go through your Linux server over SSH. From there you can also "
         "share it: friends get personal links."),
    )

    def __init__(self, parent):
        super().__init__(parent, tr("Quick start"))
        self.choice = ""
        self.setMinimumWidth(660)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(12)
        lay.addWidget(QLabel(tr("Welcome to XmelTunnel"), objectName="heroTitle"))
        note = QLabel(tr("Pick where to start. All of it works together, and everything can be changed later."),
                      objectName="note")
        note.setWordWrap(True)
        lay.addWidget(note)
        for i, (key, title, text) in enumerate(self.CHOICES):
            card = QFrame(objectName="card")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            col = QVBoxLayout()
            col.addWidget(QLabel(tr(title), objectName="appName"))
            t = QLabel(tr(text), objectName="note")
            t.setWordWrap(True)
            col.addWidget(t)
            cl.addLayout(col, 1)
            b = QPushButton(tr("Set up"), objectName="primary" if i == 0 else "")
            b.clicked.connect(lambda _=False, k=key: self.pick(k))
            cl.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
            lay.addWidget(card)
        row = QHBoxLayout()
        row.addStretch()
        later = QPushButton(tr("Later"))
        later.clicked.connect(self.reject)
        row.addWidget(later)
        lay.addLayout(row)

    def pick(self, key: str) -> None:
        self.choice = key
        self.accept()
