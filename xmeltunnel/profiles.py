"""Profiles: a named set of sites, programs, folders and subnets, and where they go.

target:
  server — through your server. Sites work always (PAC + SSH); programs, folders and subnets need the
           routing mode (they go by Shadowsocks then).
  vpn    — through your VPN client's adapter; needs the routing mode.
  direct — your normal connection; needs the routing mode (useful when everything else goes elsewhere).

entries are the user's lines as typed (comments kept); domains are derived from them for the PAC file.
Apps are watched for leaks (server profiles only). Presets are just ready-made profiles.

App methods:
  system       — the app follows the Windows proxy settings (browsers on Chromium, Electron apps).
                 Covered by the PAC file, nothing to configure per app.
  claude_code  — Claude Code CLI reads proxy settings from ~/.claude/settings.json (env block).
"""

from __future__ import annotations

import copy
import ipaddress
import re

METHODS = ("system", "claude_code")
TARGETS = ("server", "vpn", "direct")

PRESETS = [
    {
        "id": "claude",
        "name": "Claude",
        "domains": ["claude.ai", "claude.com", "anthropic.com", "claudeusercontent.com", "clau.de"],
        "nets": ["160.79.104.0/23"],
        "check_url": "https://claude.ai/cdn-cgi/trace",
        "apps": [
            {"name": "Claude (desktop)", "match": r"\\(WindowsApps\\Claude_[^\\]*|AnthropicClaude)\\.*\\claude\.exe$",
             "method": "system"},
            {"name": "Claude Code", "match": r"\\(claude-code\\.*|\.local\\bin|npm)\\claude\.exe$",
             "method": "claude_code"},
        ],
    },
    {
        "id": "chatgpt",
        "name": "ChatGPT",
        "domains": ["chatgpt.com", "openai.com", "oaistatic.com", "oaiusercontent.com", "chat.com"],
        "nets": [],
        "check_url": "https://chatgpt.com/cdn-cgi/trace",
        "apps": [{"name": "ChatGPT (desktop)", "match": r"\\ChatGPT\.exe$", "method": "system"}],
    },
    {
        "id": "gemini",
        "name": "Gemini",
        # Web Gemini, AI Studio, NotebookLM, Google Labs, Gemini API and Gemini CLI backends.
        "domains": ["gemini.google.com", "aistudio.google.com", "makersuite.google.com", "notebooklm.google.com",
                    "notebooklm.google", "labs.google", "jules.google.com", "generativelanguage.googleapis.com",
                    "alkalimakersuite-pa.clients6.google.com", "cloudcode-pa.googleapis.com",
                    "daily-cloudcode-pa.googleapis.com"],
        "nets": [],
        "check_url": "",
        "apps": [],
    },
    {
        "id": "antigravity",
        "name": "Antigravity",
        # antigravity.google/docs/enterprise: global endpoints cloudcode-pa and businessaicode must be reachable.
        "domains": ["antigravity.google", "cloudcode-pa.googleapis.com", "daily-cloudcode-pa.googleapis.com",
                    "businessaicode.googleapis.com", "generativelanguage.googleapis.com"],
        "nets": [],
        "check_url": "",
        "apps": [{"name": "Antigravity", "match": r"\\Antigravity\.exe$", "method": "system"}],
    },
    {
        "id": "grok",
        "name": "Grok",
        "domains": ["grok.com", "x.ai"],
        "nets": [],
        "check_url": "https://grok.com/cdn-cgi/trace",
        "apps": [],
    },
    {
        "id": "perplexity",
        "name": "Perplexity",
        "domains": ["perplexity.ai", "pplx.ai"],
        "nets": [],
        "check_url": "https://www.perplexity.ai/cdn-cgi/trace",
        "apps": [{"name": "Perplexity (desktop)", "match": r"\\Perplexity\.exe$", "method": "system"}],
    },
    {
        "id": "cursor",
        "name": "Cursor",
        # Cursor network help: *.cursor.sh (api2 = main API), *.cursor-cdn.com, *.cursorapi.com.
        "domains": ["cursor.com", "cursor.sh", "cursorapi.com", "cursor-cdn.com"],
        "nets": [],
        "check_url": "",
        "apps": [{"name": "Cursor", "match": r"\\Cursor\.exe$", "method": "system"}],
    },
    {
        "id": "windsurf",
        "name": "Windsurf",
        # server.codeium.com / inference.codeium.com (API), *.codeiumdata.com (downloads), windsurf.com (site).
        "domains": ["windsurf.com", "codeium.com", "codeiumdata.com"],
        "nets": [],
        "check_url": "",
        "apps": [{"name": "Windsurf", "match": r"\\Windsurf\.exe$", "method": "system"}],
    },
    {
        "id": "copilot",
        "name": "GitHub Copilot",
        # docs.github.com Copilot allowlist: *.githubcopilot.com (+ individual/business/enterprise), copilot-* hosts.
        # api.github.com is left out on purpose: it would send all GitHub API traffic through the tunnel.
        "domains": ["githubcopilot.com", "copilot-proxy.githubusercontent.com",
                    "copilot-telemetry.githubusercontent.com", "origin-tracker.githubusercontent.com"],
        "nets": [],
        "check_url": "",
        "apps": [],
    },
    {
        "id": "blocked",
        "name": "Often blocked",
        "target": "vpn",
        "entries": [
            "# YouTube", "youtube.com", "youtu.be", "googlevideo.com", "ytimg.com", "ggpht.com",
            "youtube-nocookie.com", "youtubei.googleapis.com",
            "# Discord (the whole app, so voice works too)", "Discord.exe", "discord.com", "discord.gg",
            "discordapp.com", "discordapp.net", "discord.media",
            "# Telegram", "Telegram.exe", "telegram.org", "t.me",
            "# Meta / X", "instagram.com", "cdninstagram.com", "facebook.com", "fbcdn.net", "whatsapp.com",
            "x.com", "twitter.com", "twimg.com",
            "# Other", "linkedin.com", "medium.com", "patreon.com", "soundcloud.com", "spotify.com", "scdn.co",
        ],
        "domains": [],
        "nets": [],
        "check_url": "",
        "apps": [],
    },
    {
        "id": "custom",
        "name": "My sites",
        "domains": [],
        "nets": [],
        "check_url": "",
        "apps": [],
    },
]

