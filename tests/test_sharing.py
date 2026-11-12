import json
import time

from xmeltunnel import servers, sharing


def test_new_user_ports_and_link():
    a = sharing.new_user("Петя", [])
    b = sharing.new_user("Вася", [a], days=30, quota_gb=50)
    assert (a["port"], b["port"]) == (sharing.FIRST_PORT, sharing.FIRST_PORT + 1)
    assert b["expires"] > time.time() and b["quota_gb"] == 50
    link = sharing.invite_link(a, "203.0.113.7")
    parsed = servers.parse_link(link)  # the friend's XmelTunnel (or Happ) reads it back
    assert parsed["name"] == "Петя" and parsed["outbound"]["password"] == a["key"]
    assert parsed["outbound"]["method"] == sharing.METHOD and parsed["port"] == a["port"]


def test_server_config_isolates_guests():
    u1, u2 = sharing.new_user("a", []), None
    u2 = sharing.new_user("b", [u1])
    u2["paused"] = True
    conf = sharing.server_config(8388, "OWNERKEY", [u1, u2])
    tags = [i["tag"] for i in conf["inbounds"]]
    assert tags == ["owner", f"u-{u1['id']}"]  # paused friends get no inbound
    rules = conf["route"]["rules"]
    assert {"inbound": [f"u-{u1['id']}"], "ip_is_private": True, "outbound": "block"} in rules
    assert any(r.get("port") == [25, 465, 587] for r in rules)
    assert not any("owner" in r.get("inbound", []) for r in rules)  # the owner is not limited


def test_counters_and_online_parsing():
    u = sharing.new_user("a", [])
    nft = json.dumps({"nftables": [{"metainfo": {}}, {"counter": {"name": f"u_{u['id']}_up", "bytes": 1000}},
                                   {"counter": {"name": f"u_{u['id']}_down", "bytes": 5000}}]})
    ss_out = f"ESTAB 0 0 203.0.113.7:{u['port']} 198.51.100.1:5555\nESTAB 0 0 203.0.113.7:22 1.1.1.1:4444\n"
    sharing.merge_traffic([u], sharing.parse_counters(nft), sharing.online_ports(ss_out))
    assert (u["live_up"], u["live_down"], u["online"]) == (1000, 5000, 1) and u["last_seen"]
    assert sharing.total(u) == 6000
    assert f"counter name u_{u['id']}_up" in sharing.counters_nft([u])


def test_limits():
    old = sharing.new_user("old", [])
    old["expires"] = int(time.time()) - 10
    heavy = sharing.new_user("heavy", [old], quota_gb=1)
    heavy["down"] = 2 * 2**30
    fine = sharing.new_user("fine", [old, heavy], quota_gb=10)
    assert sharing.enforce_limits([old, heavy, fine]) == ["old", "heavy"]
    assert (old["reason"], heavy["reason"], fine["paused"]) == ("expired", "quota", False)


def test_fmt_bytes():
    assert sharing.fmt_bytes(3 * 2**30) == "3.0 GB" and sharing.fmt_bytes(512) == "512 B"
