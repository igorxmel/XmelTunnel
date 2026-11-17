"""Routing mode: a whitelist for the whole PC on top of your VPN.

Everything not listed goes where route_default says (direct by default). Enabled profiles say the rest:
  target vpn     -> through the VPN adapter (Happ, v2rayN, WireGuard… must be on, in TUN mode)
  target server  -> Shadowsocks to your server (sent through the VPN when the server needs it)
  target direct  -> your normal connection

It runs sing-box with a TUN adapter. That needs admin rights, so a small helper is started elevated
(one UAC prompt): it runs sing-box, restarts it when the config changes and stops it when XmelTunnel
exits or asks it to. sing-box itself is downloaded once from its official GitHub release and checked
against a pinned SHA-256 before every start.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import zipfile

SING_BOX_VERSION = "1.14.4"
SING_BOX_URL = (f"https://github.com/SagerNet/sing-box/releases/download/v{SING_BOX_VERSION}/"
                f"sing-box-{SING_BOX_VERSION}-windows-amd64.zip")
SING_BOX_ZIP_SHA256 = "99185d75d314a07dbba4a130c8ad986cbeb629a07927975636b341ca61f991df"
SING_BOX_EXE_SHA256 = "8f30682ee198855440d2a7fe070d5d3653793b2d01bb8c85eea88f93bbe7c8b9"
# NaiveProxy servers need Chromium's network stack; it comes in the same official archive
CRONET_SHA256 = "3217c6260fbca5f16072e0b79735742f40109a63bb0ff88fd6b96dd6b54a2928"

TUN_NAME = "XmelTunnel"  # the adapter name Windows (and other VPN-aware apps) show
TUN_ADDRESS = "172.31.250.1/30"  # not sing-box's default 172.19.0.1: other VPN clients often take that one
TUN_ADDRESS6 = "fdfe:dcba:9876::1/126"
CHECK_PORTS = {"direct": 28891, "vpn": 28892, "server": 28893}
STATS_PORT = 28890  # sing-box's clash API, local only: live connections with their bytes (traffic statistics)
SS_METHOD = "2022-blake3-aes-128-gcm"
DOH_SERVER = "1.1.1.1"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---------- paths ----------

def route_dir(data: str) -> str:
    path = os.path.join(data, "routing")
    os.makedirs(path, exist_ok=True)
    return path


def sing_box_path(data: str) -> str:
    return os.path.join(route_dir(data), "sing-box.exe")


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_ok(path: str, sha: str) -> bool:
    try:
        return os.path.isfile(path) and file_sha256(path) == sha
    except OSError:
        return False


def _files(data: str) -> dict[str, tuple[str, str]]:
    """{name in the archive: (where it goes, its hash)}."""
    return {"sing-box.exe": (sing_box_path(data), SING_BOX_EXE_SHA256),
            "libcronet.dll": (os.path.join(route_dir(data), "libcronet.dll"), CRONET_SHA256)}


def sing_box_ok(data: str) -> bool:
    return all(_file_ok(p, sha) for p, sha in _files(data).values())


def download_sing_box(data: str, progress=None) -> None:
    """Fetch the official Windows build, check the hashes, keep sing-box.exe and libcronet.dll (Naive)."""
    if sing_box_ok(data):
        return
    folder = route_dir(data)
    tmp = os.path.join(folder, "download.zip")
    req = urllib.request.Request(SING_BOX_URL, headers={"User-Agent": "XmelTunnel"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 16):
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done * 100 // total)
    try:
        if file_sha256(tmp) != SING_BOX_ZIP_SHA256:
            raise RuntimeError("sing-box download: checksum mismatch")
        with zipfile.ZipFile(tmp) as z:
            for base, (path, sha) in _files(data).items():
                if _file_ok(path, sha):
                    continue  # only what is missing: a running sing-box.exe cannot be replaced
                name = next(n for n in z.namelist() if n.endswith("/" + base))
                with z.open(name) as src, open(path + ".tmp", "wb") as dst:
                    dst.write(src.read())
                os.replace(path + ".tmp", path)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if not sing_box_ok(data):
        raise RuntimeError("sing-box files: checksum mismatch")


# ---------- lists and config ----------

# Ready-made lists (sing-box rule sets), rebuilt every day by runetfreedom/russia-v2ray-rules-dat from
# antifilter, re:filter, v2fly and others. A profile holds one as a line «list:<id>».
LISTS_URL = "https://raw.githubusercontent.com/runetfreedom/russia-v2ray-rules-dat/release/sing-box/"
LISTS = {
    "ru-blocked": {"title": "Blocked in Russia", "geosite": "ru-blocked", "geoip": "ru-blocked",
                   "note": "Sites and addresses blocked or slowed down in Russia, updated every day."},
    "ru-inside": {"title": "Open only from Russia", "geosite": "ru-available-only-inside",
                  "note": "Russian services that refuse foreign addresses: banks, Gosuslugi and others."},
    "ru": {"title": "Russian sites", "geosite": "category-ru", "geoip": "ru",
           "note": "Sites in .ru, .рф and other Russian zones and Russian IP addresses."},
    "ads": {"title": "Ads and trackers", "geosite": "category-ads-all",
            "note": "Ad and tracking domains (v2fly category-ads-all)."},
    "win-spy": {"title": "Windows telemetry", "geosite": "win-spy",
                "note": "Microsoft's telemetry servers."},
}
LISTS_MAX_AGE = 24 * 3600


def lists_dir(data: str) -> str:
    path = os.path.join(route_dir(data), "lists")
    os.makedirs(path, exist_ok=True)
    return path


def list_rule_sets(lid: str) -> list[tuple[str, str]]:
    """(tag, url path) of the rule sets behind a list: its domains (geosite) and its addresses (geoip)."""
    meta = LISTS.get(lid) or {}
    out = []
    for kind in ("geosite", "geoip"):
        if meta.get(kind):
            tag = f"{kind}-{meta[kind]}"
            out.append((tag, f"rule-set-{kind}/{tag}.srs"))
    return out


def lists_ready(data: str, ids) -> dict[str, str]:
    """{rule set tag: file} of the lists already downloaded. Missing ones are left out of the config."""
    out = {}
    for lid in ids:
        for tag, _ in list_rule_sets(lid):
            path = os.path.join(lists_dir(data), tag + ".srs")
            if os.path.isfile(path):
                out[tag] = path
    return out


def download_lists(data: str, ids, proxy: str | None = None, max_age: int = LISTS_MAX_AGE,
                   timeout: float = 30) -> list[str]:
    """Fetch the lists older than max_age. Returns errors. Directly first, then through proxy (the VPN path),
    since raw.githubusercontent.com is slow or cut in some places."""
    errors = []
    for lid in ids:
        for tag, rel in list_rule_sets(lid):
            path = os.path.join(lists_dir(data), tag + ".srs")
            try:
                if time.time() - os.path.getmtime(path) < max_age:
                    continue
            except OSError:
                pass
            last = None
            for via in [None] + ([proxy] if proxy else []):
                handlers = [urllib.request.ProxyHandler({"http": via, "https": via} if via else {})]
                try:
                    req = urllib.request.Request(LISTS_URL + rel, headers={"User-Agent": "XmelTunnel"})
                    with urllib.request.build_opener(*handlers).open(req, timeout=timeout) as r:
                        body = r.read(64 << 20)
                    if body[:3] != b"SRS":
                        raise ValueError("not a sing-box rule set")
                    with open(path + ".tmp", "wb") as f:
                        f.write(body)
                    os.replace(path + ".tmp", path)  # sing-box reloads a local rule set when its file changes
                    last = None
                    break
                except Exception as e:  # noqa: BLE001
                    last = e
            if last:
                errors.append(f"{tag}: {last!r}")
    return errors


def used_lists(cfg: dict) -> list[str]:
    """Ids of the lists in enabled profiles."""
    out = []
    for p in cfg.get("profiles") or []:
        if p.get("enabled"):
            for lid in parse_list(p.get("entries", []))["lists"]:
                if lid not in out:
                    out.append(lid)
    return out


# DNS. Direct names go by DNS over HTTPS (VPN clients block port 53 outside their adapter); names that
# leave through the VPN or your server are resolved on the far side over plain DNS inside the tunnel.
DNS_PRESETS = {
    "cloudflare": ("Cloudflare", "1.1.1.1"),
    "google": ("Google", "8.8.8.8"),
    "quad9": ("Quad9", "9.9.9.9"),
    "adguard": ("AdGuard", "94.140.14.14"),
}


def doh_server(value: str) -> dict:
    """«cloudflare» or «https://dns.example/dns-query» -> sing-box https server fields."""
    if value in DNS_PRESETS:
        return {"server": DNS_PRESETS[value][1]}
    m = re.match(r"^(?:https://)?([^/:]+)(?::(\d+))?(/.*)?$", value.strip())
    if not m:
        return {"server": DOH_SERVER}
    out = {"server": m.group(1)}
    if m.group(2):
        out["server_port"] = int(m.group(2))
    if m.group(3) and m.group(3) != "/dns-query":
        out["path"] = m.group(3)
    try:
        ipaddress.ip_address(m.group(1))
    except ValueError:
        out["domain_resolver"] = "dns-boot"  # a name needs an address first
    return out


