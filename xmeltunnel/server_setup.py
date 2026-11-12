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


# Routing mode: Shadowsocks 2022 on sing-box (TCP + UDP, so games work). Pinned official build, checked by SHA-256.
# The key is made on the server once and kept in /etc/xmeltunnel (root only); re-running keeps it.
SS_SCRIPT = r"""
set -e
[ "$(id -u)" = 0 ] && SUDO= || SUDO=sudo
V=@@VER@@
case "$(uname -m)" in
  x86_64|amd64) A=amd64; H=@@SHA_AMD64@@ ;;
  aarch64|arm64) A=arm64; H=@@SHA_ARM64@@ ;;
  *) echo "XT_ERR unsupported CPU: $(uname -m)"; exit 1 ;;
esac
BIN=/usr/local/bin/sing-box
if ! { [ -x $BIN ] && $BIN version 2>/dev/null | grep -q "version $V"; }; then
  command -v curl >/dev/null || { echo "XT_ERR curl is missing: install the proxy first"; exit 1; }
  T=$(mktemp -d)
  curl -fsSL -m 300 -o $T/sb.tgz "https://github.com/SagerNet/sing-box/releases/download/v$V/sing-box-$V-linux-$A.tar.gz" \
    || { echo "XT_ERR could not download sing-box from GitHub"; rm -rf $T; exit 1; }
  echo "$H  $T/sb.tgz" | sha256sum -c - >/dev/null 2>&1 || { echo "XT_ERR sing-box checksum mismatch"; rm -rf $T; exit 1; }
  tar -xzf $T/sb.tgz -C $T
  $SUDO install -m 755 $T/sing-box-$V-linux-$A/sing-box $BIN
  rm -rf $T
fi
$SUDO mkdir -p /etc/xmeltunnel
$SUDO chmod 700 /etc/xmeltunnel
[ -s /etc/xmeltunnel/ss.key ] || $BIN generate rand --base64 16 | $SUDO tee /etc/xmeltunnel/ss.key >/dev/null
KEY=$($SUDO cat /etc/xmeltunnel/ss.key)
$SUDO tee /etc/xmeltunnel/ss.json >/dev/null <<EOF
{"log": {"level": "warn"},
 "inbounds": [{"type": "shadowsocks", "listen": "::", "listen_port": @@SSPORT@@,
               "method": "2022-blake3-aes-128-gcm", "password": "$KEY"}],
 "outbounds": [{"type": "direct"}]}
EOF
$SUDO chmod 600 /etc/xmeltunnel/ss.json /etc/xmeltunnel/ss.key
$BIN check -c /etc/xmeltunnel/ss.json
if command -v systemctl >/dev/null && [ -d /run/systemd/system ]; then
  $SUDO tee /etc/systemd/system/xmeltunnel-ss.service >/dev/null <<EOF
[Unit]
Description=XmelTunnel routing mode (Shadowsocks)
After=network-online.target
[Service]
ExecStart=$BIN run -c /etc/xmeltunnel/ss.json
Restart=on-failure
LimitNOFILE=65535
[Install]
WantedBy=multi-user.target
EOF
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable xmeltunnel-ss >/dev/null 2>&1
  $SUDO systemctl restart xmeltunnel-ss
else
  $SUDO pkill -f "xmeltunnel/ss.json" 2>/dev/null || true
  $SUDO sh -c "nohup $BIN run -c /etc/xmeltunnel/ss.json >/dev/null 2>&1 &"
fi
if command -v ufw >/dev/null && $SUDO ufw status 2>/dev/null | grep -q "Status: active"; then
  $SUDO ufw allow @@SSPORT@@ >/dev/null
elif command -v firewall-cmd >/dev/null && $SUDO firewall-cmd --state >/dev/null 2>&1; then
  $SUDO firewall-cmd -q --permanent --add-port=@@SSPORT@@/tcp --add-port=@@SSPORT@@/udp && $SUDO firewall-cmd -q --reload
fi
sleep 1
if command -v systemctl >/dev/null && [ -d /run/systemd/system ]; then
  systemctl is-active -q xmeltunnel-ss || { echo "XT_ERR the service did not start"; exit 1; }
fi
echo "XT_SS_OK $KEY"
"""
SING_BOX_LINUX_SHA = {"amd64": "699a1b510aa4396b2176d32d1181920399ebf1e267835da6f3b598d0f7c24968",
                      "arm64": "436441f76ee2f7fe21b5b2d426d3cb261a480455a704865789ad533e4273ec26"}


def _run(cfg: dict, script: str, timeout: int, extra: dict | None = None) -> subprocess.CompletedProcess:
    cmd = ssh_args(cfg) + ["-o", "ConnectTimeout=12", cfg["server"], "sh -s"]
    for k, v in (extra or {}).items():
        script = script.replace(k, v)
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


def install_ss(cfg: dict, port: int) -> tuple[bool, str, str]:
    """Install the routing mode's server part. (ok, message, key)."""
    from xmeltunnel.routing import SING_BOX_VERSION

    extra = {"@@VER@@": SING_BOX_VERSION, "@@SHA_AMD64@@": SING_BOX_LINUX_SHA["amd64"],
             "@@SHA_ARM64@@": SING_BOX_LINUX_SHA["arm64"], "@@SSPORT@@": str(int(port))}
    try:
        r = _run(cfg, SS_SCRIPT, 600, extra)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, tr("Install failed: {err}", err=type(e).__name__), ""
    m = re.search(r"XT_SS_OK (\S+)", r.stdout or "")
    if not m:
        e = re.search(r"XT_ERR (.+)", r.stdout or "")
        return False, tr("Install failed: {err}", err=e.group(1) if e else _last_error(r)), ""
    return True, tr("Shadowsocks is installed on port {port}. If your hosting has its own firewall "
                    "in the control panel, open TCP and UDP {port} there.", port=port), m.group(1)
