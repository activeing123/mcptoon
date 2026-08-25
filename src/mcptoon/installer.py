"""
mcptoon installer — MCP tool installer.

Features:
  1. Search MCP registry for available servers
  2. Install npm/pip MCP packages
  3. Auto-generate handler files
  4. Verify installation (test connection via MCPClient)

CLI:
  mcptoon install <server-name>          # Install from registry
  mcptoon install --npm <package>         # Install from npm
  mcptoon install --pip <package>         # Install from pip
  mcptoon install --url <url>             # Install HTTP/SSE MCP
  mcptoon install --list                  # List installed servers
  mcptoon install --remove <name>          # Remove an installed server
"""
import json
import os
import sys
import subprocess
import re

from .errors import make_error
from .client import MCPClient, MCPError

# MCP Registry URLs — multiple sources for resilience
MCP_REGISTRY_URL = "https://registry.modelcontextprotocol.org"
SMITHERY_API_URL = "https://smithery.ai/api"
MCP_SO_URL = "https://mcp.so/api"

# Default npx command
_NPX_CMD = "npx"
if os.name == "nt":
    _default_npx = "C:/Program Files/nodejs/npx.cmd"
    if os.path.exists(_default_npx):
        _NPX_CMD = _default_npx

INSTALL_TIMEOUT = 120

# Simple logging fallback
_log_enabled = os.environ.get("MCPTOON_DEBUG", "") != ""
class _Log:
    def info(self, component, msg):
        if _log_enabled:
            sys.stderr.write(f"[{component}] {msg}\n")
    def error(self, component, msg):
        sys.stderr.write(f"[{component}] ERROR: {msg}\n")
log = _Log()

# ─── Installed MCP servers config file ───
_INSTALLED_FILE = os.path.expanduser("~/.mcp-cli/pro_installed.json")


def _load_installed():
    """Load installed MCP servers list."""
    try:
        with open(_INSTALLED_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_installed(data):
    """Save installed MCP servers list."""
    os.makedirs(os.path.dirname(_INSTALLED_FILE), exist_ok=True)
    with open(_INSTALLED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def search_registry(keyword):
    """Search MCP registries for available servers.

    Tries Smithery API first (largest registry, 3000+ servers),
    falls back to MCP official registry.

    Returns:
        list: [{name, description, command, args, env}, ...]
    """
    # Try Smithery first (largest registry)
    results = _search_smithery(keyword)
    if results:
        return results

    # Fall back to MCP official registry
    results = _search_mcp_registry(keyword)
    if results:
        return results

    # Last resort: return empty (no error for "no results")
    return []


def _search_smithery(keyword):
    """Search Smithery registry."""
    try:
        import urllib.request
        import urllib.parse
        params = urllib.parse.urlencode({"q": keyword})
        url = f"{SMITHERY_API_URL}/servers?{params}"
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "mcptoon-installer/1.0",
        })
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))

        # Smithery returns {servers: [{name, description, command, ...}]}
        servers = data if isinstance(data, list) else data.get("servers", data.get("data", []))
        if not isinstance(servers, list):
            servers = []

        return [{
            "name": s.get("name", s.get("id", "")),
            "description": (s.get("description", "") or "")[:200],
            "command": s.get("command", "npx"),
            "args": s.get("args", ["-y", s.get("name", "")]),
            "env": s.get("env", {}),
            "source": "smithery",
            "url": s.get("url", ""),
        } for s in servers if s.get("name") or s.get("id")]
    except Exception:
        return []


def _search_mcp_registry(keyword):
    """Search MCP official registry."""
    try:
        import urllib.request
        url = f"{MCP_REGISTRY_URL}/servers?q={keyword}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        servers = data.get("servers", [])
        return [{
            "name": s.get("name", ""),
            "description": s.get("description", "")[:200],
            "command": s.get("command", ""),
            "args": s.get("args", []),
            "env": s.get("env", {}),
            "source": "registry",
        } for s in servers if s.get("name")]
    except Exception:
        return []


