"""Sharing your server: friends get their own Shadowsocks key and port, no SSH, no root.

The owner manages it over SSH from XmelTunnel. On the server:
  /etc/xmeltunnel/users.json   the list (names, keys, ports, limits, traffic totals)
  /etc/xmeltunnel/ss.json      sing-box: the owner's inbound + one inbound per active friend
  /etc/xmeltunnel/counters.nft per-port traffic counters (loaded again when the service starts)

Guests cannot reach the server itself or private addresses (tinyproxy and the rest stay closed), and
mail ports are blocked so nobody sends spam from your IP. Traffic is counted by nft per port; totals
are added to users.json every time the list is applied, because counters restart with the table.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import time
import urllib.parse

from xmeltunnel.i18n import tr

METHOD = "2022-blake3-aes-128-gcm"
FIRST_PORT = 8389
LAST_PORT = 8488
BLOCKED_PORTS = [25, 465, 587]


def new_key() -> str:
    return base64.b64encode(secrets.token_bytes(16)).decode()


def new_user(name: str, users: list[dict], days: int = 0, quota_gb: float = 0) -> dict:
    taken = {u["port"] for u in users}
    port = next((p for p in range(FIRST_PORT, LAST_PORT + 1) if p not in taken), None)
    if port is None:
        raise ValueError(tr("No free ports left (100 people at most)."))
    return {"id": secrets.token_hex(4), "name": name.strip() or tr("Guest"), "port": port, "key": new_key(),
            "created": int(time.time()), "expires": int(time.time() + days * 86400) if days else 0,
            "quota_gb": float(quota_gb or 0), "paused": False, "reason": "",
            "up": 0, "down": 0, "last_seen": 0}


def invite_link(user: dict, host: str) -> str:
    userinfo = base64.urlsafe_b64encode(f"{METHOD}:{user['key']}".encode()).decode().rstrip("=")
    return f"ss://{userinfo}@{host}:{user['port']}#{urllib.parse.quote(user['name'])}"


def server_config(owner_port: int, owner_key: str, users: list[dict]) -> dict:
    inbounds = [{"type": "shadowsocks", "tag": "owner", "listen": "::", "listen_port": int(owner_port),
                 "method": METHOD, "password": owner_key}]
    for u in active(users):
        inbounds.append({"type": "shadowsocks", "tag": f"u-{u['id']}", "listen": "::", "listen_port": u["port"],
                         "method": METHOD, "password": u["key"]})
    guests = [i["tag"] for i in inbounds[1:]]
    rules = []
    if guests:
        rules += [{"inbound": guests, "ip_is_private": True, "outbound": "block"},
                  {"inbound": guests, "port": BLOCKED_PORTS, "outbound": "block"}]
    return {"log": {"level": "warn"}, "inbounds": inbounds,
            "outbounds": [{"type": "direct", "tag": "direct"}, {"type": "block", "tag": "block"}],
            "route": {"rules": rules, "final": "direct"}}


def active(users: list[dict]) -> list[dict]:
    return [u for u in users if not u.get("paused")]


def counters_nft(users: list[dict]) -> str:
    lines = ["table inet xmeltunnel {"]
    for u in users:
        lines += [f"  counter u_{u['id']}_up {{}}", f"  counter u_{u['id']}_down {{}}"]
    lines.append("  chain input { type filter hook input priority -10; policy accept;")
    for u in users:
        lines.append(f"    meta l4proto {{ tcp, udp }} th dport {u['port']} counter name u_{u['id']}_up")
    lines.append("  }")
    lines.append("  chain output { type filter hook output priority -10; policy accept;")
    for u in users:
        lines.append(f"    meta l4proto {{ tcp, udp }} th sport {u['port']} counter name u_{u['id']}_down")
    lines += ["  }", "}"]
    return "\n".join(lines) + "\n"


# ---------- reading the server's answer ----------

def parse_counters(nft_json: str) -> dict[str, dict]:
    """nft -j list counters -> {user id: {"up": bytes, "down": bytes}}."""
    out: dict[str, dict] = {}
    try:
        data = json.loads(nft_json or "{}")
    except ValueError:
        return out
    for item in data.get("nftables", []):
        c = item.get("counter")
        if not c:
            continue
        m = re.fullmatch(r"u_([0-9a-f]+)_(up|down)", c.get("name", ""))
        if m:
            out.setdefault(m.group(1), {"up": 0, "down": 0})[m.group(2)] = int(c.get("bytes", 0))
    return out


def online_ports(ss_output: str) -> dict[int, int]:
    """`ss -Htn state established` -> {local port: connections}."""
    out: dict[int, int] = {}
    for line in ss_output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            m = re.search(r":(\d+)$", parts[-2])  # local address: last but one, with or without a state column
            if m:
                port = int(m.group(1))
                out[port] = out.get(port, 0) + 1
    return out


def merge_traffic(users: list[dict], counters: dict[str, dict], online: dict[int, int]) -> None:
    """Fold the live counters into the totals (the counters restart when the list is applied)."""
    now = int(time.time())
    for u in users:
        c = counters.get(u["id"], {})
        u["live_up"], u["live_down"] = c.get("up", 0), c.get("down", 0)
        u["online"] = online.get(u["port"], 0)
        if u["online"]:
            u["last_seen"] = now


def total(u: dict) -> int:
    return u.get("up", 0) + u.get("down", 0) + u.get("live_up", 0) + u.get("live_down", 0)


def enforce_limits(users: list[dict]) -> list[str]:
    """Pause those whose time or traffic ran out. Returns names that were paused now."""
    paused = []
    for u in users:
        if u.get("paused"):
            continue
        if u.get("expires") and time.time() > u["expires"]:
            u.update(paused=True, reason="expired")
            paused.append(u["name"])
        elif u.get("quota_gb") and total(u) >= u["quota_gb"] * 2**30:
            u.update(paused=True, reason="quota")
            paused.append(u["name"])
    return paused


# ---------- talking to the server ----------

FETCH_SCRIPT = r"""
[ "$(id -u)" = 0 ] && SUDO= || SUDO=sudo
echo XT_USERS_BEGIN
$SUDO cat /etc/xmeltunnel/users.json 2>/dev/null || echo '[]'
echo XT_USERS_END
echo XT_NFT_BEGIN
$SUDO nft -j list counters table inet xmeltunnel 2>/dev/null || echo '{}'
echo XT_NFT_END
echo XT_SS_BEGIN
ss -Htn state established 2>/dev/null
echo XT_SS_END
[ -x /usr/local/bin/sing-box ] && echo XT_HAVE_SINGBOX
"""


def _between(text: str, tag: str) -> str:
    m = re.search(rf"XT_{tag}_BEGIN\n(.*?)XT_{tag}_END", text, re.S)
    return m.group(1).strip() if m else ""


def fetch(cfg: dict) -> dict:
    """{"users": [...], "have_singbox": bool} with live traffic and who is online."""
    from xmeltunnel.server_setup import _last_error, _run

    r = _run(cfg, FETCH_SCRIPT, 60)
    if "XT_USERS_BEGIN" not in (r.stdout or ""):
        raise RuntimeError(_last_error(r))
    try:
        users = json.loads(_between(r.stdout, "USERS") or "[]")
    except ValueError:
        users = []
    merge_traffic(users, parse_counters(_between(r.stdout, "NFT")), online_ports(_between(r.stdout, "SS")))
    return {"users": users, "have_singbox": "XT_HAVE_SINGBOX" in r.stdout}


def apply(cfg: dict, users: list[dict]) -> None:
    """Write the list and the configs, reload counters and sing-box. Live traffic is folded into totals first."""
    from xmeltunnel.server_setup import _last_error, _run

    for u in users:  # the counters restart now: keep what they counted
        u["up"] = u.get("up", 0) + u.pop("live_up", 0)
        u["down"] = u.get("down", 0) + u.pop("live_down", 0)
        u.pop("online", None)
    files = {
        "/etc/xmeltunnel/users.json": json.dumps(users, ensure_ascii=False, indent=1),
        "/etc/xmeltunnel/ss.json": json.dumps(server_config(cfg["ss_port"], cfg["ss_key"], users), indent=1),
        "/etc/xmeltunnel/counters.nft": counters_nft(users),
    }
    writes = "".join(f"$SUDO tee {path} >/dev/null <<'XT_EOF'\n{body}\nXT_EOF\n" for path, body in files.items())
    script = r"""
