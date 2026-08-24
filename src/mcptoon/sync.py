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
mcptoon sync — Sync MCP server config to AI agent config files.

Reads mcptoon's unified config (~/.mcptoon/config.json) and writes
to each agent's native config format. This is the reverse of discover:
  - discover: read from agents → mcptoon config
  - sync:     write from mcptoon config → agents

Supported targets:
  - Claude Desktop (claude_desktop_config.json)
  - Cursor (.cursor/mcp.json)
  - Cline (.cline/mcp_config.json or VS Code settings)
  - Windsurf (.codeium/windsurf/mcp_config.json)
  - VS Code Copilot (settings.json → mcp.servers)
  - Codex (AGENTS.md — mentions mcptoon as the tool manager)

Usage:
    from mcptoon.sync import sync_to_all, sync_to_agent
    result = sync_to_all(dry_run=True)
    result = sync_to_agent("cursor", dry_run=False)
"""
import json
import os
import sys
from pathlib import Path

from .config import load_config, CONFIG_DIR


# ─── Path helpers (mirrors discover.py) ───

def _home() -> Path:
    """Get home directory, Windows-compatible."""
    return Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))


def _appdata() -> Path:
    """Get Windows AppData path, or fallback to home."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(_home() / "AppData" / "Roaming")))
    return _home()


# ─── Agent config file paths ───

def _claude_desktop_path() -> Path:
    """Claude Desktop config file path."""
    if sys.platform == "win32":
        return _appdata() / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        return _home() / ".config" / "Claude" / "claude_desktop_config.json"


def _cursor_path() -> list[Path]:
    """Cursor config file paths (global + project-level)."""
    return [
        _home() / ".cursor" / "mcp.json",
        Path.cwd() / ".cursor" / "mcp.json",
    ]


def _cline_path() -> Path:
    """Cline config file path (VS Code extension)."""
    # Cline stores in VS Code globalStorage on Windows
    if sys.platform == "win32":
        return _appdata() / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json"
    elif sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json"
    else:
        return _home() / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json"


def _windsurf_path() -> Path:
    """Windsurf config file path."""
    return _home() / ".codeium" / "windsurf" / "mcp_config.json"


def _vscode_copilot_path() -> Path:
    """VS Code Copilot settings.json path."""
    if sys.platform == "win32":
        return _appdata() / "Code" / "User" / "settings.json"
    elif sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    else:
        return _home() / ".config" / "Code" / "User" / "settings.json"


# ─── Config conversion ───

def _mcptoon_to_agent_format(server_name: str, server_cfg: dict) -> dict:
    """Convert mcptoon server config to agent-native format.

    Agent format (Claude Desktop / Cursor / Cline / Windsurf) is:
        {
            "command": "npx",
            "args": ["-y", "@mcp/server-fetch"],
            "env": {"KEY": "value"}
        }

    For HTTP servers:
        {
            "url": "http://localhost:8080/mcp",
            "headers": {"Authorization": "Bearer xxx"}
        }
    """
    transport = server_cfg.get("transport", "stdio")

    if transport == "http":
        result = {"url": server_cfg.get("url", "")}
        headers = server_cfg.get("headers")
        if headers:
            result["headers"] = headers
        return result

    # stdio
    command = server_cfg.get("command", [])
    args = server_cfg.get("args", [])
    env = server_cfg.get("env", {})

    # Flatten command+args into agent format
    if isinstance(command, list):
        if len(command) == 1:
            cmd_str = command[0]
            all_args = list(args)
        else:
            cmd_str = command[0] if command else ""
            all_args = list(command[1:]) + list(args)
    else:
        cmd_str = command
        all_args = list(args)

    result = {}
    if cmd_str:
        result["command"] = cmd_str
    if all_args:
        result["args"] = all_args
    if env:
        result["env"] = env

    return result


