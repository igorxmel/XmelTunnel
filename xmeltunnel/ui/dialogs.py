"""Settings (server + setup) and profile editor dialogs."""

from __future__ import annotations

import copy

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                             QPushButton, QVBoxLayout)

from xmeltunnel import core, i18n, profiles, server_setup
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


class SettingsDialog(FramelessDialog):
    FIELDS = (("server", "Server (IP, user@host or ~/.ssh/config alias)"), ("ssh_port", "SSH port"),
              ("ssh_key", "SSH key file"), ("remote_proxy_port", "Proxy port on the server"),
              ("local_proxy_port", "Proxy port on this PC"), ("pac_port", "PAC file port"))

    def __init__(self, parent, engine: core.Engine):
        super().__init__(parent, tr("Settings"))
        self.engine = engine
        self.setMinimumWidth(600)
        cfg = engine.cfg
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)
        intro = QLabel(tr("XmelTunnel needs a Linux server you can reach over SSH with a key.") + "\n"
                       + tr("The proxy listens only inside the server, nothing new is opened to the internet."),
                       objectName="note")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.edits = {}
        r = 0
        for key, label in self.FIELDS:
            grid.addWidget(QLabel(tr(label), objectName="formLabel"), r, 0)
            e = QLineEdit(str(cfg[key]))
            grid.addWidget(e, r, 1)
            self.edits[key] = e
            r += 1
        grid.addWidget(QLabel(tr("Language"), objectName="formLabel"), r, 0)
        self.lang = QComboBox()
        self.lang.addItem("Windows", "")
        for code, name in i18n.LANGS.items():
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(cfg["language"])))
        grid.addWidget(self.lang, r, 1)
        r += 1
        self.vpn = QCheckBox(tr("Warn when the VPN is off"))
        self.vpn.setChecked(cfg["require_vpn"])
        grid.addWidget(self.vpn, r, 1)
        r += 1
        grid.addWidget(QLabel(tr("VPN adapter (regular expression)"), objectName="formLabel"), r, 0)
        self.vpn_rx = QLineEdit(cfg["vpn_adapter"])
        grid.addWidget(self.vpn_rx, r, 1)
        r += 1
        grid.addWidget(QLabel(tr("Only needed if your server is reachable only through a VPN."), objectName="note"),
                       r, 1)
        lay.addLayout(grid)

        self.msg = QLabel(objectName="dim")
        self.msg.setWordWrap(True)
        self.msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.msg)

        row = QHBoxLayout()
        self.b_check = QPushButton(tr("Check connection"))
        self.b_check.clicked.connect(self.on_check)
        self.b_install = QPushButton(tr("Install proxy on the server"))
        self.b_install.clicked.connect(self.on_install)
        row.addWidget(self.b_check)
        row.addWidget(self.b_install)
        row.addStretch()
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)
        ok = QPushButton(tr("Save"), objectName="primary")
        ok.setDefault(True)
        ok.clicked.connect(self.on_save)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def collect(self) -> dict | None:
        out, errors = core.validate({k: e.text() for k, e in self.edits.items()})
        if errors:
            self.say("\n".join(errors), False)
            return None
        out.update(language=self.lang.currentData(), require_vpn=self.vpn.isChecked(),
                   vpn_adapter=self.vpn_rx.text().strip() or core.DEFAULTS["vpn_adapter"])
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
            return
        try:
            self.engine.apply_settings(new)
        except OSError as e:
            return self.say(str(e), False)
        self.accept()


class ProfileDialog(FramelessDialog):
    """Create a profile (from a preset or empty) or edit domains of an existing one."""

    def __init__(self, parent, engine: core.Engine, profile: dict | None = None):
        super().__init__(parent, tr("Profile") if profile else tr("New profile"))
        self.engine = engine
        self.is_new = profile is None
        self.profile = copy.deepcopy(profile) if profile else profiles.preset("custom")
        self.deleted = False
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)

        if self.is_new:
            lay.addWidget(QLabel(tr("Start from a preset"), objectName="formLabel"))
            self.preset = QComboBox()
            for p in profiles.PRESETS:
                self.preset.addItem(tr(p["name"]) if p["id"] == "custom" else p["name"], p["id"])
            self.preset.currentIndexChanged.connect(self.load_preset)
            lay.addWidget(self.preset)

        lay.addWidget(QLabel(tr("Name"), objectName="formLabel"))
        self.name = QLineEdit()
        lay.addWidget(self.name)
        lay.addWidget(QLabel(tr("Domains (one per line, subdomains included)"), objectName="formLabel"))
        self.domains = QPlainTextEdit()
        self.domains.setMinimumHeight(170)
        self.domains.setStyleSheet("QPlainTextEdit { font-family: Consolas, monospace; }")
        lay.addWidget(self.domains)
        lay.addWidget(QLabel(tr("Watched apps"), objectName="formLabel"))
        self.apps = QLabel(objectName="dim")
        self.apps.setWordWrap(True)
        lay.addWidget(self.apps)
        self.err = QLabel(objectName="error")
        self.err.setWordWrap(True)
        lay.addWidget(self.err)

        row = QHBoxLayout()
        if not self.is_new:
            rm = QPushButton(tr("Delete"))
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
        if self.is_new:
            self.preset.setCurrentIndex(0)
            self.load_preset()

    def load_preset(self) -> None:
        self.profile = profiles.preset(self.preset.currentData())
        if self.profile["id"] == "custom":
            self.profile["name"] = tr("My sites")
        self.show_profile()

    def show_profile(self) -> None:
        self.name.setText(self.profile["name"])
        self.domains.setPlainText("\n".join(self.profile["domains"]))
        names = [a["name"] for a in self.profile["apps"]]
        self.apps.setText(", ".join(names) if names else tr("none — leaks are not checked for this profile"))

    def on_save(self) -> None:
        ok, bad = profiles.parse_domains(self.domains.toPlainText())
        if bad:
            return self.err.setText(tr("Not domains: {items}", items=", ".join(bad[:5])))
        if not ok:
            return self.err.setText(tr("Add at least one domain."))
        p = self.profile
        p["name"] = self.name.text().strip() or p["name"]
        p["domains"] = ok
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
        if confirm(self, tr("Delete"), tr("Delete profile «{name}»?", name=self.profile["name"]), yes=tr("Delete")):
            self.engine.delete_profile(self.profile["id"])
            self.deleted = True
            self.accept()