def plain_dns(value: str) -> str:
    """«google» or «8.8.8.8» -> the address for DNS inside the tunnel."""
    if value in DNS_PRESETS:
        return DNS_PRESETS[value][1]
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return "1.1.1.1"


def doh_url(value: str) -> str:
    f = doh_server(value)
    return f"https://{f['server']}{':%d' % f['server_port'] if 'server_port' in f else ''}{f.get('path', '/dns-query')}"


def doh_works(value: str, proxy: str | None = None, timeout: float = 4) -> bool:
    """Does this DNS over HTTPS server answer at all? Any HTTP answer counts: some want HTTP/2 (Quad9)."""
    import base64
    import struct
    import urllib.error

    query = struct.pack(">HHHHHH", 0x5854, 0x0100, 1, 0, 0, 0) + b"\x07example\x03com\x00" + struct.pack(">HH", 1, 1)
    url = doh_url(value) + "?dns=" + base64.urlsafe_b64encode(query).decode().rstrip("=")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {}))
    try:
        with opener.open(urllib.request.Request(url, headers={"Accept": "application/dns-message"}), timeout=timeout) as r:
            return r.read(2) != b""
    except urllib.error.HTTPError:
        return True
    except Exception:  # noqa: BLE001
        return False


def parse_list(lines: list[str]) -> dict:
    """Lines -> {"procs", "folders", "domains", "cidrs", "lists", "bad"}. '#' starts a comment."""
    out = {"procs": [], "folders": [], "domains": [], "cidrs": [], "lists": [], "bad": []}
    for raw in lines:
        item = raw.split("#", 1)[0].strip()
        if not item:
            continue
        if item.lower().startswith("list:"):
            lid = item[5:].strip().lower()
            (out["lists"] if lid in LISTS else out["bad"]).append(lid if lid in LISTS else item)
            continue
        if "\\" in item or "%" in item or re.match(r"^[a-zA-Z]:/", item):
            path = os.path.expandvars(item).replace("/", "\\").rstrip("\\") + "\\"
            out["folders"].append(path)
        elif item.lower().endswith(".exe"):
            out["procs"].append(item)
        else:
            try:
                out["cidrs"].append(str(ipaddress.ip_network(item, strict=False)))
                continue
            except ValueError:
                pass
            d = item.lower().split("://")[-1].split("/")[0].lstrip("*.").strip(".")
            if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", d):
                out["domains"].append(d)
            else:
                out["bad"].append(item)
    return out


