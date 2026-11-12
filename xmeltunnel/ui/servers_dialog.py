"""«VPN servers»: subscriptions and links, an honest check, filters and sorting, the choice of a server."""

from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QSizePolicy, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from xmeltunnel import core, servers
from xmeltunnel.i18n import tr
from xmeltunnel.ui import theme
from xmeltunnel.ui.frameless import FramelessDialog, confirm
from xmeltunnel.ui.widgets import country_name, flag_pixmap

COLS = ("", "Country", "Name", "Protocol", "Ping", "Real exit", "Subscription")
RECHECK_AFTER = 30 * 60  # opening the window re-checks servers whose ping is older than this


class SortItem(QTableWidgetItem):
    """Sorts by a hidden key (latency in ms, failed and unchecked last), not by the shown text."""

    def __init__(self, text: str, key):
        super().__init__(text)
        self.key = key

    def __lt__(self, other):  # noqa: D105
        return self.key < getattr(other, "key", self.key)


def ping_text(chk: dict | None) -> tuple[str, str, tuple]:
    """(text, level, sort key) of a check result."""
    if not chk:
        return "—", "unknown", (2, 0)
    if chk.get("ms") is None:
        return tr("no answer ({err})", err=chk.get("error") or "?"), "down", (1, 0)
    ms = chk["ms"]
    level = "ok" if ms < 200 else "warn" if ms < 500 else "down"
    lossy = f" · {chk['ok']}/{chk['of']}" if chk.get("ok", 0) < chk.get("of", 0) else ""
    return f"{ms} {tr('ms')}{lossy}", level, (0, ms)


