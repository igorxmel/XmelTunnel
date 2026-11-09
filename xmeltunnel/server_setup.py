"""Server side: check SSH and install tinyproxy bound to 127.0.0.1 (reachable only through the SSH tunnel)."""

from __future__ import annotations

import re
import subprocess

from xmeltunnel.core import NO_WINDOW, ssh_args
from xmeltunnel.i18n import tr

CHECK_SCRIPT = r"""
echo XT_SSH_OK
code=$(curl -s -m 15 -o /tmp/xt-trace -w '%{http_code}' -x http://127.0.0.1:PORT https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null)
if [ "$code" = "200" ]; then echo "XT_PROXY_OK $(grep '^ip=' /tmp/xt-trace | cut -d= -f2)"; else echo "XT_PROXY_NO $code"; fi
rm -f /tmp/xt-trace
"""

# Debian/Ubuntu (apt), RHEL/Fedora/Alma (dnf/yum), Alpine (apk). Listens on 127.0.0.1 only.
INSTALL_SCRIPT = r"""
set -e
[ "$(id -u)" = 0 ] && SUDO= || SUDO=sudo
PKGS=tinyproxy
command -v curl >/dev/null || PKGS="tinyproxy curl"  # RHEL ships curl-minimal: do not fight it
if command -v apt-get >/dev/null; then
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get update -q >/dev/null
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -q $PKGS >/dev/null
elif command -v dnf >/dev/null; then
  $SUDO dnf install -y -q epel-release >/dev/null 2>&1 || true
  $SUDO dnf install -y -q $PKGS >/dev/null
elif command -v yum >/dev/null; then
  $SUDO yum install -y -q epel-release >/dev/null 2>&1 || true
  $SUDO yum install -y -q $PKGS >/dev/null
elif command -v apk >/dev/null; then
  $SUDO apk add -q $PKGS >/dev/null
else
  echo "XT_ERR no supported package manager (apt, dnf, yum, apk)"; exit 1
fi
CONF=/etc/tinyproxy/tinyproxy.conf
[ -f /etc/tinyproxy.conf ] && [ ! -d /etc/tinyproxy ] && CONF=/etc/tinyproxy.conf
$SUDO mkdir -p "$(dirname $CONF)"
[ -f "$CONF" ] && [ ! -f "$CONF.xmeltunnel-orig" ] && $SUDO cp "$CONF" "$CONF.xmeltunnel-orig"
USER_LINE=$(grep -E '^(User|Group) ' "$CONF.xmeltunnel-orig" 2>/dev/null || printf 'User tinyproxy\nGroup tinyproxy\n')
$SUDO tee "$CONF" >/dev/null <<EOF
# Written by XmelTunnel: reachable only through an SSH tunnel (listens on localhost).
$USER_LINE
Port PORT
Listen 127.0.0.1
Timeout 600
LogLevel Warning
MaxClients 100
Allow 127.0.0.1
DisableViaHeader Yes
ConnectPort 443
ConnectPort 80
EOF
if command -v systemctl >/dev/null && [ -d /run/systemd/system ]; then
  $SUDO systemctl enable tinyproxy >/dev/null 2>&1 || true
  $SUDO systemctl restart tinyproxy
elif command -v rc-service >/dev/null; then
  $SUDO rc-update add tinyproxy default >/dev/null 2>&1 || true
  $SUDO rc-service tinyproxy restart >/dev/null
else  # no init system we know (containers): just start it
  $SUDO pkill -x tinyproxy 2>/dev/null || true
  $SUDO tinyproxy -c "$CONF"
fi
sleep 1
echo XT_INSTALLED
"""


def _run(cfg: dict, script: str, timeout: int) -> subprocess.CompletedProcess:
    cmd = ssh_args(cfg) + ["-o", "ConnectTimeout=12", cfg["server"], "sh -s"]
    # Bytes, not text mode: on Windows text mode turns LF into CRLF and breaks the shell script.
    body = script.replace("PORT", str(int(cfg["remote_proxy_port"]))).replace(chr(13), "").encode()
    r = subprocess.run(cmd, input=body, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
    return subprocess.CompletedProcess(r.args, r.returncode, r.stdout.decode("utf-8", "replace"),
                                       r.stderr.decode("utf-8", "replace"))


def _last_error(r: subprocess.CompletedProcess) -> str:
    lines = [ln for ln in (r.stderr or "").strip().splitlines() if ln.strip()]
    return lines[-1] if lines else f"exit code {r.returncode}"


def check(cfg: dict) -> tuple[bool, bool, str]:
    """(ssh ok, proxy ok, message for the user). Retries: the first SSH over a VPN sometimes drops."""
    last = ""
    for _ in range(2):
        try:
            r = _run(cfg, CHECK_SCRIPT, 45)
        except FileNotFoundError:
            return False, False, tr("SSH failed: {err}", err=f"{cfg['ssh_exe']} not found")
        except subprocess.TimeoutExpired:
            last = "timeout"
            continue
        out = r.stdout or ""
        if "XT_SSH_OK" in out:
            m = re.search(r"XT_PROXY_OK (\S+)", out)
            if m:
                return True, True, tr("SSH works, the proxy answers. Exit IP: {ip}", ip=m.group(1))
            return True, False, tr("SSH works, but there is no proxy on port {port}. Press «Install proxy on the server».",
                                   port=cfg["remote_proxy_port"])
        last = _last_error(r)
    return False, False, tr("SSH failed: {err}", err=last)


def install(cfg: dict) -> tuple[bool, str]:
    try:
        r = _run(cfg, INSTALL_SCRIPT, 600)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, tr("Install failed: {err}", err=type(e).__name__)
    if "XT_INSTALLED" not in (r.stdout or ""):
        m = re.search(r"XT_ERR (.+)", r.stdout or "")
        return False, tr("Install failed: {err}", err=m.group(1) if m else _last_error(r))
    ssh_ok, proxy_ok, msg = check(cfg)
    if proxy_ok:
        ip = msg.rsplit(" ", 1)[-1]
        return True, tr("Proxy installed and answers. Exit IP: {ip}", ip=ip)
    return False, msg
