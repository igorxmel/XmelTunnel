"""«Connections»: what goes where right now, like a task manager. sing-box's live connections (clash API)
grouped by program: each program with its total traffic and speed, under it the sites it talks to, their
protocol, path and the profile that sent them there. Any row can be put into a profile or closed."""

from __future__ import annotations

import ipaddress
import ntpath
import re
import time

from PyQt6.QtCore import QFileInfo, Qt, QTimer
from PyQt6.QtGui import QColor, QCursor, QIcon
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QFileIconProvider, QHBoxLayout, QHeaderView, QLabel,
                             QLineEdit, QMenu, QPushButton, QSizePolicy, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from xmeltunnel import core, routing
from xmeltunnel.i18n import tr
from xmeltunnel.sharing import fmt_bytes
from xmeltunnel.ui import theme
from xmeltunnel.ui.dialogs import TARGET_SHORT, run_bg
from xmeltunnel.ui.frameless import FramelessDialog

COLS = ("Program / where to", "Protocol", "Path", "Why", "Traffic", "Speed")
C_NAME, C_PROTO, C_PATH, C_WHY, C_TRAFFIC, C_SPEED = range(len(COLS))
SECOND_LEVEL = {"co", "com", "net", "org", "gov", "edu", "ac", "msk", "spb"}
PORTS = {80: "http", 443: "https", 53: "dns", 853: "dot", 3478: "stun", 5222: "xmpp", 993: "imaps", 22: "ssh"}
SYSTEM = "~system"  # connections whose program sing-box could not find


def path_of(conn: dict) -> str:
    """direct, vpn or server: the outbound a connection left by."""
    chain = conn.get("chains") or []
    first = chain[0] if chain else ""
    if first.startswith("srv-") or "vpn" in chain:
        return "vpn"
    return first if first in ("direct", "server") else (first or "?")


def site_of(conn: dict) -> str:
    m = conn.get("metadata") or {}
    return (m.get("host") or m.get("destinationIP") or "").rstrip(".").lower()


def program_of(conn: dict) -> str:
    return ntpath.basename((conn.get("metadata") or {}).get("processPath") or "")


def protocol_of(conn: dict) -> str:
    """«TCP · https», «UDP · quic»: the transport and what the port usually is."""
    m = conn.get("metadata") or {}
    net = (m.get("network") or "").lower()
    try:
        port = int(m.get("destinationPort") or 0)
    except ValueError:
        port = 0
    name = "quic" if net == "udp" and port == 443 else PORTS.get(port, str(port) if port else "")
    return " · ".join(x for x in (net.upper(), name) if x)


def base_domain(host: str) -> str:
    """www.youtube.com -> youtube.com, news.bbc.co.uk -> bbc.co.uk (enough for a profile line)."""
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in SECOND_LEVEL and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def why_of(conn: dict, cfg: dict) -> str:
    """The profile (or list, or «everything else») that sent a connection its way, in the user's words.
    sing-box only says which rule matched; the profile is found again by what that rule holds."""
    rule = conn.get("rule") or ""
    if not rule or rule.startswith("final"):
        return tr("Everything else")
    if "inbound=" in rule:
        return tr("XmelTunnel's own check")
    if "ip_is_private" in rule:
        return tr("Local network")
    path = path_of(conn)
    enabled = [p for p in cfg.get("profiles") or [] if p.get("enabled") and p.get("target") == path]
    tags = re.findall(r"geo(?:site|ip)-[\w-]+", rule)
    if tags:
        lids = [lid for lid in routing.LISTS if any(t for t, _ in routing.list_rule_sets(lid) if t in tags)]
        for p in enabled:
            if set(routing.parse_list(p["entries"])["lists"]) & set(lids):
                return p["name"]
        return ", ".join(tr(routing.LISTS[lid]["title"]) for lid in lids) or rule
    host, prog = site_of(conn), program_of(conn).lower()
    proc_path = ((conn.get("metadata") or {}).get("processPath") or "").lower()
    for p in enabled:
        parsed = routing.parse_list(p["entries"])
        if any(host == d or host.endswith("." + d) for d in parsed["domains"]) \
                or prog in (x.lower() for x in parsed["procs"]) \
                or any(proc_path.startswith(f.lower()) for f in parsed["folders"]):
            return p["name"]
        if is_ip(host) and any(ipaddress.ip_address(host) in ipaddress.ip_network(c) for c in parsed["cidrs"]):
            return p["name"]
    return rule


