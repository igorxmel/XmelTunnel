"""VPN servers: share links and subscriptions -> sing-box outbounds.

Supported links: vless:// (incl. Reality), vmess://, trojan://, ss://, hysteria2:// (hy2://), tuic://.
Subscriptions: a list of such links (plain or base64) or a sing-box JSON config with outbounds.
A subscription is fetched as XmelTunnel itself; nothing pretends to be another client.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.parse
import urllib.request

PROTOCOLS = {"vless": "VLESS", "vmess": "VMess", "trojan": "Trojan", "shadowsocks": "Shadowsocks",
             "hysteria2": "Hysteria2", "tuic": "TUIC", "anytls": "AnyTLS", "naive": "Naive",
             "wireguard": "WireGuard"}
PROXY_TYPES = set(PROTOCOLS)
ENDPOINT_TYPES = {"wireguard"}  # sing-box keeps these under "endpoints", not "outbounds"


def place_endpoints(conf: dict) -> dict:
    """Move WireGuard (and other endpoint types) from conf["outbounds"] to conf["endpoints"].
    Every config is built with servers as outbounds; this one step makes it valid for sing-box."""
    obs = conf.get("outbounds") or []
    eps = [o for o in obs if o.get("type") in ENDPOINT_TYPES]
    if eps:
        conf["outbounds"] = [o for o in obs if o.get("type") not in ENDPOINT_TYPES]
        # the top-level server/server_port are ours (for the table); a WireGuard endpoint has its peers instead
        eps = [{k: v for k, v in o.items() if k not in ("server", "server_port")} for o in eps]
        conf["endpoints"] = (conf.get("endpoints") or []) + eps
    return conf


class LinkError(ValueError):
    pass


# ---------- helpers ----------

def _b64(text: str) -> str:
    """Decode base64 / base64url with or without padding."""
    t = text.strip().replace("-", "+").replace("_", "/")
    t += "=" * (-len(t) % 4)
    return base64.b64decode(t).decode("utf-8", "replace")


def _q(params: dict, *names: str, default: str = "") -> str:
    for n in names:
        if params.get(n):
            return params[n]
    return default


def flag_country(name: str) -> str:
    """'🇫🇮 Helsinki' -> 'FI' (regional indicator pair); '' if there is none."""
    chars = [c for c in name if 0x1F1E6 <= ord(c) <= 0x1F1FF]
    for a, b in zip(chars, chars[1:]):
        code = chr(ord(a) - 0x1F1E6 + 65) + chr(ord(b) - 0x1F1E6 + 65)
        return code
    return ""


def display_name(name: str) -> str:
    """The name without flag emoji: Windows shows them as two letters, the flag is drawn separately."""
    return re.sub(r"[\U0001F1E6-\U0001F1FF]", "", name).strip(" -|·") or name


def _tls(params: dict, host: str, reality: bool = False) -> dict:
    tls = {"enabled": True, "server_name": _q(params, "sni", "peer", "host", default=host)}
    if params.get("allowInsecure") in ("1", "true") or params.get("insecure") in ("1", "true"):
        tls["insecure"] = True
    alpn = _q(params, "alpn")
    if alpn:
        tls["alpn"] = [a for a in urllib.parse.unquote(alpn).split(",") if a]
    fp = _q(params, "fp")
    if fp or reality:
        tls["utls"] = {"enabled": True, "fingerprint": fp or "chrome"}
    if reality:
        tls["reality"] = {"enabled": True, "public_key": _q(params, "pbk"), "short_id": _q(params, "sid")}
    return tls


def _transport(params: dict) -> dict | None:
    kind = _q(params, "type", "net", default="tcp")
    host = _q(params, "host")
    path = urllib.parse.unquote(_q(params, "path"))
    if kind == "ws":
        t = {"type": "ws", "path": path or "/"}
        if host:
            t["headers"] = {"Host": host}
        return t
    if kind == "grpc":
        return {"type": "grpc", "service_name": _q(params, "serviceName", "path")}
    if kind in ("http", "h2"):
        t = {"type": "http", "path": path or "/"}
        if host:
            t["host"] = [host]
        return t
    if kind in ("httpupgrade",):
        t = {"type": "httpupgrade", "path": path or "/"}
        if host:
            t["host"] = host
        return t
    if kind in ("tcp", "raw", ""):
        return None
    raise LinkError(f"transport «{kind}» is not supported")


# ---------- links ----------

def parse_link(link: str) -> dict:
    """One share link -> {"name", "protocol", "host", "port", "outbound"} (outbound has no tag yet)."""
    link = link.strip()
    scheme = link.split("://", 1)[0].lower()
    if scheme == "vmess":
        return _vmess(link)
    if scheme == "ss":
        return _ss(link)
    if scheme in ("wireguard", "wg"):
        return _wireguard(link)
    u = urllib.parse.urlsplit(link)
    params = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
    name = urllib.parse.unquote(u.fragment) or f"{u.hostname}:{u.port}"
    host, port = u.hostname, u.port
    if not host or not port:
        raise LinkError("no server address")
    user = urllib.parse.unquote(u.username or "")
    if scheme == "vless":
        out = {"type": "vless", "server": host, "server_port": port, "uuid": user}
        if params.get("flow"):
            out["flow"] = params["flow"]
        sec = _q(params, "security")
        if sec in ("tls", "reality"):
            out["tls"] = _tls(params, host, reality=sec == "reality")
    elif scheme == "trojan":
        out = {"type": "trojan", "server": host, "server_port": port, "password": user}
        if _q(params, "security", default="tls") != "none":
            out["tls"] = _tls(params, host)
    elif scheme in ("hysteria2", "hy2"):
        password = user if not u.password else f"{user}:{urllib.parse.unquote(u.password)}"
        out = {"type": "hysteria2", "server": host, "server_port": port, "password": password,
               "tls": _tls(params, host)}
        if params.get("obfs") == "salamander":
            out["obfs"] = {"type": "salamander", "password": _q(params, "obfs-password")}
        scheme = "hysteria2"
    elif scheme == "tuic":
        out = {"type": "tuic", "server": host, "server_port": port, "uuid": user,
               "password": urllib.parse.unquote(u.password or ""), "tls": _tls(params, host)}
        if params.get("congestion_control"):
            out["congestion_control"] = params["congestion_control"]
        if not out["tls"].get("alpn"):
            out["tls"]["alpn"] = ["h3"]
    elif scheme == "anytls":
        out = {"type": "anytls", "server": host, "server_port": port, "password": user, "tls": _tls(params, host)}
    elif scheme in ("naive+https", "naive+quic", "naive"):
        out = {"type": "naive", "server": host, "server_port": port, "username": user,
               "password": urllib.parse.unquote(u.password or ""), "tls": _tls(params, host)}
        if scheme == "naive+quic":
            out["quic"] = True
        scheme = "naive"
    else:
        raise LinkError(f"«{scheme}://» links are not supported")
    if scheme in ("vless", "trojan"):
        t = _transport(params)
        if t:
            out["transport"] = t
    return {"name": name, "protocol": out["type"], "host": host, "port": port, "outbound": out}


def _vmess(link: str) -> dict:
    try:
        j = json.loads(_b64(link[len("vmess://"):]))
    except (ValueError, UnicodeError) as e:
        raise LinkError("broken vmess link") from e
    host, port = str(j.get("add", "")), int(j.get("port") or 0)
    if not host or not port:
        raise LinkError("no server address")
    out = {"type": "vmess", "server": host, "server_port": port, "uuid": j.get("id", ""),
           "security": j.get("scy") or "auto", "alter_id": int(j.get("aid") or 0)}
    params = {"type": j.get("net", "tcp"), "host": j.get("host", ""), "path": j.get("path", ""),
              "sni": j.get("sni", ""), "alpn": j.get("alpn", ""), "fp": j.get("fp", "")}
    if j.get("tls") == "tls":
        out["tls"] = _tls(params, host)
    t = _transport(params)
    if t:
        out["transport"] = t
    return {"name": j.get("ps") or f"{host}:{port}", "protocol": "vmess", "host": host, "port": port,
            "outbound": out}


def _wireguard(link: str) -> dict:
    """wireguard://<private key>@host:port?publickey=…&address=10.0.0.2/32,fd00::2/128&reserved=1,2,3&mtu=1280"""
    u = urllib.parse.urlsplit(link)
    params = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
    host, port = u.hostname, u.port
    key = urllib.parse.unquote(u.username or "") or _q(params, "privatekey", "secretkey")
    pub = _q(params, "publickey", "peer_public_key", "pbk")
    if not host or not port:
        raise LinkError("no server address")
    if not key or not pub:
        raise LinkError("WireGuard link without keys")
    address = [a.strip() for a in urllib.parse.unquote(_q(params, "address", "ip", default="10.0.0.2/32")).split(",")
               if a.strip()]
    address = [a if "/" in a else a + ("/128" if ":" in a else "/32") for a in address]
    peer = {"address": host, "port": port, "public_key": pub.replace(" ", "+"),
            "allowed_ips": ["0.0.0.0/0", "::/0"]}
    psk = _q(params, "presharedkey", "psk")
    if psk:
        peer["pre_shared_key"] = psk.replace(" ", "+")
    reserved = _q(params, "reserved")
    if reserved:
        try:
            peer["reserved"] = [int(x) for x in reserved.split(",")][:3]
        except ValueError:
            pass
    out = {"type": "wireguard", "address": address, "private_key": key.replace(" ", "+"), "peers": [peer],
           # the server's address and port are also kept at the top, where every other protocol has them
           "server": host, "server_port": port}
    mtu = _q(params, "mtu")
    if mtu.isdigit():
        out["mtu"] = int(mtu)
    name = urllib.parse.unquote(u.fragment) or f"{host}:{port}"
    return {"name": name, "protocol": "wireguard", "host": host, "port": port, "outbound": out}


