import base64
import json

import pytest

from xmeltunnel import servers

UUID = "11111111-2222-3333-4444-555555555555"


def test_vless_reality():
    link = (f"vless://{UUID}@203.0.113.5:443?type=tcp&security=reality&pbk=PUBKEY&sid=ab12&sni=www.example.com"
            "&fp=chrome&flow=xtls-rprx-vision#%F0%9F%87%AB%F0%9F%87%AE%20Helsinki")
    s = servers.make_server(servers.parse_link(link))
    ob = s["outbound"]
    assert s["name"] == "🇫🇮 Helsinki" and s["country"] == "FI" and s["protocol"] == "vless"
    assert ob["server"] == "203.0.113.5" and ob["server_port"] == 443 and ob["uuid"] == UUID
    assert ob["flow"] == "xtls-rprx-vision"
    assert ob["tls"]["reality"] == {"enabled": True, "public_key": "PUBKEY", "short_id": "ab12"}
    assert ob["tls"]["server_name"] == "www.example.com" and ob["tls"]["utls"]["fingerprint"] == "chrome"
    assert "transport" not in ob


def test_vless_ws_tls():
    link = f"vless://{UUID}@example.org:8443?type=ws&security=tls&path=%2Fws&host=cdn.example.org#ws"
    ob = servers.parse_link(link)["outbound"]
    assert ob["transport"] == {"type": "ws", "path": "/ws", "headers": {"Host": "cdn.example.org"}}
    assert ob["tls"]["server_name"] == "cdn.example.org"  # no sni: the Host header, as v2rayN does (CDN setups)


def test_vmess():
    j = {"v": "2", "ps": "🇩🇪 Frankfurt", "add": "198.51.100.7", "port": "443", "id": UUID, "aid": "0",
         "net": "grpc", "path": "svc", "tls": "tls", "sni": "front.example"}
    link = "vmess://" + base64.b64encode(json.dumps(j).encode()).decode()
    s = servers.make_server(servers.parse_link(link))
    assert s["country"] == "DE" and s["outbound"]["transport"] == {"type": "grpc", "service_name": "svc"}
    assert s["outbound"]["tls"]["server_name"] == "front.example"


def test_shadowsocks_forms():
    sip = "ss://" + base64.urlsafe_b64encode(b"2022-blake3-aes-128-gcm:KEY==").decode().rstrip("=") + "@1.2.3.4:8388#My"
    legacy = "ss://" + base64.b64encode(b"aes-256-gcm:pass@5.6.7.8:443").decode() + "#Old"
    plain = "ss://chacha20-ietf-poly1305:pw@[2001:db8::1]:8388#v6"
    a, b, c = (servers.parse_link(x)["outbound"] for x in (sip, legacy, plain))
    assert (a["method"], a["password"], a["server"], a["server_port"]) == ("2022-blake3-aes-128-gcm", "KEY==", "1.2.3.4", 8388)
    assert (b["method"], b["server"], b["server_port"]) == ("aes-256-gcm", "5.6.7.8", 443)
    assert c["server"] == "2001:db8::1"


def test_trojan_hysteria_tuic():
    t = servers.parse_link("trojan://secret@t.example:443?sni=t.example#T")["outbound"]
    assert t["type"] == "trojan" and t["password"] == "secret" and t["tls"]["enabled"]
    h = servers.parse_link("hy2://pw@h.example:443?obfs=salamander&obfs-password=x&insecure=1#H")["outbound"]
    assert h["type"] == "hysteria2" and h["obfs"]["password"] == "x" and h["tls"]["insecure"]
    u = servers.parse_link(f"tuic://{UUID}:pw@u.example:443?congestion_control=bbr#U")["outbound"]
    assert u["type"] == "tuic" and u["password"] == "pw" and u["tls"]["alpn"] == ["h3"]


def test_parse_text_base64_blob_and_dupes():
    links = "\n".join([f"vless://{UUID}@a.example:443?security=tls#A", f"vless://{UUID}@a.example:443?security=tls#A2",
                       "trojan://x@b.example:443#B", "wireguard://nope"])
    blob = base64.b64encode(links.encode()).decode()
    got, errors = servers.parse_text(blob, sub="s1")
    assert [s["name"] for s in got] == ["A", "B"] and all(s["sub"] == "s1" for s in got)
    assert errors == []


def test_parse_text_reports_garbage():
    got, errors = servers.parse_text("hello world")
    assert got == [] and errors


def test_singbox_json():
    cfg = {"outbounds": [{"type": "direct", "tag": "direct"},
                         {"type": "vless", "tag": "x", "server": "9.9.9.9", "server_port": 443, "uuid": UUID}]}
    got, errors = servers.parse_text(json.dumps(cfg))
    assert len(got) == 1 and "tag" not in got[0]["outbound"] and not errors


def test_unsupported_transport():
    with pytest.raises(servers.LinkError):
        servers.parse_link(f"vless://{UUID}@a.example:443?type=kcp#x")


def test_unencoded_spaces_and_display_name():
    got, errors = servers.parse_text("trojan://pw@a.example:443#🇫🇮 Helsinki Fast\ntrojan://pw@b.example:443#🇩🇪 Berlin")
    assert [s["name"] for s in got] == ["🇫🇮 Helsinki Fast", "🇩🇪 Berlin"] and not errors
    assert servers.display_name(got[0]["name"]) == "Helsinki Fast" and got[0]["country"] == "FI"