_DOMAIN = re.compile(r"^(?=.{1,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$")


def preset(pid: str) -> dict:
    return copy.deepcopy(next(p for p in PRESETS if p["id"] == pid))


def clean_domain(text: str) -> str | None:
    """'https://www.Example.com/path' -> 'www.example.com'; garbage -> None."""
    d = text.strip().lower()
    d = re.sub(r"^[a-z]+://", "", d).split("/")[0].split(":")[0].lstrip("*.").strip(".")
    return d if _DOMAIN.match(d) else None


def parse_domains(text: str) -> tuple[list[str], list[str]]:
    """Split user input (lines, commas, spaces) into (valid domains, rejected entries)."""
    ok, bad = [], []
    for raw in re.split(r"[\s,;]+", text):
        if not raw:
            continue
        d = clean_domain(raw)
        if d and d not in ok:
            ok.append(d)
        elif not d:
            bad.append(raw)
    return ok, bad


def normalize(p: dict) -> dict:
    """Fill missing keys so old or hand-edited configs still load (0.1 profiles had only domains)."""
    from xmeltunnel.routing import parse_list

    out = {"id": str(p.get("id") or "custom"), "name": str(p.get("name") or "Profile"),
           "enabled": bool(p.get("enabled", False)), "check_url": str(p.get("check_url") or "")}
    out["target"] = p.get("target") if p.get("target") in TARGETS else "server"
    entries = p.get("entries")
    if not isinstance(entries, list):
        entries = list(p.get("domains", []))
    out["entries"] = [str(x).rstrip() for x in entries]
    parsed = parse_list(out["entries"])
    out["domains"] = [d for d in (clean_domain(x) for x in parsed["domains"]) if d]
    nets = []
    for n in p.get("nets", []):
        try:
            nets.append(str(ipaddress.ip_network(n, strict=False)))
        except ValueError:
            pass
    out["nets"] = nets
    apps = []
    for a in p.get("apps", []):
        try:
            re.compile(a.get("match", ""))
        except re.error:
            continue
        if a.get("match") and a.get("method", "system") in METHODS:
            apps.append({"name": str(a.get("name") or "App"), "match": a["match"], "method": a.get("method", "system")})
    out["apps"] = apps
    return out


def app_matches(app: dict, exe_path: str) -> bool:
    return bool(exe_path) and re.search(app["match"], exe_path, re.I) is not None


def matches_domain(host: str, domains: list[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in domains)


def counts(p: dict) -> dict:
    """How many sites, programs (incl. folders) and subnets a profile holds."""
    from xmeltunnel.routing import parse_list

    parsed = parse_list(p["entries"])
    return {"sites": len(parsed["domains"]), "apps": len(parsed["procs"]) + len(parsed["folders"]),
            "nets": len(parsed["cidrs"])}


def needs_routing(p: dict) -> bool:
    """True if part of this profile works only while the routing mode is on."""
    from xmeltunnel.routing import parse_list

    if p["target"] != "server":
        return True
    parsed = parse_list(p["entries"])
    return bool(parsed["procs"] or parsed["folders"] or parsed["cidrs"])