def _tags(parsed: dict, ready: dict, kind: str | None = None) -> list[str]:
    """Rule set tags of the parsed lists that are downloaded; kind "geosite" = only their domain parts."""
    return [t for lid in parsed["lists"] for t, _ in list_rule_sets(lid)
            if t in ready and (kind is None or t.startswith(kind + "-"))]


def _rules(parsed: dict, outbound: str, ready: dict | None = None) -> list[dict]:
    """Route rules of one target. outbound «block» means the connection is refused."""
    then = {"action": "reject"} if outbound == "block" else {"outbound": outbound}
    rules = []
    if parsed["folders"]:
        rules.append({"process_path_regex": ["(?i)^" + re.escape(p) for p in parsed["folders"]], **then})
    if parsed["procs"]:
        rules.append({"process_name": parsed["procs"], **then})
    if parsed["domains"]:
        rules.append({"domain_suffix": parsed["domains"], **then})
    if parsed["cidrs"]:
        rules.append({"ip_cidr": parsed["cidrs"], **then})
    tags = _tags(parsed, ready or {})
    if tags:
        rules.append({"rule_set": tags, **then})
    return rules


URLTEST_URL = "http://cp.cloudflare.com/generate_204"


def chosen_servers(cfg: dict) -> list[dict]:
    """Servers the VPN path uses: the chosen one, or the candidates of «automatically»."""
    servers = cfg.get("servers") or []
    pick = cfg.get("vpn_server") or "auto"
    if not pick.startswith("auto"):
        return [s for s in servers if s["id"] == pick][:1]
    country = pick.split(":", 1)[1] if ":" in pick else ""
    checks = cfg.get("server_checks") or {}
    pool = [s for s in servers if not country or (checks.get(s["id"], {}).get("exit_loc") or s.get("country")) == country]
    working = [s for s in pool if (checks.get(s["id"]) or {}).get("ms")]
    return working or pool  # nothing checked yet: let sing-box test them all