def speed_text(down: float, up: float) -> str:
    if down < 1 and up < 1:
        return "—"
    return f"↓ {fmt_bytes(int(down))}/{tr('s')}  ↑ {fmt_bytes(int(up))}/{tr('s')}"


def traffic_text(down: int, up: int) -> str:
    return f"↓ {fmt_bytes(down)}  ↑ {fmt_bytes(up)}"


class Item(QTreeWidgetItem):
    """Sorts by hidden keys (bytes, speed), not by the shown text."""

    def __init__(self):
        super().__init__()
        self.keys: dict[int, object] = {}

    def __lt__(self, other):  # noqa: D105
        col = self.treeWidget().sortColumn() if self.treeWidget() else 0
        a, b = self.keys.get(col, self.text(col).lower()), getattr(other, "keys", {}).get(col, other.text(col).lower())
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


class ConnectionsDialog(FramelessDialog):
    def __init__(self, parent, engine: core.Engine):
        super().__init__(parent, tr("Connections"))
        self.engine = engine
        self.win = parent
        self.setMinimumSize(920, 560)
        self.resize(1180, 720)
        self._prev: dict[str, tuple[float, int, int]] = {}  # id -> (when, up, down): for the speed
        self._speed: dict[str, tuple[float, float]] = {}
        self._conns: list[dict] = []
        self._groups: dict[str, Item] = {}
        self._rows: dict[str, Item] = {}
        self._icons: dict[str, QIcon] = {}
        self._icon_provider = QFileIconProvider()
        self._busy = False
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(10)
        note = QLabel(tr("What goes where right now, program by program. If something goes the wrong way, select it "
                         "and add it to a profile."), objectName="note")
        note.setWordWrap(True)
        lay.addWidget(note)

        flt = QHBoxLayout()
        flt.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search by program or site"))
        self.search.textChanged.connect(self.fill)
        flt.addWidget(self.search, 2)
        self.path = QComboBox()
        self.path.addItem(tr("All paths"), "")
        for key, title in TARGET_SHORT:
            if key != "block":  # refused connections never show up here
                self.path.addItem(tr(title), key)
        self.path.currentIndexChanged.connect(self.fill)
        flt.addWidget(self.path, 1)
        b_open = QPushButton(tr("Expand all"), objectName="small")
        b_open.clicked.connect(lambda: self.tree.expandAll())
        flt.addWidget(b_open)
        b_shut = QPushButton(tr("Collapse all"), objectName="small")
        b_shut.clicked.connect(lambda: self.tree.collapseAll())
        flt.addWidget(b_shut)
        lay.addLayout(flt)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(COLS))
        self.tree.setHeaderLabels([tr(c) for c in COLS])
        self.tree.headerItem().setToolTip(C_WHY, tr("The profile or list that sent it this way."))
        self.tree.headerItem().setToolTip(C_TRAFFIC, tr("↓ received, ↑ sent while the connection is open."))
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSortingEnabled(True)
        self.tree.setAnimated(False)
        h = self.tree.header()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(C_NAME, QHeaderView.ResizeMode.Stretch)
        for col, w in ((C_PROTO, 110), (C_PATH, 90), (C_WHY, 190), (C_TRAFFIC, 170), (C_SPEED, 190)):
            self.tree.setColumnWidth(col, w)
        self.tree.sortByColumn(C_SPEED, Qt.SortOrder.DescendingOrder)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(lambda _: self.on_add())
        self.tree.itemSelectionChanged.connect(self.show_buttons)
        lay.addWidget(self.tree, 1)

        self.status = QLabel(objectName="note")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        self.b_close_conn = QPushButton(tr("Close connection"), objectName="small")
        self.b_close_conn.setToolTip(tr("The program opens it again, by the current profiles."))
        self.b_close_conn.clicked.connect(self.on_close_conn)
        row.addWidget(self.b_close_conn)
        row.addStretch()
        self.b_add = QPushButton(tr("Add to a profile…"), objectName="primary")
        self.b_add.clicked.connect(self.on_add)
        row.addWidget(self.b_add)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        for w in (self.b_close_conn, self.b_add, close):
            w.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        lay.addLayout(row)

        self.timer = QTimer(self, interval=1500)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.show_buttons()
        self.poll()

    # --- data ---

    def poll(self) -> None:
        if self._busy:
            return
        self._busy = True

        def done(res):
            self._busy = False
            if isinstance(res, list):
                self.take(res)

        run_bg(self, self.engine.connections, done)

    def take(self, conns: list[dict]) -> None:
        now = time.monotonic()
        speed, prev = {}, {}
        for c in conns:
            cid, up, down = c.get("id", ""), int(c.get("upload", 0)), int(c.get("download", 0))
            if cid in self._prev:
                t, u0, d0 = self._prev[cid]
                dt = max(now - t, 0.1)
                speed[cid] = (max(down - d0, 0) / dt, max(up - u0, 0) / dt)
            prev[cid] = (now, up, down)
        self._prev, self._speed, self._conns = prev, speed, conns
        self.fill()

    def visible(self) -> list[dict]:
        q = self.search.text().strip().lower()
        want = self.path.currentData()
        return [c for c in self._conns if (not want or path_of(c) == want)
                and (not q or q in site_of(c) or q in program_of(c).lower())]

    def icon_for(self, path: str) -> QIcon:
        if path not in self._icons:
            self._icons[path] = self._icon_provider.icon(QFileInfo(path)) if path else QIcon()
        return self._icons[path]

    def fill(self) -> None:
        cfg = self.engine.cfg
        names = dict((k, tr(t)) for k, t in TARGET_SHORT)
        colors = {k: QColor(theme.C["t_" + k]) for k, _ in TARGET_SHORT}
        rows = self.visible()
        groups: dict[str, list[dict]] = {}
        for c in rows:
            groups.setdefault(program_of(c).lower() or SYSTEM, []).append(c)
        self.tree.setSortingEnabled(False)
        # drop what is gone; the rest is updated in place, so expanded programs and the selection stay
        for key in [k for k in self._groups if k not in groups]:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(self._groups.pop(key)))
        alive = {c.get("id", "") for c in rows}
        for cid in [i for i in self._rows if i not in alive]:
            it = self._rows.pop(cid)
            if it.parent():
                it.parent().removeChild(it)
        total_down = total_up = 0.0
        for key, conns in groups.items():
            g = self._groups.get(key)
            if g is None:
                g = self._groups[key] = Item()
                g.setData(0, Qt.ItemDataRole.UserRole, ("group", key))
                f = g.font(C_NAME)
                f.setBold(True)
                g.setFont(C_NAME, f)
                self.tree.addTopLevelItem(g)
            proc_path = (conns[0].get("metadata") or {}).get("processPath") or ""
            title = program_of(conns[0]) or tr("System and unknown")
            g.setText(C_NAME, f"{title}  ({len(conns)})")
            g.setIcon(C_NAME, self.icon_for(proc_path))
            g.setToolTip(C_NAME, proc_path or tr("sing-box could not tell which program this is (often Windows itself)."))
            g.keys[C_NAME] = title.lower()
            paths = sorted({path_of(c) for c in conns})
            g.setText(C_PATH, ", ".join(names.get(p, p) for p in paths))
            g.setForeground(C_PATH, colors.get(paths[0], QColor(theme.C["text"])) if len(paths) == 1
                            else QColor(theme.C["text_dim"]))
            whys = sorted({why_of(c, cfg) for c in conns})
            g.setText(C_WHY, whys[0] if len(whys) == 1 else tr("{n} reasons", n=len(whys)))
            g.setToolTip(C_WHY, "\n".join(whys))
            down = sum(int(c.get("download", 0)) for c in conns)
            up = sum(int(c.get("upload", 0)) for c in conns)
            s_down = sum(self._speed.get(c.get("id", ""), (0, 0))[0] for c in conns)
            s_up = sum(self._speed.get(c.get("id", ""), (0, 0))[1] for c in conns)
            total_down, total_up = total_down + s_down, total_up + s_up
            g.setText(C_TRAFFIC, traffic_text(down, up))
            g.keys[C_TRAFFIC] = down + up
            g.setText(C_SPEED, speed_text(s_down, s_up))
            g.keys[C_SPEED] = s_down + s_up
            g.keys[C_PROTO] = ""
            for c in conns:
                cid = c.get("id", "")
                it = self._rows.get(cid)
                if it is None:
                    it = self._rows[cid] = Item()
                    it.setData(0, Qt.ItemDataRole.UserRole, ("conn", cid))
                    g.addChild(it)
                meta = c.get("metadata") or {}
                site = site_of(c)
                port = meta.get("destinationPort")
                it.setText(C_NAME, f"{site}:{port}" if port and is_ip(site) else site or "—")
                it.setToolTip(C_NAME, f"→ {meta.get('destinationIP') or site}:{port}")
                it.keys[C_NAME] = site
                it.setText(C_PROTO, protocol_of(c))
                path = path_of(c)
                it.setText(C_PATH, names.get(path, path))
                it.setForeground(C_PATH, colors.get(path, QColor(theme.C["text"])))
                it.setText(C_WHY, why_of(c, cfg))
                it.setToolTip(C_WHY, c.get("rule") or "")
                d, u = int(c.get("download", 0)), int(c.get("upload", 0))
                it.setText(C_TRAFFIC, traffic_text(d, u))
                it.keys[C_TRAFFIC] = d + u
                sd, su = self._speed.get(cid, (0.0, 0.0))
                it.setText(C_SPEED, speed_text(sd, su))
                it.keys[C_SPEED] = sd + su
        self.tree.setSortingEnabled(True)
        running = self.engine.state["route"]["status"] == "running"
        self.status.setText(tr("Programs: {p} · connections: {n} · ↓ {down}/s ↑ {up}/s", p=len(groups),
                               n=len(self._conns), down=fmt_bytes(int(total_down)), up=fmt_bytes(int(total_up)))
                            if running else tr("The VPN is not connected: nothing to show."))
        self.show_buttons()

    def selected(self) -> tuple[str, list[dict]]:
        """("group" | "conn" | "", the connections of the selected row)."""
        items = self.tree.selectedItems()
        if not items:
            return "", []
        kind, key = items[0].data(0, Qt.ItemDataRole.UserRole) or ("", "")
        if kind == "conn":
            return kind, [c for c in self._conns if c.get("id") == key]
        return kind, [c for c in self._conns if (program_of(c).lower() or SYSTEM) == key]

    def show_buttons(self) -> None:
        kind, conns = self.selected()
        self.b_add.setEnabled(bool(conns) and not (kind == "group" and not program_of(conns[0])))
        self.b_close_conn.setEnabled(bool(conns))
        self.b_close_conn.setText(tr("Close all of the program") if kind == "group" else tr("Close connection"))

    # --- actions ---

    def on_close_conn(self) -> None:
        _, conns = self.selected()
        ids = [c["id"] for c in conns if c.get("id")]

        def close_all():
            for cid in ids:
                self.engine.close_connection(cid)

        if ids:
            run_bg(self, close_all, lambda _: self.poll())

    def lines_for(self, kind: str, conns: list[dict]) -> list[tuple[str, str]]:
        """(menu title, profile line) of what the selection can be added as."""
        out = []
        prog = program_of(conns[0]) if conns else ""
        if kind == "conn":
            site = site_of(conns[0])
            if site and is_ip(site):
                out.append((tr("Address {ip}", ip=site), site))
            elif site:
                base = base_domain(site)
                out.append((tr("Site {site} (with subdomains)", site=base), base))
                if base != site:
                    out.append((tr("Only {site}", site=site), site))
        if prog:
            out.append((tr("Program {name} (all its traffic)", name=prog), prog))
        return out

    def on_add(self) -> None:
        kind, conns = self.selected()
        lines = self.lines_for(kind, conns) if conns else []
        if not lines:
            return
        names = dict((k, tr(t)) for k, t in TARGET_SHORT)
        menu = QMenu(self)
        for title, line in lines:
            sub = menu.addMenu(title)
            for p in self.engine.cfg["profiles"]:
                label = f"{p['name']}  →  {names.get(p['target'], p['target'])}"
                if not p.get("enabled"):
                    label += "  (" + tr("off") + ")"
                sub.addAction(label).triggered.connect(lambda _=False, pid=p["id"], ln=line: self.add_to(pid, ln))
            sub.addSeparator()
            sub.addAction(tr("New profile…")).triggered.connect(lambda _=False, ln=line: self.new_profile(ln))
        menu.exec(QCursor.pos())

    def add_to(self, pid: str, line: str) -> None:
        p = next((x for x in self.engine.cfg["profiles"] if x["id"] == pid), None)
        if not p:
            return
        if self.engine.add_entry(pid, line):
            self.status.setText(tr("Added {line} to «{name}». Open connections keep their way until they reconnect.",
                                   line=line, name=p["name"]))
        else:
            self.status.setText(tr("{line} is already in «{name}».", line=line, name=p["name"]))
        self.win.refresh()

    def new_profile(self, line: str) -> None:
        from xmeltunnel.ui.dialogs import ProfileDialog

        d = ProfileDialog(self, self.engine)
        d.name.setText(line)
        d.entries.setPlainText(line)
        d.exec()
        self.win.refresh()

    def done(self, r):  # noqa: D102
        self.timer.stop()
        super().done(r)
