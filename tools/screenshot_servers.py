"""Render the «VPN servers» dialog with made-up servers and check results (no network, no real config)."""
import os as _os, tempfile as _tf
# Never touch the real %APPDATA%\XmelTunnel: these tools build fake engines that may save.
_tmp = _tf.mkdtemp(prefix="xt-tools-")
_os.environ["APPDATA"] = _os.path.join(_tmp, "appdata")
_os.environ["USERPROFILE"] = _os.path.join(_tmp, "home")

import json, sys, time
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from xmeltunnel import core, i18n, servers
from xmeltunnel.ui import theme
from xmeltunnel.ui.servers_dialog import ServersDialog

lang, out = sys.argv[1], sys.argv[2]
i18n.set_language(lang)
qa = QApplication(sys.argv)
theme.apply(_os.environ.get("XT_LIGHT") == "1"); qa.setStyleSheet(theme.stylesheet())
U = "11111111-2222-3333-4444-555555555555"
spec = [("🇫🇮 Helsinki", "vless", 84, "FI"), ("🇫🇮 Helsinki 2", "vless", 131, "FI"), ("🇩🇪 Frankfurt", "trojan", 62, "DE"),
        ("🇳🇱 Amsterdam", "vmess", 97, "NL"), ("🇳🇱 Amsterdam Hy2", "hysteria2", 54, "NL"), ("🇺🇸 New York", "vless", 241, "US"),
        ("🇯🇵 Tokyo", "tuic", 412, "JP"), ("🇹🇷 Istanbul", "shadowsocks", None, ""), ("🇬🇧 London", "vless", 118, "DE"),
        ("🇵🇱 Warsaw", "trojan", 73, "PL")]
links = []
for i, (name, proto, _, _) in enumerate(spec):
    host = f"198.51.100.{10 + i}"
    links.append({"vless": f"vless://{U}@{host}:443?security=reality&pbk=k&sid=1&sni=a.example#{name}",
                  "trojan": f"trojan://pw@{host}:443#{name}", "hysteria2": f"hy2://pw@{host}:443#{name}",
                  "tuic": f"tuic://{U}:pw@{host}:443#{name}", "shadowsocks": f"ss://aes-256-gcm:pw@{host}:8388#{name}",
                  "vmess": "vmess://" + __import__("base64").b64encode(json.dumps(
                      {"ps": name, "add": host, "port": "443", "id": U, "net": "tcp"}).encode()).decode()}[proto])
got, _ = servers.parse_text("\n".join(links), sub="demo")
cfg = json.loads(json.dumps(core.DEFAULTS))
cfg.update(server="root@203.0.113.7", profiles=[], servers=got, vpn_source="servers", vpn_server=got[4]["id"],
           subscriptions=[{"id": "demo", "url": "https://sub.example.com/abc", "title": "My VPN", "updated_at": time.time() - 1500,
                           "count": len(got), "error": "", "info": {"total": 200 * 2**30, "upload": 3 * 2**30,
                                                                     "download": 38 * 2**30, "expire": time.time() + 20 * 86400}}])
cfg["server_checks"] = {s["id"]: ({"ms": ms, "ok": 3, "of": 3, "exit_loc": loc, "exit_ip": s["host"], "error": "", "at": time.time()}
                                  if ms else {"ms": None, "ok": 0, "of": 3, "error": "timeout", "exit_loc": "", "at": time.time()})
                        for s, (_, _, ms, loc) in zip(got, spec)}
class E(core.Engine):
    def start(self): pass
d = ServersDialog(None, E(cfg)); d.show()
QTimer.singleShot(900, lambda: (d.grab().save(out), qa.quit())); qa.exec()
