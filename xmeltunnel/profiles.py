"""Profiles: a set of domains that go through the tunnel, plus the apps we watch for leaks.

A profile is plain data so users can add their own. Presets are just ready-made profiles.

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
        "domains": ["antigravity.google", "cloudcode-pa.googleapis.com", "daily-cloudcode-pa.googleapis.com",
                    "generativelanguage.googleapis.com"],
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
        "domains": ["cursor.com", "cursor.sh", "cursorapi.com"],
        "nets": [],
        "check_url": "",
        "apps": [{"name": "Cursor", "match": r"\\Cursor\.exe$", "method": "system"}],
    },
    {
        "id": "windsurf",
        "name": "Windsurf",
        "domains": ["windsurf.com", "codeium.com", "codeiumdata.com"],
        "nets": [],
        "check_url": "",
        "apps": [{"name": "Windsurf", "match": r"\\Windsurf\.exe$", "method": "system"}],
    },
    {
        "id": "copilot",
        "name": "GitHub Copilot",
        "domains": ["githubcopilot.com", "copilot-proxy.githubusercontent.com"],
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


def default_profiles() -> list[dict]:
    """First run: Claude preset, switched off until the user turns it on."""
    p = preset("claude")
    p["enabled"] = False
    return [p]


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
    """Fill missing keys so old or hand-edited configs still load."""
    out = {"id": str(p.get("id") or "custom"), "name": str(p.get("name") or "Profile"),
           "enabled": bool(p.get("enabled", False)), "check_url": str(p.get("check_url") or "")}
    out["domains"] = [d for d in (clean_domain(x) for x in p.get("domains", [])) if d]
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
