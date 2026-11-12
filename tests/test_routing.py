import json
import os

from xmeltunnel import core, profiles, routing


def prof(pid, target, entries, enabled=True):
    return profiles.normalize({"id": pid, "name": pid, "target": target, "entries": entries, "enabled": enabled})


def cfg(vpn=None, server=None, direct=None, **kw):
    c = json.loads(json.dumps(core.DEFAULTS))
    vpn = ["# comment", "Discord.exe", "youtube.com", "https://www.x.com/home"] if vpn is None else vpn
    server = ["%TESTDIR%\\Roblox\\", "RobloxPlayerBeta.exe", "10.0.0.0/8 # lan"] if server is None else server
    c["profiles"] = [prof("v", "vpn", vpn), prof("s", "server", server), prof("d", "direct", direct or [])]
    c.update(ss_key="k", require_vpn=True)
    c.update(kw)
    return c


def rule_for(conf, key):
    return [r for r in conf["route"]["rules"] if key in r]


def test_parse_list(monkeypatch):
    monkeypatch.setenv("TESTDIR", r"C:\Games")
    p = routing.parse_list(["# x", "", "Tanki.exe", "%TESTDIR%\\Tanki", "D:/Games/W/", "*.Example.COM",
                            "1.2.3.4", "fd00::/8", "not a domain"])
    assert p["procs"] == ["Tanki.exe"]
    assert p["folders"] == ["C:\\Games\\Tanki\\", "D:\\Games\\W\\"]
    assert p["domains"] == ["example.com"]
    assert p["cidrs"] == ["1.2.3.4/32", "fd00::/8"]
    assert p["bad"] == ["not a domain"]


def test_lists_by_target_only_enabled():
    c = cfg()
    c["profiles"].append(prof("off", "vpn", ["off.example"], enabled=False))
    lists = routing.lists_by_target(c)
    assert "youtube.com" in lists["vpn"] and "off.example" not in lists["vpn"]


def test_build_config_routes(monkeypatch):
    monkeypatch.setenv("TESTDIR", r"C:\Games")
    conf = routing.build_config(cfg(), "5.6.7.8", "Ethernet", "happ-xray")
    out = {o["tag"]: o for o in conf["outbounds"]}
    assert out["direct"]["bind_interface"] == "Ethernet"
    assert out["vpn"]["bind_interface"] == "happ-xray"
    assert out["server"]["type"] == "shadowsocks" and out["server"]["bind_interface"] == "happ-xray"
    assert conf["route"]["final"] == "direct"
    rules = conf["route"]["rules"]
    assert rules[0] == {"inbound": ["check-direct"], "outbound": "direct"}
    assert {"ip_cidr": ["5.6.7.8/32"], "outbound": "vpn"} in rules
    srv = rule_for(conf, "process_path_regex")[0]
    assert srv["outbound"] == "server" and srv["process_path_regex"] == ["(?i)^C:\\\\Games\\\\Roblox\\\\"]
    assert {"process_name": ["Discord.exe"], "outbound": "vpn"} in rules
    assert {"domain_suffix": ["youtube.com", "www.x.com"], "outbound": "vpn"} in rules
    assert rules.index(srv) < rules.index({"process_name": ["Discord.exe"], "outbound": "vpn"})
    tun = conf["inbounds"][0]
    assert tun["route_address"] == ["0.0.0.0/1", "128.0.0.0/1", "::/1", "8000::/1"]
    assert tun["address"] == [routing.TUN_ADDRESS, routing.TUN_ADDRESS6]
    i6 = rules.index({"ip_version": 6, "action": "reject"})
    assert rules.index({"ip_is_private": True, "outbound": "direct"}) < i6 < rules.index(srv)
    assert conf["dns"]["servers"][0] == {"type": "https", "tag": "dns-local", "server": "1.1.1.1", "detour": "direct"}


def test_server_direct_when_vpn_not_required():
    conf = routing.build_config(cfg(require_vpn=False), "5.6.7.8", "Ethernet", "happ-xray")
    out = {o["tag"]: o for o in conf["outbounds"]}
    assert out["server"]["bind_interface"] == "Ethernet"
    assert {"ip_cidr": ["5.6.7.8/32"], "outbound": "direct"} in conf["route"]["rules"]


def test_no_vpn_blocks_instead_of_leaking():
    conf = routing.build_config(cfg(ss_key=""), "5.6.7.8", "Ethernet", None)
    out = {o["tag"]: o for o in conf["outbounds"]}
    assert out["vpn"]["type"] == "block" and out["server"]["type"] == "block"


def test_server_sites_without_shadowsocks_are_left_to_pac():
    c = cfg(server=["claude.ai"], ss_key="")
    conf = routing.build_config(c, "5.6.7.8", "Ethernet", "happ-xray")
    assert not [r for r in conf["route"]["rules"] if r.get("outbound") == "server" and "inbound" not in r]
    assert routing.problems(c, "happ") == []  # sites alone need no Shadowsocks


