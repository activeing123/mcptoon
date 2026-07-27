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
mcptoon cli — Command-line entry point

Usage:
    mcptoon list                         List configured servers
    mcptoon manifest                     List all tools (compact)
    mcptoon manifest --full              List all tools with params
    mcptoon inspect <server> <tool>      Show tool schema
    mcptoon call <server> <tool> [ARGS]  Call a tool
    mcptoon init                         Create sample config
    mcptoon add <name> [options]         Add a server
    mcptoon remove <name>                Remove a server
    mcptoon usage                        Show usage stats

Output flags (global):
    --toon         Token-efficient output (default for claude)
    --json         JSON output
    --compact      Names only
    --raw          Raw output
    --head N       Limit to N items
    --max-chars N  Truncate to N chars
    --full         No truncation
"""
import json
import sys
import os

from . import config as cfg
from . import manifest as manifest_mod
from . import output
from . import usage as usage_mod
from .router import call_tool
from .errors import is_error, get_error_message


def main():
    args = sys.argv[1:]

    if not args:
        _print_help()
        sys.exit(0)

    # ─── Parse global output flags ───
    fmt = "auto"
    head_n = 0
    max_chars = 0
    full = False
    cmd_args = []

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--json":
            fmt = "json"
        elif a == "--compact":
            fmt = "compact"
        elif a == "--toon":
            fmt = "toon"
        elif a == "--raw":
            fmt = "raw"
        elif a == "--full":
            full = True
        elif a == "--head" and i + 1 < len(args):
            try:
                head_n = int(args[i + 1])
            except ValueError:
                pass
            i += 1
        elif a == "--max-chars" and i + 1 < len(args):
            try:
                max_chars = int(args[i + 1])
            except ValueError:
                pass
            i += 1
        elif a.startswith("--head="):
            try:
                head_n = int(a.split("=", 1)[1])
            except ValueError:
                pass
        elif a.startswith("--max-chars="):
            try:
                max_chars = int(a.split("=", 1)[1])
            except ValueError:
                pass
        else:
            cmd_args.append(a)
        i += 1

    if not cmd_args:
        _print_help()
        sys.exit(0)

    command = cmd_args[0]
    rest = cmd_args[1:]

    # ─── Dispatch ───
    if command in ("list", "servers"):
        _cmd_list(rest)
    elif command in ("manifest", "tools"):
        _cmd_manifest(rest, fmt, head_n, max_chars, full)
    elif command == "inspect":
        _cmd_inspect(rest, fmt, max_chars, full)
    elif command == "call":
        _cmd_call(rest, fmt, head_n, max_chars, full)
    elif command == "init":
        _cmd_init(rest)
    elif command == "add":
        _cmd_add(rest)
    elif command == "remove":
        _cmd_remove(rest)
    elif command == "usage":
        _cmd_usage(rest, fmt)
    elif command in ("help", "-h", "--help"):
        _print_help()
    else:
        # Try natural language: "mcptoon 有什么工具"
        _try_natural(command, rest, fmt, head_n, max_chars, full)


# ═══════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════

def _cmd_list(_rest):
    """List configured servers."""
    servers = cfg.list_servers()
    if not servers:
        print("No servers configured. Run: mcptoon init")
        return
    print(f"Configured servers ({len(servers)}):")
    for name in servers:
        s_cfg = cfg.get_server_config(name)
        transport = s_cfg.get("transport", "stdio") if s_cfg else "?"
        if transport == "stdio":
            cmd_str = " ".join(
                (s_cfg.get("command", []) if isinstance(s_cfg.get("command"), list) else [s_cfg.get("command", [])])
                + s_cfg.get("args", [])
            )
            print(f"  {name:20s} [stdio]  {cmd_str}")
        else:
            url = s_cfg.get("url", "?") if s_cfg else "?"
            print(f"  {name:20s} [http]   {url}")


def _cmd_manifest(rest, fmt, head_n, max_chars, full):
    """List all tools."""
    full_mode = "--full" in rest or full

    manifest = manifest_mod.get_manifest(use_cache=True)
    if not manifest:
        print("No tools found. Run: mcptoon init")
        return

    if fmt in ("toon", "compact"):
        # For toon/compact, output just the tool names
        result = {}
        for server, tools in manifest.items():
            names = [t.get("name", "?") for t in tools if "error" not in t]
            if names:
                result[server] = names
        print(output.render(result, fmt=fmt, head_n=head_n, max_chars=max_chars, full=full))
    else:
        # Human-readable or JSON
        if fmt == "json":
            print(output.render(manifest, fmt="json", head_n=head_n, max_chars=max_chars, full=full))
        else:
            text = manifest_mod.format_manifest(manifest, full=full_mode)
            if max_chars > 0:
                text = output._truncate(text, max_chars)
            print(text)


def _cmd_inspect(rest, fmt, max_chars, full):
    """Show tool schema."""
    if len(rest) < 2:
        print("Usage: mcptoon inspect <server> <tool>")
        sys.exit(1)

    server = rest[0]
    tool = rest[1]

    info = manifest_mod.inspect_tool(server, tool)
    if not info:
        print(f"Tool not found: {server}:{tool}")
        sys.exit(1)

    print(output.render(info, fmt=fmt if fmt != "auto" else "json", max_chars=max_chars, full=full))


def _cmd_call(rest, fmt, head_n, max_chars, full):
    """Call a tool."""
    if len(rest) < 2:
        print("Usage: mcptoon call <server> <tool> [JSON_ARGS] [--destructive]")
        print("")
        print("Examples:")
        print('  mcptoon call fetch fetch \'{"url":"https://example.com"}\' --toon')
        print('  mcptoon call exa search \'{"query":"AI"}\' --json')
        sys.exit(1)

    server = rest[0]
    tool = rest[1]
    is_destructive = "--destructive" in rest

    # Parse args (JSON string or key=value pairs)
    args = {}
    for item in rest[2:]:
        if item == "--destructive":
            continue
        # Try JSON
        if item.startswith("{"):
            try:
                args = json.loads(item)
                break
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON args: {e}")
                sys.exit(1)
        # key=value
        if "=" in item:
            k, v = item.split("=", 1)
            # Try to parse value as JSON
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                pass
            args[k] = v

    result = call_tool(server, tool, args, is_destructive=is_destructive)

    if is_error(result):
        err = result["_error"]
        print(f"Error [{err['code']}]: {err['message']}", file=sys.stderr)
        if err.get("retry"):
            print("  (retryable)", file=sys.stderr)
        sys.exit(1)

    print(output.render(result, fmt=fmt, head_n=head_n, max_chars=max_chars, full=full))


def _cmd_init(_rest):
    """Create sample config."""
    if cfg.init_sample_config():
        print(f"Sample config created: {cfg.CONFIG_FILE}")
        print("Edit it to add your MCP servers, then run: mcptoon manifest")
    else:
        print(f"Config already exists: {cfg.CONFIG_FILE}")


def _cmd_add(rest):
    """Add a server to config."""
    if not rest:
        print("Usage: mcptoon add <name> --stdio <command> [args...]")
        print("       mcptoon add <name> --http <url> [--header 'Key: Value']")
        sys.exit(1)

    name = rest[0]
    flags = rest[1:]

    if "--stdio" in flags:
        idx = flags.index("--stdio")
        cmd_parts = flags[idx + 1:]
        if not cmd_parts:
            print("Error: --stdio requires a command")
            sys.exit(1)
        # First part is command, rest are args
        server_cfg = {
            "transport": "stdio",
            "command": cmd_parts[0:1] if isinstance(cmd_parts[0], str) else cmd_parts,
            "args": cmd_parts[1:] if len(cmd_parts) > 1 else [],
        }
        # Actually, command should be a list for npx-style
        # Support: mcptoon add fetch --stdio npx -y @mcp/server-fetch
        server_cfg = {
            "transport": "stdio",
            "command": [cmd_parts[0]] + (cmd_parts[1:2] if len(cmd_parts) > 1 else []),
            "args": cmd_parts[2:] if len(cmd_parts) > 2 else [],
        }
        cfg.add_server(name, server_cfg)
        print(f"Added server '{name}' [stdio]: {' '.join(cmd_parts)}")

    elif "--http" in flags:
        idx = flags.index("--http")
        if idx + 1 >= len(flags):
            print("Error: --http requires a URL")
            sys.exit(1)
        url = flags[idx + 1]
        server_cfg = {"transport": "http", "url": url}

        # Parse headers
        headers = {}
        for j, f in enumerate(flags):
            if f == "--header" and j + 1 < len(flags):
                h = flags[j + 1]
                if ":" in h:
                    k, v = h.split(":", 1)
                    headers[k.strip()] = v.strip()
        if headers:
            server_cfg["headers"] = headers

        cfg.add_server(name, server_cfg)
        print(f"Added server '{name}' [http]: {url}")

    else:
        print("Error: must specify --stdio or --http")
        sys.exit(1)


def _cmd_remove(rest):
    """Remove a server."""
    if not rest:
        print("Usage: mcptoon remove <name>")
        sys.exit(1)
    name = rest[0]
    if cfg.remove_server(name):
        print(f"Removed server: {name}")
    else:
        print(f"Server not found: {name}")


def _cmd_usage(_rest, fmt):
    """Show usage stats."""
    stats = usage_mod.get_usage_stats()
    if fmt in ("toon", "compact"):
        print(output.render(stats, fmt=fmt))
    else:
        print(f"Total calls: {stats['total_calls']}")
        print(f"Success rate: {stats['success_rate']}")
        print(f"Tokens (est): {stats['total_tokens_est']}")
        if stats["by_server"]:
            print("\nBy server:")
            for s, c in stats["by_server"].items():
                print(f"  {s:20s} {c}")
        if stats["top_tools"]:
            print("\nTop tools:")
            for t, c in stats["top_tools"].items():
                print(f"  {t:30s} {c}")


# ═══════════════════════════════════════════════════
# Natural language fallback
# ═══════════════════════════════════════════════════

def _try_natural(command, rest, fmt, head_n, max_chars, full):
    """Try to interpret natural language input."""
    text = " ".join([command] + rest).lower()

    if any(kw in text for kw in ["什么", "有哪些", "工具", "tools", "list", "manifest"]):
        _cmd_manifest(rest, fmt, head_n, max_chars, full)
        return

    if any(kw in text for kw in ["服务器", "server", "list server"]):
        _cmd_list(rest)
        return

    print(f"Unknown command: {command}")
    print("Run: mcptoon help")


# ═══════════════════════════════════════════════════
# Help
# ═══════════════════════════════════════════════════

def _print_help():
    print("""mcptoon — Token-efficient MCP CLI client

Usage:
    mcptoon list                         List configured servers
    mcptoon manifest                     List all tools (compact)
    mcptoon manifest --full              List all tools with params
    mcptoon inspect <server> <tool>      Show tool schema
    mcptoon call <server> <tool> [ARGS]  Call a tool
    mcptoon init                         Create sample config
    mcptoon add <name> [options]         Add a server
    mcptoon remove <name>                Remove a server
    mcptoon usage                        Show usage stats

Output flags:
    --toon         Token-efficient output (saves 40-60% tokens)
    --json         JSON output
    --compact      Names only
    --head N       Limit to N items
    --max-chars N  Truncate to N chars
    --full         No truncation

Examples:
    mcptoon init
    mcptoon manifest --toon
    mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
    mcptoon add myserver --stdio npx -y @mcp/server-fetch

Environment:
    MCPTOON_AGENT_TYPE=claude    Auto-select --toon
    MCPTOON_AGENT_TYPE=openai    Auto-select --json

Config: ~/.mcptoon/config.json
""")


if __name__ == "__main__":
    main()
