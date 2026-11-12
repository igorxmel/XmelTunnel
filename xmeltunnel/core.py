"""Everything except the UI: config, SSH tunnel, PAC file, Windows proxy settings, leak watching.

The UI only reads Engine.snapshot() and calls its methods; all work happens in background threads.
"""

from __future__ import annotations

import hashlib
import http.server
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import psutil

from xmeltunnel import APP_NAME, i18n, pinger, profiles, routing, servers, updater
from xmeltunnel.i18n import tr

try:
    import winreg
except ImportError:  # tests on non-Windows
    winreg = None

OK, WARN, DOWN, OFF = "ok", "warn", "down", "unknown"

DEFAULTS = {
    "server_enabled": True,             # «Disconnect» on the server card turns it off (no tunnel, no PAC)
    "server_mode": "ssh",               # ssh = your own server over SSH; link = a share link (ss://, vless://…)
    "server_link": "",
    "server": "",                       # user@host, bare IP (-> root@IP) or an alias from ~/.ssh/config
    "ssh_port": 22,
    "ssh_key": r"~\.ssh\id_ed25519",
    "remote_proxy_port": 8888,          # tinyproxy on the server, listens on 127.0.0.1 only
    "local_proxy_port": 8888,
    "pac_port": 8889,
    "ssh_exe": r"C:\Windows\System32\OpenSSH\ssh.exe",
    "reconnect_delay": 5,
    "language": "",                     # "" = follow Windows
    "require_vpn": False,
    # «tun» only as a word or with a number: «Teredo Tunneling Pseudo-Interface» is Windows' own, not a VPN
    "vpn_adapter": r"happ|xray|wireguard|wintun|clash|sing-?box|outline|amnezia|throne|vpn|\btun\b|tun\d",
    "profiles": None,                   # None = first run, filled with presets
    "prev_autoconfig": None,            # the user's own PAC URL before we replaced it
    # routing mode: the whole PC goes direct except these lists (see routing.py)
    "route_enabled": False,
    "route_default": "direct",          # where everything not listed goes: direct, vpn or server
    # 0.2 test builds kept three lists here; they become profiles once (see migrate_route_lists)
    "route_direct": None,
    "route_vpn": None,
    "route_server": None,
    "routes_migrated": False,
    "ss_port": 8388,                    # Shadowsocks on the server, installed from Settings
    "ss_key": "",
    # the built-in VPN client: servers from links and subscriptions
    "vpn_source": "adapter",            # adapter = your VPN client (Happ…); servers = XmelTunnel's own list
    "vpn_server": "auto",               # a server id, "auto" (fastest) or "auto:FI" (fastest in a country)
    "servers": [],
    "subscriptions": [],                # {id, url, title, updated_at, count, error, info}
    "server_checks": {},                # server id -> last check result
    "servers_via_adapter": False,       # reach these servers through the VPN client's adapter
    "sharing_used": False,              # friends have access to your server: check their limits now and then
    "check_updates": True,
    # app
    "theme": "system",                  # system, dark, light
    "ui_scale": 0.0,                    # 0 = as in Windows; applied at start (QT_SCALE_FACTOR)
    "start_minimized": False,
    "close_to_tray": True,
    "notifications": True,
    "route_on_start": True,             # turn the routing mode back on at start if it was on
    "route_no_uac": False,              # start the routing mode through a scheduled task (one UAC, once)
    "window": None,                     # [width, height, maximized]
    "expanded_profiles": [],            # profile ids shown with their apps
    "notified_version": "",             # a new version is announced in the tray once
}
UPDATE_CHECK_EVERY = 6 * 3600
UPDATE_FIRST_CHECK = 20
EDITABLE = ("server", "ssh_port", "ssh_key", "remote_proxy_port", "local_proxy_port", "pac_port", "language",
            "require_vpn", "vpn_adapter")

FALLBACK_CHECK = "https://www.cloudflare.com/cdn-cgi/trace"
OLD_VPN_PATTERNS = (r"happ|xray|wireguard|wintun|clash|sing-?box|outline|amnezia|throne|vpn|tun",)
NOT_VPN = re.compile(r"teredo|isatap|6to4|pseudo-interface|xmeltunnel|xt-route|tailscale|virtualbox|hyper-v|vethernet|vmware|loopback", re.I)
EXIT_CHECK_EVERY = 60
POLL_EVERY = 3
RESOLVE_EVERY = 300
NOTIFY_COOLDOWN = 90
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
CLAUDE_SETTINGS = os.path.expanduser(os.path.join("~", ".claude", "settings.json"))
INET_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = APP_NAME


# ---------- paths and config ----------

def data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def normalize_server(value: str) -> str:
    value = value.strip()
    return "root@" + value if "@" not in value and _IPV4.match(value) else value