def test_problems():
    assert routing.problems(cfg(), "happ") == []
    assert routing.problems(cfg(), None) == ["novpn"]
    assert routing.problems(cfg(vpn=[], require_vpn=False), None) == []
    assert routing.problems(cfg(ss_key=""), "happ") == ["noserver"]


def test_default_vpn_with_direct_list():
    c = cfg(route_default="vpn", direct=["D:\\Games\\Tanki\\", "lesta.ru"], vpn=[])
    conf = routing.build_config(c, "5.6.7.8", "Ethernet", "happ-xray")
    assert conf["route"]["final"] == "vpn"
    rules = conf["route"]["rules"]
    tanks = {"process_path_regex": ["(?i)^D:\\\\Games\\\\Tanki\\\\"], "outbound": "direct"}
    assert tanks in rules
    srv = rule_for(conf, "process_path_regex")[1]
    assert srv["outbound"] == "server" and rules.index(tanks) < rules.index(srv)
    assert conf["dns"]["final"] == "dns-remote"
    assert {"domain_suffix": ["lesta.ru"], "server": "dns-local"} in conf["dns"]["rules"]


def test_problems_follow_default():
    assert routing.problems(cfg(route_default="vpn", vpn=[]), None) == ["novpn"]
    assert routing.problems(cfg(route_default="server", server=[], ss_key=""), "happ") == ["noserver"]


def test_old_lists_become_profiles(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"language": "ru", "profiles": [],
                             "route_vpn": ["# c", "youtube.com"], "route_server": ["# only a comment"],
                             "route_direct": ["D:\\Games\\Tanki\\"]}), encoding="utf-8")
    c = core.load_config(str(p))
    got = {x["id"]: (x["target"], x["enabled"]) for x in c["profiles"]}
    assert got == {"list-direct": ("direct", True), "list-vpn": ("vpn", True)}
    assert c["route_vpn"] is None and c["routes_migrated"] is True
    core.save_config(c, str(p))
    again = core.load_config(str(p))
    assert [x["id"] for x in again["profiles"]] == ["list-direct", "list-vpn"]  # once only


def test_old_profiles_load_as_server_targets():
    p = profiles.normalize({"id": "claude", "name": "Claude", "domains": ["claude.ai"], "enabled": True})
    assert p["target"] == "server" and p["entries"] == ["claude.ai"] and p["domains"] == ["claude.ai"]


def test_pac_only_server_profiles():
    c = cfg(server=["claude.ai"])
    assert "claude.ai" in core.pac_text(c) and "youtube.com" not in core.pac_text(c)


def test_state_roundtrip(tmp_path):
    data = str(tmp_path)
    assert routing.read_state(data) == {}
    routing._write_state(data, status="running", helper=os.getpid(), started=0)
    assert routing.read_state(data)["status"] == "running"
    assert not routing.helper_alive(data)


def _srv(sid, country="", host="1.1.1.1"):
    return {"id": sid, "name": sid, "protocol": "trojan", "host": host, "port": 443, "country": country,
            "outbound": {"type": "trojan", "server": host, "server_port": 443, "password": "x"}}


def test_builtin_client_single_server():
    c = cfg(vpn_source="servers", vpn_server="a", servers=[_srv("a"), _srv("b")])
    conf = routing.build_config(c, "5.6.7.8", "Ethernet", None)  # no VPN client adapter at all
    out = {o["tag"]: o for o in conf["outbounds"]}
    assert out["vpn"]["type"] == "trojan" and out["vpn"]["bind_interface"] == "Ethernet"
    assert out["server"]["detour"] == "vpn" and "bind_interface" not in out["server"]
    assert routing.problems(c, None) == []


def test_builtin_client_auto_by_country():
    c = cfg(vpn_source="servers", vpn_server="auto:FI",
            servers=[_srv("a", "FI"), _srv("b", "DE"), _srv("c", "FI")],
            server_checks={"a": {"ms": 80, "exit_loc": "FI"}, "c": {"ms": None, "exit_loc": ""}})
    conf = routing.build_config(c, "5.6.7.8", "Ethernet", None)
    out = {o["tag"]: o for o in conf["outbounds"]}
    assert out["vpn"]["type"] == "urltest" and out["vpn"]["outbounds"] == ["srv-a"]  # only working FI ones


def test_builtin_client_without_servers_is_a_problem():
    c = cfg(vpn_source="servers", servers=[])
    assert routing.problems(c, None) == ["noservers"]


def test_builtin_servers_through_the_vpn_client():
    c = cfg(vpn_source="servers", vpn_server="a", servers=[_srv("a")], servers_via_adapter=True)
    conf = routing.build_config(c, "5.6.7.8", "Ethernet", "happ-xray")
    out = {o["tag"]: o for o in conf["outbounds"]}
    assert out["vpn"]["bind_interface"] == "happ-xray"
    assert routing.problems(c, None) == ["novpn"]  # asked to go through the VPN client, but it is off