def install_by_name(name, server_name=None):
    """Install a server by name from registry (auto-discover source).

    Usage:
        install_by_name("fetch")      # searches registry, installs best match
        install_by_name("filesystem")  # same pattern

    Returns:
        dict: Installation result
    """
    # 1. Search for the server
    results = search_registry(name)
    if not results:
        return make_error("NOT_FOUND",
            f"No MCP server found matching '{name}'. "
            f"Try: mcptoon install --npm <package> or --pip <package>",
            "installer")

    # 2. Find best match (exact name or first result)
    match = None
    for r in results:
        if r.get("name", "").lower() == name.lower():
            match = r
            break
    if not match:
        match = results[0]

    # 3. Determine install method
    command = match.get("command", "npx")
    args = match.get("args", ["-y", match.get("name", name)])

    if command == "npx" or (args and "-y" in args):
        # npm-based server
        package = name
        if args and len(args) > 1:
            # Extract package name from args
            for a in args:
                if a.startswith("@") or (a != "-y" and not a.startswith("-")):
                    package = a
                    break
        return install_npm(package, server_name or name)
    elif command in (sys.executable, "python", "python3"):
        return install_pip(match.get("name", name), server_name or name)
    else:
        # Custom command
        if not server_name:
            server_name = name
        return install_custom(server_name, command, args, match.get("env", {}))


def install_npm(package, server_name=None):
    """Install MCP server from npm.

    Args:
        package: npm package name (e.g. "@anthropic/mcp-fetch")
        server_name: Custom server name (defaults to last segment of package)

    Returns:
        dict: Installation result
    """
    if not server_name:
        # Extract server_name from package name
        parts = package.split("/")
        server_name = parts[-1].replace("mcp-", "").replace("-", "_")

    # npx -y <package> as launch command
    command = _NPX_CMD if os.path.exists(_NPX_CMD) else "npx"
    args_list = ["-y", package]

    # Verify installation: try to connect
    result = _verify_and_generate(server_name, command, args_list, {}, package)
    return result


def install_pip(package, server_name=None):
    """Install MCP server from pip.

    Args:
        package: pip package name
        server_name: Custom server name

    Returns:
        dict: Installation result
    """
    if not server_name:
        server_name = package.replace("mcp-", "").replace("-", "_")

    # First: pip install
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True, timeout=INSTALL_TIMEOUT,
            encoding="utf-8", errors="replace"
        )
        if r.returncode != 0:
            return make_error("INSTALL_FAILED",
                f"pip install failed: {r.stderr[:200]}", "installer")
    except subprocess.TimeoutExpired:
        return make_error("TIMEOUT", f"pip install timeout ({INSTALL_TIMEOUT}s)", "installer")

    # Find executable entry point
    # Most MCP pip packages provide a <name> CLI entry point
    entry_point = package.replace("-", "_").replace("mcp_", "")
    command = sys.executable
    args_list = ["-m", entry_point]

    result = _verify_and_generate(server_name, command, args_list, {}, package)
    return result


def install_custom(server_name, command, args_list, env=None):
    """Install custom MCP server.

    Args:
        server_name: Server name
        command: Launch command
        args_list: Launch arguments
        env: Environment variables

    Returns:
        dict: Installation result
    """
    return _verify_and_generate(server_name, command, args_list, env or {}, "custom")


