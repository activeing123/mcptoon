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
mcptoon cli — Command-line entry point

Usage:
    mcptoon list                         List configured servers
    mcptoon manifest                     List all tools (compact)
    mcptoon manifest --full              List all tools with params
    mcptoon manifest --format openai    Export as OpenAI function calling
    mcptoon manifest --format openapi   Export as OpenAPI 3.0 spec
    mcptoon discover                     Auto-discover MCP servers (scan + probe)
    mcptoon discover --write             Discover + write to config
    mcptoon discover --http <url>        Probe a specific HTTP MCP endpoint
    mcptoon inspect <server> <tool>      Show tool schema
    mcptoon search <query>              Search tools across all servers
    mcptoon call <server> <tool> [ARGS]  Call a tool
    mcptoon call --auto <tool> [ARGS]    Call a tool (auto-find server)
    mcptoon call <server> <tool> --stdin   Read args from stdin (large payloads)
    mcptoon init                         Create sample config
    mcptoon init --auto                  Auto-discover all MCP servers
    mcptoon init --auto --dry            Discover, print only, don't write
    mcptoon init --auto --http <url>     Add HTTP MCP endpoint
    mcptoon add <name> [options]         Add a server
    mcptoon remove <name>                Remove a server
    mcptoon usage                        Show usage stats
    mcptoon stats                        Token savings dashboard (detailed)
    mcptoon toggle <server> <tool>       Toggle a tool on/off
    mcptoon toggle --list                List all toggled tools
    mcptoon install <name> --npm <pkg>    Install MCP server from npm
    mcptoon install <name> --pip <pkg>    Install MCP server from pip
    mcptoon install <name> --url <url>   Install HTTP/SSE MCP server
    mcptoon install --list               List installed servers
    mcptoon install --remove <name>      Remove an installed server
    mcptoon sync                         Sync config to all agents (Claude Desktop, Cursor, etc.)
    mcptoon sync --dry                   Preview without writing
    mcptoon sync --agent <id>            Sync to one agent only
    mcptoon health                       Health check all MCP servers (catches zombies)
    mcptoon health --json                JSON output for CI/CD (exit 1 if any dead)
    mcptoon health --timeout <sec>       Set per-server timeout
    mcptoon serve                        Run as stdio MCP server (1 Agent → 100 servers)
    mcptoon serve --listen :8080         HTTP mode for remote/multi-agent
    mcptoon doctor                       Self-diagnose config + connectivity
    mcptoon completion <shell>           Generate shell completion (bash|zsh|fish|ps)

Output flags (global):
    --toon         Standard TOON (toon-format/toon spec, saves 30-60% tokens)
    --mcptoon      Legacy mcptoon pipe format (saves 20-40% tokens, round-trip safe)
    --slim         Ultra-compact tool manifests (93% savings)
    --json         JSON output
    --compact      Names only
    --raw          Raw output
    --head N       Limit to N items
    --max-chars N  Truncate to N chars
    --full         No truncation
    --format X     Export format: openai|openapi|mcp|json|human
    --stdin        Read JSON args from stdin (for large payloads)
