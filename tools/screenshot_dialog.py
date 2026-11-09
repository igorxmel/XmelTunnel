import sys, json
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from xmeltunnel import core, i18n, profiles
from xmeltunnel.ui import theme
from xmeltunnel.ui.dialogs import ProfileDialog, SettingsDialog
i18n.set_language(sys.argv[1])
qa = QApplication(sys.argv)
theme.apply(False); qa.setStyleSheet(theme.stylesheet())
cfg = json.loads(json.dumps(core.DEFAULTS)); cfg["server"] = "root@203.0.113.7"
cfg["profiles"] = [profiles.normalize(dict(profiles.preset("claude"), enabled=True))]
class E(core.Engine):
    def start(self): pass
e = E(cfg)
d = SettingsDialog(None, e) if sys.argv[2] == "settings" else ProfileDialog(None, e, None)
if sys.argv[2] == "profile":
    d.preset.setCurrentIndex(3)
d.show()
QTimer.singleShot(700, lambda: (d.grab().save(sys.argv[3]), qa.quit()))
qa.exec()

