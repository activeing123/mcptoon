# Copyright 2025 cxh
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
mcptoon config — Server configuration management

Reads server definitions from:
  1. ~/.mcptoon/config.json  (user config)
  2. ./.mcptoon.json          (project config, overrides user)
  3. MCPTOON_SERVERS env var   (JSON string, highest priority)

Config format:
{
  "servers": {
    "exa": {
      "transport": "stdio",
      "command": ["npx", "-y"],
      "args": ["@anthropic/mcp-exa"],
      "env": {"EXA_API_KEY": "..."}
    },
    "github": {
      "transport": "http",
      "url": "http://localhost:3001/mcp",
      "headers": {"Authorization": "Bearer ghp_xxx"}
    }
  }
}
"""
import json
import os
from pathlib import Path


# ─── Paths ───

HOME_DIR = Path.home()
CONFIG_DIR = HOME_DIR / ".mcptoon"
# Env overrides let CI/tests redirect all config I/O without touching the
# real ~/.mcptoon (same isolation pattern as MCPTOON_SERVERS). Resolved at
# CALL time (not import time) so test processes can retarget safely.
CONFIG_FILE = Path(os.environ.get(
    "MCPTOON_CONFIG_FILE", str(CONFIG_DIR / "config.json")))
CONFIG_FILE_TOML = Path(os.environ.get(
    "MCPTOON_CONFIG_FILE_TOML", str(CONFIG_DIR / "config.toml")))


def _config_file() -> Path:
    return Path(os.environ.get("MCPTOON_CONFIG_FILE", str(CONFIG_FILE)))


def _config_file_toml() -> Path:
    return Path(os.environ.get("MCPTOON_CONFIG_FILE_TOML", str(CONFIG_FILE_TOML)))
CACHE_DIR = HOME_DIR / ".cache" / "mcptoon"
LOG_DIR = CONFIG_DIR / "logs"
TOGGLE_FILE = CONFIG_DIR / "toggles.json"

# Ensure dirs exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ─── Server name aliases ───

# Users can use short names; we map to canonical names
SERVER_ALIASES = {
    "exa": "exa",
    "fetch": "fetch",
    "github": "github",
    "fs": "filesystem",
    "filesystem": "filesystem",
}


def resolve_server_name(name: str) -> str:
    """Resolve short name to canonical server name.

    Checks static aliases first, then dynamically checks if 'name'
    is a prefix of any configured server name (e.g. 'fs' → 'filesystem').
    """
    # 1. Static aliases (backward compat)
    if name in SERVER_ALIASES:
        return SERVER_ALIASES[name]

    # 2. Check if exact name exists in config (no resolution needed)
    servers = load_config()
    if name in servers:
        return name

    # 3. Dynamic prefix matching (e.g. 'fs' → 'filesystem')
    for sname in servers:
        if sname.lower() == name.lower():
            return sname

    # 4. Return as-is (let caller handle unknown server)
    return name


# ─── Config loading ───

def load_config() -> dict:
    """Load merged server configuration.

    Priority (highest wins):
      1. MCPTOON_SERVERS env var (JSON string)
      2. ./.mcptoon.json (project local)
      3. ./.mcptoon.toml (project local, TOML)
      4. ~/.mcptoon/config.toml (user global, TOML)
      5. ~/.mcptoon/config.json (user global, JSON)

    Supports both JSON and TOML config files.
    TOML is preferred for hand-editing (comments, cleaner syntax).
    """
    servers = {}

    # 1. User global config — try TOML first, then JSON
    toml_file = _config_file_toml()
    json_file = _config_file()
    if toml_file.exists():
        try:
            data = _parse_toml(toml_file.read_text(encoding="utf-8"))
            servers.update(data.get("servers", {}))
        except (OSError, ValueError):
            pass
    if json_file.exists():
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            servers.update(data.get("servers", {}))
        except (json.JSONDecodeError, OSError):
            pass

    # 2. Project local config (overrides user) — try TOML first, then JSON
    local_toml = Path(".mcptoon.toml")
    if local_toml.exists():
        try:
            data = _parse_toml(local_toml.read_text(encoding="utf-8"))
            servers.update(data.get("servers", {}))
        except (OSError, ValueError):
            pass
    local = Path(".mcptoon.json")
    if local.exists():
        try:
            data = json.loads(local.read_text(encoding="utf-8"))
            servers.update(data.get("servers", {}))
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Environment variable (highest priority)
    env_servers = os.environ.get("MCPTOON_SERVERS", "")
    if env_servers:
        try:
            data = json.loads(env_servers)
            servers.update(data.get("servers", {}))
        except json.JSONDecodeError:
            pass

    return servers


def save_config(servers: dict, fmt: str = ""):
    """Save server configuration to user config file.

    Args:
        servers: Server config dict
        fmt: "json" or "toml". If empty, preserves existing format,
              defaults to JSON for new configs.
    """
    # Determine format: explicit > existing file > default JSON
    json_file = _config_file()
    toml_file = _config_file_toml()
    if not fmt:
        if toml_file.exists() and not json_file.exists():
            fmt = "toml"
        else:
            fmt = "json"

    if fmt == "toml":
        toml_file.write_text(
            _dump_toml(servers),
            encoding="utf-8",
        )
    else:
        json_file.write_text(
            json.dumps({"servers": servers}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def add_server(name: str, config: dict):
    """Add or update a server in config."""
    servers = load_config()
    servers[name] = config
    save_config(servers)


def merge_servers(new_servers: dict, overwrite: bool = False) -> tuple:
    """Merge new servers into existing config.

    Args:
        new_servers: {name: config} to merge in
        overwrite: If True, overwrite existing servers. If False, skip existing.

    Returns:
        (added_count, skipped_count, overwritten_count)
    """
    existing = load_config()
    added = 0
    skipped = 0
    overwritten = 0

    for name, cfg in new_servers.items():
        if name in existing and not overwrite:
            skipped += 1
        elif name in existing and overwrite:
            existing[name] = cfg
            overwritten += 1
        else:
            existing[name] = cfg
            added += 1

    save_config(existing)
    return (added, skipped, overwritten)


def remove_server(name: str) -> bool:
    """Remove a server from config. Returns True if existed."""
    servers = load_config()
    if name in servers:
        del servers[name]
        save_config(servers)
        return True
    return False


def list_servers() -> list[str]:
    """List configured server names."""
    return sorted(load_config().keys())


def get_server_config(name: str) -> dict | None:
    """Get config for a specific server."""
    return load_config().get(name)


# ─── Toggle management (per-tool enable/disable) ───

def load_toggles() -> dict:
    """Load tool toggle state. Format: {"server:tool": true/false}."""
    if not TOGGLE_FILE.exists():
        return {}
    try:
        return json.loads(TOGGLE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_toggles(toggles: dict):
    """Save tool toggle state."""
    TOGGLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOGGLE_FILE.write_text(
        json.dumps(toggles, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def is_tool_enabled(server: str, tool: str) -> bool:
    """Check if a tool is enabled (default: True)."""
    toggles = load_toggles()
    key = f"{server}:{tool}"
    return toggles.get(key, True)


def toggle_tool(server: str, tool: str) -> bool:
    """Toggle a tool on/off. Returns new state (True=enabled, False=disabled)."""
    toggles = load_toggles()
    key = f"{server}:{tool}"
    current = toggles.get(key, True)
    toggles[key] = not current
    save_toggles(toggles)
    return not current


def list_disabled_tools() -> list[str]:
    """List all disabled tool keys."""
    toggles = load_toggles()
    return [k for k, v in toggles.items() if not v]


# ─── Sample config for first-time users ───

SAMPLE_CONFIG = {
    "servers": {
        "fetch": {
            "transport": "stdio",
            "command": ["npx", "-y"],
            "args": ["@modelcontextprotocol/server-fetch"],
        },
        "filesystem": {
            "transport": "stdio",
            "command": ["npx", "-y"],
            "args": ["@modelcontextprotocol/server-filesystem", "."],
        },
    }
}


def init_sample_config():
    """Create a sample config if none exists."""
    if not _config_file().exists() and not _config_file_toml().exists():
        save_config(SAMPLE_CONFIG["servers"])
        return True
    return False


# ═══════════════════════════════════════════════════════════════
# TOML support (zero-dependency, pure stdlib)
# ═══════════════════════════════════════════════════════════════

def _parse_toml(text: str) -> dict:
    """Parse a TOML string into a dict.

    Uses Python 3.11+ tomllib when available. Falls back to a
    minimal built-in parser that handles the mcptoon config subset
    (tables, strings, arrays, booleans).

    Raises ValueError on parse error.
    """
    # Try stdlib tomllib (Python 3.11+)
    try:
        import tomllib
        return tomllib.loads(text)
    except ImportError:
        pass

    # Fallback: minimal parser for mcptoon config format
    return _toml_lite_parse(text)


def _toml_lite_parse(text: str) -> dict:
    """Minimal TOML parser for mcptoon config files.

    Supports:
      - [section.subsection] tables
      - key = "string"
      - key = ["a", "b"] arrays
      - key = true/false
      - # comments

    Not supported (not needed for mcptoon config):
      - Inline tables, multiline strings, dates, floats, hex
    """
    result = {}
    current_table = result

    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Table header: [section] or [section.subsection]
        # Strip inline comments from table headers first
        if line.startswith("["):
            # Find the closing bracket, ignore anything after it (inline comment)
            close = line.find("]")
            if close >= 0:
                line = line[:close + 1]
        if line.startswith("[") and line.endswith("]"):
            table_path = line[1:-1].strip()
            parts = [p.strip() for p in table_path.split(".")]
            current_table = result
            for part in parts:
                if part not in current_table:
                    current_table[part] = {}
                current_table = current_table[part]
            continue

        # key = value
        if "=" not in line:
            raise ValueError(f"TOML parse error at line {line_num}: no '=' found")

        eq_pos = line.index("=")
        key = line[:eq_pos].strip()
        value_str = line[eq_pos + 1:].strip()

        # Strip inline comments (but not inside strings)
        if value_str.startswith('"'):
            # String value — find closing quote, then strip comment after it
            i = 1
            while i < len(value_str):
                if value_str[i] == '\\':
                    i += 2  # Skip escaped char
                    continue
                if value_str[i] == '"':
                    break
                i += 1
            if i < len(value_str):
                # Found closing quote at position i
                # Keep the quoted string, strip everything after (inline comment)
                value_str = value_str[:i + 1]
        elif "#" in value_str:
            value_str = value_str[:value_str.index("#")].strip()

        value = _toml_parse_value(value_str, line_num)
        current_table[key] = value

    return result


def _toml_parse_value(s: str, line_num: int = 0):
    """Parse a TOML value string."""
    s = s.strip()

    # String
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")

    # Array
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        items = []
        # Simple split by comma (handles typical config arrays)
        parts = _split_array_items(inner)
        for part in parts:
            part = part.strip()
            if part:
                items.append(_toml_parse_value(part, line_num))
        return items

    # Boolean
    if s == "true":
        return True
    if s == "false":
        return False

    # Integer
    try:
        return int(s)
    except ValueError:
        pass

    # Float
    try:
        return float(s)
    except ValueError:
        pass

    # Bare string (TOML doesn't officially support this, but be lenient)
    return s


def _split_array_items(s: str) -> list[str]:
    """Split array items by comma, respecting quoted strings."""
    items = []
    current = ""
    in_quotes = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '"':
            in_quotes = not in_quotes
            current += c
        elif c == "," and not in_quotes:
            items.append(current)
            current = ""
        else:
            current += c
        i += 1
    if current.strip():
        items.append(current)
    return items


def _dump_toml(servers: dict) -> str:
    """Serialize servers config as TOML string.

    Produces clean, human-readable TOML with comments.

    Example output:
        # mcptoon configuration
        # See: https://github.com/activeing123/mcptoon

        [servers.fetch]
        transport = "stdio"
        command = ["npx", "-y"]
        args = ["@modelcontextprotocol/server-fetch"]

        [servers.filesystem]
        transport = "stdio"
        command = ["npx", "-y"]
        args = ["@modelcontextprotocol/server-filesystem", "."]
    """
    lines = [
        "# mcptoon configuration",
        "# Format: TOML (easier to hand-edit than JSON)",
        "# Run: mcptoon manifest  to see your tools",
        "",
    ]

    for name in sorted(servers.keys()):
        cfg = servers[name]
        lines.append(f"[servers.{name}]")

        # Transport
        transport = cfg.get("transport", "stdio")
        lines.append(f'transport = "{transport}"')

        # stdio fields
        if transport == "stdio":
            command = cfg.get("command", [])
            if isinstance(command, list):
                lines.append(f"command = {_toml_array(command)}")
            else:
                lines.append(f'command = ["{command}"]')

            args = cfg.get("args", [])
            if args:
                lines.append(f"args = {_toml_array(args)}")

            env = cfg.get("env", {})
            if env:
                lines.append("")
                lines.append(f"[servers.{name}.env]")
                for k, v in sorted(env.items()):
                    lines.append(f'{k} = "{v}"')
                lines.append("")

        # http fields
        elif transport == "http":
            url = cfg.get("url", "")
            lines.append(f'url = "{url}"')
            headers = cfg.get("headers", {})
            if headers:
                lines.append("")
                lines.append(f"[servers.{name}.headers]")
                for k, v in sorted(headers.items()):
                    lines.append(f'{k} = "{v}"')
                lines.append("")

        lines.append("")

    return "\n".join(lines)


def _toml_array(items: list) -> str:
    """Format a list as a TOML array string."""
    parts = []
    for item in items:
        if isinstance(item, str):
            parts.append(f'"{item}"')
        elif isinstance(item, bool):
            parts.append("true" if item else "false")
        elif item is None:
            parts.append('""')
        else:
            parts.append(str(item))
    return "[" + ", ".join(parts) + "]"
