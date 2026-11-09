"""Render the main window with fake state, without starting the engine or touching Windows settings."""
import sys, time, json
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from xmeltunnel import core, i18n, profiles
from xmeltunnel.ui import theme, app as A

lang, scenario, out = sys.argv[1], sys.argv[2], sys.argv[3]
i18n.set_language(lang)
qa = QApplication(sys.argv)
theme.apply(False); qa.setStyleSheet(theme.stylesheet())
cfg = json.loads(json.dumps(core.DEFAULTS))
cfg["server"] = "" if scenario == "setup" else "root@203.0.113.7"
cfg["profiles"] = [profiles.normalize(dict(profiles.preset("claude"), enabled=True)),
                   profiles.normalize(dict(profiles.preset("gemini"), enabled=True)),
                   profiles.normalize(dict(profiles.preset("antigravity"), enabled=False)),
                   profiles.normalize(dict(profiles.preset("chatgpt"), enabled=False))]
class E(core.Engine):
    def start(self): pass
e = E(cfg); e.ip = "203.0.113.7"
apps = {k: {"pids": set(), "via": 0, "direct": 0} for k in e.state["apps"]}
if scenario == "ok":
    apps[("claude", 0)] = {"pids": {1, 2, 3}, "via": 6, "direct": 0}
    apps[("claude", 1)] = {"pids": {9}, "via": 2, "direct": 0}
    e.state.update(tunnel=True, since=time.time() - 3720, exit_ok=True, exit_ip="203.0.113.7", exit_loc="FI",
                   exit_ms=48, exit_at=time.time() - 12, pac=True, vpn="wg0")
elif scenario == "down":
    apps[("claude", 1)] = {"pids": {9}, "via": 0, "direct": 0}
    e.state.update(tunnel=False, pac=True)
e.state["apps"] = apps
e.level, e.problems = core.evaluate(cfg, e.state)
w = A.MainWindow(e)
w.port_hack = None
w.show()
def grab():
    w.refresh(); qa.processEvents(); w.grab().save(out); qa.quit()
QTimer.singleShot(900, grab)
qa.exec()