"""
import json
import sys
import os

from . import config as cfg
from . import manifest as manifest_mod
from . import output
from . import usage as usage_mod
from .router import call_tool
from .errors import is_error


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
    export_format = ""
    use_stdin = False
    fallback_json = False
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
        elif a == "--mcptoon":
            fmt = "mcptoon"
        elif a == "--slim":
            fmt = "slim"
        elif a == "--raw":
            fmt = "raw"
        elif a == "--full":
            full = True
        elif a == "--stdin":
            use_stdin = True
        elif a == "--fallback-json":
            fallback_json = True
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
        elif a == "--format" and i + 1 < len(args):
            export_format = args[i + 1]
            i += 1
        elif a.startswith("--format="):
            export_format = a.split("=", 1)[1]
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
        _cmd_manifest(rest, fmt, head_n, max_chars, full, export_format)
    elif command == "inspect":
        _cmd_inspect(rest, fmt, max_chars, full)
    elif command == "search":
        _cmd_search(rest, fmt, head_n, max_chars, full)
    elif command == "call":
        _cmd_call(rest, fmt, head_n, max_chars, full, use_stdin, fallback_json)
    elif command in ("quickstart", "qs"):
        _cmd_quickstart(rest, fmt)
    elif command == "init":
        _cmd_init(rest, fmt)
    elif command == "add":
        _cmd_add(rest)
    elif command == "remove":
        _cmd_remove(rest)
    elif command == "usage":
        _cmd_usage(rest, fmt)
    elif command == "stats":
        _cmd_stats(rest, fmt)
    elif command == "toggle":
        _cmd_toggle(rest, fmt)
    elif command == "discover":
        if "--health" in rest:
            # Legacy health-check mode
            health_args = [a for a in rest if a != "--health"]
            _cmd_health_check(health_args, fmt)
        else:
            _cmd_auto_discover(rest, fmt)
    elif command == "doctor":
        _cmd_doctor(rest)
    elif command == "install":
        _cmd_install(rest, fmt)
    elif command == "completion":
        _cmd_completion(rest)
    elif command == "serve":
        _cmd_serve(rest)
    elif command == "demo":
        _cmd_demo(rest)
    elif command == "sync":
        _cmd_sync(rest, fmt)
    elif command == "health":
        _cmd_health(rest, fmt)
    elif command in ("help", "-h", "--help"):
        _print_help()
    else:
        # Try natural language: "mcptoon 有什么工具"
        _try_natural(command, rest, fmt, head_n, max_chars, full)


# ═══════════════════════════════════════════════════
# Error fix suggestions
# ═══════════════════════════════════════════════════

_FIX_SUGGESTIONS = {
    "SERVER_NOT_FOUND": "Try: mcptoon list    | mcptoon add <name> --stdio npx -y <package>    | mcptoon doctor",
    "CONFIG_MISSING": "Try: mcptoon init",
    "TOOL_NOT_FOUND": "Try: mcptoon manifest    | mcptoon inspect <server>",
    "UNKNOWN_TOOL": "Try: mcptoon inspect <server>    | mcptoon manifest --slim",
    "CONNECTION_FAILED": "Try: mcptoon doctor    | check if npx/node is installed and in PATH",
    "TIMEOUT": "Try: mcptoon doctor    | the server may be slow to start (first npx download)",
    "DANGEROUS_OP": "Add --destructive flag to confirm: mcptoon call <server> <tool> '{...}' --destructive",
    "CREDENTIAL_LEAK": "Result blocked for safety. If this is a false positive, use --raw to bypass",
    "TOOL_POISONING": "Result blocked for safety. If this is a false positive, use --raw to bypass",
    "PARSE_ERROR": "Try: mcptoon inspect <server> <tool>    | check required parameters and types",
}


def _fix_suggestion(code: str, server: str = "", tool: str = "") -> str:
    """Return a fix suggestion string for a given error code."""
    suggestion = _FIX_SUGGESTIONS.get(code, "")
    if suggestion and server:
        suggestion = suggestion.replace("<server>", server)
    if suggestion and tool:
        suggestion = suggestion.replace("<tool>", tool)
    return suggestion


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


def _cmd_manifest(rest, fmt, head_n, max_chars, full, export_format=""):
    """List all tools."""
    full_mode = "--full" in rest or full

    manifest = manifest_mod.get_manifest(use_cache=True)
    if not manifest:
        print("No tools found. Run: mcptoon init")
        return

    # Export format takes priority
    if export_format:
        exported = manifest_mod.export_manifest(manifest, export_format)
        print(exported)
        return

    if fmt == "slim":
        # For slim, output ultra-compact tool schemas
        all_tools = []
        for server, tools in manifest.items():
            for t in tools:
                if "error" not in t:
                    all_tools.append(t)
        print(output.render(all_tools, fmt="slim", head_n=head_n, max_chars=max_chars, full=full))
    elif fmt in ("toon", "mcptoon", "compact"):
        # For toon/mcptoon/compact, output just the tool names
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
        print("       mcptoon inspect <server>           (list all tools)")
        sys.exit(1)

    server = rest[0]
    tool = rest[1]

    info = manifest_mod.inspect_tool(server, tool)
    if not info:
        # Fuzzy match: "Did you mean?"
        suggestions = manifest_mod.fuzzy_match_tool(server, tool)
        if suggestions:
            print(f"Tool not found: {server}:{tool}")
            print(f"Did you mean: {', '.join(suggestions)}")
        else:
            print(f"Tool not found: {server}:{tool}")
            # Show all tools for this server
            tools = manifest_mod.get_server_tools(server)
            if tools:
                print(f"Available tools: {' '.join(t.get('name','?') for t in tools)}")
        sys.exit(1)

    print(output.render(info, fmt=fmt if fmt != "auto" else "json", max_chars=max_chars, full=full))


def _cmd_call(rest, fmt, head_n, max_chars, full, use_stdin=False, fallback_json=False):
    """Call a tool."""
    # Check for --auto mode
    is_auto = "--auto" in rest
    if is_auto:
        rest = [a for a in rest if a != "--auto"]
        if len(rest) < 1:
            print("Usage: mcptoon call --auto <tool> [JSON_ARGS] [--destructive] [--stdin]")
            print("")
            print("Examples:")
            print('  mcptoon call --auto search \'{"query":"AI"}\' --toon')
            print('  mcptoon call --auto fetch \'{"url":"https://example.com"}\'')
            sys.exit(1)

        tool = rest[0]
        is_destructive = "--destructive" in rest

        # Parse args (same logic as below)
        args = {}
        if use_stdin:
            stdin_data = sys.stdin.read()
            if stdin_data.strip():
                try:
                    args = json.loads(stdin_data)
                except json.JSONDecodeError as e:
                    print(f"Error parsing stdin JSON: {e}", file=sys.stderr)
                    sys.exit(1)
        else:
            for item in rest[1:]:
                if item == "--destructive":
                    continue
                if item.startswith("{"):
                    try:
                        args = json.loads(item)
                        break
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON args: {e}")
                        sys.exit(1)
                if "=" in item:
                    k, v = item.split("=", 1)
                    try:
                        v = json.loads(v)
                    except json.JSONDecodeError:
                        pass
                    args[k] = v

        from .router import call_tool_auto
        result = call_tool_auto(tool, args, is_destructive=is_destructive)

        if is_error(result):
            err = result["_error"]
            print(f"Error [{err['code']}]: {err['message']}", file=sys.stderr)
            if result.get("suggestions"):
                servers_list = ", ".join(result["suggestions"])
                print(f"  Available on servers: {servers_list}", file=sys.stderr)
                print(f"  Try: mcptoon call <server> {tool} ...", file=sys.stderr)
            sys.exit(1)

        # Render with fallback-json if needed
        _render_result(result, fmt, head_n, max_chars, full, fallback_json)
        return

    if len(rest) < 2:
        print("Usage: mcptoon call <server> <tool> [JSON_ARGS] [--destructive] [--stdin]")
        print("       mcptoon call --auto <tool> [JSON_ARGS] [--destructive] [--stdin]")
        print("")
        print("Examples:")
        print('  mcptoon call fetch fetch \'{"url":"https://example.com"}\' --toon')
        print('  mcptoon call exa search \'{"query":"AI"}\' --json')
        print('  mcptoon call --auto search \'{"query":"AI"}\'  # auto-find server')
        print('  echo \'{"huge":"payload"}\' | mcptoon call server tool --stdin --toon')
        sys.exit(1)

    server = rest[0]
    tool = rest[1]
    is_destructive = "--destructive" in rest

    # Parse args
    args = {}

    if use_stdin:
        # Read JSON args from stdin (for large payloads >32767 chars)
        stdin_data = sys.stdin.read()
        if stdin_data.strip():
            try:
                args = json.loads(stdin_data)
            except json.JSONDecodeError as e:
                print(f"Error parsing stdin JSON: {e}", file=sys.stderr)
                sys.exit(1)
    else:
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
        # Fuzzy match suggestions for unknown tools
        if err["code"] == "UNKNOWN_TOOL" and result.get("suggestions"):
            print(f"Did you mean: {', '.join(result['suggestions'])}", file=sys.stderr)
        # Fix suggestions for common errors
        fix = _fix_suggestion(err["code"], server, tool)
        if fix:
            print(f"  Fix: {fix}", file=sys.stderr)
        sys.exit(1)

    _render_result(result, fmt, head_n, max_chars, full, fallback_json)


def _render_result(result, fmt, head_n, max_chars, full, fallback_json=False):
    """Render tool call result with optional fallback-json.

    If fallback_json is True and the chosen format (toon/mcptoon/slim) fails
    to encode the result, automatically fall back to JSON output.
    """
    if not fallback_json or fmt in ("json", "auto", "raw"):
        print(output.render(result, fmt=fmt, head_n=head_n, max_chars=max_chars, full=full))
        return

    # Try the requested format, fall back to JSON on error
    try:
        rendered = output.render(result, fmt=fmt, head_n=head_n, max_chars=max_chars, full=full)
        # Check for encoding issues
        if rendered and "Error" in rendered[:50] and "encode" in rendered.lower():
            raise ValueError(f"Encoding failed with {fmt}")
        print(rendered)
    except (ValueError, TypeError, KeyError) as e:
        print(f"# fallback-json: {fmt} encoding failed ({e}), falling back to JSON", file=sys.stderr)
        print(output.render(result, fmt="json", head_n=head_n, max_chars=max_chars, full=full))


# ═══════════════════════════════════════════════════
# Search command
# ═══════════════════════════════════════════════════

def _cmd_search(rest, fmt, head_n, max_chars, full):
    """Search tools across all configured servers.

    Usage:
        mcptoon search <query>          # search by keyword
        mcptoon search "git commit"     # multi-word query
        mcptoon search web --slim       # slim format output
        mcptoon search fetch --json     # JSON output
        mcptoon search fetch --head 5   # limit to 5 results
    """
    if not rest:
        print("Usage: mcptoon search <query>")
        print("")
        print("Examples:")
        print('  mcptoon search "search web"')
        print("  mcptoon search git")
        print("  mcptoon search fetch --slim")
        print("  mcptoon search url --json --head 5")
        sys.exit(1)

    query = " ".join(rest)

    from . import manifest as manifest_mod

    results = manifest_mod.search_tools(query, limit=20)

    if not results:
        print(f"No tools found matching '{query}'.")
        print("")
        print("Tips:")
        print("  - Check if your servers are configured: mcptoon list")
        print("  - See all available tools: mcptoon manifest")
        sys.exit(0)

    if fmt == "slim":
        # Ultra-compact: server/tool_name|params
        lines = []
        for r in results:
            lines.append(f"{r['server']}/{r['name']}|{r['params']}|score:{r['score']}")
        print("\n".join(lines))
    elif fmt == "compact":
        # Names only
        names = [f"{r['server']}/{r['name']}" for r in results]
        print(" ".join(names))
    elif fmt == "json":
        print(output.render(results, fmt="json", head_n=head_n, max_chars=max_chars, full=full))
    elif fmt == "toon":
        print(output.render(results, fmt="toon", head_n=head_n, max_chars=max_chars, full=full))
    else:
        # Human-readable
        print(f"Found {len(results)} tool(s) matching '{query}':")
        print("")
        for r in results:
            server = r["server"]
            name = r["name"]
            desc = r["description"]
            params = r["params"]
            score = r["score"]
            print(f"  {server}/{name}  (score: {score})")
            if desc:
                print(f"    {desc}")
            if params:
                print(f"    params: {params}")
            print("")


def _cmd_quickstart(rest, fmt="auto"):
    """One-command onboarding: discover + configure + show tools.

    This is the "aha moment" command. Designed for first-time users.
    Replaces the old 4-step flow (init → add → manifest → call) with one command.

    Usage:
        mcptoon quickstart              # discover + configure + show slim manifest
        mcptoon qs                      # alias
        mcptoon quickstart --http URL    # include HTTP MCP endpoint
        mcptoon quickstart --dry        # don't write config, just show
    """
    is_dry = "--dry" in rest
    http_url = ""
    for i, a in enumerate(rest):
        if a == "--http" and i + 1 < len(rest):
            http_url = rest[i + 1]
            break
        elif a.startswith("--http="):
            http_url = a.split("=", 1)[1]
            break

    from . import discover as disc

    print("mcptoon quickstart — discovering your MCP servers...")
    print("")

    # Step 1: Auto-discover
    result = disc.auto_discover()

    if http_url:
        probe_info = disc.probe_http_endpoint(http_url, timeout=2.0)
        if probe_info and probe_info.get("alive"):
            http_config = disc.make_http_config(http_url)
            result.servers["http-endpoint"] = http_config
            result.sources["http-endpoint"] = ["manual"]
            tool_count = probe_info.get("tools_count", 0)
            result.reasons["http-endpoint"] = f"HTTP MCP endpoint at {http_url} ({tool_count} tools)"

    if result.count == 0:
        print("  No MCP servers found on this machine.")
        print("")
        print("  Don't worry — here's how to get started:")
        print("")
        print("    # Add a zero-config server (no API key needed):")
        print("    mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch")
        print("")
        print("    # Then see your tools:")
        print("    mcptoon manifest --slim")
        print("")
        print("    # Call a tool:")
        print("    mcptoon call fetch fetch '{\"url\":\"https://example.com\"}'")
        print("")
        print("  Or browse MCP servers:")
        print("    https://github.com/modelcontextprotocol/servers")
        return

    # Step 2: Write config (unless dry)
    if not is_dry:
        if cfg.CONFIG_FILE.exists():
            added, skipped, _ = cfg.merge_servers(result.servers, overwrite=False)
            if added > 0:
                print(f"  ✓ {added} new server(s) added to config")
            if skipped > 0:
                print(f"  = {skipped} existing server(s) kept (use 'mcptoon init --auto --force' to overwrite)")
        else:
            cfg.save_config(result.servers)
            print(f"  ✓ Config created: {cfg.CONFIG_FILE}")
    else:
        print("  (--dry mode: config not written)")

    print("")

    # Step 3: Show summary
    print(result.summary())

    # Step 4: The "aha moment" — show slim manifest
    if not is_dry:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  Your tools (--slim format, 93% smaller than JSON):")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        try:
            manifest = manifest_mod.get_manifest(use_cache=False)
            slim_output = manifest_mod.format_manifest(manifest, full=False)
            if slim_output.strip():
                print(slim_output)
            else:
                print("  (tools will appear after servers are started)")
        except Exception as e:
            print(f"  Could not fetch tools yet: {e}")
            print("  Run 'mcptoon manifest --slim' after servers are started")

    print("")
    print("Next steps:")
    print("  mcptoon manifest --slim     # see all available tools")
    print("  mcptoon call <server> <tool> '{...}'   # call a tool")
    print("  mcptoon doctor             # check connectivity")
    if result.count <= 3:
        print("")
        print("  Want more servers?")
        print("  mcptoon add github --stdio npx -y @modelcontextprotocol/server-github")
        print("  mcptoon add memory --stdio npx -y @modelcontextprotocol/server-memory")


def _cmd_health_check(rest, fmt):
    """Health check for configured servers (legacy discover behavior).

    Usage:
        mcptoon discover --health           # check all servers
        mcptoon discover --health exa       # filter by name
    """
    servers = cfg.list_servers()
    if not servers:
        print("No servers configured. Run: mcptoon init --auto")
        return

    filter_name = rest[0] if rest else None

    results = []
    for name in servers:
        if filter_name and filter_name not in name:
            continue
        s_cfg = cfg.get_server_config(name)
        transport = s_cfg.get("transport", "stdio") if s_cfg else "?"
        tool_count = 0
        status = "ok"
        error_msg = ""

        try:
            tools = manifest_mod.get_server_tools(name, use_cache=True)
            tool_count = len(tools)
            if tool_count == 0:
                status = "no-tools"
        except Exception as e:
            status = "error"
            error_msg = str(e)[:80]

        results.append({
            "server": name,
            "transport": transport,
            "tools": tool_count,
            "status": status,
            "error": error_msg,
        })

    if fmt in ("toon", "mcptoon", "compact"):
        print(output.render(results, fmt=fmt))
    elif fmt == "json":
        print(output.render(results, fmt="json"))
    else:
        print(f"Health check: {len(results)} server(s)")
        print()
        for r in results:
            icon = "+" if r["status"] == "ok" else "x"
            print(f"  {icon} {r['server']:20s} [{r['transport']:5s}] {r['tools']:3d} tools  {r['status']}")
            if r["error"]:
                print(f"    -> {r['error']}")


def _cmd_init(rest, fmt="auto"):
    """Create sample config or auto-discover servers.

    Usage:
        mcptoon init                  # Create sample config (2 servers)
        mcptoon init --auto           # Auto-discover all MCP servers
        mcptoon init --auto --dry     # Discover, print only, don't write
        mcptoon init --auto --force   # Overwrite existing config with discovered
        mcptoon init --auto --http http://localhost:8080/mcp  # Add HTTP MCP endpoint
    """
    is_auto = "--auto" in rest
    is_dry = "--dry" in rest or "--dry-run" in rest
    is_force = "--force" in rest

    # Check for --http URL
    http_url = ""
    for i, a in enumerate(rest):
        if a == "--http" and i + 1 < len(rest):
            http_url = rest[i + 1]
            break
        elif a.startswith("--http="):
            http_url = a.split("=", 1)[1]
            break

    if not is_auto:
        # Legacy: create sample config
        if cfg.init_sample_config():
            print(f"Sample config created: {cfg.CONFIG_FILE}")
            print("Edit it to add your MCP servers, then run: mcptoon manifest")
            print("")
            print("Tip: Run 'mcptoon init --auto' to auto-discover all your MCP servers.")
        else:
            print(f"Config already exists: {cfg.CONFIG_FILE}")
            print("Run 'mcptoon init --auto' to discover more servers.")
        return

    # ─── Auto-discover mode ───
    from . import discover as disc

    print("Auto-discovering MCP servers...")
    print("")

    result = disc.auto_discover()

    # Add explicit HTTP endpoint if specified
    if http_url:
        probe_info = disc.probe_http_endpoint(http_url, timeout=2.0)
        if probe_info and probe_info.get("alive"):
            http_config = disc.make_http_config(http_url)
            result.servers["http-endpoint"] = http_config
            result.sources["http-endpoint"] = ["manual"]
            tool_count = probe_info.get("tools_count", 0)
            result.reasons["http-endpoint"] = f"HTTP MCP endpoint at {http_url} ({tool_count} tools)"
            print(f"  [Manual] http-endpoint: {http_url} ({tool_count} tools)")
        else:
            print(f"  [Manual] http-endpoint: {http_url} — NOT responding (added anyway)")
            result.servers["http-endpoint"] = disc.make_http_config(http_url)
            result.sources["http-endpoint"] = ["manual"]
            result.reasons["http-endpoint"] = f"HTTP MCP endpoint at {http_url} (not responding)"

    print("")
    print(result.summary())

    if is_dry:
        print("(--dry mode: config not written. Run without --dry to save.)")
        return

    if result.count == 0:
        print("No servers discovered. Try: mcptoon init (creates sample config)")
        return

    # Write config
    if cfg.CONFIG_FILE.exists() and not is_force:
        added, skipped, overwritten = cfg.merge_servers(result.servers, overwrite=False)
        print(f"Config updated: {cfg.CONFIG_FILE}")
        print(f"  +{added} new servers added")
        print(f"  ={skipped} existing servers skipped (use --force to overwrite)")
    else:
        cfg.save_config(result.servers)
        print(f"Config written: {cfg.CONFIG_FILE} ({result.count} servers)")

    print("")
    print("Next steps:")
    print("  mcptoon manifest --slim    # see all available tools")
    print("  mcptoon doctor             # verify connectivity")


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
    if fmt in ("toon", "mcptoon", "compact"):
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


def _cmd_stats(_rest, fmt):
    """Token savings dashboard — shows how much mcptoon saves vs raw JSON.

    Usage:
        mcptoon stats              Human-readable dashboard
        mcptoon stats --json       JSON output
    """
    from . import schema_simplifier

    manifest = manifest_mod.get_manifest(use_cache=True)
    usage = usage_mod.get_usage_stats()

    # Count tools & compute token savings
    total_tools = 0
    total_full_tokens = 0
    total_slim_tokens = 0
    by_server_full = {}
    by_server_slim = {}

    for server, tools in manifest.items():
        if not tools:
            continue
        server_full = 0
        server_slim = 0
        for t in tools:
            if "error" in t:
                continue
            total_tools += 1
            full_json = json.dumps(t, ensure_ascii=False)
            slim = schema_simplifier.simplify_tool_def(t)
            slim_json = json.dumps(slim, ensure_ascii=False)
            full_tok = len(full_json) // 4  # rough token estimate
            slim_tok = len(slim_json) // 4
            total_full_tokens += full_tok
            total_slim_tokens += slim_tok
            server_full += full_tok
            server_slim += slim_tok
        by_server_full[server] = server_full
        by_server_slim[server] = server_slim

    saved = total_full_tokens - total_slim_tokens
    pct = (saved / total_full_tokens * 100) if total_full_tokens > 0 else 0
    disabled = cfg.list_disabled_tools()

    if fmt == "json":
        data = {
            "total_tools": total_tools,
            "full_tokens_est": total_full_tokens,
            "slim_tokens_est": total_slim_tokens,
            "tokens_saved": saved,
            "savings_pct": round(pct, 1),
            "total_calls": usage["total_calls"],
            "success_rate": usage["success_rate"],
            "disabled_tools": len(disabled),
            "by_server": {s: {"full": by_server_full.get(s, 0), "slim": by_server_slim.get(s, 0)} for s in by_server_full},
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("╔══════════════════════════════════════════╗")
        print("║      mcptoon — Token Savings Dashboard   ║")
        print("╚══════════════════════════════════════════╝")
        print()
        print(f"  Tools discovered:     {total_tools}")
        print(f"  Full JSON tokens:     {total_full_tokens:,}")
        print(f"  Slim manifest tokens: {total_slim_tokens:,}")
        print(f"  ─────────────────────────────────")
        print(f"  Tokens SAVED:         {saved:,} ({pct:.1f}%)")
        print(f"  Disabled tools:       {len(disabled)}")
        print()
        if usage["total_calls"] > 0:
            print(f"  Usage: {usage['total_calls']} calls, {usage['success_rate']} success")
            if usage["by_server"]:
                print("  Top servers by usage:")
                for s, c in list(usage["by_server"].items())[:5]:
                    print(f"    {s:20s} {c} calls")
        print()
        if by_server_full:
            print("  Per-server token savings:")
            for s in sorted(by_server_full):
                sf = by_server_full[s]
                ss = by_server_slim.get(s, 0)
                sp = ((sf - ss) / sf * 100) if sf > 0 else 0
                print(f"    {s:20s} {sf:>6,} → {ss:>6,}  (-{sp:.0f}%)")


def _cmd_toggle(rest, fmt):
    """Toggle a tool on/off (persisted in ~/.mcptoon/toggles.json).

    Usage:
        mcptoon toggle <server> <tool>     Toggle a specific tool
        mcptoon toggle --list              List all toggled tools
    """
    if "--list" in rest or not rest:
        disabled = cfg.list_disabled_tools()
        if not disabled:
            print("No tools are disabled. All tools are active.")
            print("")
            print("Usage: mcptoon toggle <server> <tool>   # toggle a tool off/on")
            return
        print(f"Disabled tools ({len(disabled)}):")
        for key in sorted(disabled):
            print(f"  ✗ {key}")
        print("")
        print("Re-enable: mcptoon toggle <server> <tool>  (toggle again)")
        return

    if len(rest) < 2:
        print("Usage: mcptoon toggle <server> <tool>")
        print("")
        print("Examples:")
        print("  mcptoon toggle exa search        # disable exa's search tool")
        print("  mcptoon toggle exa search        # re-enable it")
        print("  mcptoon toggle --list            # show all disabled tools")
        sys.exit(1)

    server = rest[0]
    tool = rest[1]

    # Verify server and tool exist
    servers = cfg.load_config()
    if server not in servers:
        print(f"Server '{server}' not found.")
        print(f"Available: {', '.join(sorted(servers.keys()))}")
        sys.exit(1)

    new_state = cfg.toggle_tool(server, tool)
    status = "ENABLED ✓" if new_state else "DISABLED ✗"
    print(f"{server}:{tool} → {status}")


def _cmd_auto_discover(rest, fmt):
    """Auto-discover MCP servers (network probe + config scan + env detection).

    Usage:
        mcptoon discover                  # auto-discover, print results
        mcptoon discover --write          # discover + write to config
        mcptoon discover --http <url>     # probe a specific HTTP MCP endpoint
        mcptoon discover --no-network     # skip network probing (faster)
        mcptoon discover --no-configs     # skip scanning existing configs
    """
    do_write = "--write" in rest
    http_url = ""
    scan_configs = "--no-configs" not in rest
    detect_env = "--no-env" not in rest
    detect_local = "--no-local" not in rest
    probe_network = "--no-network" not in rest

    for i, a in enumerate(rest):
        if a == "--http" and i + 1 < len(rest):
            http_url = rest[i + 1]
            break
        elif a.startswith("--http="):
            http_url = a.split("=", 1)[1]
            break

    from . import discover as disc

    print("Auto-discovering MCP servers...")
    print("")

    result = disc.auto_discover(
        scan_configs=scan_configs,
        detect_env=detect_env,
        detect_local=detect_local,
        probe_network=probe_network,
    )

    # Add explicit HTTP endpoint if specified
    if http_url:
        probe_info = disc.probe_http_endpoint(http_url, timeout=2.0)
        if probe_info and probe_info.get("alive"):
            http_config = disc.make_http_config(http_url)
            result.servers["http-endpoint"] = http_config
            result.sources["http-endpoint"] = ["manual"]
            tool_count = probe_info.get("tools_count", 0)
            result.reasons["http-endpoint"] = f"HTTP MCP endpoint at {http_url} ({tool_count} tools)"
        else:
            result.servers["http-endpoint"] = disc.make_http_config(http_url)
            result.sources["http-endpoint"] = ["manual"]
            result.reasons["http-endpoint"] = f"HTTP MCP endpoint at {http_url} (not responding)"

    if fmt in ("toon", "mcptoon", "compact", "slim"):
        print(output.render(list(result.servers.keys()), fmt=fmt))
    elif fmt == "json":
        print(output.render(result.servers, fmt="json"))
    else:
        print(result.summary())

    if do_write and result.count > 0:
        added, skipped, overwritten = cfg.merge_servers(result.servers, overwrite=False)
        print(f"Config updated: {cfg.CONFIG_FILE}")
        print(f"  +{added} new servers added")
        if skipped:
            print(f"  ={skipped} existing servers skipped")
        print("")
        print("Run: mcptoon manifest --slim")


def _cmd_doctor(_rest):
    """Self-diagnose configuration and connectivity."""
    print("mcptoon doctor — running diagnostics...")
    print()

    issues = 0
    checks = 0

    # 1. Python version
    checks += 1
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        print(f"  ✓ Python {py_ver} (>=3.10 required)")
    else:
        print(f"  ✗ Python {py_ver} — needs 3.10+")
        issues += 1

    # 2. Config file
    checks += 1
    if cfg.CONFIG_FILE.exists():
        servers = cfg.load_config()
        print(f"  ✓ Config: {cfg.CONFIG_FILE} ({len(servers)} servers)")
    else:
        print("  ✗ No config found. Run: mcptoon init")
        issues += 1
        print()
        print(f"  {checks} checks, {issues} issue(s)")
        return

    # 3. Cache directory
    checks += 1
    if cfg.CACHE_DIR.exists():
        print(f"  ✓ Cache dir: {cfg.CACHE_DIR}")
    else:
        print("  ! Cache dir missing (will be created on first use)")
        cfg.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 4. Check each server
    servers = cfg.load_config()
    for name in sorted(servers.keys()):
        s_cfg = servers[name]
        transport = s_cfg.get("transport", "stdio")
        checks += 1

        try:
            tools = manifest_mod.get_server_tools(name, use_cache=True)
            count = len(tools)
            if count > 0:
                print(f"  ✓ {name:20s} [{transport:5s}] {count} tools")
            else:
                print(f"  ! {name:20s} [{transport:5s}] 0 tools (server may be empty)")
        except Exception as e:
            print(f"  ✗ {name:20s} [{transport:5s}] ERROR: {str(e)[:80]}")
            issues += 1

    # 5. Environment
    checks += 1
    agent_type = os.environ.get("MCPTOON_AGENT_TYPE", "")
    if agent_type:
        print(f"  ✓ MCPTOON_AGENT_TYPE={agent_type}")
    else:
        print("  - MCPTOON_AGENT_TYPE not set (defaulting to auto)")

    print()
    print(f"  {checks} checks, {issues} issue(s)")
    if issues == 0:
        print("  All good! ✓")
    else:
        print(f"  {issues} issue(s) found. See above for details.")

    # ─── Smart tips ───
    _doctor_smart_tips(servers)


def _doctor_smart_tips(servers: dict):
    """Print smart tips based on current configuration.

    This is the Land & Expand strategy in action:
    - <3 servers: suggest adding more (zero-config servers)
    - 3-5 stdio servers: mention HTTP endpoints as an option
    - >5 stdio servers: strongly recommend HTTP aggregation
    - HTTP endpoint already configured: confirm it's working
    """
    if not servers:
        return

    stdio_count = sum(1 for s in servers.values() if s.get("transport", "stdio") == "stdio")
    http_count = sum(1 for s in servers.values() if s.get("transport") == "http")
    total = len(servers)

    tips = []

    # Tip 1: Too few servers
    if total <= 2:
        tips.append(
            "Tip: Add zero-config servers (no API key needed):\n"
            "  mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch\n"
            "  mcptoon add memory --stdio npx -y @modelcontextprotocol/server-memory\n"
            "  Or run: mcptoon init --auto"
        )

    # Tip 2: Many stdio servers — recommend HTTP aggregation
    if stdio_count >= 6:
        tips.append(
            f"Tip: You have {stdio_count} stdio servers. Each spawns a separate process.\n"
            "  Consider aggregating them behind one HTTP MCP endpoint:\n"
            "  mcptoon init --auto --http http://your-server:8080/mcp\n"
            "  Benefits: faster startup, shared connection, all tools behind one URL"
        )
    elif stdio_count >= 3:
        tips.append(
            f"Tip: {stdio_count} stdio servers detected. If startup feels slow,\n"
            "  consider an HTTP MCP endpoint: mcptoon add my-server --http http://localhost:8080/mcp"
        )

    # Tip 3: HTTP endpoint already configured
    has_http = any(s.get("transport") == "http" for s in servers.values())
    if has_http:
        tips.append(
            "HTTP MCP endpoint configured. All tools across all servers are accessible\n"
            "  through one endpoint — no per-server process spawning needed."
        )

    # Tip 4: No HTTP servers at all
    if http_count == 0 and stdio_count >= 4:
        tips.append(
            "Tip: All your servers use stdio (subprocess). For better performance,\n"
            "  consider running an HTTP MCP server to serve them over HTTP."
        )

    if tips:
        print()
        print("  ── Smart Tips ──")
        for tip in tips:
            print()
            for line in tip.split("\n"):
                print(f"  {line}")


# ═══════════════════════════════════════════════════
# Install — one-command MCP server installation
# ═══════════════════════════════════════════════════

def _cmd_install(rest, fmt):
    """Install/list/remove MCP servers with auto-handler generation.

    Usage:
        mcptoon install <name> --npm <package>   Install from npm (npx)
        mcptoon install <name> --pip <package>   Install from pip
        mcptoon install <name> --url <url>       Install HTTP/SSE MCP
        mcptoon install --list                   List installed servers
        mcptoon install --remove <name>           Remove an installed server
    """
    npm_pkg = None
    pip_pkg = None
    http_url = None
    server_name = None
    do_list = False
    do_remove = False

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--npm" and i + 1 < len(rest):
            npm_pkg = rest[i + 1]
            i += 2
        elif a == "--pip" and i + 1 < len(rest):
            pip_pkg = rest[i + 1]
            i += 2
        elif a == "--url" and i + 1 < len(rest):
            http_url = rest[i + 1]
            i += 2
        elif a == "--list":
            do_list = True
            i += 1
        elif a == "--remove" and i + 1 < len(rest):
            server_name = rest[i + 1]
            do_remove = True
            i += 2
        elif not a.startswith("--"):
            server_name = a
            i += 1
        else:
            i += 1

    if do_list:
        from .installer import list_installed
        result = list_installed()
        print(output.render(result, fmt=fmt))
        return

    if do_remove:
        from .installer import remove_installed
        result = remove_installed(server_name)
        print(output.render(result, fmt=fmt))
        return

    if http_url:
        from .installer import install_http
        result = install_http(http_url, server_name)
        print(output.render(result, fmt=fmt))
        return

    if npm_pkg:
        from .installer import install_npm
        result = install_npm(npm_pkg, server_name)
        print(output.render(result, fmt=fmt))
        return

    if pip_pkg:
        from .installer import install_pip
        result = install_pip(pip_pkg, server_name)
        print(output.render(result, fmt=fmt))
        return

    # mcptoon install --search <keyword>  → search registry
    if server_name and server_name == "--search":
        # This shouldn't happen (handled above), but just in case
        pass

    # mcptoon install <name>  (no --npm/--pip/--url) → auto-search & install
    if server_name and not server_name.startswith("--"):
        from .installer import install_by_name, search_registry
        # First: show search results
        results = search_registry(server_name)
        if not results:
            print(f"  ❌ No MCP server found matching '{server_name}'.")
            print(f"  Try: mcptoon install {server_name} --npm <package>")
            print(f"  Or:  mcptoon install {server_name} --pip <package>")
            return
        # If multiple results, show them
        if len(results) > 1:
            print(f"  Found {len(results)} servers matching '{server_name}':")
            for i, r in enumerate(results[:10]):
                name = r.get("name", "")
                desc = r.get("description", "")[:60]
                src = r.get("source", "")
                print(f"    {i+1}. {name} ({src}) — {desc}")
            print(f"\n  Installing best match: {results[0].get('name', server_name)}")
        else:
            print(f"  Found: {results[0].get('name', server_name)} — {results[0].get('description', '')[:80]}")

        result = install_by_name(server_name)
        print(output.render(result, fmt=fmt))
        return

    print("Usage:")
    print("  mcptoon install <name>              # Auto-search & install from registry")
    print("  mcptoon install <name> --npm <pkg>  # Install from npm")
    print("  mcptoon install <name> --pip <pkg>  # Install from pip")
    print("  mcptoon install <name> --url <url>  # Install HTTP/SSE MCP")
    print("  mcptoon install --list              # List installed servers")
    print("  mcptoon install --remove <name>      # Remove an installed server")


# ═══════════════════════════════════════════════════
# Shell completion
# ═══════════════════════════════════════════════════

_BASH_COMPLETION = r'''
_mcptoon_complete() {
    local cur prev commands
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    commands="init quickstart list manifest inspect call add remove usage discover doctor completion help sync health serve demo install search"

    if [ $COMP_CWORD -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$commands" -- $cur) )
        return 0
    fi

    case "$prev" in
        call|inspect)
            if [ $COMP_CWORD -eq 2 ]; then
                COMPREPLY=( $(compgen -W "$(mcptoon list 2>/dev/null | sed 's/  //;s/ \[.*//')" -- $cur) )
            fi
            ;;
        --format)
            COMPREPLY=( $(compgen -W "openai openapi mcp json human" -- $cur) )
            ;;
        --toon|--mcptoon|--slim|--json|--compact|--raw|--full|--stdin)
            COMPREPLY=()
            ;;
    esac
}
complete -F _mcptoon_complete mcptoon
'''

_ZSH_COMPLETION = r'''
#compdef mcptoon

_mcptoon() {
    local commands=(init list manifest inspect call add remove usage discover doctor completion help sync health serve demo install search)
    local formats=(openai openapi mcp json human)

    if (( CURRENT == 1 )); then
        _describe 'command' commands
        return
    fi

    case $words[2] in
        call|inspect)
            if (( CURRENT == 2 )); then
                local servers=($(mcptoon list 2>/dev/null | sed 's/  //;s/ \[.*//'))
                _describe 'server' servers
            fi
            ;;
        --format)
            _describe 'format' formats
            ;;
    esac
}
compdef _mcptoon mcptoon
'''

_FISH_COMPLETION = r'''
complete -c mcptoon -n '__fish_use_subcommand' -a 'init quickstart list manifest inspect call add remove usage discover doctor completion help sync health serve demo install search'
complete -c mcptoon -n '__fish_seen_subcommand_from call inspect' -a '(mcptoon list 2>/dev/null | sed "s/  //;s/ \[.*//")'
complete -c mcptoon -n '__fish_seen_subcommand_from --format' -a 'openai openapi mcp json human'
'''

_PS_COMPLETION = '''
$scriptBlock = {
    param($wordToComplete, $commandAst, $cursorPosition)
    $commands = 'init','quickstart','list','manifest','inspect','call','add','remove','usage','discover','doctor','completion','help','sync','health','serve','demo','install','search'
    $commands | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
    }
}
Register-ArgumentCompleter -CommandName mcptoon -ScriptBlock $scriptBlock
'''


def _cmd_completion(rest):
    """Generate shell completion script."""
    shell = rest[0] if rest else "bash"

    scripts = {
        "bash": ("Bash", _BASH_COMPLETION),
        "zsh": ("Zsh", _ZSH_COMPLETION),
        "fish": ("Fish", _FISH_COMPLETION),
        "powershell": ("PowerShell", _PS_COMPLETION),
        "ps": ("PowerShell", _PS_COMPLETION),
    }

    if shell not in scripts:
        print(f"Unknown shell: {shell}")
        print(f"Supported: {', '.join(scripts.keys())}")
        sys.exit(1)

    name, script = scripts[shell]
    print(f"# mcptoon completion for {name}")
    print("# Install: eval this script or add to your shell config")
    print(script)


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

    if any(kw in text for kw in ["搜工具", "找工具", "search tool", "search"]):
        _cmd_search(rest, fmt, head_n, max_chars, full)
        return

    if any(kw in text for kw in ["发现", "搜索服务器", "discover", "auto-discover"]):
        _cmd_auto_discover(rest, fmt)
        return

    if any(kw in text for kw in ["健康", "health", "check"]):
        _cmd_health_check(rest, fmt)
        return

    print(f"Unknown command: {command}")
    print("Run: mcptoon help")


# ═══════════════════════════════════════════════════
# Help
# ═══════════════════════════════════════════════════

def _print_help():
    print(f"""mcptoon v{__import__('mcptoon').__version__} — Token-efficient MCP CLI client

