"""Honest server check: a real request through every server, not a knock on its port.

The latency is sing-box's own URL test (clash API), the number Throne and other sing-box clients show;
many other clients only "ping" a server by opening a TCP connection to its port. That says nothing about whether
the proxy behind it works (a blocked or misconfigured server still accepts TCP), so results look random.
Here a separate sing-box (no admin rights, no TUN) gives every server its own local proxy port, and
each server gets:
  * 3 plain HTTP requests (generate_204) through it; the median time is the latency shown;
  * one request to Cloudflare's trace through it: the real exit IP and country.
Traffic of this check goes out through the normal adapter, around any VPN client and the routing mode.
"""

from __future__ import annotations

import json
import os
import socket
import statistics
import subprocess
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from xmeltunnel import routing

LATENCY_URL = "http://cp.cloudflare.com/generate_204"
TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"
SAMPLES = 3
TIMEOUT = 8
PARALLEL = 16


def _free_base(count: int) -> int:
    """A start port with `count` free ports after it."""
    for base in range(31000, 60000, 500):
        ok = True
        for port in (base, base + count - 1):
            with socket.socket() as s:
                try:
                    s.bind(("127.0.0.1", port))
                except OSError:
                    ok = False
                    break
        if ok:
            return base
    raise RuntimeError("no free local ports")


def build_config(servers: list[dict], base: int, phys: str | None, api_port: int = 0) -> dict:
    inbounds, outbounds, rules = [], [], []
    dial = {"bind_interface": phys} if phys else {}
    for i, s in enumerate(servers):
        inbounds.append({"type": "mixed", "tag": f"in-{i}", "listen": "127.0.0.1", "listen_port": base + i})
        outbounds.append(dict(s["outbound"], tag=f"s-{i}", **dial))
        rules.append({"inbound": [f"in-{i}"], "outbound": f"s-{i}"})
    outbounds.append(dict({"type": "direct", "tag": "direct"}, **dial))
    return {
        "log": {"level": "error"},
        # server host names are resolved over HTTPS: VPN clients block port 53 outside their adapter
        "dns": {"servers": [dict({"type": "https", "tag": "doh", "server": routing.DOH_SERVER},
                                 **({"detour": "direct"} if phys else {}))],
                "final": "doh", "strategy": "prefer_ipv4"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": {"rules": rules, "final": "direct", "default_domain_resolver": "doh"},
        # sing-box's own URL test (the one Throne, Hiddify and other sing-box clients show) answers here
        **({"experimental": {"clash_api": {"external_controller": f"127.0.0.1:{api_port}"}}} if api_port else {}),
    }


def _opener(port: int):
    proxy = f"http://127.0.0.1:{port}"
    return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))


def _delay(api_port: int, tag: str) -> int:
    """sing-box's URL test of one outbound, in ms: the same number sing-box clients (Throne…) show."""
    q = urllib.parse.urlencode({"url": LATENCY_URL, "timeout": TIMEOUT * 1000})
    req = urllib.request.Request(f"http://127.0.0.1:{api_port}/proxies/{tag}/delay?{q}")
    no_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with no_proxy.open(req, timeout=TIMEOUT + 3) as r:
        return int(json.loads(r.read().decode())["delay"])


def _check_one(port: int, api_port: int = 0, tag: str = "") -> dict:
    opener = _opener(port)
    times, error = [], ""
    for _ in range(SAMPLES if not api_port else 2):
        try:
            if api_port:
                times.append(_delay(api_port, tag))  # sing-box measures it, like other clients do
            else:
                t = time.perf_counter()
                with opener.open(LATENCY_URL, timeout=TIMEOUT) as r:
                    r.read(64)
                times.append((time.perf_counter() - t) * 1000)
        except Exception as e:  # noqa: BLE001 — any failure is a result here
            error = _short(e)
            if not times:
                break  # the first one failed: the server does not work, no need to wait for more
    # with the URL test the second try is the fair one: the first includes setting the connection up
    ms = (min(times) if api_port else statistics.median(times)) if times else None
    out = {"ms": int(ms) if ms is not None else None, "ok": len(times), "of": SAMPLES if not api_port else 2,
           "error": "" if times else error, "exit_ip": "", "exit_loc": "", "at": time.time()}
    if times:
        try:
            with opener.open(TRACE_URL, timeout=TIMEOUT) as r:
                kv = dict(ln.split("=", 1) for ln in r.read(4096).decode("ascii", "replace").splitlines() if "=" in ln)
            out["exit_ip"], out["exit_loc"] = kv.get("ip", ""), kv.get("loc", "")
        except Exception:  # noqa: BLE001 — latency is known, the exit just stays unknown
            pass
    return out


def _short(e: Exception) -> str:
    text = str(getattr(e, "reason", "") or e) or type(e).__name__
    for key, nice in (("timed out", "timeout"), ("10061", "refused"), ("10054", "reset"), ("10060", "timeout"),
                      ("Remote end closed", "closed"), ("EOF", "closed"), ("Bad Gateway", "no connection"),
                      ("502", "no connection"), ("Service Unavailable", "no answer"),
                      ("Gateway Timeout", "timeout")):
        if key in text:
            return nice
    return text[:60]


def check(data: str, servers: list[dict], phys: str | None, progress=None, stop=None) -> dict[str, dict]:
    """{server id: result}. progress(done, total) is called from worker threads."""
    if not servers:
        return {}
    routing.download_sing_box(data)
    base = _free_base(len(servers) + 1)
    api_port = base + len(servers)
    folder = routing.route_dir(data)
    conf = os.path.join(folder, "ping.json")
    with open(conf, "w", encoding="utf-8") as f:
        json.dump(build_config(servers, base, phys, api_port), f)
    log = os.path.join(folder, "ping.log")
    proc = subprocess.Popen([routing.sing_box_path(data), "run", "-c", conf, "--disable-color"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=open(log, "w", encoding="utf-8"),
                            creationflags=routing.NO_WINDOW)
    results: dict[str, dict] = {}
    try:
        deadline = time.time() + 15
        last = base + len(servers) - 1
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(_tail(log) or "sing-box stopped")
            try:
                with socket.create_connection(("127.0.0.1", last), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        done = [0]

        def work(i: int) -> None:
            if stop is not None and stop.is_set():
                return
            results[servers[i]["id"]] = _check_one(base + i, api_port, f"s-{i}")
            done[0] += 1
            if progress:
                progress(done[0], len(servers))

        with ThreadPoolExecutor(PARALLEL) as pool:
            list(pool.map(work, range(len(servers))))
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return results


def _tail(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        return lines[-1][-200:] if lines else ""
    except OSError:
        return ""
