from xmeltunnel import servers as S

LINKS = """anytls://pw@1.2.3.4:443/?sni=a.com#A
naive+https://u:p@b.com:443#N
wireguard://cHJpdg==@5.6.7.8:51820?publickey=cHVi&address=10.8.0.2,fd00::2&reserved=1,2,3#W
socks://x@1.1.1.1:1080#S
vless://u@1.2.3.4:443?type=xhttp&security=tls#X"""


def test_new_protocols_and_skipped():
    found, errors = S.parse_text(LINKS)
    assert [s["protocol"] for s in found] == ["anytls", "naive", "wireguard"]
    wg = found[2]["outbound"]
    assert wg["address"] == ["10.8.0.2/32", "fd00::2/128"] and wg["peers"][0]["reserved"] == [1, 2, 3]
    assert S.skipped_summary(errors) == {"«socks://» links are not supported": 1,
                                         "transport «xhttp» is not supported": 1}
    conf = S.place_endpoints({"outbounds": [dict(s["outbound"], tag=s["id"]) for s in found]})
    assert [o["type"] for o in conf["outbounds"]] == ["anytls", "naive"]
    assert conf["endpoints"][0]["type"] == "wireguard" and "server" not in conf["endpoints"][0]
