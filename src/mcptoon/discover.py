# Copyright 2025-2026 cxh
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
mcptoon discover — Auto-discovery of MCP servers

Four-layer discovery strategy (all zero-dependency, pure stdlib):

  1. Scan existing MCP client configs (Claude Desktop, Cursor, Cline, Windsurf, etc.)
  2. Detect from environment variables (GITHUB_TOKEN → github server, etc.)
  3. Detect local tools (npx in PATH → zero-config servers, docker, sqlite, git repo)
  4. Check env vars for HTTP MCP endpoints (MCP_HTTP_URL, etc.)

Usage:
    from mcptoon.discover import auto_discover
    results = auto_discover()
    # results.servers → {name: config}
    # results.sources → {name: [source_labels]}
    # results.summary → human-readable report

CLI:
    mcptoon init --auto         # discover + write config
    mcptoon init --auto --dry   # discover + print, don't write
    mcptoon discover            # show discovered servers (alias for --dry)
"""
import json
import os
import shutil
import sys
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════

@dataclass
class DiscoveryResult:
    """Result of auto-discovery."""
    servers: dict = field(default_factory=dict)          # {name: config}
    sources: dict = field(default_factory=dict)           # {name: [source labels]}
    reasons: dict = field(default_factory=dict)           # {name: reason string}
    skipped: list = field(default_factory=list)           # [names skipped due to missing env]

    @property
    def count(self) -> int:
        return len(self.servers)

    def summary(self) -> str:
        """Human-readable summary report."""
        lines = []
        lines.append(f"Discovered {self.count} MCP server(s):")
        lines.append("")

        # Group by source
        by_source = {}
        for name, srcs in self.sources.items():
            for s in srcs:
                by_source.setdefault(s, []).append(name)

        source_labels = {
            "claude-desktop": "Claude Desktop config",
            "cursor": "Cursor config",
            "cline": "Cline config",
            "windsurf": "Windsurf config",
            "env": "Environment variables",
            "local": "Local tools",
            "network": "HTTP endpoint (env var)",
            "manual": "Manual (--http)",
        }

        for src_key in ["claude-desktop", "cursor", "cline", "windsurf", "env", "local", "network", "manual"]:
            names = by_source.get(src_key, [])
            if not names:
                continue
            label = source_labels.get(src_key, src_key)
            lines.append(f"  [{label}]")
            for name in names:
                reason = self.reasons.get(name, "")
                lines.append(f"    + {name}: {reason}")
            lines.append("")

        if self.skipped:
            lines.append(f"  Skipped {len(self.skipped)} server(s) (missing env vars or tools):")
            for s in self.skipped:
                lines.append(f"    - {s}")
            lines.append("")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Layer 1: Scan existing MCP client configs
# ═══════════════════════════════════════════════════════════════

def _home() -> Path:
    """Get home directory, Windows-compatible."""
    return Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))


def _appdata() -> Path:
    """Get Windows AppData path, or fallback to home."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(_home() / "AppData" / "Roaming")))
    return _home()


