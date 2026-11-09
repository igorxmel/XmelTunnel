import json
from collections import namedtuple

import pytest

from xmeltunnel import core, i18n, profiles

Addr = namedtuple("Addr", "ip port")
Conn = namedtuple("Conn", "pid raddr status")

CLAUDE_DESKTOP = r"C:\Program Files\WindowsApps\Claude_4.2_x64__abc\app\Claude.exe"
CLAUDE_CODE = r"C:\Users\u\AppData\Roaming\Claude\claude-code\2.1\x\claude.exe"


@pytest.fixture(autouse=True)
def english():
    i18n.set_language("en")


def cfg(**kw):
    c = json.loads(json.dumps(core.DEFAULTS))
    c.update(server="root@1.2.3.4", profiles=[dict(profiles.preset("claude"), enabled=True)])
    c.update(kw)
    c["profiles"] = [profiles.normalize(p) for p in c["profiles"]]
    return c


def state(**kw):
    s = {"vpn": "wg0", "tunnel": True, "exit_ok": True, "exit_ip": "1.2.3.4", "apps": {}}
    s.update(kw)
    return s


# --- profiles ---

def test_clean_domain():
    assert profiles.clean_domain("https://www.Example.com/path?x") == "www.example.com"
    assert profiles.clean_domain("*.example.org") == "example.org"
    assert profiles.clean_domain("not a domain") is None
    assert profiles.clean_domain("localhost") is None


def test_parse_domains():
    ok, bad = profiles.parse_domains("a.com, b.org\nhttps://c.net/x  ?? a.com")
    assert ok == ["a.com", "b.org", "c.net"] and bad == ["??"]


def test_presets_are_valid():
    for p in profiles.PRESETS:
        n = profiles.normalize(p)
        assert len(n["domains"]) == len(p["domains"]), p["id"]
        assert len(n["apps"]) == len(p["apps"]), p["id"]


def test_app_matching():
    claude = profiles.preset("claude")["apps"]
    assert profiles.app_matches(claude[0], CLAUDE_DESKTOP)
    assert not profiles.app_matches(claude[0], CLAUDE_CODE)
    assert profiles.app_matches(claude[1], CLAUDE_CODE)
    assert profiles.app_matches(claude[1], r"C:\Users\u\.local\bin\claude.exe")
    assert not profiles.app_matches(claude[1], r"C:\x\chrome.exe")
    ag = profiles.preset("antigravity")["apps"][0]
    assert profiles.app_matches(ag, r"C:\Users\u\AppData\Local\Programs\Antigravity\Antigravity.exe")


def test_normalize_drops_garbage():
    p = profiles.normalize({"id": "x", "domains": ["ok.com", "bad domain"], "nets": ["1.2.3.0/24", "zzz"],
                            "apps": [{"name": "a", "match": "("}, {"name": "b", "match": "b\\.exe$"}]})
    assert p["domains"] == ["ok.com"] and p["nets"] == ["1.2.3.0/24"] and [a["name"] for a in p["apps"]] == ["b"]


# --- PAC ---

def test_pac_only_enabled_profiles_and_no_direct_fallback():
    c = cfg(profiles=[dict(profiles.preset("claude"), enabled=True), dict(profiles.preset("chatgpt"), enabled=False)])
    pac = core.pac_text(c)
    assert '"claude.ai"' in pac and '"chatgpt.com"' not in pac
    assert 'return "PROXY 127.0.0.1:8888";' in pac
    assert "; DIRECT" not in pac


# --- config ---

def test_config_roundtrip(tmp_path):
    path = str(tmp_path / "c.json")
    c = cfg()
    c["profiles"][0]["domains"].append("extra.com")
    core.save_config(c, path)
    loaded = core.load_config(path)
    assert loaded["server"] == "root@1.2.3.4" and "extra.com" in loaded["profiles"][0]["domains"]


def test_first_run_has_claude_preset_off(tmp_path):
    c = core.load_config(str(tmp_path / "missing.json"))
    assert c["profiles"][0]["id"] == "claude" and not c["profiles"][0]["enabled"]