Usage:
    mcptoon quickstart                    One-command setup (discover + config + show tools)
    mcptoon list                          List configured servers
    mcptoon manifest                      List all tools (compact)
    mcptoon manifest --full               List all tools with params
    mcptoon manifest --format openai      Export as OpenAI function calling format
    mcptoon manifest --format openapi     Export as OpenAPI 3.0 spec
    mcptoon manifest --format mcp         Export as MCP tools/list format
    mcptoon discover                      Auto-discover MCP servers (scan + probe)
    mcptoon discover --write              Discover + write to config
    mcptoon discover --http <url>         Probe a specific HTTP MCP endpoint
    mcptoon discover --health             Health check (legacy discover behavior)
    mcptoon inspect <server> <tool>       Show tool schema
    mcptoon search <query>              Search tools across all servers
    mcptoon call <server> <tool> [ARGS]   Call a tool
    mcptoon call --auto <tool> [ARGS]    Call a tool (auto-find server)
    mcptoon call <server> <tool> --stdin   Read args from stdin (large payloads)
    mcptoon init                          Create sample config
    mcptoon init --auto                   Auto-discover all MCP servers
    mcptoon init --auto --http <url>      Auto-discover + add HTTP MCP endpoint
    mcptoon add <name> [options]          Add a server
    mcptoon remove <name>                 Remove a server
    mcptoon usage                         Show usage stats
    mcptoon doctor                        Self-diagnose config + connectivity
    mcptoon completion <shell>            Generate shell completion (bash|zsh|fish|ps)
    mcptoon install <name> --npm <pkg>    Install MCP server from npm
    mcptoon install <name> --pip <pkg>    Install MCP server from pip
    mcptoon install <name> --url <url>   Install HTTP/SSE MCP server
    mcptoon install --list               List installed servers
    mcptoon install --remove <name>      Remove an installed server

    mcptoon serve                        Run as MCP server (stdio bridge for agents)
    mcptoon demo                         Zero-config one-command demo
    mcptoon sync                         Sync config to all agents (Claude Desktop, Cursor, etc.)
    mcptoon sync --dry                   Preview without writing
    mcptoon sync --agent <id>            Sync to one agent only
    mcptoon health                       Health check all MCP servers
    mcptoon health --json                JSON output for CI/CD (exit 1 if dead)