def install_http(url, server_name=None, transport="auto"):
    """Install HTTP/SSE MCP server.

    Args:
        url: MCP server URL (e.g. https://example.com/sse)
        server_name: Custom server name
        transport: Transport mode (auto / sse / http)

    Returns:
        dict: Installation result
    """
    if not server_name:
        # Extract server name from URL
        from urllib.parse import urlparse
        parsed = urlparse(url)
        server_name = parsed.path.rstrip("/").split("/")[-1] or parsed.hostname
        server_name = re.sub(r'[^a-z0-9_]', '_', server_name.lower())

    # Verify connection
    client = MCPClient(http=url)
    init_result = client.initialize()

    if isinstance(init_result, Exception):
        client.close()
        return make_error("VERIFY_FAILED",
            f"HTTP/SSE MCP server '{server_name}' connection failed: {str(init_result)[:200]}",
            "installer")

    # Get tool list
    try:
        tools = client.list_tools()
    except Exception:
        tools = []

    client.close()

    # Generate handler file
    _generate_http_handler_file(server_name, tools, url, transport)

    # Record to installed.json
    tools_with_schema = [
        {"name": t.get("name", ""),
         "description": t.get("description", ""),
         "inputSchema": t.get("inputSchema", {})}
        for t in tools
    ]
    installed = _load_installed()
    installed[server_name] = {
        "url": url,
        "transport": transport,
        "source": "http",
        "tools": [t.get("name", "") for t in tools],
        "tools_with_schema": tools_with_schema,
        "tool_count": len(tools),
        "installed_at": _now_iso(),
    }
    _save_installed(installed)

    return {
        "status": "installed",
        "server": server_name,
        "tools": len(tools),
        "tool_names": [t.get("name", "") for t in tools][:20],
        "source": "http",
        "url": url,
        "transport": transport,
    }


def _generate_http_handler_file(server_name, tools, url, transport):
    """Auto-generate HTTP/SSE handler file."""
    handlers_dir = os.path.join(os.path.dirname(__file__), "handlers")
    safe_name = re.sub(r'[^a-z0-9_]', '_', server_name.lower())
    handler_file = os.path.join(handlers_dir, f"{safe_name}.py")

    # Generate SCHEMA — use json.dumps for safe handling of newlines/quotes/special chars
    schema_lines = []
    for tool in tools:
        name_str = json.dumps(tool.get("name", "unknown"), ensure_ascii=False)
        desc_str = json.dumps(tool.get("description", "")[:200], ensure_ascii=False)
        input_schema = tool.get("inputSchema", {})
        schema_lines.append(f'    {{"name": {name_str}, "description": {desc_str}, "inputSchema": {repr(input_schema)}}},')

    schema_str = "\n".join(schema_lines) if schema_lines else "    # Tool list will be fetched from HTTP on first call"

    handler_code = f'''# -*- coding: utf-8 -*-
"""Auto-generated HTTP/SSE handler for {server_name}"""
import os, sys

# ─── path setup for local execution ───
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
_SRC_DIR = os.path.join(os.path.dirname(_PARENT_DIR), "src")
for p in [_SRC_DIR, _PARENT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from router import register
except ImportError:
    try:
        from ..router import register
    except ImportError:
        from mcptoon.router import register

SERVER_NAME = "{server_name}"
ALIASES = ()

SCHEMA = [
{schema_str}
]

# HTTP/SSE config
MCP_URL = "{url}"
MCP_TRANSPORT = "{transport}"


@register(SERVER_NAME, *ALIASES)
def handle(tool, args):
    """Call HTTP/SSE MCP tool."""
    try:
        from mcptoon.client import MCPClient
    except ImportError:
        from client import MCPClient

    client = MCPClient(http=MCP_URL)
    client.initialize()
    result = client.call_tool(tool, args or {{}})
    client.close()
    return result
'''

    with open(handler_file, "w", encoding="utf-8") as f:
        f.write(handler_code)

    log.info("installer", f"Generated HTTP handler: {handler_file}")

    with open(handler_file, "w", encoding="utf-8") as f:
        f.write(handler_code)

    log.info("installer", f"Generated HTTP handler: {handler_file}")


def _verify_and_generate(server_name, command, args_list, env, source):
    """Verify installation + auto-generate handler file.

    1. Connect via MCPClient
    2. Call tools/list to get tool list
    3. Generate handler file
    4. Record to installed.json
    """
    # 1. Try to connect
    client = MCPClient(stdio=[command] + (args_list or []))
    try:
        client.initialize()
    except MCPError as e:
        client.close()
        return make_error("VERIFY_FAILED",
            f"MCP server '{server_name}' connection failed: {str(e)[:200]}",
            "installer")

    # 2. Get tool list
    try:
        tools = client.list_tools()
    except Exception:
        tools = []

    client.close()

    # 3. Generate handler file
    _generate_handler_file(server_name, tools, command, args_list, env, source)

    # 4. Record to installed.json — preserve full inputSchema
    tools_with_schema = [
        {"name": t.get("name", ""),
         "description": t.get("description", ""),
         "inputSchema": t.get("inputSchema", {})}
        for t in tools
    ]
    installed = _load_installed()
    installed[server_name] = {
        "command": command,
        "args": args_list,
        "env": list(env.keys()) if env else [],
        "source": source,
        "tools": [t.get("name", "") for t in tools],
        "tools_with_schema": tools_with_schema,
        "tool_count": len(tools),
        "installed_at": _now_iso(),
    }
    _save_installed(installed)

    return {
        "status": "installed",
        "server": server_name,
        "tools": len(tools),
        "tool_names": [t.get("name", "") for t in tools][:20],
        "source": source,
    }


