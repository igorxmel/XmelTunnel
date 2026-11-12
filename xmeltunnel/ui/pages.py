"""Pages of the left menu besides the overview: Settings (dialogs.SettingsPanel), Log, Updates."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from xmeltunnel import __version__, core
from xmeltunnel.i18n import tr


def page_head(lay: QVBoxLayout, title: str, subtitle: str) -> None:
    head = QVBoxLayout()
    head.setSpacing(2)
    head.addWidget(QLabel(title, objectName="title"))
    sub = QLabel(subtitle, objectName="subtitle")
    sub.setWordWrap(True)
    head.addWidget(sub)
    lay.addLayout(head)


class LogPage(QWidget):
    def __init__(self):
        super().__init__(objectName="page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(12)
        page_head(lay, tr("Log"), tr("What XmelTunnel did and what went wrong: useful when something does not work."))
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet("QPlainTextEdit { font-family: Consolas, monospace; font-size: 9pt; }")
        lay.addWidget(self.text, 1)
        row = QHBoxLayout()
        for title, fn in ((tr("Refresh"), self.load), (tr("Open the file"), self.open_file),
                          (tr("Open the folder"), lambda: os.startfile(core.data_dir()))):  # noqa: S606
            b = QPushButton(title, objectName="small")
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

    def load(self) -> None:
        try:
            with open(core.log_path(), encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-600:]
        except OSError:
            lines = [tr("The log is empty.")]
        self.text.setPlainText("".join(lines))
        self.text.moveCursor(self.text.textCursor().MoveOperation.End)

    def open_file(self) -> None:
        if not os.path.exists(core.log_path()):
            core.log("log created")
        os.startfile(core.log_path())  # noqa: S606


class UpdatesPage(QWidget):
    def __init__(self, win):
        super().__init__(objectName="page")
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(12)
        page_head(lay, tr("Updates"), tr("XmelTunnel updates itself from its GitHub releases; every file is checked "
                                         "by its checksum before it is installed."))
        self.version = QLabel(objectName="cardTitle")
        lay.addWidget(self.version)
        self.state = QLabel(objectName="note")
        self.state.setWordWrap(True)
        lay.addWidget(self.state)
        row = QHBoxLayout()
        self.b_action = QPushButton(objectName="primary")
        self.b_action.setMinimumWidth(220)
        self.b_action.clicked.connect(win.update_action)
        row.addWidget(self.b_action)
        row.addStretch()
        lay.addLayout(row)
        self.auto = QCheckBox(tr("Check for updates automatically"))
        self.auto.toggled.connect(win.engine.set_check_updates)
        lay.addWidget(self.auto)
        lay.addStretch()

    def update_from(self, u: dict) -> None:
        kind = {"setup": tr("installed version"), "portable": tr("portable version"),
                "source": tr("running from source")}[u["kind"]]
        self.version.setText(f"XmelTunnel {__version__} · {kind}")
        text, visible = self.win.update_text(u)
        self.b_action.setText(text)
        self.b_action.setVisible(visible)
        if u["kind"] == "source":
            state = tr("Running from source: update with git.")
        elif u["status"] == "error":
            state = tr("Update check failed: {err}", err=u["error"])
        elif u["version"]:
            state = tr("Version {v} is available.", v=u["version"])
        elif u["checked_at"]:
            state = tr("This is the latest version.")
        else:
            state = tr("Not checked yet.")
        self.state.setText(state)
        self.auto.blockSignals(True)
        self.auto.setChecked(bool(self.win.engine.cfg.get("check_updates", True)))
        self.auto.blockSignals(False)