def _scan_claude_desktop() -> list[dict]:
    """Scan Claude Desktop config for MCP servers."""
    found = []
    candidates = []

    if sys.platform == "win32":
        candidates.append(_appdata() / "Claude" / "claude_desktop_config.json")
    elif sys.platform == "darwin":
        candidates.append(_home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
    else:
        # Linux: ~/.config/Claude/claude_desktop_config.json
        candidates.append(_home() / ".config" / "Claude" / "claude_desktop_config.json")

    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            mcp_servers = data.get("mcpServers", {})
            for name, cfg in mcp_servers.items():
                server_cfg = _normalize_imported_config(cfg)
                if server_cfg:
                    found.append({
                        "name": name,
                        "config": server_cfg,
                        "source": "claude-desktop",
                        "reason": f"Imported from {path.name}",
                    })
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    return found


def _scan_cursor() -> list[dict]:
    """Scan Cursor config for MCP servers."""
    found = []
    candidates = [
        _home() / ".cursor" / "mcp.json",
        Path.cwd() / ".cursor" / "mcp.json",
    ]

    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            mcp_servers = data.get("mcpServers", {})
            for name, cfg in mcp_servers.items():
                server_cfg = _normalize_imported_config(cfg)
                if server_cfg:
                    found.append({
                        "name": name,
                        "config": server_cfg,
                        "source": "cursor",
                        "reason": f"Imported from {path}",
                    })
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    return found


def _scan_cline() -> list[dict]:
    """Scan Cline (VS Code extension) config."""
    found = []
    candidates = [
        _home() / ".cline" / "mcp_settings.json",
        _appdata() / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
    ]

    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            mcp_servers = data.get("mcpServers", {})
            for name, cfg in mcp_servers.items():
                server_cfg = _normalize_imported_config(cfg)
                if server_cfg:
                    found.append({
                        "name": name,
                        "config": server_cfg,
                        "source": "cline",
                        "reason": "Imported from Cline config",
                    })
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    return found


def _scan_windsurf() -> list[dict]:
    """Scan Windsurf config for MCP servers."""
    found = []
    candidates = [
        _home() / ".codeium" / "windsurf" / "mcp_config.json",
    ]

    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            mcp_servers = data.get("mcpServers", {})
            for name, cfg in mcp_servers.items():
                server_cfg = _normalize_imported_config(cfg)
                if server_cfg:
                    found.append({
                        "name": name,
                        "config": server_cfg,
                        "source": "windsurf",
                        "reason": "Imported from Windsurf config",
                    })
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    return found


def _normalize_imported_config(cfg: dict) -> dict | None:
    """Normalize a config from external MCP client to mcptoon format.

    Different clients use slightly different config formats:
    - Claude Desktop: {"command": "npx", "args": ["-y", "@mcp/server"]}
    - Cursor: same as Claude Desktop
    - Some use "transport" key, some don't
    """
    if not isinstance(cfg, dict):
        return None

    # Already in mcptoon format
    transport = cfg.get("transport", "")

    if transport == "http" and "url" in cfg:
        return {
            "transport": "http",
            "url": cfg["url"],
            "headers": cfg.get("headers", {}),
        }

    # stdio: command + args
    command = cfg.get("command", [])
    args = cfg.get("args", [])
    env = cfg.get("env", {})

    if not command and not args:
        return None

    # Normalize: command might be a string or list
    if isinstance(command, str):
        cmd_list = [command]
    else:
        cmd_list = list(command)

    # On Windows, npx needs .cmd resolution — but we let client.py handle that
    result = {
        "transport": "stdio",
        "command": cmd_list[:2] if len(cmd_list) >= 2 else cmd_list,
        "args": cmd_list[2:] if len(cmd_list) > 2 else args,
    }

    # If command is just ["npx"] and args has the package
    if len(cmd_list) == 1 and args:
        result["command"] = cmd_list
        result["args"] = list(args)

    # Merge: command might be ["npx", "-y"] and args is ["@mcp/server"]
    if len(cmd_list) >= 2 and not args:
        result["command"] = [cmd_list[0]]
        result["args"] = cmd_list[1:]

    if env:
        result["env"] = env

    return result


# ═══════════════════════════════════════════════════════════════
# Layer 2: Environment variable detection
# ═══════════════════════════════════════════════════════════════

# Map: env var → (server_name, command_list, env_key_to_set)
_ENV_MAP = [
    # (env_var, server_name, command, args, env_key_for_config)
    ("GITHUB_PERSONAL_ACCESS_TOKEN", "github",
     ["npx", "-y"], ["@modelcontextprotocol/server-github"],
     "GITHUB_PERSONAL_ACCESS_TOKEN"),
    ("GITHUB_TOKEN", "github",
     ["npx", "-y"], ["@modelcontextprotocol/server-github"],
     "GITHUB_TOKEN"),
    ("BRAVE_API_KEY", "brave-search",
     ["npx", "-y"], ["@modelcontextprotocol/server-brave-search"],
     "BRAVE_API_KEY"),
    ("EXA_API_KEY", "exa",
     ["npx", "-y"], ["exa-mcp-server"],
     "EXA_API_KEY"),
    ("TAVILY_API_KEY", "tavily",
     ["npx", "-y"], ["tavily-mcp"],
     "TAVILY_API_KEY"),
    ("FIRECRAWL_API_KEY", "firecrawl",
     ["npx", "-y"], ["firecrawl-mcp"],
     "FIRECRAWL_API_KEY"),
    ("SLACK_BOT_TOKEN", "slack",
     ["npx", "-y"], ["@modelcontextprotocol/server-slack"],
     "SLACK_BOT_TOKEN"),
    ("SLACK_TOKEN", "slack",
     ["npx", "-y"], ["@modelcontextprotocol/server-slack"],
     "SLACK_TOKEN"),
    ("NOTION_API_KEY", "notion",
     ["npx", "-y"], ["@modelcontextprotocol/server-notion"],
     "NOTION_API_KEY"),
    ("NOTION_TOKEN", "notion",
     ["npx", "-y"], ["@modelcontextprotocol/server-notion"],
     "NOTION_TOKEN"),
    # Memory server uses MCP memory, no API key needed but we check for MEMORY_DIR
    # Postgres
    ("DATABASE_URL", "postgres",
     ["npx", "-y"], ["@modelcontextprotocol/server-postgres"],
     None),  # DATABASE_URL is passed as arg, not env
]


def _detect_from_env() -> list[dict]:
    """Detect MCP servers from environment variables."""
    found = []

    for env_var, name, command, args, env_key in _ENV_MAP:
        val = os.environ.get(env_var, "")
        if not val:
            continue

        # Skip placeholder values
        if val.startswith("<") and val.endswith(">"):
            continue

        config = {
            "transport": "stdio",
            "command": command,
            "args": args,
        }

        # Set env for the subprocess
        if env_key:
            config["env"] = {env_key: val}

        # Special case: postgres uses DATABASE_URL as arg
        if name == "postgres" and env_var == "DATABASE_URL":
            config["args"] = ["@modelcontextprotocol/server-postgres", val]
            config.pop("env", None)

        found.append({
            "name": name,
            "config": config,
            "source": "env",
            "reason": f"Found {env_var} in environment",
        })

    return found


# ═══════════════════════════════════════════════════════════════
# Layer 3: Local tool detection
# ═══════════════════════════════════════════════════════════════

# Zero-config servers: only need npx, no API key
_ZERO_CONFIG_SERVERS = [
    ("fetch", ["npx", "-y"], ["@modelcontextprotocol/server-fetch"],
     "Zero-config (no API key needed)"),
    ("filesystem", ["npx", "-y"], ["@modelcontextprotocol/server-filesystem", "."],
     "Zero-config — current directory as allowed path"),
    ("memory", ["npx", "-y"], ["@modelcontextprotocol/server-memory"],
     "Zero-config (knowledge graph in memory)"),
    ("sequential-thinking", ["npx", "-y"], ["@modelcontextprotocol/server-sequential-thinking"],
     "Zero-config (thinking tool for reasoning)"),
    ("time", ["npx", "-y"], ["@modelcontextprotocol/server-time"],
     "Zero-config (time and timezone)"),
    ("git", ["npx", "-y"], ["@modelcontextprotocol/server-git"],
     "Zero-config (git operations on current repo)"),
]


def _detect_local_tools() -> list[dict]:
    """Detect local tools and recommend zero-config MCP servers."""
    found = []
    has_npx = _which("npx") is not None
    has_uvx = _which("uvx") is not None

    if has_npx:
        for name, command, args, reason in _ZERO_CONFIG_SERVERS:
            found.append({
                "name": name,
                "config": {
                    "transport": "stdio",
                    "command": command,
                    "args": args,
                },
                "source": "local",
                "reason": reason,
            })
    else:
        # No npx — check if uvx (uv) is available as alternative
        if has_uvx:
            found.append({
                "name": "fetch",
                "config": {
                    "transport": "stdio",
                    "command": ["uvx"],
                    "args": ["mcp-server-fetch"],
                },
                "source": "local",
                "reason": "uvx detected (Python MCP servers)",
            })

    # sqlite3 available
    if _which("sqlite3"):
        found.append({
            "name": "sqlite",
            "config": {
                "transport": "stdio",
                "command": ["npx", "-y"],
                "args": ["@modelcontextprotocol/server-sqlite"],
            },
            "source": "local",
            "reason": "sqlite3 detected in PATH",
        })

    # Docker available
    if _which("docker"):
        found.append({
            "name": "docker",
            "config": {
                "transport": "stdio",
                "command": ["npx", "-y"],
                "args": ["@modelcontextprotocol/server-docker"],
            },
            "source": "local",
            "reason": "docker detected in PATH",
        })

    # In a git repository — git server is extra useful
    if Path.cwd().is_dir() and (Path.cwd() / ".git").exists():
        found.append({
            "name": "git",
            "config": {
                "transport": "stdio",
                "command": ["npx", "-y"],
                "args": ["@modelcontextprotocol/server-git"],
            },
            "source": "local",
            "reason": "Currently in a git repository",
        })

    return found


def _which(cmd: str) -> str | None:
    """Check if a command is in PATH. Returns path or None."""
    return shutil.which(cmd)


# ═══════════════════════════════════════════════════════════════
# Layer 4: HTTP MCP endpoint detection (env var only, no port scanning)
# ═══════════════════════════════════════════════════════════════

# Env vars that users can set to point to an HTTP MCP endpoint
_MCP_HTTP_ENV_VARS = ["MCP_HTTP_URL", "MCP_SERVER_URL"]


def _probe_http_mcp() -> list[dict]:
    """Check for HTTP MCP endpoints via environment variables.

    This does NOT scan ports or probe LAN hosts — that would be invasive
    and trigger firewall alerts. Users who want an HTTP endpoint set an
    env var or use --http explicitly.
    """
    found = []

    for env_var in _MCP_HTTP_ENV_VARS:
        url = os.environ.get(env_var, "")
        if url and not url.startswith("<"):
            if _probe_endpoint(url, timeout=2.0):
                found.append({
                    "name": "http-endpoint",
                    "config": {
                        "transport": "http",
                        "url": url,
                    },
                    "source": "network",
                    "reason": f"HTTP MCP endpoint detected via {env_var}",
                })

    return found


def _probe_endpoint(url: str, timeout: float = 0.5) -> bool:
    """Check if a URL is a responding MCP endpoint.

    Tries a lightweight MCP initialize request.
    """
    try:
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcptoon-discover", "version": "0.1"},
            },
        }
        payload = json.dumps(msg).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")

        # Disable proxy
        handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(handler)
        resp = opener.open(req, timeout=timeout)

        body = resp.read().decode("utf-8", errors="replace")

        # Check if response looks like MCP (JSON-RPC or SSE)
        if "jsonrpc" in body or "result" in body or "data: " in body:
            return True

        # Some endpoints return 200 with non-JSON for non-MCP requests
        return False

    except (TimeoutError, urllib.error.HTTPError, urllib.error.URLError, ConnectionError, OSError):
        return False
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# Main: auto_discover
# ═══════════════════════════════════════════════════════════════