def load_config(path: str | None = None) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    cfg["_first_run"] = not os.path.exists(path or config_path())  # not saved: only DEFAULTS keys are
    try:
        with open(path or config_path(), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass  # broken or missing file must not kill the app
    cfg["server"] = normalize_server(str(cfg["server"]))
    # A fresh install starts empty: presets are offered in «Add profile», nothing is switched on for you.
    cfg["profiles"] = [profiles.normalize(p) for p in (cfg["profiles"] or [])]
    migrate_route_lists(cfg)
    if cfg["vpn_adapter"] in OLD_VPN_PATTERNS:  # the old default matched Teredo: move to the new one
        cfg["vpn_adapter"] = DEFAULTS["vpn_adapter"]
    if cfg["route_default"] not in ("direct", "vpn", "server"):
        cfg["route_default"] = "direct"
    return cfg


def save_config(cfg: dict, path: str | None = None) -> None:
    path = path or config_path()
    data = {k: cfg[k] for k in DEFAULTS if k in cfg and k not in ("ssh_exe", "reconnect_delay")}
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(path + ".tmp", path)


def validate(raw: dict) -> tuple[dict, list[str]]:
    """Values from the settings form (strings) -> (partial config, errors)."""
    errors, out = [], {}
    server = normalize_server(str(raw.get("server", "")))
    if not server or " " in server:
        errors.append(tr("Server: IP, user@host or an alias from ~/.ssh/config."))
    out["server"] = server
    for key, title in (("ssh_port", tr("SSH port")), ("remote_proxy_port", tr("Proxy port on the server")),
                       ("local_proxy_port", tr("Proxy port on this PC")), ("pac_port", tr("PAC file port"))):
        text = str(raw.get(key, "")).strip()
        if text.isdigit() and 1 <= int(text) <= 65535:
            out[key] = int(text)
        else:
            errors.append(tr("{field}: a number from 1 to 65535.", field=title))
    if out.get("local_proxy_port") and out.get("local_proxy_port") == out.get("pac_port"):
        errors.append(tr("The two local ports must differ."))
    key = str(raw.get("ssh_key", "")).strip()
    if not key or not os.path.isfile(os.path.expanduser(key)):
        # ssh silently falls back to other keys if this one is missing, so check it ourselves
        errors.append(tr("SSH key: file not found ({path}).", path=key))
    out["ssh_key"] = key
    return out, errors


def ssh_args(cfg: dict) -> list[str]:
    return [cfg["ssh_exe"], "-i", os.path.expanduser(cfg["ssh_key"]), "-p", str(cfg["ssh_port"]),
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]


def link_server(cfg: dict) -> dict | None:
    """The parsed share link of the «link» mode, or None."""
    if cfg.get("server_mode") != "link" or not cfg.get("server_link"):
        return None
    try:
        return servers.parse_link(cfg["server_link"])
    except (servers.LinkError, ValueError, KeyError, UnicodeError):
        return None


def has_server(cfg: dict) -> bool:
    return bool(link_server(cfg)) if cfg.get("server_mode") == "link" else bool(cfg["server"])


def server_host(cfg: dict) -> str:
    """What to show as «Server: …»."""
    ls = link_server(cfg)
    if cfg.get("server_mode") == "link":
        return ls["host"] if ls else ""
    return cfg["server"].split("@")[-1]


def server_ip(cfg: dict) -> str:
    """Server IP from user@IP, otherwise via `ssh -G` (aliases) and DNS. In the link mode: the link's host."""
    if cfg.get("server_mode") == "link":
        ls = link_server(cfg)
        if not ls:
            return ""
        try:
            return socket.gethostbyname(ls["host"])
        except OSError:
            return ls["host"]
    host = cfg["server"].split("@")[-1]
    if not host:
        return ""
    if not _IPV4.match(host):
        try:
            out = subprocess.run([cfg["ssh_exe"], "-G", cfg["server"]], capture_output=True, text=True,
                                 timeout=10, creationflags=NO_WINDOW).stdout
            host = next((ln.split()[1] for ln in out.splitlines() if ln.startswith("hostname ")), host)
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        return socket.gethostbyname(host)
    except OSError:
        return host


# ---------- PAC and Windows settings ----------

LIST_NAMES = {"en": {"direct": "Direct list", "server": "Server list", "vpn": "VPN list"},
              "ru": {"direct": "Список «Напрямую»", "server": "Список «Через сервер»", "vpn": "Список «Через VPN»"}}


def migrate_route_lists(cfg: dict) -> None:
    """The three lists of the 0.2 test builds become ordinary profiles, once."""
    if cfg.get("routes_migrated"):
        return
    lang = cfg.get("language") or i18n.system_language()
    names = LIST_NAMES.get(lang, LIST_NAMES["en"])
    taken = {p["id"] for p in cfg["profiles"]}
    for key, target in (("route_direct", "direct"), ("route_server", "server"), ("route_vpn", "vpn")):
        lines = cfg.get(key) or []
        if routing.has_items(lines) and f"list-{target}" not in taken:
            cfg["profiles"].append(profiles.normalize({"id": f"list-{target}", "name": names[target],
                                                       "target": target, "entries": lines, "enabled": True}))
        cfg[key] = None
    cfg["routes_migrated"] = True


def enabled_profiles(cfg: dict) -> list[dict]:
    return [p for p in cfg["profiles"] if p["enabled"]]


def pac_profiles(cfg: dict) -> list[dict]:
    """Enabled profiles whose sites go through the server by the PAC file (no admin rights needed)."""
    return [p for p in cfg["profiles"] if p["enabled"] and p.get("target", "server") == "server"]


def pac_text(cfg: dict) -> str:
    domains = sorted({d for p in pac_profiles(cfg) for d in p["domains"]})
    listed = ", ".join(f'"{d}"' for d in domains)
    # No "; DIRECT" fallback: if the tunnel is down, these sites fail instead of silently going direct.
    return f"""// XmelTunnel: these domains go through your server, everything else is direct.
function FindProxyForURL(url, host) {{
  host = host.toLowerCase();
  var d = [{listed}];
  for (var i = 0; i < d.length; i++)
    if (host == d[i] || dnsDomainIs(host, "." + d[i])) return "PROXY 127.0.0.1:{cfg['local_proxy_port']}";
  return "DIRECT";
}}
"""


def pac_url(cfg: dict) -> str:
    return f"http://127.0.0.1:{cfg['pac_port']}/xmeltunnel.pac"


def is_our_pac(url, cfg: dict) -> bool:
    """Our PAC address, with or without the ?v= mark."""
    return bool(url) and str(url).split("?", 1)[0] == pac_url(cfg)


def fresh_pac_url(cfg: dict) -> str:
    """Chromium-based apps (Claude Desktop, Electron) fetch a PAC file once and keep it until the address in
    Windows settings changes. A new mark makes them fetch it again: after XmelTunnel restarts or updates
    (they fell back to direct while nobody served it) and after the list of sites changed."""
    return f"{pac_url(cfg)}?v={int(time.time() * 1000)}"


def _reg_get(path: str, name: str):
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _reg_set(path: str, name: str, value) -> None:
    if winreg is None:
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as k:
        if value is None:
            try:
                winreg.DeleteValue(k, name)
            except OSError:
                pass
        else:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _notify_inet_changed() -> None:
    """Tell Windows and Chromium-based apps that proxy settings changed."""
    try:
        import ctypes

        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
        wininet.InternetSetOptionW(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH
    except Exception:  # noqa: BLE001
        pass


def pac_installed(cfg: dict) -> bool:
    return is_our_pac(_reg_get(INET_KEY, "AutoConfigURL"), cfg)


def install_pac(cfg: dict, on: bool, refresh: bool = False) -> None:
    """Point Windows at our PAC file, remembering and later restoring the user's own one.

    refresh: write a new ?v= mark even if ours is already there, so apps fetch the PAC file again."""
    current = _reg_get(INET_KEY, "AutoConfigURL")
    if on and (refresh or not is_our_pac(current, cfg)):
        if not is_our_pac(current, cfg):
            cfg["prev_autoconfig"] = current
        _reg_set(INET_KEY, "AutoConfigURL", fresh_pac_url(cfg))
    elif not on and is_our_pac(current, cfg):
        _reg_set(INET_KEY, "AutoConfigURL", cfg.get("prev_autoconfig"))
        cfg["prev_autoconfig"] = None
    _notify_inet_changed()


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def claude_code_proxy_on(cfg: dict, path: str = CLAUDE_SETTINGS) -> bool:
    try:
        return _read_json(path).get("env", {}).get("HTTPS_PROXY") == f"http://127.0.0.1:{cfg['local_proxy_port']}"
    except (OSError, ValueError):
        return False


def set_claude_code_proxy(cfg: dict, on: bool, path: str = CLAUDE_SETTINGS) -> None:
    """Claude Code reads proxy env vars from ~/.claude/settings.json. Only our own values are removed."""
    data = _read_json(path)  # broken JSON raises: better than overwriting the user's file
    env = data.setdefault("env", {})
    ours = f"http://127.0.0.1:{cfg['local_proxy_port']}"
    if on:
        env["HTTPS_PROXY"] = env["HTTP_PROXY"] = ours
        env.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
    else:
        for k in ("HTTPS_PROXY", "HTTP_PROXY"):
            if env.get(k) == ours:
                env.pop(k)
        if env.get("NO_PROXY") == "localhost,127.0.0.1,::1" and "HTTPS_PROXY" not in env:
            env.pop("NO_PROXY")
        if not env:
            data.pop("env")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(path + ".tmp", path)


def wants_claude_code(cfg: dict) -> bool:
    return any(a["method"] == "claude_code" for p in pac_profiles(cfg) for a in p["apps"])


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --hidden'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pythonw}" -m xmeltunnel --hidden'


def autostart_enabled() -> bool:
    return _reg_get(RUN_KEY, RUN_NAME) == autostart_command()


def set_autostart(on: bool) -> None:
    _reg_set(RUN_KEY, RUN_NAME, autostart_command() if on else None)


def remove_from_pc(cfg: dict, claude_settings: str = CLAUDE_SETTINGS, data: str | None = None) -> list[str]:
    """Undo everything XmelTunnel changed on this PC. Returns what was done (for the user).

    The server is left alone: the proxy there listens on localhost only and is harmless.
    """
    import shutil

    done = []
    path = data or data_dir()
    if routing.helper_alive(path):
        routing.request_stop(path)
        for _ in range(30):
            if not routing.helper_alive(path):
                break
            time.sleep(0.5)
        done.append("routing")
    current = _reg_get(INET_KEY, "AutoConfigURL")
    if is_our_pac(current, cfg):
        _reg_set(INET_KEY, "AutoConfigURL", cfg.get("prev_autoconfig"))
        _notify_inet_changed()
        done.append("pac")
    try:
        if claude_code_proxy_on(cfg, claude_settings):
            set_claude_code_proxy(cfg, False, claude_settings)
            done.append("claude_code")
    except (OSError, ValueError) as e:
        log(f"remove: Claude Code settings: {e}")
    if _reg_get(RUN_KEY, RUN_NAME) is not None:
        _reg_set(RUN_KEY, RUN_NAME, None)
        done.append("autostart")
    if routing.task_supported() and cfg.get("route_no_uac") and routing.remove_task():
        done.append("task")
    shutil.rmtree(path, ignore_errors=True)
    if not os.path.exists(path):
        done.append("data")
    return done


# ---------- watching ----------

def in_nets(ip: str, nets: list) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in n for n in nets)


def resolve_ips(domains: list[str]) -> set[str]:
    out = set()
    for d in domains:
        try:
            for info in socket.getaddrinfo(d, 443, proto=socket.IPPROTO_TCP):
                out.add(info[4][0])
        except OSError:
            pass
    return out


def list_processes() -> list[tuple[int, str]]:
    out = []
    for p in psutil.process_iter(["pid", "exe"]):
        if p.info.get("exe"):
            out.append((p.info["pid"], p.info["exe"]))
    return out


def established() -> list:
    try:
        return [c for c in psutil.net_connections(kind="tcp") if c.raddr and c.status == psutil.CONN_ESTABLISHED]
    except (psutil.AccessDenied, OSError):
        return []


def scan(cfg: dict, targets: dict, procs=None, conns=None) -> dict:
    """For every app of every profile: its pids, connections through our proxy, and direct ones.

    targets: profile id -> (ip set, network list) the profile's sites live on.
    Returns {(profile id, app index): {"pids": set, "via": int, "direct": int}}.
    """
    procs = list_processes() if procs is None else procs
    owner, result = {}, {}
    for p in cfg["profiles"]:
        for i, app in enumerate(p["apps"]):
            key = (p["id"], i)
            result[key] = {"pids": set(), "via": 0, "direct": 0}
            for pid, exe in procs:
                if profiles.app_matches(app, exe):
                    result[key]["pids"].add(pid)
                    owner.setdefault(pid, []).append(key)
    if not owner:
        return result
    conns = established() if conns is None else conns
    port = cfg["local_proxy_port"]
    for c in conns:
        for key in owner.get(c.pid, ()):
            ip = c.raddr.ip if hasattr(c.raddr, "ip") else c.raddr[0]
            rport = c.raddr.port if hasattr(c.raddr, "port") else c.raddr[1]
            ips, nets = targets.get(key[0], (set(), []))
            if ip in ("127.0.0.1", "::1") and rport == port:
                result[key]["via"] += 1
            elif ip in ips or in_nets(ip, nets):
                result[key]["direct"] += 1
    return result


def vpn_adapter(pattern: str) -> str | None:
    try:
        stats = psutil.net_if_stats()
        rx = re.compile(pattern, re.I)
    except (OSError, re.error):
        return None
    for name, st in stats.items():
        if st.isup and rx.search(name) and not NOT_VPN.search(name):
            return name
    return None


def network_adapters() -> list[str]:
    """Adapters that are up, for picking the VPN one by name (our own TUN and loopback left out)."""
    try:
        stats = psutil.net_if_stats()
    except OSError:
        return []
    return sorted(n for n, st in stats.items() if st.isup and not re.search(r"loopback|xmeltunnel|xt-route", n, re.I))


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def check_exit(proxy_port: int, url: str = FALLBACK_CHECK) -> tuple[str, str, int]:
    """IP and country Cloudflare sees when we come through the tunnel."""
    proxy = f"http://127.0.0.1:{proxy_port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
    t = time.monotonic()
    with opener.open(url, timeout=15) as r:
        body = r.read(4096).decode("ascii", "replace")
    kv = dict(ln.split("=", 1) for ln in body.splitlines() if "=" in ln)
    return kv.get("ip", "?"), kv.get("loc", "?"), int((time.monotonic() - t) * 1000)


def evaluate(cfg: dict, st: dict) -> tuple[str, list[tuple[str, str]]]:
    """Overall level and a list of (key, human text) problems. Pure, for tests."""
    problems = []
    if has_server(cfg) and not cfg.get("server_enabled", True):
        return OFF, []  # the user disconnected it on purpose: no warnings
    if not has_server(cfg):
        # The server is optional: the routing mode works without it, only profiles need it.
        if pac_profiles(cfg):
            return WARN, [("setup", tr("Profiles need your server: set it up in Settings."))]
        return OFF, []
    if not st["tunnel"]:
        if cfg["require_vpn"] and not st["vpn"]:
            problems.append(("vpn", tr("The server waits for the VPN: it is reachable only through it.")))
        else:
            problems.append(("tunnel", tr("No connection to the server: the SSH tunnel does not come up.")))
    elif st["exit_ok"] is False:
        problems.append(("exit", tr("The tunnel is up, but the exit is not your server ({ip}).",
                                    ip=st["exit_ip"] or "?")))
    for p in cfg["profiles"]:
        if p.get("target", "server") != "server":
            continue  # leaks are about the server path; other targets need the routing mode anyway
        for i, app in enumerate(p["apps"]):
            a = st["apps"].get((p["id"], i))
            if not a or not a["direct"]:
                continue
            if p["enabled"]:
                hint = tr(" Restart it if you turned the profile on just now.") if app["method"] == "claude_code" else ""
                problems.append((f"leak:{p['id']}:{i}", tr("{app} talks to {profile} directly, around your server.",
                                                           app=app["name"], profile=p["name"]) + hint))
            else:
                problems.append((f"off:{p['id']}:{i}", tr("{app} goes direct: the {profile} profile is off.",
                                                          app=app["name"], profile=p["name"])))
    keys = [k for k, _ in problems]
    waiting = "vpn" in keys  # the server is fine, only the VPN it needs is off: yellow, not red
    if (not st["tunnel"] and not waiting) or st["exit_ok"] is False or any(k.startswith("leak") for k in keys):
        level = DOWN
    elif waiting or st["exit_ok"] is None:
        level = WARN
    else:
        level = OK  # the ring is about the connection; switched-off profiles show their own yellow dot
    return level, problems


def launch_message(launched: list[str], key: str, text: str) -> str:
    """Notification text when an app has just started: 'X started, but …'."""
    if launched and key in ("vpn", "tunnel", "exit"):
        keep = len(text) > 1 and text[1].isupper()  # keep "VPN …", lower "No connection …"
        return tr("{apps} started, but {problem}", apps=", ".join(launched),
                  problem=text if keep else text[0].lower() + text[1:])
    return text


# ---------- logging ----------

_log_lock = threading.Lock()


def log_path() -> str:
    return os.path.join(data_dir(), "xmeltunnel.log")


def log(text: str) -> None:
    try:
        path = log_path()
        with _log_lock:
            if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
                os.replace(path, path + ".old")
            with open(path, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text.rstrip() + "\n")
    except OSError:
        pass


def logged(fn):
    def run():
        try:
            fn()
        except Exception:  # noqa: BLE001
            import traceback

            log(f"{fn.__name__} crashed:\n{traceback.format_exc()}")
    return run


def kill_stale_tunnels(cfg: dict) -> None:
    """An ssh (or a link proxy) left over from a killed previous run keeps the port busy — remove it."""
    mark = f"127.0.0.1:{cfg['local_proxy_port']}:127.0.0.1:{cfg['remote_proxy_port']}"
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            line = " ".join(p.info["cmdline"] or [])
            name = (p.info["name"] or "").lower()
            if (name == "ssh.exe" and mark in line) or (name == "sing-box.exe" and "server-proxy.json" in line):
                p.kill()
                log(f"killed ssh left from a previous run (pid {p.pid})")
        except (psutil.Error, OSError):
            pass


def _net_error(e: Exception) -> str:
    """A short human error for a failed download."""
    code = getattr(e, "code", None)
    if code == 404:
        return tr("the service answered 404: the link is wrong or works only in its own app")
    if code:
        return tr("the service answered {code}", code=code)
    return str(getattr(e, "reason", "") or e)[:160] or type(e).__name__


class PacHandler(http.server.BaseHTTPRequestHandler):
    body = b""

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ns-proxy-autoconfig")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *a):
        pass


# ---------- engine ----------

class Engine:
    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or load_config()
        self.ip = server_ip(self.cfg)
        self.proc = None
        self.running = True
        self.lock = threading.Lock()
        self.cfg_lock = threading.RLock()
        self.targets: dict = {}
        self._resolved_at = 0.0
        self.state = {"vpn": None, "tunnel": False, "exit_ok": None, "exit_ip": None, "exit_loc": None,
                      "exit_ms": None, "exit_at": 0, "checking": False, "since": None,
                      "apps": {}, "pac": pac_installed(self.cfg), "autostart": autostart_enabled(),
                      "route": {"status": "off", "error": "", "progress": 0, "checks": {}, "checking": False,
                                "phys": None, "vpn": None},
                      "servers": {"checking": False, "done": 0, "total": 0, "error": "", "updating": False},
                      "update": {"version": None, "status": "idle", "progress": 0, "error": "", "path": "",
                                 "kind": updater.kind(), "checked_at": 0}}
        self.level, self.problems = WARN, []
        self.notes: list[tuple[str, str]] = []
        self._notified: dict[str, float] = {}
        self._seen: dict = {}
        self._exit_now = threading.Event()
        self._restart = threading.Event()
        self._route_check = threading.Event()
        self._update_now = threading.Event()
        self._route_busy = threading.Lock()
        # leak targets are resolved by the monitor thread: DNS can be slow, the window must not wait for it
        self.state["apps"] = scan(self.cfg, self.targets)
        self._seen = {k: set(v["pids"]) for k, v in self.state["apps"].items()}

    # --- for the UI ---

    def snapshot(self) -> tuple[dict, str, list]:
        with self.lock:
            s = dict(self.state)
            s["apps"] = {k: dict(v) for k, v in self.state["apps"].items()}
            s["route"] = dict(self.state["route"], checks=dict(self.state["route"]["checks"]))
            s["update"] = dict(self.state["update"])
            s["servers"] = dict(self.state["servers"])
            return s, self.level, list(self.problems)

    def take_notes(self) -> list[tuple[str, str]]:
        with self.lock:
            notes, self.notes = self.notes, []
            return notes

    def check_now(self) -> None:
        self._exit_now.set()

    def reconnect(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def save(self) -> None:
        with self.cfg_lock:
            save_config(self.cfg)

    def apply_profiles(self, refresh_pac: bool = False) -> None:
        """After profiles changed: PAC body, Windows PAC, Claude Code settings, leak targets."""
        with self.cfg_lock:
            body = pac_text(self.cfg).encode()
            changed = body != PacHandler.body
            PacHandler.body = body
            on = self.cfg.get("server_enabled", True)
            install_pac(self.cfg, on and bool(pac_profiles(self.cfg)), refresh=refresh_pac or changed)
            want = on and wants_claude_code(self.cfg)
            try:
                if want != claude_code_proxy_on(self.cfg):
                    set_claude_code_proxy(self.cfg, want)
            except (OSError, ValueError) as e:
                log(f"Claude Code settings: {e}")
            self.save()
        self._resolved_at = 0.0  # the monitor thread re-resolves; DNS here would freeze the window
        with self.lock:
            self.state["pac"] = pac_installed(self.cfg)
            route_status = self.state["route"]["status"]
        if self.cfg["route_enabled"] and route_status in ("running", "error"):
            self._route_bg(self._route_start)  # the helper reloads sing-box with the new rules

    def set_profile_enabled(self, pid: str, on: bool) -> None:
        with self.cfg_lock:
            for p in self.cfg["profiles"]:
                if p["id"] == pid:
                    p["enabled"] = on
        self.apply_profiles()

    def upsert_profile(self, profile: dict) -> None:
        with self.cfg_lock:
            ps = self.cfg["profiles"]
            idx = next((i for i, p in enumerate(ps) if p["id"] == profile["id"]), None)
            if idx is None:
                ps.append(profile)
            else:
                ps[idx] = profile
        self.apply_profiles()

    def delete_profile(self, pid: str) -> None:
        with self.cfg_lock:
            self.cfg["profiles"] = [p for p in self.cfg["profiles"] if p["id"] != pid]
        self.apply_profiles()

    def set_no_uac(self, on: bool) -> bool:
        """Register or remove the scheduled task (one UAC prompt). Returns whether it is now as asked."""
        ok = routing.install_task() if on else routing.remove_task()
        with self.cfg_lock:
            self.cfg["route_no_uac"] = routing.task_installed()
            self.save()
        log(f"start without UAC: {'on' if self.cfg['route_no_uac'] else 'off'}")
        return ok

    def apply_app_settings(self, values: dict) -> None:
        """App tab of Settings: theme, scale, start options. Autostart lives in the registry, not the config."""
        values = dict(values)
        values.pop("route_no_uac", None)  # handled by set_no_uac: it needs a UAC prompt
        auto = values.pop("autostart", None)
        with self.cfg_lock:
            self.cfg.update(values)
            self.save()
        if auto is not None and auto != autostart_enabled():
            self.set_autostart(auto)

    def set_server_enabled(self, on: bool) -> None:
        """The server card's Connect / Disconnect."""
        with self.cfg_lock:
            self.cfg["server_enabled"] = on
            self.save()
        self.apply_profiles(refresh_pac=on)
        if not on:
            self.reconnect()  # stops ssh / the link proxy; the tunnel thread then waits
        log(f"server: {'connected' if on else 'disconnected'} by the user")

    def set_autostart(self, on: bool) -> None:
        set_autostart(on)
        with self.lock:
            self.state["autostart"] = autostart_enabled()

    def apply_settings(self, new: dict) -> None:
        with self.cfg_lock:
            old = dict(self.cfg)
            pac_was = pac_installed(old)
            code_was = claude_code_proxy_on(old)
            self.cfg.update(new)
            if any(old.get(k) != self.cfg.get(k) for k in ("server", "server_mode", "server_link")):
                self.ip = ""
                # aliases and host names need ssh -G and DNS: not in the window's thread
                threading.Thread(target=lambda: setattr(self, "ip", server_ip(self.cfg)), daemon=True).start()
            if pac_was and old["pac_port"] != self.cfg["pac_port"]:
                install_pac(old, False)
            if code_was and old["local_proxy_port"] != self.cfg["local_proxy_port"]:
                set_claude_code_proxy(old, False)
        self.apply_profiles()
        if old["pac_port"] != self.cfg["pac_port"]:
            self._restart.set()
        ssh_keys = ("server", "ssh_port", "ssh_key", "remote_proxy_port", "local_proxy_port", "server_mode",
                    "server_link")
        if any(old[k] != self.cfg[k] for k in ssh_keys):
            self.reconnect()  # only then: dropping the tunnel for a theme change is pointless

    def start(self) -> None:
        kill_stale_tunnels(self.cfg)
        if pac_profiles(self.cfg):
            self.apply_profiles(refresh_pac=True)  # apps may have fallen back to direct while we were closed  # restore PAC / Claude Code settings if something reset them
        PacHandler.body = pac_text(self.cfg).encode()
        for target in (self._serve_pac, self._tunnel, self._exit_checker, self._monitor, self._route_checker,
                       self._update_checker, self._subscription_updater):
            threading.Thread(target=logged(target), daemon=True).start()
        if routing.helper_alive(data_dir()) or (self.cfg["route_enabled"] and self.cfg["route_on_start"]):
            self._route_bg(self._route_start)  # take over a running helper or start as the user left it

    def stop(self) -> None:
        self.running = False
        self._exit_now.set()
        self.reconnect()

    # --- built-in VPN client: servers ---

    def _servers_set(self, **kw) -> None:
        with self.lock:
            self.state["servers"].update(kw)

    def _servers_changed(self) -> None:
        self.save()
        if self.cfg["route_enabled"] and self.cfg.get("vpn_source") == "servers":
            self._route_bg(self._route_start)

    def add_servers_text(self, text: str) -> tuple[int, list[str]]:
        """Links or a subscription URL. Returns (servers added, errors); a URL is fetched in the background."""
        text = text.strip()
        if re.match(r"^https?://\S+$", text):
            sid = hashlib.sha1(text.encode()).hexdigest()[:10]
            with self.cfg_lock:
                if not any(s["id"] == sid for s in self.cfg["subscriptions"]):
                    self.cfg["subscriptions"].append({"id": sid, "url": text, "title": "", "updated_at": 0,
                                                      "count": 0, "error": "", "info": {}})
                self.save()
            self.refresh_subscriptions([sid])
            return 0, []
        found, errors = servers.parse_text(text)
        with self.cfg_lock:
            have = {s["id"] for s in self.cfg["servers"]}
            new = [s for s in found if s["id"] not in have]
            self.cfg["servers"] += new
        self._servers_changed()
        return len(new), errors

    def refresh_subscriptions(self, ids: list[str] | None = None) -> None:
        def run():
            self._servers_set(updating=True)
            for sub in list(self.cfg["subscriptions"]):
                if ids and sub["id"] not in ids:
                    continue
                try:
                    body, info = servers.fetch_subscription(sub["url"])
                    found, errors = servers.parse_text(body, sub=sub["id"])
                    err = "" if found else ("; ".join(errors[:2]) or tr("no servers in the answer"))
                except Exception as e:  # noqa: BLE001
                    found, info, err = None, {}, _net_error(e)
                with self.cfg_lock:
                    sub.update(updated_at=time.time(), error=err)
                    if found is not None and found:
                        sub.update(count=len(found), info=info, title=info.get("title") or sub.get("title", ""))
                        others = [s for s in self.cfg["servers"] if s.get("sub") != sub["id"]]
                        self.cfg["servers"] = others + found
                log(f"subscription {sub['id']}: {len(found or [])} servers {err}")
            with self.cfg_lock:
                self._servers_changed()
            self._servers_set(updating=False)
        threading.Thread(target=logged(run), daemon=True).start()

    def _subscription_updater(self) -> None:
        """Subscriptions refresh themselves: as often as the service asks (profile-update-interval), else 12 h."""
        time.sleep(60)
        while self.running:
            due = [s["id"] for s in list(self.cfg["subscriptions"])
                   if time.time() - s.get("updated_at", 0) > 3600 * max(1, (s.get("info") or {}).get("update_hours") or 12)]
            if due and not self.state["servers"].get("updating"):
                self.refresh_subscriptions(due)
            if self.cfg.get("sharing_used") and self.cfg.get("ss_key") and \
                    time.time() - getattr(self, "_limits_at", 0) > 6 * 3600:
                self._limits_at = time.time()
                try:  # friends whose time or traffic ran out are paused even if nobody opens the panel
                    from xmeltunnel import sharing

                    st = sharing.fetch(self.cfg)
                    paused = sharing.enforce_limits(st["users"])
                    if paused:
                        sharing.apply(self.cfg, st["users"])
                        log(f"friends paused (time or traffic ran out): {', '.join(paused)}")
                except Exception as e:  # noqa: BLE001 — the server may be unreachable right now
                    log(f"friends' limits: {e!r}")
            for _ in range(30 * 60):
                if not self.running:
                    return
                time.sleep(1)

    def remove_subscription(self, sid: str) -> None:
        with self.cfg_lock:
            self.cfg["subscriptions"] = [s for s in self.cfg["subscriptions"] if s["id"] != sid]
            self.cfg["servers"] = [s for s in self.cfg["servers"] if s.get("sub") != sid]
            self._servers_changed()

    def remove_servers(self, ids: list[str]) -> None:
        with self.cfg_lock:
            self.cfg["servers"] = [s for s in self.cfg["servers"] if s["id"] not in ids]
            if self.cfg["vpn_server"] in ids:
                self.cfg["vpn_server"] = "auto"
            self._servers_changed()

    def set_vpn_source(self, source: str) -> None:
        if source in ("adapter", "servers") and source != self.cfg.get("vpn_source"):
            with self.cfg_lock:
                self.cfg["vpn_source"] = source
                self._servers_changed()

    def set_vpn_server(self, pick: str) -> None:
        if pick != self.cfg.get("vpn_server"):
            with self.cfg_lock:
                self.cfg["vpn_server"] = pick
                self._servers_changed()

    def check_servers(self, ids: list[str] | None = None) -> None:
        """Real requests through each server (see pinger.py), in the background."""
        if self.state["servers"].get("checking"):
            return
        todo = [s for s in self.cfg["servers"] if not ids or s["id"] in ids]
        if not todo:
            return

        def run():
            self._servers_set(checking=True, done=0, total=len(todo), error="")
            try:
                phys = routing.physical_adapter(self.cfg["vpn_adapter"])
                if self.cfg.get("servers_via_adapter"):
                    phys = vpn_adapter(self.cfg["vpn_adapter"]) or phys
                res = pinger.check(data_dir(), todo, phys, lambda d, t: self._servers_set(done=d, total=t))
                with self.cfg_lock:
                    # a new dict, not .update(): the window may be reading the old one right now
                    self.cfg["server_checks"] = {**self.cfg["server_checks"], **res}
                    self._servers_changed() if (self.cfg.get("vpn_server") or "").startswith("auto") else self.save()
            except Exception as e:  # noqa: BLE001
                log(f"server check failed: {e!r}")
                self._servers_set(error=str(e)[:200])
            self._servers_set(checking=False)
        threading.Thread(target=logged(run), daemon=True).start()

    # --- updates ---

    def _update_set(self, **kw) -> None:
        with self.lock:
            self.state["update"].update(kw)

    def check_updates_now(self) -> None:
        self._update_set(status="checking", error="")
        self._update_now.set()

    def set_check_updates(self, on: bool) -> None:
        with self.cfg_lock:
            self.cfg["check_updates"] = on
            self.save()
        if on:
            self._update_now.set()

    def _update_checker(self) -> None:
        manual = self._update_now.wait(UPDATE_FIRST_CHECK)
        while self.running:
            self._update_now.clear()
            if (manual or self.cfg["check_updates"]) and self.state["update"]["kind"] != "source" \
                    and self.state["update"]["status"] not in ("downloading", "ready"):
                self._update_set(status="checking", error="")
                try:
                    version = updater.check()
                    self._update_set(version=version, status="idle", checked_at=time.time())
                    if version and version != self.cfg.get("notified_version"):
                        with self.cfg_lock:
                            self.cfg["notified_version"] = version
                            self.save()
                        with self.lock:
                            self.notes.append((APP_NAME, tr("Version {v} is available. Open XmelTunnel to update.",
                                                            v=version)))
                except Exception as e:  # noqa: BLE001 — no network or GitHub hiccup: try again later
                    log(f"update check failed: {e!r}")
                    self._update_set(status="error", error=str(e) or type(e).__name__, checked_at=time.time())
            elif manual and self.state["update"]["kind"] == "source":
                self._update_set(status="idle", checked_at=time.time())
            manual = self._update_now.wait(UPDATE_CHECK_EVERY)

    def download_update(self) -> None:
        version = self.state["update"]["version"]
        if not version or self.state["update"]["status"] in ("downloading", "ready"):
            return

        def run():
            self._update_set(status="downloading", progress=0, error="")
            try:
                path = updater.download(version, os.path.join(data_dir(), "update"),
                                        lambda pct: self._update_set(progress=pct))
            except Exception as e:  # noqa: BLE001
                log(f"update download failed: {e!r}")
                return self._update_set(status="error", error=tr("Could not download the update: {err}",
                                                                 err=str(e) or type(e).__name__))
            log(f"update {version} downloaded: {path}")
            self._update_set(status="ready", path=path)
        threading.Thread(target=logged(run), daemon=True).start()

    def install_update(self, args: list[str]) -> None:
        """Called by the UI when the download is ready; the UI quits right after."""
        u = self.state["update"]
        if u["kind"] == "setup":
            updater.install_setup(u["path"], args)
        else:
            updater.install_portable(u["path"], u["version"], args)
        log(f"update {u['version']}: installing ({u['kind']})")

    # --- routing mode ---

    def _route_set(self, **kw) -> None:
        with self.lock:
            self.state["route"].update(kw)

    def _route_bg(self, fn) -> None:
        def run():
            if not self._route_busy.acquire(blocking=False):
                return
            try:
                fn()
            finally:
                self._route_busy.release()
        threading.Thread(target=logged(run), daemon=True).start()

    def set_route_enabled(self, on: bool) -> None:
        with self.cfg_lock:
            self.cfg["route_enabled"] = on
            self.save()
        self._route_bg(self._route_start if on else self._route_stop)

    def retry_route(self) -> None:
        if self.cfg["route_enabled"]:
            self._route_bg(self._route_start)

    def check_route(self) -> None:
        self._route_check.set()

    def set_route_default(self, default: str) -> None:
        """Where everything not in an enabled profile goes: direct, vpn or server."""
        if default not in ("direct", "vpn", "server") or default == self.cfg["route_default"]:
            return
        with self.cfg_lock:
            self.cfg["route_default"] = default
            self.save()
        if self.cfg["route_enabled"]:
            self._route_bg(self._route_start)

    def set_server_ss(self, port: int, key: str) -> None:
        with self.cfg_lock:
            self.cfg["ss_port"], self.cfg["ss_key"] = port, key
            self.save()
        if self.cfg["route_enabled"]:
            self._route_bg(self._route_start)

    def _route_start(self) -> None:
        data = data_dir()
        with self.cfg_lock:
            cfg = json.loads(json.dumps(self.cfg))
        try:
            if not routing.sing_box_ok(data):
                self._route_set(status="downloading", progress=0, error="")
                routing.download_sing_box(data, lambda pct: self._route_set(progress=pct))
        except Exception as e:  # noqa: BLE001
            log(f"routing: download failed: {e!r}")
            return self._route_set(status="error", error=tr("Could not download sing-box: {err}", err=str(e)))
        phys = routing.physical_adapter(cfg["vpn_adapter"])
        vpn = vpn_adapter(cfg["vpn_adapter"])
        self._route_set(phys=phys, vpn=vpn)
        if not phys:
            return self._route_set(status="error", error=tr("Normal network adapter not found."))
        bad = routing.problems(cfg, vpn)
        if "noservers" in bad:
            return self._route_set(status="error", error=tr("No VPN server chosen: open «Servers…» and add some."))
        if "novpn" in bad:
            return self._route_set(status="error", error=tr("VPN is off: turn it on (TUN mode) and press Retry."))
        if "noserver" in bad:
            return self._route_set(status="error",
                                   error=tr("Your server part is not installed: Lists… → Install on the server."))
        conf = routing.build_config(cfg, self.ip, phys, vpn)
        path = routing.config_file(data)
        body = json.dumps(conf, ensure_ascii=False, indent=2)
        try:
            with open(path, encoding="utf-8") as f:
                same = f.read() == body
        except OSError:
            same = False
        alive = routing.helper_alive(data)
        if same and alive and routing.read_state(data).get("status") == "running":
            # nothing changed for sing-box (a theme, a PAC-only profile…): no restart, no outage
            self._route_set(status="running", error="", phys=phys, vpn=vpn)
            return
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(path + ".tmp", path)
        if not alive:
            self._route_set(status="starting", error="")
            by_task = cfg.get("route_no_uac") and routing.task_supported() and routing.task_installed()
            if not (routing.run_task(data) if by_task else routing.launch_helper(data)):
                with self.cfg_lock:
                    self.cfg["route_enabled"] = False
                    self.save()
                return self._route_set(status="off", error=tr("Admin rights were not given."))
            for _ in range(120):  # a retry after a stuck adapter takes ~20 s
                time.sleep(0.5)
                if routing.read_state(data).get("status") in ("running", "stopped"):
                    break
        else:
            # the helper restarts sing-box with the new config: wait for its fresh "running"
            self._route_set(status="restarting", error="")
            t0 = time.time()
            for _ in range(60):
                time.sleep(0.5)
                st = routing.read_state(data)
                if st.get("status") == "stopped" or (st.get("status") == "running" and st.get("at", 0) > t0):
                    break
        st = routing.read_state(data)
        if st.get("status") == "running" and routing.helper_alive(data):
            log(f"routing: on (direct={phys}, vpn={vpn})")
            self._route_set(status="running", error="", checks={})
            self._route_check.set()
        else:
            err = st.get("error") or routing.last_log_error(data) or tr("sing-box did not start")
            log(f"routing: failed: {err}")
            self._route_set(status="error", error=err)

    def _route_stop(self) -> None:
        data = data_dir()
        if routing.helper_alive(data):
            routing.request_stop(data)
            for _ in range(30):
                if not routing.helper_alive(data):
                    break
                time.sleep(0.5)
        log("routing: off")
        self._route_set(status="off", error="", checks={})

    def _route_checker(self) -> None:
        retry = 0
        while self.running:
            # a failed path is re-checked soon (sing-box may have been restarting), then every minute
            self._route_check.wait(8 if retry else EXIT_CHECK_EVERY)
            self._route_check.clear()
            if not self.running:
                return
            with self.lock:
                route = dict(self.state["route"])
            data = data_dir()
            if route["status"] in ("error", "starting", "restarting") and self.cfg["route_enabled"] \
                    and routing.helper_alive(data) and routing.read_state(data).get("status") == "running":
                self._route_set(status="running", error="")  # the helper got there after we stopped waiting
                route["status"] = "running"
            if route["status"] != "running":
                retry = max(retry, 1) if route["status"] in ("starting", "restarting") else retry
                continue
            if routing.read_state(data).get("status") == "restarting":
                retry = max(retry, 1)
                continue
            if not routing.helper_alive(data):
                err = routing.read_state(data).get("error") or routing.last_log_error(data) or tr("stopped")
                self._route_set(status="error", error=tr("VPN disconnected: {err}", err=err), checks={})
                continue
            self._route_set(checking=True)
            checks = {}
            for name in routing.CHECK_PORTS:
                if name == "server" and not self.cfg.get("ss_key") and not link_server(self.cfg):
                    continue
                if name == "vpn" and not route["vpn"] and self.cfg.get("vpn_source") != "servers":
                    continue  # no VPN client adapter; the built-in client needs none
                try:
                    checks[name] = routing.check_path(name)
                except Exception as e:  # noqa: BLE001
                    checks[name] = (type(e).__name__, None)
            self._route_set(checks=checks, checking=False)
            failed = any(loc is None for _, loc in checks.values())
            retry = retry + 1 if failed and retry < 3 else 0

    # --- threads ---

    def _serve_pac(self) -> None:
        while self.running:
            port = self.cfg["pac_port"]
            try:
                srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), PacHandler)
            except OSError as e:
                log(f"PAC: port {port} is busy: {e}")
                time.sleep(10)
                continue
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self._restart.wait()
            self._restart.clear()
            srv.shutdown()
            srv.server_close()

    def _link_proxy_cmd(self, cfg: dict) -> list[str] | None:
        """«Your server» by a share link: a local HTTP/SOCKS proxy on sing-box (no admin rights) in place of
        the SSH tunnel. Profiles, Claude Code and the exit check use it exactly like the SSH one."""
        ls = link_server(cfg)
        if not ls:
            return None
        data = data_dir()
        routing.download_sing_box(data)
        conf = {"log": {"level": "warn"},
                "dns": {"servers": [{"type": "https", "tag": "doh", "server": routing.DOH_SERVER}], "final": "doh"},
                "inbounds": [{"type": "mixed", "tag": "in", "listen": "127.0.0.1",
                              "listen_port": int(cfg["local_proxy_port"])}],
                "outbounds": [dict(ls["outbound"], tag="server")],
                "route": {"final": "server", "default_domain_resolver": "doh"}}
        path = os.path.join(routing.route_dir(data), "server-proxy.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(conf, f)
        return [routing.sing_box_path(data), "run", "-c", path, "--disable-color"]

    def _tunnel(self) -> None:
        while self.running:
            cfg = self.cfg
            if not has_server(cfg) or not cfg.get("server_enabled", True):
                time.sleep(1)
                continue
            if cfg.get("server_mode") == "link":
                try:
                    cmd = self._link_proxy_cmd(cfg)
                except Exception as e:  # noqa: BLE001 — e.g. sing-box could not be downloaded
                    log(f"link proxy: {e!r}")
                    cmd = None
                if not cmd:
                    time.sleep(cfg["reconnect_delay"])
                    continue
                self._run_tunnel(cmd, cfg)
                continue
            cmd = ssh_args(cfg) + ["-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15",
                                   "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=15",
                                   "-L", f"127.0.0.1:{cfg['local_proxy_port']}:127.0.0.1:{cfg['remote_proxy_port']}",
                                   cfg["server"]]
            self._run_tunnel(cmd, cfg)

    def _run_tunnel(self, cmd: list[str], cfg: dict) -> None:
        """Run ssh -L or the link proxy until it exits; then wait a little before the next try."""
        if True:
            try:
                self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
            except FileNotFoundError:
                log(f"not found: {cmd[0]}")
                time.sleep(cfg["reconnect_delay"])
                return
            for _ in range(40):
                if self.proc.poll() is not None or port_open(cfg["local_proxy_port"]):
                    break
                time.sleep(0.5)
            if self.proc.poll() is None:
                with self.lock:
                    self.state["since"] = time.time()
                self._exit_now.set()
                self.proc.wait()
            with self.lock:
                self.state["since"] = None
            if self.running:
                time.sleep(cfg["reconnect_delay"])

    def tunnel_up(self) -> bool:
        return bool(self.proc and self.proc.poll() is None and port_open(self.cfg["local_proxy_port"]))

    def check_url(self) -> str:
        return next((p["check_url"] for p in pac_profiles(self.cfg) if p["check_url"]), FALLBACK_CHECK)

    def _exit_checker(self) -> None:
        while self.running:
            self._exit_now.wait(EXIT_CHECK_EVERY)
            self._exit_now.clear()
            if not self.running:
                return
            if not self.tunnel_up():
                with self.lock:
                    self.state.update(exit_ok=None, exit_ip=None)
                continue
            with self.lock:
                self.state["checking"] = True
            try:
                ip, loc, ms = check_exit(self.cfg["local_proxy_port"], self.check_url())
                ok = ip == self.ip or self.cfg.get("server_mode") == "link"
            except Exception as e:  # noqa: BLE001 — any error means the exit does not work
                ip, loc, ms, ok = type(e).__name__, None, None, False
            with self.lock:
                self.state.update(exit_ok=ok, exit_ip=ip, exit_loc=loc, exit_ms=ms, exit_at=time.time(),
                                  checking=False)

    def _refresh_targets(self, force: bool = False) -> None:
        if not force and time.time() - self._resolved_at < RESOLVE_EVERY:
            return
        targets = {}
        for p in list(self.cfg["profiles"]):
            if not p["apps"] or p.get("target", "server") != "server":
                continue
            nets = [ipaddress.ip_network(n) for n in p["nets"]]
            targets[p["id"]] = (resolve_ips(p["domains"]), nets)
        self.targets, self._resolved_at = targets, time.time()

    def _restore_pac(self) -> bool:
        """A profile is on, but the PAC URL is gone from Windows settings.

        VPN clients (Happ, v2rayN, Clash…) reset the system proxy when they disconnect and wipe our
        PAC URL with it. The profile switch is the user's intent, so put the PAC back.
        """
        now = time.time()
        if now - getattr(self, "_pac_restored_at", 0) < 5:
            return False
        self._pac_restored_at = now
        with self.cfg_lock:
            current = _reg_get(INET_KEY, "AutoConfigURL")
            # someone else's PAC (not a reset) is kept as the one to restore later
            if current and not is_our_pac(current, self.cfg):
                self.cfg["prev_autoconfig"] = current
            _reg_set(INET_KEY, "AutoConfigURL", fresh_pac_url(self.cfg))
            _notify_inet_changed()
            self.save()
        log(f"Windows proxy settings were reset (was: {current!r}) — PAC restored")
        return pac_installed(self.cfg)

    def _monitor(self) -> None:
        while self.running:
            self._refresh_targets()
            with self.cfg_lock:
                light = {k: v for k, v in self.cfg.items() if k not in ("servers", "server_checks", "subscriptions")}
                cfg = json.loads(json.dumps(light))
            apps = scan(cfg, self.targets)
            if cfg.get("vpn_source") == "servers":
                # the VPN is XmelTunnel's own client: it is «on» while the routing mode runs
                vpn = tr("built-in client") if self.state["route"]["status"] == "running" else None
            else:
                vpn = vpn_adapter(cfg["vpn_adapter"])
            up = self.tunnel_up()
            pac = pac_installed(cfg)
            if not pac and pac_profiles(cfg) and cfg.get("server_enabled", True):
                pac = self._restore_pac()
            with self.lock:
                self.state.update(vpn=vpn, tunnel=up, apps=apps, pac=pac)
                if not up:
                    self.state.update(exit_ok=None)
                self.level, self.problems = evaluate(cfg, self.state)
            launched = []
            for p in cfg["profiles"]:
                for i, app in enumerate(p["apps"]):
                    key = (p["id"], i)
                    if apps[key]["pids"] and not self._seen.get(key):
                        launched.append(app["name"])
            self._seen = {k: set(v["pids"]) for k, v in apps.items()}
            self._queue_notes(launched)
            time.sleep(POLL_EVERY)

    def _queue_notes(self, launched: list[str]) -> None:
        if not self.problems:
            return
        running = any(a["pids"] for a in self.state["apps"].values())
        now = time.time()
        for key, text in self.problems:
            if key == "setup" or (key.startswith("off") and not launched):
                continue
            relevant = launched or key.startswith("leak") or (key in ("vpn", "tunnel", "exit") and running)
            if not relevant or now - self._notified.get(key, 0) < NOTIFY_COOLDOWN:
                continue
            self._notified[key] = now
            with self.lock:
                self.notes.append((APP_NAME, launch_message(launched, key, text)))
            break  # one notification at a time