def _build_mcp_servers_dict(config: dict) -> dict:
    """Build {name: agent_format} from mcptoon config's servers."""
    servers = config.get("servers", {})
    if not servers:
        # Try flat format (server names at top level)
        servers = {k: v for k, v in config.items()
                   if isinstance(v, dict) and ("transport" in v or "command" in v or "url" in v)}

    result = {}
    for name, cfg in servers.items():
        agent_cfg = _mcptoon_to_agent_format(name, cfg)
        if agent_cfg:
            result[name] = agent_cfg
    return result


# ─── Detection (which agents are installed) ───

def detect_installed_agents() -> list[dict]:
    """Detect which AI agents are installed on this machine.

    Returns list of {id, name, config_path, exists}.
    """
    agents = []

    # Claude Desktop
    path = _claude_desktop_path()
    agents.append({
        "id": "claude-desktop",
        "name": "Claude Desktop",
        "config_path": str(path),
        "exists": path.parent.exists(),
    })

    # Cursor
    for p in _cursor_path():
        agents.append({
            "id": "cursor",
            "name": f"Cursor ({'project' if p == _cursor_path()[-1] else 'global'})",
            "config_path": str(p),
            "exists": p.parent.exists() or p.exists(),
        })

    # Cline
    path = _cline_path()
    agents.append({
        "id": "cline",
        "name": "Cline",
        "config_path": str(path),
        "exists": path.parent.parent.parent.parent.exists() if path.parts else False,
    })

    # Windsurf
    path = _windsurf_path()
    agents.append({
        "id": "windsurf",
        "name": "Windsurf",
        "config_path": str(path),
        "exists": path.parent.exists(),
    })

    # VS Code Copilot
    path = _vscode_copilot_path()
    agents.append({
        "id": "vscode-copilot",
        "name": "VS Code Copilot",
        "config_path": str(path),
        "exists": path.parent.exists(),
    })

    return agents


# ─── Sync functions ───

def _read_json_safe(path: Path) -> dict:
    """Read JSON file, return empty dict on error."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json_safe(path: Path, data: dict) -> bool:
    """Write JSON file, creating parent dirs. Returns True on success."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def _merge_mcp_servers(existing: dict, new_servers: dict) -> dict:
    """Merge new servers into existing config's mcpServers.

    Preserves existing servers not in mcptoon, updates existing ones
    that are in mcptoon, and adds new ones.
    """
    result = dict(existing)
    current_servers = dict(result.get("mcpServers", {}))
    current_servers.update(new_servers)
    result["mcpServers"] = current_servers
    return result