def auto_discover(
    scan_configs: bool = True,
    detect_env: bool = True,
    detect_local: bool = True,
    probe_network: bool = True,
    network_timeout: float = 0.5,
) -> DiscoveryResult:
    """Run all discovery layers and return merged result.

    Args:
        scan_configs: Scan existing MCP client configs (Claude Desktop, etc.)
        detect_env: Detect from environment variables
        detect_local: Detect local tools (npx, docker, sqlite)
        probe_network: Check env vars for HTTP MCP endpoints
    Returns:
        DiscoveryResult with merged, deduplicated servers.
    """
    result = DiscoveryResult()

    all_findings = []

    if scan_configs:
        all_findings.extend(_scan_claude_desktop())
        all_findings.extend(_scan_cursor())
        all_findings.extend(_scan_cline())
        all_findings.extend(_scan_windsurf())

    if detect_env:
        all_findings.extend(_detect_from_env())

    if detect_local:
        all_findings.extend(_detect_local_tools())

    if probe_network:
        all_findings.extend(_probe_http_mcp())

    # Merge and deduplicate
    # Priority: existing config > claude-desktop > cursor > cline > windsurf > env > local > network > manual
    source_priority = {
        "claude-desktop": 0,
        "cursor": 1,
        "cline": 2,
        "windsurf": 3,
        "env": 4,
        "local": 5,
        "network": 6,
        "manual": 8,
    }

    # Sort by source priority (lowest = highest priority)
    all_findings.sort(key=lambda x: source_priority.get(x["source"], 99))

    for item in all_findings:
        name = item["name"]
        config = item["config"]
        source = item["source"]
        reason = item["reason"]

        if name in result.servers:
            # Already found — just add the source
            result.sources[name].append(source)
            # Don't overwrite config (first source wins)
        else:
            result.servers[name] = config
            result.sources[name] = [source]
            result.reasons[name] = reason

    return result