def vpn_outbounds(cfg: dict, phys: str | None, adapter: str | None = None) -> list[dict]:
    """Outbounds for the built-in VPN client: one server tagged «vpn», or urltest picking the fastest."""
    if cfg.get("vpn_source") != "servers":
        return []
    chosen = chosen_servers(cfg)
    if not chosen:
        return []
    # «through my VPN client»: a friend whose access to your server is blocked reaches it over their own VPN
    via = adapter if cfg.get("servers_via_adapter") and adapter else phys
    dial = {"bind_interface": via} if via else {}
    if len(chosen) == 1 and not (cfg.get("vpn_server") or "auto").startswith("auto"):
        return [dict(chosen[0]["outbound"], tag="vpn", **dial)]
    out = [dict(s["outbound"], tag=f"srv-{s['id']}", **dial) for s in chosen[:200]]
    out.append({"type": "urltest", "tag": "vpn", "outbounds": [o["tag"] for o in out], "url": URLTEST_URL,
                "interval": "5m", "tolerance": 50})
    return out


def _server_link(cfg: dict) -> dict | None:
    if cfg.get("server_mode") != "link" or not cfg.get("server_link"):
        return None
    from xmeltunnel import servers

    try:
        return servers.parse_link(cfg["server_link"])
    except Exception:  # noqa: BLE001
        return None


def lists_by_target(cfg: dict) -> dict[str, list[str]]:
    """Entries of the enabled profiles, joined per target."""
    out = {"block": [], "direct": [], "server": [], "vpn": []}
    for p in cfg["profiles"]:
        if p.get("enabled") and p.get("target") in out:
            out[p["target"]] += p.get("entries", [])
    return out


