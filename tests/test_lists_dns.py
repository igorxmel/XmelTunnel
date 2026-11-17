"""Ready-made lists, the «block» target and DNS choices in the routing config."""

import json

from xmeltunnel import core, profiles, routing


def cfg_with(*profs, **kw):
    cfg = json.loads(json.dumps(core.DEFAULTS))
    cfg["profiles"] = [profiles.normalize(dict(p, enabled=True)) for p in profs]
    cfg.update(kw)
    return cfg


READY = {"geosite-ru-blocked": "a.srs", "geoip-ru-blocked": "b.srs", "geosite-category-ads-all": "c.srs"}


def test_parse_list_reads_lists():
    p = routing.parse_list(["list:ru-blocked  # comment", "LIST:ads", "list:nope", "youtube.com"])
    assert p["lists"] == ["ru-blocked", "ads"]
    assert p["bad"] == ["list:nope"]
    assert p["domains"] == ["youtube.com"]
    assert routing.has_items(["list:ads"])


def test_lists_become_rule_sets():
    cfg = cfg_with(profiles.preset("ru-blocked"), {"id": "b", "name": "b", "target": "block", "entries": ["list:ads"]})
    conf = routing.build_config(cfg, "", "Ethernet", "Happ", READY)
    tags = {r["tag"]: r for r in conf["route"]["rule_set"]}
    assert set(tags) == set(READY)
    assert tags["geoip-ru-blocked"] == {"type": "local", "tag": "geoip-ru-blocked", "format": "binary",
                                        "path": "b.srs"}
    rules = conf["route"]["rules"]
    blk = next(i for i, r in enumerate(rules) if r.get("rule_set") == ["geosite-category-ads-all"])
    vpn = next(i for i, r in enumerate(rules) if r.get("rule_set") == ["geosite-ru-blocked", "geoip-ru-blocked"])
    assert rules[blk]["action"] == "reject" and rules[vpn]["outbound"] == "vpn"
    assert blk < vpn  # blocked wins over a wider list
    # DNS: blocked names refused, listed names get FakeIP; address lists never reach DNS rules
    dns = conf["dns"]["rules"]
    assert {"action": "reject", "rule_set": ["geosite-category-ads-all"]} in dns
    assert any(r.get("server") == "fakeip" and r.get("rule_set") == ["geosite-ru-blocked"] for r in dns)
    assert not any("geoip-ru-blocked" in r.get("rule_set", []) for r in dns)


def test_missing_lists_are_skipped():
    conf = routing.build_config(cfg_with(profiles.preset("ru-blocked")), "", "Ethernet", "Happ", {})
    assert "rule_set" not in conf["route"]
    assert not any("rule_set" in r for r in conf["route"]["rules"])


def test_block_target_rejects():
    cfg = cfg_with({"id": "b", "name": "b", "target": "block", "entries": ["ads.example.com", "Spy.exe", "10.9.0.0/16"]})
    rules = routing.build_config(cfg, "", "Ethernet", None)["route"]["rules"]
    for key in ("domain_suffix", "process_name", "ip_cidr"):
        r = next(r for r in rules if key in r and r.get("action") == "reject")
        assert "outbound" not in r
    assert profiles.needs_routing(profiles.normalize({"target": "block", "entries": ["x.com"]}))
    assert not core.pac_profiles(cfg)  # never in the PAC file


def test_used_lists():
    cfg = cfg_with(profiles.preset("ru-sites"), profiles.preset("ads"))
    cfg["profiles"].append(profiles.normalize({"id": "off", "entries": ["list:ru-blocked"], "enabled": False}))
    assert routing.used_lists(cfg) == ["ru", "ru-inside", "ads", "win-spy"]


def test_dns_choices():
    assert routing.doh_server("google") == {"server": "8.8.8.8"}
    assert routing.doh_server("https://dns.example.com/dns-query") == {"server": "dns.example.com",
                                                                       "domain_resolver": "dns-boot"}
    assert routing.doh_server("https://1.2.3.4:8443/q") == {"server": "1.2.3.4", "server_port": 8443, "path": "/q"}
    assert routing.plain_dns("quad9") == "9.9.9.9" and routing.plain_dns("8.8.4.4") == "8.8.4.4"
    assert routing.plain_dns("junk") == "1.1.1.1"
    conf = routing.build_config(cfg_with(dns_direct="https://dns.example.com/dns-query", dns_remote="google"),
                                "", "Ethernet", "Happ")
    servers = {s["tag"]: s for s in conf["dns"]["servers"]}
    assert servers["dns-local"]["server"] == "dns.example.com"
    assert servers["dns-boot"]["server"] == "8.8.8.8"
    assert servers["dns-remote"]["server"] == "8.8.8.8"
    # the one that answered at connect wins over the chosen one
    conf = routing.build_config(cfg_with(dns_direct="cloudflare", dns_direct_used="adguard"), "", "Ethernet", None)
    assert conf["dns"]["servers"][0]["server"] == "94.140.14.14"
    assert "dns-boot" not in {s["tag"] for s in conf["dns"]["servers"]}


def test_list_presets_are_valid():
    for pid in ("ru-blocked", "ru-sites", "ads"):
        p = profiles.normalize(profiles.preset(pid))
        assert not routing.parse_list(p["entries"])["bad"]
        assert profiles.counts(p)["lists"] >= 1