def ago_short(ts: float) -> str:
    if not ts:
        return tr("never")
    m = int((time.time() - ts) // 60)
    return tr("just now") if m < 1 else tr("{n} min ago", n=m) if m < 60 else tr("{h} h ago", h=m // 60)


class ServersDialog(FramelessDialog):
    def __init__(self, parent, engine: core.Engine):
        super().__init__(parent, tr("Choose a VPN server"))
        self.engine = engine
        self.setMinimumSize(980, 640)
        self.resize(1160, 780)
        self._auto_checked = False
        self._sig = None
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(10)

        add = QHBoxLayout()
        self.link = QLineEdit()
        self.link.setPlaceholderText(tr("A subscription link (https://…) or server links (vless://, vmess://, trojan://, "
                                        "ss://, hysteria2://, tuic://)"))
        self.link.returnPressed.connect(self.on_add)
        add.addWidget(self.link, 1)
        b = QPushButton(tr("Add"), objectName="primary")
        b.clicked.connect(self.on_add)
        add.addWidget(b)
        lay.addLayout(add)
        self.add_msg = QLabel(objectName="note")
        self.add_msg.setWordWrap(True)
        self.add_msg.hide()
        lay.addWidget(self.add_msg)

        subs = QHBoxLayout()
        self.subs = QListWidget()
        self.subs.setMaximumHeight(74)
        subs.addWidget(self.subs, 1)
        col = QVBoxLayout()
        for text, fn in ((tr("Update"), self.on_update_subs), (tr("Delete"), self.on_delete_sub)):
            sb = QPushButton(text, objectName="small")
            sb.clicked.connect(fn)
            col.addWidget(sb)
        col.addStretch()
        subs.addLayout(col)
        lay.addLayout(subs)

        flt = QHBoxLayout()
        flt.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search by name or address"))
        self.search.textChanged.connect(self.fill)
        flt.addWidget(self.search, 2)
        self.country = QComboBox()
        self.country.currentIndexChanged.connect(self.fill)
        flt.addWidget(self.country, 1)
        self.proto = QComboBox()
        self.proto.addItem(tr("All protocols"), "")
        for key, title in servers.PROTOCOLS.items():
            self.proto.addItem(title, key)
        self.proto.currentIndexChanged.connect(self.fill)
        flt.addWidget(self.proto, 1)
        self.working = QCheckBox(tr("Only working"))
        self.working.toggled.connect(self.fill)
        flt.addWidget(self.working)
        self.b_check = QPushButton(tr("Check ping"), objectName="primary")
        self.b_check.setToolTip(tr("A real request through every shown server: the ping is the time it takes, "
                                   "the real exit is where traffic comes out. Not a knock on the port."))
        self.b_check.clicked.connect(self.on_check)
        flt.addWidget(self.b_check)
        lay.addLayout(flt)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels([tr(c) if c else "" for c in COLS])
        self.table.horizontalHeaderItem(4).setToolTip(tr("Median of 3 real requests through the server. Click to sort."))
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSortingEnabled(True)
        h = self.table.horizontalHeader()
        # Not ResizeToContents: it re-measures every row after every cell, which froze the window for
        # minutes on a 600-server subscription. Widths are measured once after filling (see fill).
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setStretchLastSection(True)  # spare room goes to the subscription name, not to an empty gap
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(30)
        h.setSortIndicator(4, Qt.SortOrder.AscendingOrder)
        self.table.doubleClicked.connect(lambda _: self.on_use())
        lay.addWidget(self.table, 1)

        self.via = QCheckBox(tr("Connect through my VPN client"))
        self.via.setToolTip(tr("Turn on if these servers are blocked where you are: XmelTunnel will reach them "
                               "through Happ, v2rayN or another VPN client that is running."))
        self.via.setChecked(bool(engine.cfg.get("servers_via_adapter")))
        self.via.toggled.connect(self.on_via)
        lay.addWidget(self.via)
        self.status = QLabel(objectName="note")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        rb = QPushButton(tr("Delete selected"), objectName="dangerSmall")
        rb.clicked.connect(self.on_delete)
        row.addWidget(rb)
        row.addStretch()
        self.b_auto = QPushButton(objectName="small")
        self.b_auto.clicked.connect(self.on_auto)
        row.addWidget(self.b_auto)
        use = QPushButton(tr("Use the selected one"), objectName="primary")
        use.clicked.connect(self.on_use)
        row.addWidget(use)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        for w in (rb, self.b_auto, use, close, self.b_check):
            w.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)  # never squeezed
        lay.addLayout(row)

        self.timer = QTimer(self, interval=700)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.fill()
        QTimer.singleShot(400, self.auto_check)

    def auto_check(self) -> None:
        """Check the shown servers by itself if their ping is missing or old: nobody should have to guess."""
        checks = self._checks()
        stale = [s["id"] for s in self.visible()
                 if time.time() - (checks.get(s["id"]) or {}).get("at", 0) > RECHECK_AFTER]
        if stale:
            self.engine.check_servers(stale)
        self._auto_checked = True

    # --- data ---

    def _checks(self) -> dict:
        return dict(self.engine.cfg.get("server_checks") or {})  # a copy: the check thread writes the original

    def _country(self, s: dict) -> str:
        checks = getattr(self, "_checks_now", None) or {}
        return s.get("country") or (checks.get(s["id"]) or {}).get("exit_loc", "")

    def visible(self) -> list[dict]:
        q = self.search.text().strip().lower()
        cc, proto, only_ok = self.country.currentData(), self.proto.currentData(), self.working.isChecked()
        checks = self._checks()
        out = []
        for s in list(self.engine.cfg.get("servers") or []):
            if q and q not in s["name"].lower() and q not in s["host"].lower():
                continue
            if cc and self._country(s) != cc:
                continue
            if proto and s["protocol"] != proto:
                continue
            if only_ok and not (checks.get(s["id"]) or {}).get("ms"):
                continue
            out.append(s)
        return out

    def fill(self) -> None:
        cfg = self.engine.cfg
        # countries in the filter, with counts
        counts: dict[str, int] = {}
        self._checks_now = self._checks()
        for s in list(cfg.get("servers") or []):
            c = self._country(s)
            counts[c] = counts.get(c, 0) + 1
        keep = self.country.currentData()
        self.country.blockSignals(True)
        self.country.clear()
        self.country.addItem(tr("All countries"), "")
        for c in sorted(counts, key=lambda x: country_name(x) if x else "~"):
            if c:
                self.country.addItem(QIcon(flag_pixmap(c, 18, 13)), f"{country_name(c)} ({counts[c]})", c)
        self.country.setCurrentIndex(max(0, self.country.findData(keep)))
        self.country.blockSignals(False)

        subs = {s["id"]: (s.get("title") or s["url"]) for s in cfg.get("subscriptions") or []}
        checks = self._checks()
        pick = cfg.get("vpn_server") or "auto"
        rows = self.visible()
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, s in enumerate(rows):
            chk = checks.get(s["id"])
            mark = "●" if s["id"] == pick else ""
            cc = self._country(s)
            text, level, key = ping_text(chk)
            exit_loc = (chk or {}).get("exit_loc", "")
            cells = [
                SortItem(mark, 0 if mark else 1),
                SortItem(country_name(cc) if cc else "—", country_name(cc) if cc else "~"),
                SortItem(servers.display_name(s["name"]), s["name"].lower()),
                SortItem(servers.PROTOCOLS.get(s["protocol"], s["protocol"]), s["protocol"]),
                SortItem(text, key),
                SortItem(f"{exit_loc} · {(chk or {}).get('exit_ip', '')}" if exit_loc else "—", exit_loc or "~"),
                SortItem(subs.get(s.get("sub"), tr("added by hand")), s.get("sub") or "~"),
            ]
            if cc:
                cells[1].setIcon(self._flag(cc))
            if exit_loc:
                cells[5].setIcon(self._flag(exit_loc))
                if cc and exit_loc != cc:
                    cells[5].setToolTip(tr("The name says {a}, but traffic really exits in {b}.",
                                           a=country_name(cc), b=country_name(exit_loc)))
            cells[4].setForeground(QColor(theme.level_color(level)))
            if chk and chk.get("error"):
                cells[4].setToolTip(chk["error"])
            cells[0].setForeground(QColor(theme.C["success"]))
            for c, item in enumerate(cells):
                item.setData(Qt.ItemDataRole.UserRole, s["id"])
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        for c in range(len(COLS) - 1):  # once per fill; never narrower than the column's own title
            w = self.table.sizeHintForColumn(c) if len(rows) <= 200 else self._sample_width(c)
            w = max(w + 18, header.sectionSizeFromContents(c).width() + 12, 36)
            self.table.setColumnWidth(c, min(w, 420) if c == 2 else w)
        self.table.setUpdatesEnabled(True)

        self.subs.clear()
        for sub in cfg.get("subscriptions") or []:
            info = sub.get("info") or {}
            extra = ""
            if info.get("total"):
                used = (info.get("upload", 0) + info.get("download", 0)) / 2**30
                extra = " · " + tr("{used:.1f} of {total:.0f} GB", used=used, total=info["total"] / 2**30)
            if info.get("expire"):
                extra += " · " + tr("until {date}", date=time.strftime("%d.%m.%Y", time.localtime(info["expire"])))
            text = f"{sub.get('title') or sub['url']} — " + tr("servers: {n}", n=sub.get("count", 0)) + \
                f" · {ago_short(sub.get('updated_at', 0))}{extra}"
            if sub.get("error"):
                text += "  ⚠ " + sub["error"]
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, sub["id"])
            it.setToolTip(sub["url"])
            self.subs.addItem(it)
        cc = self.country.currentData()
        self.b_auto.setText(tr("Automatically: fastest in {country}", country=country_name(cc)) if cc
                            else tr("Automatically: the fastest"))
        self._sig = self._signature()
        self.tick()

    def _sample_width(self, col: int) -> int:
        fm = self.table.fontMetrics()
        texts = {self.table.item(r, col).text() for r in range(self.table.rowCount()) if self.table.item(r, col)}
        icon = 26 if col in (1, 5) else 0
        return max((fm.horizontalAdvance(t) for t in texts), default=40) + icon

    def _flag(self, code: str) -> QIcon:
        cache = self.__dict__.setdefault("_icons", {})
        if code not in cache:
            cache[code] = QIcon(flag_pixmap(code, 18, 13))
        return cache[code]

    def _signature(self):
        cfg = self.engine.cfg
        checks = cfg.get("server_checks") or {}
        return (len(cfg.get("servers") or []), len(cfg.get("subscriptions") or []), cfg.get("vpn_server"),
                len(checks), max((v.get("at", 0) for v in checks.values()), default=0),
                tuple(s.get("updated_at") for s in cfg.get("subscriptions") or []))

    def tick(self) -> None:
        st = self.engine.snapshot()[0]["servers"]
        if self._signature() != self._sig and not st["checking"]:
            self.fill()
            return
        total = len(self.engine.cfg.get("servers") or [])
        pick = self.engine.cfg.get("vpn_server") or "auto"
        current = tr("automatically, the fastest") if pick == "auto" else \
            tr("automatically, the fastest in {country}", country=country_name(pick[5:])) if pick.startswith("auto:") \
            else next((servers.display_name(s["name"]) for s in self.engine.cfg["servers"] if s["id"] == pick), "—")
        parts = [tr("Servers: {n}, shown: {m}", n=total, m=self.table.rowCount()), tr("In use: {name}", name=current)]
        self.b_check.setEnabled(not st["checking"])
        self.b_check.setText(tr("Checking… {done} of {total}", done=st["done"], total=st["total"]) if st["checking"]
                             else tr("Check ping"))
        was = getattr(self, "_was_updating", False)
        self._was_updating = bool(st.get("updating"))
        if was and not st.get("updating"):
            QTimer.singleShot(300, self.auto_check)  # a subscription brought new servers: show their ping
        if st["checking"]:
            parts.append(tr("Checking… {done} of {total}", done=st["done"], total=st["total"]))
        elif st.get("updating"):
            parts.append(tr("Updating subscriptions…"))
        elif st.get("error"):
            parts.append(tr("Check failed: {err}", err=st["error"]))
        self.status.setText("   ·   ".join(parts))

    # --- actions ---

    def on_add(self) -> None:
        text = self.link.text().strip()
        if not text:
            return
        n, errors = self.engine.add_servers_text(text)
        self.link.clear()
        if text.startswith("http"):
            msg = tr("Subscription added, loading its servers…")
        else:
            msg = tr("Servers added: {n}.", n=n) + (" " + tr("Not understood: {items}", items="; ".join(errors[:3]))
                                                     if errors else "")
        self.add_msg.setText(msg)
        self.add_msg.show()
        self.fill()

    def _selected_ids(self) -> list[str]:
        ids = []
        for idx in self.table.selectionModel().selectedRows():
            sid = self.table.item(idx.row(), 0).data(Qt.ItemDataRole.UserRole)
            if sid not in ids:
                ids.append(sid)
        return ids

    def on_via(self, on: bool) -> None:
        with self.engine.cfg_lock:
            self.engine.cfg["servers_via_adapter"] = on
            self.engine._servers_changed()

    def on_use(self) -> None:
        ids = self._selected_ids()
        if ids:
            self.engine.set_vpn_server(ids[0])
            self.fill()

    def on_auto(self) -> None:
        cc = self.country.currentData()
        self.engine.set_vpn_server(f"auto:{cc}" if cc else "auto")
        self.fill()

    def on_check(self) -> None:
        self.engine.check_servers([s["id"] for s in self.visible()])
        self.tick()

    def on_delete(self) -> None:
        ids = self._selected_ids()
        if ids and confirm(self, tr("Delete"), tr("Delete the selected servers: {n}?", n=len(ids)), yes=tr("Delete"),
                           danger=True):
            self.engine.remove_servers(ids)
            self.fill()

    def _sub_id(self) -> str | None:
        it = self.subs.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def on_update_subs(self) -> None:
        sid = self._sub_id()
        self.engine.refresh_subscriptions([sid] if sid else None)
        self.tick()

    def on_delete_sub(self) -> None:
        sid = self._sub_id()
        if sid and confirm(self, tr("Delete"), tr("Delete the subscription and its servers?"), yes=tr("Delete"),
                           danger=True):
            self.engine.remove_subscription(sid)
            self.fill()
