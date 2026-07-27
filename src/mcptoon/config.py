# -*- coding: utf-8 -*-
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
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = HOME_DIR / ".cache" / "mcptoon"
LOG_DIR = CONFIG_DIR / "logs"

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
    """Resolve short name to canonical server name."""
    return SERVER_ALIASES.get(name, name)


# ─── Config loading ───

def load_config() -> dict:
    """Load merged server configuration.

    Priority (highest wins):
      1. MCPTOON_SERVERS env var (JSON string)
      2. ./.mcptoon.json (project local)
      3. ~/.mcptoon/config.json (user global)
    """
    servers = {}

    # 1. User global config
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            servers.update(data.get("servers", {}))
        except (json.JSONDecodeError, OSError):
            pass

    # 2. Project local config (overrides user)
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


def save_config(servers: dict):
    """Save server configuration to user config file."""
    CONFIG_FILE.write_text(
        json.dumps({"servers": servers}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def add_server(name: str, config: dict):
    """Add or update a server in config."""
    servers = load_config()
    servers[name] = config
    save_config(servers)


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
    if not CONFIG_FILE.exists():
        save_config(SAMPLE_CONFIG["servers"])
        return True
    return False
