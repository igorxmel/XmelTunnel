"""Render the main window with fake state, without starting the engine or touching Windows settings."""
import os as _os, tempfile as _tf
# Never touch the real %APPDATA%\XmelTunnel: these tools build fake engines that may save.
_tmp = _tf.mkdtemp(prefix="xt-tools-")
_os.environ["APPDATA"] = _os.path.join(_tmp, "appdata")
_os.environ["USERPROFILE"] = _os.path.join(_tmp, "home")

import sys, time, json
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from xmeltunnel import core, i18n, profiles
from xmeltunnel.ui import theme, app as A

lang, scenario, out = sys.argv[1], sys.argv[2], sys.argv[3]
i18n.set_language(lang)
qa = QApplication(sys.argv)
qa.setStyle("Fusion")
theme.apply(_os.environ.get("XT_LIGHT") == "1"); qa.setStyleSheet(theme.stylesheet())
cfg = json.loads(json.dumps(core.DEFAULTS))
cfg["server"] = "" if scenario == "setup" else "root@203.0.113.7"
cfg["profiles"] = [profiles.normalize(dict(profiles.preset("claude"), enabled=True)),
                   profiles.normalize(dict(profiles.preset("gemini"), enabled=True)),
                   profiles.normalize(dict(profiles.preset("antigravity"), enabled=False)),
                   profiles.normalize(dict(profiles.preset("chatgpt"), enabled=False)),
                   profiles.normalize(dict(profiles.preset("blocked"), name="Часто блокируемое", enabled=True)),
                   profiles.normalize({"id": "games", "name": "Игры", "target": "direct", "enabled": True,
                                       "entries": ["D:\\Games\\Tanki\\", "lesta.ru"]})]
class E(core.Engine):
    def start(self): pass
e = E(cfg); e.ip = "203.0.113.7"
apps = {k: {"pids": set(), "via": 0, "direct": 0} for k in e.state["apps"]}
if scenario in ("ok", "leak"):
    apps[("claude", 0)] = {"pids": {1, 2, 3}, "via": 6, "direct": 0}
    apps[("claude", 1)] = {"pids": {9}, "via": 2, "direct": 0}
    e.state.update(tunnel=True, since=time.time() - 3720, exit_ok=True, exit_ip="203.0.113.7", exit_loc="FI",
                   exit_ms=48, exit_at=time.time() - 12, pac=True, vpn="wg0")
    cfg.update(route_enabled=True, ss_key="x")
    e.state["route"].update(status="running", vpn="wg0", checks={"direct": ("198.51.100.23", "DE"),
                                                                  "vpn": ("192.0.2.80", "NL"),
                                                                  "server": ("203.0.113.7", "FI")})
if scenario == "leak":
    apps[("claude", 0)] = {"pids": {1, 2, 3}, "via": 2, "direct": 3}
    cfg["expanded_profiles"] = ["claude"]
if scenario == "down":
    apps[("claude", 1)] = {"pids": {9}, "via": 0, "direct": 0}
    e.state.update(tunnel=False, pac=True)
e.state["apps"] = apps
if _os.environ.get("XT_BUILTIN") == "1":
    from xmeltunnel import servers as _sv
    got, _ = _sv.parse_text("trojan://pw@198.51.100.7:443#%F0%9F%87%AB%F0%9F%87%AE%20Helsinki%20Fast")
    cfg.update(vpn_source="servers", servers=got, vpn_server=got[0]["id"],
               server_checks={got[0]["id"]: {"ms": 84, "ok": 3, "of": 3, "exit_loc": "FI", "exit_ip": "198.51.100.7", "at": 1}})
e.level, e.problems = core.evaluate(cfg, e.state)
w = A.MainWindow(e)
w.port_hack = None
w.resize(1260, 840)
w.show()
if _os.environ.get('XT_PAGE'):
    w.select(_os.environ['XT_PAGE'])
def grab():
    w.refresh(); qa.processEvents(); w.grab().save(out); qa.quit()
QTimer.singleShot(900, grab)
qa.exec()