def test_validate():
    out, err = core.validate({"server": "5.6.7.8", "ssh_port": "22", "ssh_key": __file__,
                              "remote_proxy_port": "8888", "local_proxy_port": "8888", "pac_port": "8888"})
    assert out["server"] == "root@5.6.7.8"
    assert any("differ" in e for e in err)


# --- Claude Code settings ---

def test_claude_code_settings_keep_user_values(tmp_path):
    path = str(tmp_path / "settings.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"model": "x", "env": {"FOO": "1"}}, f)
    c = cfg()
    core.set_claude_code_proxy(c, True, path)
    assert core.claude_code_proxy_on(c, path)
    core.set_claude_code_proxy(c, False, path)
    data = json.load(open(path, encoding="utf-8"))
    assert data == {"model": "x", "env": {"FOO": "1"}}


def test_claude_code_settings_do_not_remove_foreign_proxy(tmp_path):
    path = str(tmp_path / "settings.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"env": {"HTTPS_PROXY": "http://corp:3128"}}, f)
    core.set_claude_code_proxy(cfg(), False, path)
    assert json.load(open(path, encoding="utf-8"))["env"]["HTTPS_PROXY"] == "http://corp:3128"


# --- scanning ---

def test_scan_counts_proxy_and_direct():
    c = cfg()
    procs = [(1, CLAUDE_DESKTOP), (2, CLAUDE_CODE), (3, r"C:\x\chrome.exe")]
    conns = [Conn(1, Addr("127.0.0.1", 8888), "ESTABLISHED"), Conn(1, Addr("160.79.104.10", 443), "ESTABLISHED"),
             Conn(2, Addr("127.0.0.1", 8888), "ESTABLISHED"), Conn(3, Addr("160.79.104.10", 443), "ESTABLISHED"),
             Conn(2, Addr("8.8.8.8", 443), "ESTABLISHED")]
    targets = {"claude": (set(), [__import__("ipaddress").ip_network("160.79.104.0/23")])}
    r = core.scan(c, targets, procs, conns)
    assert r[("claude", 0)] == {"pids": {1}, "via": 1, "direct": 1}
    assert r[("claude", 1)] == {"pids": {2}, "via": 1, "direct": 0}


# --- evaluate ---

def apps(direct=0, via=0):
    return {("claude", 0): {"pids": {1}, "via": via, "direct": direct}, ("claude", 1): {"pids": set(), "via": 0, "direct": 0}}


def test_evaluate_ok():
    level, problems = core.evaluate(cfg(), state(apps=apps(via=2)))
    assert level == core.OK and not problems


def test_evaluate_setup_needed():
    level, problems = core.evaluate(cfg(server=""), state())
    assert level == core.WARN and problems[0][0] == "setup"


def test_evaluate_vpn_only_when_required():
    _, p = core.evaluate(cfg(require_vpn=True), state(vpn=None, tunnel=False, exit_ok=None))
    assert p[0][0] == "vpn"
    _, p = core.evaluate(cfg(require_vpn=False), state(vpn=None, tunnel=False, exit_ok=None))
    assert p[0][0] == "tunnel"


def test_evaluate_leak_vs_profile_off():
    level, p = core.evaluate(cfg(), state(apps=apps(direct=3)))
    assert level == core.DOWN and p[0][0] == "leak:claude:0"
    off = cfg(profiles=[dict(profiles.preset("claude"), enabled=False)])
    level, p = core.evaluate(off, state(apps=apps(direct=3)))
    assert level == core.WARN and p[0][0] == "off:claude:0"


def test_evaluate_wrong_exit():
    level, p = core.evaluate(cfg(), state(exit_ok=False, exit_ip="9.9.9.9"))
    assert level == core.DOWN and "9.9.9.9" in p[0][1]


def test_launch_message_keeps_acronyms():
    assert core.launch_message(["Claude Code"], "vpn", "VPN is off").startswith("Claude Code started, but VPN")
    assert core.launch_message(["X"], "tunnel", "No connection") == "X started, but no connection"
    assert core.launch_message([], "vpn", "VPN is off") == "VPN is off"


def test_russian_translation():
    i18n.set_language("ru")
    assert i18n.tr("Overview") == "Обзор"
    assert i18n.tr("{n} s ago", n=5) == "5 с назад"
