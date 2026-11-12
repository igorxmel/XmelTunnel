"""«Access for friends»: the owner's panel. Everything goes over SSH in the background."""

from __future__ import annotations

import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import (QAbstractItemView, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QPlainTextEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from xmeltunnel import core, sharing
from xmeltunnel.i18n import tr
from xmeltunnel.ui import theme
from xmeltunnel.ui.dialogs import run_bg
from xmeltunnel.ui.frameless import FramelessDialog, ask_text, confirm, info

COLS = ("Person", "Status", "Traffic", "Limit", "Valid until", "Online", "Port")


def ago(ts: int) -> str:
    if not ts:
        return tr("never")
    m = int((time.time() - ts) // 60)
    return tr("now") if m < 2 else tr("{n} min ago", n=m) if m < 60 else tr("{h} h ago", h=m // 60) \
        if m < 2880 else time.strftime("%d.%m.%Y", time.localtime(ts))


class InviteDialog(FramelessDialog):
    """A new friend: name, how long, how much traffic."""

    def __init__(self, parent):
        super().__init__(parent, tr("New person"))
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("For example, Pete"))
        self.days = QComboBox()
        for d in (0, 7, 30, 90, 365):
            self.days.addItem(tr("no limit") if not d else tr("{n} days", n=d), d)
        self.days.setCurrentIndex(0)
        self.quota = QComboBox()
        for g in (0, 10, 50, 100, 500):
            self.quota.addItem(tr("no limit") if not g else f"{g} " + tr("GB"), g)
        for r, (label, w) in enumerate(((tr("Person"), self.name), (tr("Valid for"), self.days), (tr("Traffic limit"), self.quota))):
            grid.addWidget(QLabel(label, objectName="formLabel"), r, 0)
            grid.addWidget(w, r, 1)
        lay.addLayout(grid)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)
        ok = QPushButton(tr("Create the link"), objectName="primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)


class LinkDialog(FramelessDialog):
    def __init__(self, parent, name: str, link: str):
        super().__init__(parent, tr("Link for {name}", name=name))
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)
        note = QLabel(tr("Send this link to {name}. In XmelTunnel it goes to Settings → Server → «By a link» (your server for "
                         "their sites and apps) or to «Choose a VPN server» → Add (a VPN server); it also works in Happ "
                         "and v2rayN. Anyone with the link can use it: send it privately.", name=name),
                      objectName="note")
        note.setWordWrap(True)
        lay.addWidget(note)
        box = QPlainTextEdit(link)
        box.setReadOnly(True)
        box.setMaximumHeight(80)
        box.setStyleSheet("QPlainTextEdit { font-family: Consolas, monospace; }")
        lay.addWidget(box)
        row = QHBoxLayout()
        row.addStretch()
        copy = QPushButton(tr("Copy"), objectName="primary")
        copy.clicked.connect(lambda: (QGuiApplication.clipboard().setText(link), copy.setText(tr("Copied"))))
        row.addWidget(copy)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)