# ═══════════════════════════════════════════════════════════════
# HTTP MCP endpoint helpers
# ═══════════════════════════════════════════════════════════════

def probe_http_endpoint(url: str, timeout: float = 2.0) -> dict | None:
    """Probe an HTTP MCP endpoint and return info if alive.

    Returns:
        {"url": ..., "tools_count": N, "alive": True} or None
    """
    if not url.startswith("http"):
        url = f"http://{url}"

    # Ensure /mcp path
    if not url.rstrip("/").endswith("/mcp"):
        url = url.rstrip("/") + "/mcp"

    if not _probe_endpoint(url, timeout=timeout):
        return None

    # Try to get tool count
    try:
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }
        payload = json.dumps(msg).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")

        handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(handler)
        resp = opener.open(req, timeout=timeout)
        body = resp.read().decode("utf-8", errors="replace")

        # Parse response
        data = None
        for line in body.split("\n"):
            s = line.strip()
            if s.startswith("data: "):
                try:
                    data = json.loads(s[6:])
                    break
                except json.JSONDecodeError:
                    continue

        if data is None:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                pass

        if isinstance(data, dict) and "result" in data:
            tools = data["result"].get("tools", [])
            return {
                "url": url,
                "tools_count": len(tools),
                "alive": True,
            }

        return {"url": url, "tools_count": 0, "alive": True}

    except Exception:
        return {"url": url, "tools_count": 0, "alive": True}


def make_http_config(url: str, name: str = "http-endpoint") -> dict:
    """Create a config entry for an HTTP MCP endpoint.

    Args:
        url: HTTP MCP endpoint URL (e.g. "http://localhost:8080/mcp")
        name: Server name in config

    Returns:
        Config dict ready for add_server()
    """
    if not url.startswith("http"):
        url = f"http://{url}"
    if not url.rstrip("/").endswith("/mcp"):
        url = url.rstrip("/") + "/mcp"

    return {
        "transport": "http",
        "url": url,
    }
