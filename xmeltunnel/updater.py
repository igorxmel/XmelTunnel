"""Self-update for both builds.

Portable XmelTunnel.exe: a running exe can't be overwritten but can be renamed. The old file moves to
XmelTunnel.old.exe, the new one takes its place, the app restarts and deletes .old on the next start.

Installed (Setup): the new XmelTunnel-Setup.exe runs silently once this app has exited; the installer
starts the app again. That keeps Windows "Installed apps" (version, uninstaller) right.

The latest version comes from github.com/<repo>/releases/latest (a redirect), not from the API:
the API is rate-limited per IP, and providers put many users behind one IP. Every download is checked
against the .sha256 file published in the same release; without it nothing is installed.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

from xmeltunnel import __version__

REPO = "igorxmel/XmelTunnel"
SITE = "https://github.com"
UA = f"XmelTunnel/{__version__}"
PORTABLE_ASSET = "XmelTunnel.exe"
SETUP_ASSET = "XmelTunnel-Setup.exe"
RESTART_FLAG = "--restarted"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_staged = ""  # portable: a newer exe already sits in place and waits for a restart


class UpdateError(Exception):
    pass


# ---------- versions ----------

def parse_version(text: str) -> tuple:
    """'v0.2.1' -> (0, 2, 1, 1); a pre-release ('0.3.0-rc.1') sorts below its release."""
    text = text.strip().lstrip("vV")
    main, _, pre = text.partition("-")
    nums = tuple(int(n) for n in re.findall(r"\d+", main)[:3])
    nums += (0,) * (3 - len(nums))
    return nums + ((0, pre) if pre else (1, ""))


def is_newer(candidate: str, current: str) -> bool:
    try:
        return parse_version(candidate) > parse_version(current)
    except ValueError:
        return False


def newest_here() -> str:
    return _staged or __version__


# ---------- which build is this ----------

def kind() -> str:
    """'setup', 'portable' or 'source' (from source git does the updating)."""
    if not getattr(sys, "frozen", False):
        return "source"
    folder = os.path.dirname(os.path.abspath(sys.executable))
    return "setup" if os.path.exists(os.path.join(folder, "unins000.exe")) else "portable"


def asset_name(build: str | None = None) -> str:
    return SETUP_ASSET if (build or kind()) == "setup" else PORTABLE_ASSET


# ---------- GitHub ----------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def _get(url: str, timeout: int = 20, follow: bool = True):
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(_NoRedirect)
    return opener.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout)


def latest(repo: str = REPO, timeout: int = 20) -> tuple[str, list[str]]:
    """(version, asset names) of the latest non-pre-release."""
    try:
        r = _get(f"{SITE}/{repo}/releases/latest", timeout, follow=False)
        location = r.headers.get("Location", "")
    except urllib.error.HTTPError as e:  # 302 comes back as an "error" without the redirect handler
        location = e.headers.get("Location", "")
    m = re.search(r"/releases/tag/([^/?#]+)$", location)
    if not m:
        raise UpdateError("GitHub did not name the latest release")
    tag = m.group(1)
    with _get(f"{SITE}/{repo}/releases/expanded_assets/{tag}", timeout) as r:
        page = r.read().decode("utf-8", "replace")
    prefix = f"/{repo}/releases/download/{tag}/"
    names = list(dict.fromkeys(urllib.request.unquote(x) for x in re.findall(
        rf'href="{re.escape(prefix)}([^"]+)"', page)))
    return urllib.request.unquote(tag).lstrip("vV"), names


def check(repo: str = REPO) -> str | None:
    """A newer version than the one on disk, or None."""
    version, names = latest(repo)
    if not is_newer(version, newest_here()):
        return None
    if asset_name() not in names or asset_name() + ".sha256" not in names:
        return None  # nothing we could install and verify
    return version


def download(version: str, folder: str, progress=None, repo: str = REPO) -> str:
    """Download this build's asset into folder and verify it. Returns the file path."""
    name = asset_name()
    base = f"{SITE}/{repo}/releases/download/v{version}/"
    with _get(base + name + ".sha256") as r:
        expected = r.read(4096).decode("ascii", "replace").split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise UpdateError("the release has no valid checksum")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, name)
    part = target + ".part"
    h = hashlib.sha256()
    with _get(base + name, 60) as r, open(part, "wb") as f:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while chunk := r.read(1 << 16):
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(done * 100 // total)
    if h.hexdigest() != expected:
        os.remove(part)
        raise UpdateError("the download does not match the release checksum")
    os.replace(part, target)
    return target


# ---------- installing ----------

def child_env() -> dict:
    """Environment for starting our exe from a one-file build.

    A one-file build unpacks itself to a temp folder and leaves its path in _MEIPASS2 and friends.
    A child that sees them uses the parent's folder, which vanishes when the parent exits:
    the new version then dies with "no Qt platform plugin could be initialized".
    """
    env = dict(os.environ)
    for k in ("_MEIPASS2", "_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL"):
        env.pop(k, None)
    for k in [k for k in env if k.endswith("_ORIG")]:
        orig = env.pop(k)
        if orig:
            env[k[:-5]] = orig
        else:
            env.pop(k[:-5], None)
    tmp = getattr(sys, "_MEIPASS", "")
    if tmp:
        for k in ("PATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
            if k in env:
                parts = [p for p in env[k].split(os.pathsep) if p and not p.startswith(tmp)]
                env[k] = os.pathsep.join(parts)
    return env


def cleanup() -> None:
    """Portable: delete the exe the last update moved aside (it was busy until now)."""
    if kind() != "portable":
        return
    exe = os.path.abspath(sys.executable)
    old = os.path.splitext(exe)[0] + ".old.exe"
    try:
        if os.path.exists(old):
            os.remove(old)
    except OSError:
        pass


def install_portable(downloaded: str, version: str, args: list[str]) -> None:
    """Put the new exe in place of the running one and start it. The caller then quits."""
    global _staged
    exe = os.path.abspath(sys.executable)
    old = os.path.splitext(exe)[0] + ".old.exe"
    if _staged:
        # .old is the running app; in place sits the previous, never-started update — just replace it
        os.replace(downloaded, exe)
    else:
        try:
            if os.path.exists(old):
                os.remove(old)
        except OSError as e:
            raise UpdateError("the previous version's file is still busy: restart XmelTunnel and retry") from e
        os.replace(exe, old)
        try:
            os.replace(downloaded, exe)
        except OSError as e:
            os.replace(old, exe)
            raise UpdateError(f"could not put the new version in place: {e}") from e
    _staged = version
    subprocess.Popen([exe, RESTART_FLAG, *args], close_fds=True, cwd=os.path.dirname(exe), env=child_env())


def install_setup(downloaded: str, args: list[str]) -> None:
    """Run the installer silently after this process exits; it starts the app again."""
    me = os.getpid()
    extra = " ".join(args)
    # Setup checks the app's mutex first, so it must wait for us to quit. A hidden PowerShell waits.
    ps = (f"Wait-Process -Id {me} -ErrorAction SilentlyContinue; "
          f"Start-Process -FilePath '{downloaded}' -ArgumentList "
          f"'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/XTARGS=\"{extra}\"'")
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                     close_fds=True, creationflags=NO_WINDOW, env=child_env())


def wait_for_previous(seconds: float = 20) -> None:
    """After a restart: wait until the old instance has let go of its mutex."""
    import time

    try:
        import ctypes

        k32 = ctypes.windll.kernel32
    except Exception:  # noqa: BLE001
        return
    deadline = time.time() + seconds
    while time.time() < deadline:
        h = k32.OpenMutexW(0x00100000, False, "XmelTunnelAppMutex")  # SYNCHRONIZE
        if not h:
            return
        k32.CloseHandle(h)
        time.sleep(0.3)