def _generate_handler_file(server_name, tools, command, args_list, env_keys, source):
    """Auto-generate handler file to handlers/ directory."""
    handlers_dir = os.path.join(os.path.dirname(__file__), "handlers")
    safe_name = re.sub(r'[^a-z0-9_]', '_', server_name.lower())
    handler_file = os.path.join(handlers_dir, f"{safe_name}.py")

    # Generate SCHEMA — use json.dumps for safe handling of newlines/quotes/special chars
    schema_lines = []
    for tool in tools:
        name = tool.get("name", "unknown")
        name_str = json.dumps(name, ensure_ascii=False)
        desc_str = json.dumps(tool.get("description", "")[:200], ensure_ascii=False)
        input_schema = tool.get("inputSchema", {})
        schema_lines.append(f'    {{"name": {name_str}, "description": {desc_str}, "inputSchema": {repr(input_schema)}}},')

    schema_str = "\n".join(schema_lines) if schema_lines else "    # Tool list will be fetched from daemon on first call"

    # Generate env keys
    env_str = ", ".join(f'"{k}": ""' for k in env_keys) if env_keys else ""

    # Generate args list
    args_str = ", ".join(f'"{a}"' for a in args_list)

    handler_code = f'''# -*- coding: utf-8 -*-
"""Auto-generated handler for {server_name} (source: {source})"""
import os, sys

# ─── path setup for local execution ───
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
_SRC_DIR = os.path.join(os.path.dirname(_PARENT_DIR), "src")
for p in [_SRC_DIR, _PARENT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from router import register
except ImportError:
    try:
        from ..router import register
    except ImportError:
        from mcptoon.router import register

SERVER_NAME = "{server_name}"
ALIASES = ()

SCHEMA = [
{schema_str}
]

# MCP stdio launch config
MCP_COMMAND = "{command}"
MCP_ARGS = [{args_str}]
MCP_ENV = {{{env_str}}}


@register(SERVER_NAME, *ALIASES)
def handle(tool, args):
    """Call MCP stdio tool."""
    try:
        from mcptoon.client import MCPClient
    except ImportError:
        from client import MCPClient

    env = {{}}
    for key in MCP_ENV:
        val = os.environ.get(key, "")
        if val:
            env[key] = val

    client = MCPClient(stdio=[MCP_COMMAND] + MCP_ARGS, env=env)
    client.initialize()
    result = client.call_tool(tool, args or {{}})
    client.close()
    return result
'''

    with open(handler_file, "w", encoding="utf-8") as f:
        f.write(handler_code)

    log.info("installer", f"Generated handler: {handler_file}")


def list_installed():
    """List installed MCP servers."""
    return _load_installed()


def remove_installed(server_name):
    """Remove an installed MCP server."""
    installed = _load_installed()
    if server_name not in installed:
        return make_error("NOT_FOUND", f"Server '{server_name}' not installed", "installer")

    # Delete handler file
    safe_name = re.sub(r'[^a-z0-9_]', '_', server_name.lower())
    handler_file = os.path.join(os.path.dirname(__file__), "handlers", f"{safe_name}.py")
    if os.path.exists(handler_file):
        os.remove(handler_file)

    # Remove from installed.json
    del installed[server_name]
    _save_installed(installed)

    return {"status": "removed", "server": server_name}


def _now_iso():
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")
