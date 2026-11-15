"""«What's new»: once after an update (everything since the version seen last), and from the Updates page."""
from __future__ import annotations

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout

from xmeltunnel import __version__, changelog
from xmeltunnel.i18n import tr
from xmeltunnel.ui.frameless import FramelessDialog

RELEASES = "https://github.com/igorxmel/XmelTunnel/releases"


class WhatsNewDialog(FramelessDialog):
    def __init__(self, parent, entries: list[tuple[str, str]], heading: str, subtitle: str = ""):
        super().__init__(parent, tr("What's new"))
        self.resize(620, 560 if len(entries) > 1 else 460)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)
        lay.addWidget(QLabel(heading, objectName="cardTitle"))
        if subtitle:
            lay.addWidget(QLabel(subtitle, objectName="note"))
        view = QTextBrowser(objectName="whatsNew")
        view.setOpenExternalLinks(True)
        # one version: just its notes; several: newest first, each under its own heading
        if len(entries) == 1:
            view.setMarkdown(entries[0][1])
        else:
            view.setMarkdown("\n\n".join(f"## {tr('Version {v}', v=v)}\n\n{n}" for v, n in entries))
        lay.addWidget(view, 1)
        row = QHBoxLayout()
        allv = QPushButton(tr("All versions"))
        allv.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES)))
        row.addWidget(allv)
        row.addStretch()
        ok = QPushButton(tr("Got it"), objectName="primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        lay.addLayout(row)


def after_update(parent, seen: str) -> None:
    """Shown once after an update: everything that came out since the version seen last."""
    entries = changelog.since(seen, __version__)
    if not entries:
        return
    sub = tr("Updates since version {v}: {n}", v=seen, n=len(entries)) if seen and len(entries) > 1 else ""
    WhatsNewDialog(parent, entries, tr("Updated to {v}", v=__version__), sub).exec()


def history(parent) -> None:
    entries = changelog.since("", __version__)
    if entries:
        WhatsNewDialog(parent, entries, tr("Version {v}", v=__version__)).exec()