def build_config(cfg: dict, server_ip: str, phys: str, vpn: str | None, ready: dict | None = None) -> dict:
    """sing-box config for the routing mode. Pure: tests call it directly.

    phys: the normal adapter (direct traffic), vpn: the VPN client's adapter or None.
    ready: {rule set tag: file} of the downloaded lists (lists_ready); the others are skipped for now.
    """
    ready = ready or {}
    lists = lists_by_target(cfg)
    via_vpn = parse_list(lists["vpn"])
    via_srv = parse_list(lists["server"])
    via_dir = parse_list(lists["direct"])
    via_blk = parse_list(lists["block"])
    default = cfg.get("route_default") or "direct"  # where everything not listed goes
    link = _server_link(cfg)
    has_server = bool(link) or (bool(cfg.get("ss_key")) and bool(server_ip))
    builtin = vpn_outbounds(cfg, phys, vpn)  # servers of XmelTunnel's own VPN client, if that is the source
    if builtin:
        vpn = vpn or "builtin"  # the VPN path exists even without a VPN client's adapter
    to_server = "vpn" if cfg["require_vpn"] and vpn else "direct"  # how sing-box itself reaches the server
    outbounds = [{"type": "direct", "tag": "direct", "bind_interface": phys}]
    if builtin:
        outbounds += builtin
    elif vpn:
        outbounds.append({"type": "direct", "tag": "vpn", "bind_interface": vpn})
    else:
        outbounds.append({"type": "block", "tag": "vpn"})  # never leak listed sites around the VPN
    if link:
        outbounds.append(dict(link["outbound"], tag="server",
                              **({"detour": "vpn"} if to_server == "vpn" and builtin else
                                 {"bind_interface": vpn if to_server == "vpn" else phys})))
    elif has_server:
        outbounds.append({"type": "shadowsocks", "tag": "server", "server": server_ip,
                          "server_port": int(cfg["ss_port"]), "method": SS_METHOD, "password": cfg["ss_key"],
                          **({"detour": "vpn"} if to_server == "vpn" and builtin else
                             {"bind_interface": vpn if to_server == "vpn" else phys})})
    else:
        outbounds.append({"type": "block", "tag": "server"})

    inbounds = [{"type": "tun", "tag": "tun", "interface_name": TUN_NAME, "address": [TUN_ADDRESS, TUN_ADDRESS6],
                 # Two /1 halves beat a VPN client's own default route, whatever its metric. IPv6 is taken
                 # too: otherwise it would slip past the lists into the VPN client (or out directly).
                 "route_address": ["0.0.0.0/1", "128.0.0.0/1", "::/1", "8000::/1"],
                 # strict_route: Windows asks every adapter's DNS at once (the router too, by a route more
                 # specific than ours); sing-box's firewall rules stop those queries going around the adapter
                 "mtu": 1400, "auto_route": True, "strict_route": True, "stack": "mixed"}]
    for name, port in CHECK_PORTS.items():  # local proxies the app uses to check each path
        inbounds.append({"type": "mixed", "tag": f"check-{name}", "listen": "127.0.0.1", "listen_port": port})

    rules = [{"inbound": [f"check-{n}"], "outbound": n} for n in CHECK_PORTS]
    rules += [{"action": "sniff"}, {"protocol": "dns", "action": "hijack-dns"},
              {"ip_is_private": True, "outbound": "direct"},
              # Public IPv6 is refused: apps fall back to IPv4 at once, and IPv4 follows the lists.
              {"ip_version": 6, "action": "reject"}]
    if server_ip:  # the SSH tunnel and anything else to the server itself
        rules.append({"ip_cidr": [server_ip + "/32"], "outbound": to_server})
    # an entry in several lists: the first wins, in this order
    # Without the Shadowsocks part, server profiles keep working for sites through the PAC file
    # (their traffic reaches 127.0.0.1, not this adapter), so they get no rules here.
    # «block» first: an ad domain stays blocked even if a wider list sends its site through the VPN
    rules += (_rules(via_blk, "block", ready) + _rules(via_dir, "direct", ready)
              + (_rules(via_srv, "server", ready) if has_server else []) + _rules(via_vpn, "vpn", ready))

    # FakeIP for whatever may leave through the VPN or your server: apps get a placeholder address, and the
    # outbound receives the site's NAME, not an IP we resolved here. Servers route by names (Quattro sends
    # Google/Gemini through Cloudflare), so a bare IP made Gemini come from a datacenter address it refuses.
    # Throne and other sing-box clients behave the same way. Direct traffic resolves names normally.
    def by_name(parsed: dict, then: dict) -> list[dict]:
        out = [dict(then, domain_suffix=parsed["domains"])] if parsed["domains"] else []
        tags = _tags(parsed, ready, "geosite")  # only domain lists: address lists mean nothing to DNS
        return out + ([dict(then, rule_set=tags)] if tags else [])

    fake = {"query_type": ["A", "AAAA"], "server": "fakeip"}
    dns_rules = by_name(via_blk, {"action": "reject"})  # blocked names do not even resolve
    if default == "direct":
        dns_rules += by_name(via_srv, fake) if has_server else []
        dns_rules += by_name(via_vpn, fake)
        dns_final = "dns-local"
    else:
        dns_rules += by_name(via_dir, {"server": "dns-local"})
        dns_rules.append(fake)
        dns_final = "dns-remote"
    local = {"type": "https", "tag": "dns-local", "detour": "direct",
             **doh_server(cfg.get("dns_direct_used") or cfg.get("dns_direct") or "cloudflare")}
    dns_servers = [
        # DNS over HTTPS: VPN clients (Happ and others) block port 53 outside their adapter
        # to stop DNS leaks, so plain DNS on the normal adapter would just time out.
        local,
        # listed sites are resolved on the far side, so the answer fits the exit
        {"type": "udp", "tag": "dns-remote", "server": plain_dns(cfg.get("dns_remote") or "cloudflare"),
         "detour": "vpn" if vpn else ("server" if has_server else "direct")},
        # IPv4 only: an IPv6 range would fall into fc00::/7, which counts as a private address
        {"type": "fakeip", "tag": "fakeip", "inet4_range": "198.18.0.0/15"},
    ]
    if local.get("domain_resolver"):  # your own DoH by name: its address comes from Google's DoH
        dns_servers.append({"type": "https", "tag": "dns-boot", "server": "8.8.8.8", "detour": "direct"})
    # find_process: every connection carries its program, also without process rules (the «Connections» window)
    route = {"rules": rules, "final": default, "default_domain_resolver": "dns-local", "find_process": True}
    tags = sorted({t for r in rules for t in r.get("rule_set", [])})
    if tags:
        route["rule_set"] = [{"type": "local", "tag": t, "format": "binary", "path": ready[t]} for t in tags]
    return {
        "log": {"level": "warn", "timestamp": True},
        "dns": {"servers": dns_servers, "rules": dns_rules, "final": dns_final, "strategy": "ipv4_only"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": route,
        "experimental": {"clash_api": {"external_controller": f"127.0.0.1:{STATS_PORT}"}},
    }


def has_items(lines: list[str]) -> bool:
    p = parse_list(lines)
    return any(p[k] for k in ("procs", "folders", "domains", "cidrs", "lists"))


def problems(cfg: dict, vpn: str | None) -> list[str]:
    """Keys of what prevents the mode from working: "novpn", "noserver"."""
    default = cfg.get("route_default") or "direct"
    lists = lists_by_target(cfg)
    srv = parse_list(lists["server"])
    wants_vpn = has_items(lists["vpn"]) or default == "vpn"
    # server sites alone work through the PAC file; programs, folders and subnets need Shadowsocks
    wants_server = bool(srv["procs"] or srv["folders"] or srv["cidrs"] or srv["lists"]) or default == "server"
    out = []
    if cfg.get("vpn_source") == "servers":
        if wants_vpn and not chosen_servers(cfg):
            out.append("noservers")
        if cfg.get("servers_via_adapter") and not vpn:
            out.append("novpn")
    elif not vpn and (wants_vpn or (cfg["require_vpn"] and wants_server)):
        out.append("novpn")
    if wants_server and not cfg.get("ss_key") and not _server_link(cfg):
        out.append("noserver")
    return out


# ---------- adapters ----------

def physical_adapter(vpn_pattern: str) -> str | None:
    """The adapter of the lowest-metric default route that is not a VPN or our own TUN."""
    ps = ("Get-NetRoute -AddressFamily IPv4 -DestinationPrefix 0.0.0.0/0 -ErrorAction SilentlyContinue | "
          "ForEach-Object { $i = Get-NetIPInterface -InterfaceIndex $_.ifIndex -AddressFamily IPv4; "
          "[pscustomobject]@{a=$_.InterfaceAlias; m=$_.RouteMetric + $i.InterfaceMetric} } "
          "| ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             timeout=20, creationflags=NO_WINDOW).stdout.strip()
        rows = json.loads(out) if out else []
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    rows = rows if isinstance(rows, list) else [rows]
    try:
        rx = re.compile(vpn_pattern, re.I)
    except re.error:
        rx = re.compile(r"$^")
    skip = re.compile(r"xmeltunnel|xt-route|tailscale|virtualbox|vmware|vethernet|loopback", re.I)
    rows = [r for r in rows if r.get("a") and not rx.search(r["a"]) and not skip.search(r["a"])]
    rows.sort(key=lambda r: r.get("m") or 0)
    return rows[0]["a"] if rows else None


# ---------- the elevated helper ----------

def state_path(data: str) -> str:
    return os.path.join(route_dir(data), "helper.json")


def stop_path(data: str) -> str:
    return os.path.join(route_dir(data), "stop")


def config_file(data: str) -> str:
    return os.path.join(route_dir(data), "route.json")


def log_file(data: str) -> str:
    return os.path.join(route_dir(data), "sing-box.log")


def _write_state(data: str, **kw) -> None:
    kw["at"] = time.time()
    path = state_path(data)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(kw, f)
    os.replace(path + ".tmp", path)


def read_state(data: str) -> dict:
    try:
        with open(state_path(data), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def helper_alive(data: str) -> bool:
    import psutil

    st = read_state(data)
    pid = st.get("helper")
    if not pid or st.get("status") == "stopped":
        return False
    try:
        return abs(psutil.Process(pid).create_time() - st.get("started", 0)) < 1
    except (psutil.Error, OSError):
        return False


def launch_helper(data: str) -> bool:
    """Start the helper elevated (UAC prompt). False if the user said no."""
    import ctypes

    try:
        os.remove(stop_path(data))
    except OSError:
        pass
    me = os.getpid()
    if getattr(sys, "frozen", False):
        exe, args, cwd = sys.executable, f'--route-helper {me} "{data}"', None
    else:
        exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        args = f'-m xmeltunnel --route-helper {me} "{data}"'
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, cwd, 0)
    return rc > 32


def request_stop(data: str) -> None:
    with open(stop_path(data), "w") as f:
        f.write("stop")


def _wait_adapter_gone(timeout: float = 12) -> None:
    """Windows removes a stopped sing-box's adapter with a delay; starting before that fails
    with "Cannot create a file when that file already exists"."""
    import psutil

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if not any(n.lower().startswith(TUN_NAME.lower()) for n in psutil.net_if_stats()):
                time.sleep(2)  # the name goes first, the driver object a moment later
                return
        except OSError:
            return
        time.sleep(0.5)


def _hidden_console() -> None:
    """The helper is a windowed exe: give it a hidden console so sing-box can share it and receive
    CTRL_BREAK. A killed sing-box leaves its TUN adapter behind for a while ("file already exists");
    a sing-box stopped by CTRL_BREAK removes it itself."""
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        if not k32.GetConsoleWindow():
            k32.AllocConsole()
            ctypes.windll.user32.ShowWindow(k32.GetConsoleWindow(), 0)
    except Exception:  # noqa: BLE001 — without it we fall back to killing
        pass


def _start_sing_box(exe: str, conf: str, log: str):
    return subprocess.Popen([exe, "run", "-c", conf, "--disable-color"], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=open(log, "a", encoding="utf-8"),
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)


def _stop_sing_box(proc) -> None:
    """Ask sing-box to stop (it then removes its adapter); kill only if it does not."""
    import signal

    if proc is None or proc.poll() is not None:
        return
    try:
        os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
        proc.wait(10)
    except (OSError, subprocess.TimeoutExpired):
        proc.kill()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            pass


# ---------- start without a UAC prompt (opt-in) ----------
# A scheduled task with the highest privileges, registered once with one UAC prompt. Running it later
# needs no prompt. Trade-off, said in Settings: anything running as this user can start it too.

TASK_NAME = "XmelTunnel Routing"


def task_supported() -> bool:
    return bool(getattr(sys, "frozen", False))  # the task points at XmelTunnel.exe


def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, encoding="oem", errors="replace",
                          timeout=30, creationflags=NO_WINDOW)


def task_installed() -> bool:
    try:
        r = _schtasks("/Query", "/TN", TASK_NAME, "/XML")
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and os.path.abspath(sys.executable).lower() in r.stdout.lower()


def _elevated(exe: str, params: str) -> bool:
    import ctypes

    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 0) > 32