Output flags:
    --toon         Standard TOON (toon-format/toon spec, saves 30-60% tokens)
    --mcptoon      Legacy mcptoon pipe format (saves 20-40% tokens)
    --slim         Ultra-compact tool manifests (saves 93% tokens)
    --json         JSON output
    --compact      Names only
    --stdin        Read JSON args from stdin (for large payloads)
    --head N       Limit to N items
    --max-chars N  Truncate to N chars
    --full         No truncation
    --format X     Export: openai|openapi|mcp|json|human
    --fallback-json  Fall back to JSON if TOON encoding fails

Examples:
    mcptoon init
    mcptoon manifest --toon              # standard TOON format
    mcptoon manifest --mcptoon           # legacy pipe format
    mcptoon manifest --slim              # ultra-compact tool schemas
    mcptoon call fetch fetch '{{"url":"https://example.com"}}' --toon
    echo '{{"huge":"payload"}}' | mcptoon call server tool --stdin --toon
    mcptoon discover
    mcptoon doctor

Environment:
MCPTOON_AGENT_TYPE=claude    Auto-select --toon (optional)
MCPTOON_AGENT_TYPE=openai    Auto-select --json (default)

Config: ~/.mcptoon/config.json
""")


# ═══════════════════════════════════════════════════
# New commands (v0.6+)
# ═══════════════════════════════════════════════════

def _cmd_serve(rest):
    """Run as MCP server (stdio bridge for agents)."""
    from .serve import run_serve
    run_serve(rest)


def _cmd_demo(rest):
    """Zero-config one-command demo."""
    from .demo import run_demo
    run_demo(rest)


def _cmd_sync(rest, fmt):
    """Sync mcptoon config to AI agent config files.

    Usage:
        mcptoon sync                 # sync to all detected agents
        mcptoon sync --dry           # preview without writing
        mcptoon sync --agent cursor  # sync to specific agent only
        mcptoon sync --agent claude-desktop
        mcptoon sync --agent windsurf
        mcptoon sync --watch         # keep syncing as configs change
        mcptoon sync --watch --interval 5 --quiet --watch-mode strict
    """
    from .sync import sync_to_all, sync_to_agent, format_sync_report

    dry_run = "--dry" in rest or "--dry-run" in rest

    # --watch: continuous sync loop (see watch.py)
    if "--watch" in rest:
        from .watch import main as watch_main
        sys.exit(watch_main(rest))

    # Parse --agent
    agent_id = None
    for i, a in enumerate(rest):
        if a == "--agent" and i + 1 < len(rest):
            agent_id = rest[i + 1]
            break
        elif a.startswith("--agent="):
            agent_id = a.split("=", 1)[1]
            break

    if agent_id:
        result = sync_to_agent(agent_id, dry_run=dry_run)
        report = format_sync_report([result], dry_run=dry_run)
    else:
        results = sync_to_all(dry_run=dry_run)
        report = format_sync_report(results, dry_run=dry_run)

    print(report)


def _cmd_health(rest, fmt):
    """Health check all configured MCP servers.

    Usage:
        mcptoon health                # check all servers
        mcptoon health --timeout 5    # 5 second timeout per server
        mcptoon health --json         # JSON output (for CI/CD)
    """
    from .health import check_all, format_health_report

    timeout = 10.0
    for i, a in enumerate(rest):
        if a == "--timeout" and i + 1 < len(rest):
            try:
                timeout = float(rest[i + 1])
            except ValueError:
                pass
            break

    # JSON output for CI/CD
    if fmt == "json" or "--json" in rest:
        import json as _json
        results = check_all(timeout=timeout)
        print(_json.dumps(results, ensure_ascii=False, indent=2))
        # Exit code 1 if any server is dead (for CI/CD)
        dead = sum(1 for r in results if r["status"] in ("error", "timeout"))
        if dead > 0:
            sys.exit(1)
    else:
        results = check_all(timeout=timeout)
        print(format_health_report(results))
