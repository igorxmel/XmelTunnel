"""Everything except the UI: config, SSH tunnel, PAC file, Windows proxy settings, leak watching.

The UI only reads Engine.snapshot() and calls its methods; all work happens in background threads.
"""

from __future__ import annotations

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

from xmeltunnel import APP_NAME, profiles
from xmeltunnel.i18n import tr

try:
    import winreg
except ImportError:  # tests on non-Windows
    winreg = None

OK, WARN, DOWN, OFF = "ok", "warn", "down", "unknown"

DEFAULTS = {
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
    "vpn_adapter": r"happ|xray|wireguard|wintun|clash|sing-?box|outline|amnezia|throne|vpn|tun",
    "profiles": None,                   # None = first run, filled with presets
    "prev_autoconfig": None,            # the user's own PAC URL before we replaced it
}
EDITABLE = ("server", "ssh_port", "ssh_key", "remote_proxy_port", "local_proxy_port", "pac_port", "language",
            "require_vpn", "vpn_adapter")

FALLBACK_CHECK = "https://www.cloudflare.com/cdn-cgi/trace"
NOT_VPN = re.compile(r"tailscale|virtualbox|hyper-v|vethernet|vmware|loopback", re.I)
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
    try:
        with open(path or config_path(), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass  # broken or missing file must not kill the app
    cfg["server"] = normalize_server(str(cfg["server"]))
    cfg["profiles"] = [profiles.normalize(p) for p in (cfg["profiles"] or profiles.default_profiles())]
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


def server_ip(cfg: dict) -> str:
    """Server IP from user@IP, otherwise via `ssh -G` (aliases) and DNS."""
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

def enabled_profiles(cfg: dict) -> list[dict]:
    return [p for p in cfg["profiles"] if p["enabled"]]


def pac_text(cfg: dict) -> str:
    domains = sorted({d for p in enabled_profiles(cfg) for d in p["domains"]})
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
    return _reg_get(INET_KEY, "AutoConfigURL") == pac_url(cfg)


def install_pac(cfg: dict, on: bool) -> None:
    """Point Windows at our PAC file, remembering and later restoring the user's own one."""
    current = _reg_get(INET_KEY, "AutoConfigURL")
    if on and current != pac_url(cfg):
        cfg["prev_autoconfig"] = current
        _reg_set(INET_KEY, "AutoConfigURL", pac_url(cfg))
    elif not on and current == pac_url(cfg):
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
    return any(a["method"] == "claude_code" for p in enabled_profiles(cfg) for a in p["apps"])


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --hidden'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pythonw}" -m xmeltunnel --hidden'


def autostart_enabled() -> bool:
    return _reg_get(RUN_KEY, RUN_NAME) == autostart_command()


def set_autostart(on: bool) -> None:
    _reg_set(RUN_KEY, RUN_NAME, autostart_command() if on else None)


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
    if not cfg["server"]:
        return WARN, [("setup", tr("Server is not set up yet"))]
    if not st["tunnel"]:
        if cfg["require_vpn"] and not st["vpn"]:
            problems.append(("vpn", tr("VPN is off: turn it on, the server is reachable only through it.")))
        else:
            problems.append(("tunnel", tr("No connection to the server: the SSH tunnel does not come up.")))
    elif st["exit_ok"] is False:
        problems.append(("exit", tr("The tunnel is up, but the exit is not your server ({ip}).",
                                    ip=st["exit_ip"] or "?")))
    for p in cfg["profiles"]:
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
    if not st["tunnel"] or st["exit_ok"] is False or any(k.startswith("leak") for k in keys):
        level = DOWN
    elif not enabled_profiles(cfg) or st["exit_ok"] is None or any(k.startswith("off") for k in keys):
        level = WARN
    else:
        level = OK
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
    """An ssh left over from a killed previous run keeps the port busy — remove it."""
    mark = f"127.0.0.1:{cfg['local_proxy_port']}:127.0.0.1:{cfg['remote_proxy_port']}"
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() == "ssh.exe" and mark in " ".join(p.info["cmdline"] or []):
                p.kill()
                log(f"killed ssh left from a previous run (pid {p.pid})")
        except (psutil.Error, OSError):
            pass


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
                      "apps": {}, "pac": pac_installed(self.cfg), "autostart": autostart_enabled()}
        self.level, self.problems = WARN, []
        self.notes: list[tuple[str, str]] = []
        self._notified: dict[str, float] = {}
        self._seen: dict = {}
        self._exit_now = threading.Event()
        self._restart = threading.Event()
        self._refresh_targets(force=True)
        self.state["apps"] = scan(self.cfg, self.targets)
        self._seen = {k: set(v["pids"]) for k, v in self.state["apps"].items()}

    # --- for the UI ---

    def snapshot(self) -> tuple[dict, str, list]:
        with self.lock:
            s = dict(self.state)
            s["apps"] = {k: dict(v) for k, v in self.state["apps"].items()}
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

    def apply_profiles(self) -> None:
        """After profiles changed: PAC body, Windows PAC, Claude Code settings, leak targets."""
        with self.cfg_lock:
            PacHandler.body = pac_text(self.cfg).encode()
            install_pac(self.cfg, bool(enabled_profiles(self.cfg)))
            want = wants_claude_code(self.cfg)
            try:
                if want != claude_code_proxy_on(self.cfg):
                    set_claude_code_proxy(self.cfg, want)
            except (OSError, ValueError) as e:
                log(f"Claude Code settings: {e}")
            self.save()
        self._refresh_targets(force=True)
        with self.lock:
            self.state["pac"] = pac_installed(self.cfg)

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
            self.ip = server_ip(self.cfg)
            if pac_was and old["pac_port"] != self.cfg["pac_port"]:
                install_pac(old, False)
            if code_was and old["local_proxy_port"] != self.cfg["local_proxy_port"]:
                set_claude_code_proxy(old, False)
        self.apply_profiles()
        if old["pac_port"] != self.cfg["pac_port"]:
            self._restart.set()
        self.reconnect()

    def start(self) -> None:
        kill_stale_tunnels(self.cfg)
        if enabled_profiles(self.cfg):
            self.apply_profiles()  # restore PAC / Claude Code settings if something reset them
        PacHandler.body = pac_text(self.cfg).encode()
        for target in (self._serve_pac, self._tunnel, self._exit_checker, self._monitor):
            threading.Thread(target=logged(target), daemon=True).start()

    def stop(self) -> None:
        self.running = False
        self._exit_now.set()
        self.reconnect()

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

    def _tunnel(self) -> None:
        while self.running:
            cfg = self.cfg
            if not cfg["server"]:
                time.sleep(1)
                continue
            cmd = ssh_args(cfg) + ["-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15",
                                   "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=15",
                                   "-L", f"127.0.0.1:{cfg['local_proxy_port']}:127.0.0.1:{cfg['remote_proxy_port']}",
                                   cfg["server"]]
            try:
                self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
            except FileNotFoundError:
                log(f"ssh not found: {cfg['ssh_exe']}")
                time.sleep(cfg["reconnect_delay"])
                continue
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
        return next((p["check_url"] for p in enabled_profiles(self.cfg) if p["check_url"]), FALLBACK_CHECK)

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
                ok = ip == self.ip
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
            if not p["apps"]:
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
            if current and current != pac_url(self.cfg):
                self.cfg["prev_autoconfig"] = current
            _reg_set(INET_KEY, "AutoConfigURL", pac_url(self.cfg))
            _notify_inet_changed()
            self.save()
        log(f"Windows proxy settings were reset (was: {current!r}) — PAC restored")
        return pac_installed(self.cfg)

    def _monitor(self) -> None:
        while self.running:
            self._refresh_targets()
            with self.cfg_lock:
                cfg = json.loads(json.dumps(self.cfg))
            apps = scan(cfg, self.targets)
            vpn = vpn_adapter(cfg["vpn_adapter"])
            up = self.tunnel_up()
            pac = pac_installed(cfg)
            if not pac and enabled_profiles(cfg):
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