set -e
[ "$(id -u)" = 0 ] && SUDO= || SUDO=sudo
$SUDO mkdir -p /etc/xmeltunnel
""" + writes + r"""
$SUDO chmod 600 /etc/xmeltunnel/users.json /etc/xmeltunnel/ss.json
/usr/local/bin/sing-box check -c /etc/xmeltunnel/ss.json
$SUDO nft delete table inet xmeltunnel 2>/dev/null || true
$SUDO nft -f /etc/xmeltunnel/counters.nft
UNIT=/etc/systemd/system/xmeltunnel-ss.service
if [ -f $UNIT ] && ! grep -q counters.nft $UNIT; then
  $SUDO sed -i 's|^ExecStart=|ExecStartPre=-/bin/sh -c "nft delete table inet xmeltunnel 2>/dev/null; nft -f /etc/xmeltunnel/counters.nft"\nExecStart=|' $UNIT
  $SUDO systemctl daemon-reload
fi
if command -v ufw >/dev/null && $SUDO ufw status 2>/dev/null | grep -q "Status: active"; then
  $SUDO ufw status | grep -q "PORTS_RANGE" || { $SUDO ufw allow PORTS_RANGE/tcp >/dev/null; $SUDO ufw allow PORTS_RANGE/udp >/dev/null; }
elif command -v firewall-cmd >/dev/null && $SUDO firewall-cmd --state >/dev/null 2>&1; then
  $SUDO firewall-cmd -q --permanent --add-port=PORTS_DASH/tcp --add-port=PORTS_DASH/udp && $SUDO firewall-cmd -q --reload
fi
$SUDO systemctl restart xmeltunnel-ss
sleep 1
systemctl is-active -q xmeltunnel-ss && echo XT_APPLIED
"""
    script = script.replace("PORTS_RANGE", f"{FIRST_PORT}:{LAST_PORT}").replace("PORTS_DASH", f"{FIRST_PORT}-{LAST_PORT}")
    r = _run(cfg, script, 120, {"@@": "@@"})
    if "XT_APPLIED" not in (r.stdout or ""):
        raise RuntimeError(_last_error(r))


def fmt_bytes(n: int) -> str:
    for unit, size in ((tr("GB"), 2**30), (tr("MB"), 2**20), (tr("KB"), 2**10)):
        if n >= size:
            return f"{n / size:.1f} {unit}"
    return f"{n} {tr('B')}"