def _ss(link: str) -> dict:
    body = link[len("ss://"):]
    body, _, frag = body.partition("#")
    name = urllib.parse.unquote(frag)
    body = body.split("?", 1)[0].rstrip("/")
    if "@" in body:  # SIP002: base64(method:password)@host:port or method:password@host:port
        userinfo, _, hostport = body.rpartition("@")
        userinfo = urllib.parse.unquote(userinfo)
        if ":" not in userinfo:
            userinfo = _b64(userinfo)
    else:  # legacy: base64(method:password@host:port)
        userinfo, _, hostport = _b64(body).rpartition("@")
    method, _, password = userinfo.partition(":")
    host, _, port = hostport.rpartition(":")
    host = host.strip("[]")
    if not (method and password and host and port.isdigit()):
        raise LinkError("broken ss link")
    out = {"type": "shadowsocks", "server": host, "server_port": int(port), "method": method,
           "password": password}
    return {"name": name or f"{host}:{port}", "protocol": "shadowsocks", "host": host, "port": int(port),
            "outbound": out}


def server_id(outbound: dict) -> str:
    """Stable id from what identifies a server (address, port, protocol, credentials)."""
    key = json.dumps({k: outbound.get(k) for k in ("type", "server", "server_port", "uuid", "password",
                                                   "private_key", "username")},
                     sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def make_server(parsed: dict, sub: str = "") -> dict:
    return {"id": server_id(parsed["outbound"]), "name": parsed["name"].strip(), "protocol": parsed["protocol"],
            "host": parsed["host"], "port": parsed["port"], "country": flag_country(parsed["name"]),
            "sub": sub, "outbound": parsed["outbound"]}


# ---------- text and subscriptions ----------

LINK_RX = re.compile(r"(?:vless|vmess|trojan|ss|hysteria2|hy2|tuic|anytls|naive\+https|naive\+quic|wireguard|wg)"
                     r"://[^\r\n\t\"'<>]+", re.I)
OTHER_RX = re.compile(r"(?<![\w+.-])([a-z][a-z0-9+.-]{1,20})://", re.I)  # any link, to name the ones we skip


def parse_text(text: str, sub: str = "") -> tuple[list[dict], list[str]]:
    """Links (plain or a base64 blob) or a sing-box JSON -> (servers, errors)."""
    text = text.strip()
    if text.startswith("{"):
        return _from_singbox(text, sub)
    if not LINK_RX.search(text):
        try:
            decoded = _b64(re.sub(r"\s+", "", text))
            if LINK_RX.search(decoded):
                text = decoded
        except (ValueError, UnicodeError):
            pass
    servers, errors, seen = [], [], set()
    for scheme in OTHER_RX.findall(text):
        sc = scheme.lower()
        if sc not in ("http", "https") and not LINK_RX.match(sc + "://x"):
            errors.append(f"{sc}://…: «{sc}://» links are not supported")
    for link in LINK_RX.findall(text):
        link = link.strip()
        try:
            s = make_server(parse_link(link), sub)
        except (LinkError, ValueError, KeyError, UnicodeError) as e:
            errors.append(f"{link[:40]}…: {e}")
            continue
        if s["id"] not in seen:
            seen.add(s["id"])
            servers.append(s)
    if not servers and not errors:
        errors.append("no server links found")
    return servers, errors


def skipped_summary(errors: list[str]) -> dict[str, int]:
    """{reason: how many servers} from parse errors: what a subscription had that we could not use."""
    out: dict[str, int] = {}
    for e in errors:
        reason = e.split(": ", 1)[-1] if ": " in e else e
        if reason == "no server links found":
            continue
        out[reason] = out.get(reason, 0) + 1
    return out


def _from_singbox(text: str, sub: str) -> tuple[list[dict], list[str]]:
    try:
        data = json.loads(text)
    except ValueError as e:
        return [], [f"broken JSON: {e}"]
    servers = []
    for ob in (data.get("outbounds") or []) + (data.get("endpoints") or []):
        if ob.get("type") not in PROXY_TYPES:
            continue
        if ob.get("type") == "wireguard" and not ob.get("server") and ob.get("peers"):
            ob = dict(ob, server=ob["peers"][0].get("address", ""), server_port=ob["peers"][0].get("port", 0))
        if not ob.get("server"):
            continue
        ob = {k: v for k, v in ob.items() if k not in ("tag", "detour")}
        name = data.get("_names", {}).get(ob.get("server"), "") or f"{ob['server']}:{ob.get('server_port')}"
        servers.append({"id": server_id(ob), "name": name, "protocol": ob["type"], "host": ob["server"],
                        "port": ob.get("server_port", 0), "country": flag_country(name), "sub": sub, "outbound": ob})
    return servers, ([] if servers else ["no proxy outbounds in the config"])


def fetch_subscription(url: str, timeout: int = 30) -> tuple[str, dict]:
    """Body and useful headers (traffic, expiry, update interval) of a subscription."""
    from xmeltunnel import __version__

    req = urllib.request.Request(url, headers={"User-Agent": f"XmelTunnel/{__version__} (sing-box)",
                                               "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(5 * 1024 * 1024).decode("utf-8", "replace")
        info = {}
        ui = r.headers.get("subscription-userinfo", "")
        for part in ui.split(";"):
            k, _, v = part.strip().partition("=")
            if k and v.strip().isdigit():
                info[k] = int(v)
        title = r.headers.get("profile-title", "")
        if title.startswith("base64:"):
            try:
                title = _b64(title[7:])
            except (ValueError, UnicodeError):
                title = ""
        info["title"] = title
        upd = r.headers.get("profile-update-interval", "")
        if upd.isdigit():
            info["update_hours"] = int(upd)
    return body, info