def task_xml() -> str:
    """Task definition. Made from XML because plain `schtasks /Create` tasks do not start on battery
    and are stopped after 3 days."""
    from xml.sax.saxutils import escape

    exe = escape(os.path.abspath(sys.executable))
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>XmelTunnel: starts the routing mode helper (sing-box) with admin rights.</Description></RegistrationInfo>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author"><Exec><Command>{exe}</Command><Arguments>--route-helper-task</Arguments></Exec></Actions>
</Task>
"""


def install_task() -> bool:
    """One UAC prompt. True once the task exists."""
    import tempfile

    path = os.path.join(tempfile.gettempdir(), "xmeltunnel-task.xml")
    with open(path, "w", encoding="utf-16") as f:
        f.write(task_xml())
    if not _elevated("schtasks.exe", f'/Create /TN "{TASK_NAME}" /XML "{path}" /F'):
        return False
    for _ in range(40):
        if task_installed():
            return True
        time.sleep(0.5)
    return False


def remove_task(elevate: bool = True) -> bool:
    try:
        if _schtasks("/Delete", "/TN", TASK_NAME, "/F").returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    if not elevate or not _elevated("schtasks.exe", f'/Delete /TN "{TASK_NAME}" /F'):
        return False
    for _ in range(20):
        try:
            if _schtasks("/Query", "/TN", TASK_NAME).returncode != 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            return False
        time.sleep(0.5)
    return False


def run_task(data: str) -> bool:
    """Start the helper through the task. The task has no arguments, so the parent pid and the data
    folder go through a file in %APPDATA% (the same user runs both)."""
    try:
        os.remove(stop_path(data))
    except OSError:
        pass
    with open(os.path.join(route_dir(data), "parent.json"), "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "data": data}, f)
    try:
        return _schtasks("/Run", "/TN", TASK_NAME).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _wait_ready(proc, timeout: float = 30) -> bool:
    """sing-box is ready once its local check proxy answers: inbounds start in order, the TUN one first.

    Its process lives for ~15 s even when the TUN adapter fails, so "still running" is not enough."""
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", CHECK_PORTS["direct"]), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return proc.poll() is None


def helper_main(argv: list[str]) -> int:
    """Runs elevated: keep sing-box running while the parent XmelTunnel lives."""
    import psutil

    if "--route-helper-task" in argv:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        with open(os.path.join(base, "XmelTunnel", "routing", "parent.json"), encoding="utf-8") as f:
            info = json.load(f)
        parent, data = int(info["pid"]), info["data"]
    else:
        i = argv.index("--route-helper")
        parent, data = int(argv[i + 1]), argv[i + 2]
    _hidden_console()
    exe, conf, log = sing_box_path(data), config_file(data), log_file(data)
    started = psutil.Process().create_time()
    _write_state(data, status="starting", helper=os.getpid(), started=started)

    for p in psutil.process_iter(["name", "exe"]):  # a sing-box left from a killed run
        try:
            if (p.info["name"] or "").lower() == "sing-box.exe" and (p.info["exe"] or "").lower() == exe.lower():
                p.kill()
        except (psutil.Error, OSError):
            pass

    proc, conf_mtime, error, attempt, fails = None, 0.0, "", 0, []
    run_conf = os.path.join(route_dir(data), "run.json")
    try:
        while True:
            if not psutil.pid_exists(parent) or os.path.exists(stop_path(data)):
                break
            try:
                mtime = os.path.getmtime(conf)
            except OSError:
                error = "no config"
                break
            dead = proc is not None and proc.poll() is not None
            if proc is None or mtime != conf_mtime or dead:
                if dead:
                    # Retry instead of giving up: on Windows a killed sing-box can leave its adapter behind
                    # for a few seconds ("Cannot create a file when that file already exists").
                    now = time.time()
                    fails = [t for t in fails if now - t < 120] + [now]
                    if len(fails) > 3:
                        error = "sing-box keeps stopping (details in sing-box.log)"
                        break
                    _write_state(data, status="restarting", helper=os.getpid(), started=started)
                    _wait_adapter_gone()
                elif proc is not None:
                    _write_state(data, status="restarting", helper=os.getpid(), started=started)
                    _stop_sing_box(proc)
                    _wait_adapter_gone()
                # checked right before every start: the folder is writable by the user
                if file_sha256(exe) != SING_BOX_EXE_SHA256:
                    error = "sing-box.exe checksum mismatch"
                    break
                conf_mtime = mtime
                attempt += 1
                try:
                    with open(conf, encoding="utf-8") as cf:
                        body = json.load(cf)
                    # A fresh adapter name every start: a leftover of the previous one cannot block it.
                    for ib in body.get("inbounds", []):
                        if ib.get("type") == "tun":
                            # Plain «XmelTunnel»; after a failed start a numbered spare name (a new adapter id),
                            # so a leftover of a killed run cannot block it
                            ib["interface_name"] = TUN_NAME if not fails else f"{TUN_NAME}-{len(fails) + 1}"
                    with open(run_conf, "w", encoding="utf-8") as rf:
                        json.dump(body, rf)
                except (OSError, ValueError):
                    error = "bad config"
                    break
                with open(log, "a", encoding="utf-8") as lf:
                    lf.write(time.strftime("\n--- %Y-%m-%d %H:%M:%S start\n"))
                proc = _start_sing_box(exe, run_conf, log)
                if _wait_ready(proc):
                    _write_state(data, status="running", helper=os.getpid(), started=started, singbox=proc.pid)
            time.sleep(1)
    finally:
        _stop_sing_box(proc)
        _write_state(data, status="stopped", error=error, helper=os.getpid(), started=started)
        try:
            os.remove(stop_path(data))
        except OSError:
            pass
    return 0


# ---------- checks ----------

def check_path(name: str, timeout: int = 15) -> tuple[str, str]:
    """(ip, country) Cloudflare sees through one path of the running mode."""
    proxy = f"http://127.0.0.1:{CHECK_PORTS[name]}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
    with opener.open("https://www.cloudflare.com/cdn-cgi/trace", timeout=timeout) as r:
        body = r.read(4096).decode("ascii", "replace")
    kv = dict(ln.split("=", 1) for ln in body.splitlines() if "=" in ln)
    return kv.get("ip", "?"), kv.get("loc", "?")


def last_log_error(data: str) -> str:
    try:
        with open(log_file(data), encoding="utf-8", errors="replace") as f:
            # only a start failure (FATAL): «ERROR … i/o timeout» lines are ordinary sites not answering
            lines = [ln.strip() for ln in f.readlines()[-60:] if "FATAL" in ln]
        return lines[-1][-200:] if lines else ""
    except OSError:
        return ""
