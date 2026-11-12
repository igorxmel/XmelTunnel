import hashlib
import os
import sys

import pytest

from xmeltunnel import updater


def test_versions():
    assert updater.is_newer("0.2.1", "0.2.0")
    assert updater.is_newer("v1.0", "0.9.9")
    assert not updater.is_newer("0.2.0", "0.2.0")
    assert not updater.is_newer("0.3.0-rc.1", "0.3.0")
    assert updater.is_newer("0.3.0", "0.3.0-rc.1")
    assert not updater.is_newer("garbage", "0.1.0")


def test_kind_and_asset(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert updater.kind() == "source"
    exe = tmp_path / "XmelTunnel.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert updater.kind() == "portable" and updater.asset_name() == "XmelTunnel.exe"
    (tmp_path / "unins000.exe").write_bytes(b"x")
    assert updater.kind() == "setup" and updater.asset_name() == "XmelTunnel-Setup.exe"


def test_child_env_drops_onefile_vars(monkeypatch):
    monkeypatch.setenv("_MEIPASS2", r"C:\Temp\_MEI1")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "keep")
    monkeypatch.setattr(sys, "_MEIPASS", r"C:\Temp\_MEI1", raising=False)
    monkeypatch.setenv("PATH", r"C:\Temp\_MEI1;C:\Windows")
    env = updater.child_env()
    assert "_MEIPASS2" not in env and env["LD_LIBRARY_PATH"] == "keep"
    assert env["PATH"] == r"C:\Windows"


def test_install_portable_swaps_files(monkeypatch, tmp_path):
    exe = tmp_path / "XmelTunnel.exe"
    exe.write_bytes(b"old")
    new = tmp_path / "new.exe"
    new.write_bytes(b"new")
    started = []
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(updater, "_staged", "")
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kw: started.append((args, kw)))
    updater.install_portable(str(new), "9.9.9", ["--hidden"])
    assert exe.read_bytes() == b"new" and (tmp_path / "XmelTunnel.old.exe").read_bytes() == b"old"
    assert started[0][0] == [str(exe), updater.RESTART_FLAG, "--hidden"]
    assert updater.newest_here() == "9.9.9"
    # a second update before restarting replaces the staged file and keeps the running one in .old
    newer = tmp_path / "newer.exe"
    newer.write_bytes(b"newer")
    updater.install_portable(str(newer), "9.9.10", [])
    assert exe.read_bytes() == b"newer" and (tmp_path / "XmelTunnel.old.exe").read_bytes() == b"old"


class _Resp:
    def __init__(self, body: bytes):
        self.body, self.headers = body, {"Content-Length": str(len(body))}

    def read(self, n=-1):
        out, self.body = (self.body, b"") if n < 0 else (self.body[:n], self.body[n:])
        return out

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def test_download_checks_hash(monkeypatch, tmp_path):
    payload = b"exe bytes" * 1000
    good = hashlib.sha256(payload).hexdigest()
    files = {"XmelTunnel.exe": payload, "XmelTunnel.exe.sha256": f"{good}  XmelTunnel.exe\n".encode()}
    monkeypatch.setattr(updater, "kind", lambda: "portable")
    monkeypatch.setattr(updater, "_get", lambda url, *a, **k: _Resp(files[url.rsplit("/", 1)[1]]))
    path = updater.download("1.2.3", str(tmp_path))
    assert open(path, "rb").read() == payload
    files["XmelTunnel.exe.sha256"] = ("0" * 64).encode()
    with pytest.raises(updater.UpdateError):
        updater.download("1.2.3", str(tmp_path / "b"))
    assert not os.listdir(tmp_path / "b")