class SharingDialog(FramelessDialog):
    def __init__(self, parent, engine: core.Engine):
        super().__init__(parent, tr("Sharing"))
        self.engine = engine
        self.users: list[dict] = []
        self.setMinimumSize(900, 560)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(10)
        note = QLabel(tr("Each person gets a personal link: their own key and port on your server, no SSH or root. "
                         "Guests cannot reach the server itself or local addresses, and mail ports are closed. "
                         "Their traffic leaves from your server's IP: complaints about it would come to you."),
                      objectName="note")
        note.setWordWrap(True)
        lay.addWidget(note)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLS])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)  # a few dozen rows at most
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _: self.on_link())
        lay.addWidget(self.table, 1)

        self.status = QLabel(objectName="note")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        self.buttons = []
        for text, fn, name in ((tr("Add a person…"), self.on_add, "primary"), (tr("Copy the link"), self.on_link, "small"),
                               (tr("Rename…"), self.on_rename, "small"), (tr("Pause / resume"), self.on_pause, "small"),
                               (tr("Refresh"), self.load, "small")):
            b = QPushButton(text, objectName=name)
            b.clicked.connect(fn)
            row.addWidget(b)
            self.buttons.append(b)
        row.addStretch()
        rm = QPushButton(tr("Remove"), objectName="dangerSmall")
        rm.clicked.connect(self.on_remove)
        row.addWidget(rm)
        self.buttons.append(rm)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        if not engine.cfg.get("ss_key"):
            self.say(tr("First install Shadowsocks: Settings → Server → «Install on the server»."), False)
            for b in self.buttons:
                b.setEnabled(False)
        else:
            self.load()

    # --- helpers ---

    def say(self, text: str, ok: bool | None = None) -> None:
        self.status.setText(text)
        self.status.setStyleSheet("" if ok is not False else f"color: {theme.C['danger']};")

    def busy(self, text: str) -> None:
        self.say(text)
        for b in self.buttons:
            b.setEnabled(False)

    def idle(self) -> None:
        for b in self.buttons:
            b.setEnabled(True)

    def host(self) -> str:
        return self.engine.ip or core.server_host(self.engine.cfg)

    def selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.say(tr("Choose a person in the list first."), False)
            return None
        uid = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((u for u in self.users if u["id"] == uid), None)

    # --- server round trips ---

    def load(self) -> None:
        self.busy(tr("Asking the server…"))
        cfg = dict(self.engine.cfg)

        def job():
            st = sharing.fetch(cfg)
            paused = sharing.enforce_limits(st["users"])
            if paused:
                sharing.apply(cfg, st["users"])
            return st["users"], paused

        def finished(res):
            self.idle()
            if isinstance(res, Exception):
                return self.say(tr("Could not reach the server: {err}", err=res), False)
            self.users, paused = res
            self.fill()
            msg = tr("People: {n}, online now: {m}.", n=len(self.users), m=sum(1 for u in self.users if u.get("online")))
            if paused:
                msg += " " + tr("Paused now (time or traffic ran out): {names}.", names=", ".join(paused))
            self.say(msg, True)

        run_bg(self, job, finished)

    def save(self, then=None, text: str = "") -> None:
        self.busy(text or tr("Saving on the server…"))
        cfg, users = dict(self.engine.cfg), [dict(u) for u in self.users]

        def finished(res):
            self.idle()
            if isinstance(res, Exception):
                self.say(tr("The server did not accept the change: {err}", err=res), False)
                return self.load()
            with self.engine.cfg_lock:
                self.engine.cfg["sharing_used"] = bool(self.users)
                self.engine.save()
            if then:
                then()
            self.load()

        run_bg(self, lambda: sharing.apply(cfg, users), finished)

    # --- table ---

    def fill(self) -> None:
        self.table.setRowCount(len(self.users))
        for r, u in enumerate(self.users):
            if u.get("paused"):
                status, level = {"expired": tr("paused: time is up"), "quota": tr("paused: traffic is used up")}.get(
                    u.get("reason", ""), tr("paused")), "warn"
            else:
                status, level = tr("active"), "ok"
            used = sharing.total(u)
            limit = f"{sharing.fmt_bytes(used)} / {u['quota_gb']:g} {tr('GB')}" if u.get("quota_gb") else tr("no limit")
            until = time.strftime("%d.%m.%Y", time.localtime(u["expires"])) if u.get("expires") else tr("no limit")
            online = tr("online ({n})", n=u["online"]) if u.get("online") else (tr("seen {ago}", ago=ago(u["last_seen"])) if u.get("last_seen") else tr("not connected yet"))
            cells = [u["name"], status, sharing.fmt_bytes(used), limit, until, online, str(u["port"])]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                it.setData(Qt.ItemDataRole.UserRole, u["id"])
                if c == 1:
                    it.setForeground(QColor(theme.level_color(level)))
                if c == 5 and u.get("online"):
                    it.setForeground(QColor(theme.C["success"]))
                self.table.setItem(r, c, it)

    # --- actions ---

    def on_add(self) -> None:
        dlg = InviteDialog(self)
        if not dlg.exec():
            return
        try:
            user = sharing.new_user(dlg.name.text(), self.users, dlg.days.currentData(), dlg.quota.currentData())
        except ValueError as e:
            return self.say(str(e), False)
        self.users.append(user)
        link = sharing.invite_link(user, self.host())
        self.save(lambda: LinkDialog(self, user["name"], link).exec(), tr("Adding {name}…", name=user["name"]))

    def on_link(self) -> None:
        u = self.selected()
        if u:
            LinkDialog(self, u["name"], sharing.invite_link(u, self.host())).exec()

    def on_rename(self) -> None:
        u = self.selected()
        if not u:
            return
        name = ask_text(self, tr("Rename"), tr("New name"), u["name"])
        if name and name.strip() and name.strip() != u["name"]:
            u["name"] = name.strip()
            self.save()

    def on_pause(self) -> None:
        u = self.selected()
        if not u:
            return
        if u.get("paused"):
            if u.get("reason") == "expired" and u.get("expires") and u["expires"] < time.time():
                u["expires"] = 0  # resuming an expired one: no end date unless set again
            u.update(paused=False, reason="")
        else:
            u.update(paused=True, reason="")
        self.save()

    def on_remove(self) -> None:
        u = self.selected()
        if u and confirm(self, tr("Remove"), tr("Remove {name}? Their link stops working at once.", name=u["name"]),
                         yes=tr("Remove"), danger=True):
            self.users = [x for x in self.users if x["id"] != u["id"]]
            self.save()