def sync_to_agent(agent_id: str, dry_run: bool = False, config: dict | None = None) -> dict:
    """Sync mcptoon config to a specific agent.

    Args:
        agent_id: One of 'claude-desktop', 'cursor', 'cline', 'windsurf', 'vscode-copilot', 'codex'
        dry_run: If True, return what would be written without writing
        config: Override config (for testing). If None, loads from default.

    Returns:
        {
            "agent": agent_id,
            "path": str,
            "servers_synced": int,
            "written": bool,
            "error": str | None,
        }
    """
    if config is None:
        config = load_config()

    mcp_servers = _build_mcp_servers_dict(config)

    if not mcp_servers:
        return {
            "agent": agent_id,
            "path": "",
            "servers_synced": 0,
            "written": False,
            "error": "No servers in mcptoon config. Run: mcptoon add <name> ...",
        }

    # Determine config file path and write logic
    if agent_id == "claude-desktop":
        path = _claude_desktop_path()
        existing = _read_json_safe(path)
        merged = _merge_mcp_servers(existing, mcp_servers)
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        ok = _write_json_safe(path, merged)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": ok, "error": None if ok else "Write failed"}

    elif agent_id == "cursor":
        # Write to global cursor config
        path = _cursor_path()[0]
        existing = _read_json_safe(path)
        merged = _merge_mcp_servers(existing, mcp_servers)
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        ok = _write_json_safe(path, merged)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": ok, "error": None if ok else "Write failed"}

    elif agent_id == "cline":
        path = _cline_path()
        existing = _read_json_safe(path)
        merged = _merge_mcp_servers(existing, mcp_servers)
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        ok = _write_json_safe(path, merged)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": ok, "error": None if ok else "Write failed"}

    elif agent_id == "windsurf":
        path = _windsurf_path()
        existing = _read_json_safe(path)
        merged = _merge_mcp_servers(existing, mcp_servers)
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        ok = _write_json_safe(path, merged)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": ok, "error": None if ok else "Write failed"}

    elif agent_id == "vscode-copilot":
        path = _vscode_copilot_path()
        existing = _read_json_safe(path)
        # VS Code stores MCP servers under "mcp.servers" in settings.json
        mcp_section = existing.get("mcp", {})
        current_servers = dict(mcp_section.get("servers", {}))
        current_servers.update(mcp_servers)
        mcp_section["servers"] = current_servers
        existing["mcp"] = mcp_section
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        ok = _write_json_safe(path, existing)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": ok, "error": None if ok else "Write failed"}

    elif agent_id == "codex":
        # Codex uses AGENTS.md — append a note about mcptoon
        path = Path.cwd() / "AGENTS.md"
        content = "\n## MCP Tools\n\nThis project uses [mcptoon](https://github.com/activeing123/mcptoon) for MCP tool management.\nRun `mcptoon manifest --compact` to see available tools.\n\n"
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        try:
            existing_content = path.read_text(encoding="utf-8") if path.exists() else ""
            if "mcptoon" not in existing_content:
                path.write_text(existing_content + content, encoding="utf-8")
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": True, "error": None}
        except OSError as e:
            return {"agent": agent_id, "path": str(path), "servers_synced": 0, "written": False, "error": str(e)}

    else:
        return {"agent": agent_id, "path": "", "servers_synced": 0, "written": False, "error": f"Unknown agent: {agent_id}"}


def sync_to_all(dry_run: bool = False, config: dict | None = None) -> list[dict]:
    """Sync mcptoon config to all installed agents.

    Args:
        dry_run: If True, preview without writing
        config: Override config (for testing)

    Returns:
        List of sync results, one per agent.
    """
    agents = detect_installed_agents()
    results = []
    for agent in agents:
        result = sync_to_agent(agent["id"], dry_run=dry_run, config=config)
        result["agent_name"] = agent["name"]
        result["config_exists"] = agent["exists"]
        results.append(result)
    return results


def format_sync_report(results: list[dict], dry_run: bool = False) -> str:
    """Format sync results as human-readable report."""
    mode = "DRY RUN (preview)" if dry_run else "SYNC COMPLETE"
    lines = [f"── mcptoon sync: {mode} ──", ""]

    written_count = sum(1 for r in results if r.get("written"))
    total_servers = sum(r.get("servers_synced", 0) for r in results)
    error_count = sum(1 for r in results if r.get("error"))

    for r in results:
        icon = "✓" if r.get("written") else ("→" if dry_run and r.get("servers_synced", 0) > 0 else "·")
        name = r.get("agent_name", r.get("agent", ""))
        count = r.get("servers_synced", 0)
        path = r.get("path", "")
        err = r.get("error", "")

        if count > 0:
            lines.append(f"  {icon} {name:25s} {count:3d} servers  {path}")
        elif err:
            lines.append(f"  ! {name:25s} skip ({err})")
        else:
            lines.append(f"  · {name:25s} not installed")

    lines.append("")
    if dry_run:
        lines.append(f"  Preview: {written_count + sum(1 for r in results if r.get('servers_synced', 0) > 0)} agents would be updated, {total_servers} servers total")
    else:
        lines.append(f"  Done: {written_count} agents updated, {total_servers} servers synced, {error_count} errors")

    return "\n".join(lines)
