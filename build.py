"""Build everything into dist/:

    XmelTunnel.exe              portable, single file
    XmelTunnel/                 the app as a folder (goes into the installer)
    XmelTunnel-Setup.exe        per-user installer (needs Inno Setup 6+; skipped if not found)
    *.sha256                    checksums

Run:  .venv\\Scripts\\python build.py
"""

from __future__ import annotations

import glob
import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from xmeltunnel import APP_NAME, __version__  # noqa: E402

PUBLISHER = "igorxmel"
DESCRIPTION = "XmelTunnel: your server for chosen sites and apps"
URL = "https://github.com/igorxmel/XmelTunnel"

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{publisher}'),
      StringStruct('FileDescription', '{description}'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('LegalCopyright', 'Copyright (C) 2026 {publisher}. GPL-3.0-or-later.'),
      StringStruct('OriginalFilename', '{name}.exe'),
      StringStruct('ProductName', '{name}'),
      StringStruct('ProductVersion', '{ver}'),
      StringStruct('Comments', '{url}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def find_iscc() -> str | None:
    for pattern in (r"C:\Program Files*\Inno Setup *\ISCC.exe",
                    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup *\ISCC.exe")):
        found = sorted(glob.glob(pattern))
        if found:
            return found[-1]
    return shutil.which("iscc")


def sha256(path: str) -> None:
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    with open(path + ".sha256", "w", encoding="ascii") as f:
        f.write(f"{h}  {os.path.basename(path)}\n")


def main() -> None:
    os.chdir(ROOT)
    os.makedirs("build", exist_ok=True)
    nums = [int(x) for x in __version__.split(".")] + [0] * 4
    with open("build/version_info.txt", "w", encoding="utf-8") as f:
        f.write(VERSION_INFO.format(tup=tuple(nums[:4]), ver=__version__, name=APP_NAME, publisher=PUBLISHER,
                                    description=DESCRIPTION, url=URL))
    py = sys.executable
    for spec in ("XmelTunnel.spec", "XmelTunnel-dir.spec"):
        subprocess.run([py, "-m", "PyInstaller", "-y", "--log-level", "WARN", spec], check=True)
    sha256("dist/XmelTunnel.exe")
    iscc = find_iscc()
    if not iscc:
        print("Inno Setup not found: installer skipped")
        return
    subprocess.run([iscc, "/Q", f"/DAppVersion={__version__}", f"/DAppPublisher={PUBLISHER}", f"/DAppURL={URL}",
                    "installer.iss"], check=True)
    sha256("dist/XmelTunnel-Setup.exe")
    print("built:", ", ".join(sorted(os.listdir("dist"))))


if __name__ == "__main__":
    main()
