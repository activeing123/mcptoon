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
mcptoon health — Batch health check for all configured MCP servers.

Checks connectivity, tool discovery, and response time for each server.
52% of MCP servers are "zombies" (unreachable) — this command catches them.

Usage:
    from mcptoon.health import check_all, check_server
    results = check_all(timeout=10)
    result = check_server("fetch")
"""
import concurrent.futures
import time

from .config import load_config, list_servers, get_server_config
from .client import MCPClient, MCPError


# ─── Single server check ───

def check_server(name: str, timeout: float = 10.0, config: dict | None = None) -> dict:
    """Check health of a single MCP server.

    Args:
        name: Server name from mcptoon config
        timeout: Seconds to wait for connection
        config: Override config (for testing)

    Returns:
        {
            "server": str,
            "transport": str,
            "status": "ok" | "error" | "timeout" | "no-config",
            "tools": int,
            "latency_ms": int,
            "error": str | None,
        }
    """
    if config is None:
        config = load_config()

    server_cfg = get_server_config(name)
    if not server_cfg:
        return {
            "server": name,
            "transport": "?",
            "status": "no-config",
            "tools": 0,
            "latency_ms": 0,
            "error": "Server not found in config",
        }

    transport = server_cfg.get("transport", "stdio")
    start = time.time()

    try:
        # Use MCPClient to connect and list tools
        if transport == "http":
            url = server_cfg.get("url", "")
            headers = server_cfg.get("headers", {})
            with MCPClient(http_url=url, headers=headers, timeout=timeout) as client:
                tools = client.list_tools()
                elapsed = (time.time() - start) * 1000
                return {
                    "server": name,
                    "transport": transport,
                    "status": "ok",
                    "tools": len(tools),
                    "latency_ms": int(elapsed),
                    "error": None,
                }
        else:
            # stdio
            command = server_cfg.get("command", [])
            args = server_cfg.get("args", [])
            env = server_cfg.get("env", {})

            if isinstance(command, list):
                cmd_list = command
            else:
                cmd_list = [command]
            full_cmd = cmd_list + list(args)

            with MCPClient(stdio=full_cmd, env=env, timeout=timeout) as client:
                tools = client.list_tools()
                elapsed = (time.time() - start) * 1000
                return {
                    "server": name,
                    "transport": transport,
                    "status": "ok",
                    "tools": len(tools),
                    "latency_ms": int(elapsed),
                    "error": None,
                }

    except MCPError as e:
        elapsed = (time.time() - start) * 1000
        # Classify as timeout if the error is timeout-related
        is_timeout = "timeout" in e.code.lower() or "timeout" in e.message.lower()
        return {
            "server": name,
            "transport": transport,
            "status": "timeout" if is_timeout else "error",
            "tools": 0,
            "latency_ms": int(elapsed),
            "error": f"[{e.code}] {e.message}"[:100],
        }
    except TimeoutError:
        elapsed = (time.time() - start) * 1000
        return {
            "server": name,
            "transport": transport,
            "status": "timeout",
            "tools": 0,
            "latency_ms": int(elapsed),
            "error": f"Timed out after {timeout}s",
        }
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return {
            "server": name,
            "transport": transport,
            "status": "error",
            "tools": 0,
            "latency_ms": int(elapsed),
            "error": str(e)[:100],
        }


# ─── Batch check ───

def check_all(timeout: float = 10.0, config: dict | None = None, max_workers: int = 20) -> list[dict]:
    """Check health of all configured MCP servers in parallel.

    Args:
        timeout: Seconds to wait per server
        config: Override config (for testing)
        max_workers: Max parallel checks

    Returns:
        List of health check results, sorted by status (errors first).
    """
    if config is None:
        config = load_config()

    servers = list_servers()
    if not servers:
        return []

    results = []

    # Use thread pool for parallel checks
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_name = {
            executor.submit(check_server, name, timeout, config): name
            for name in servers
        }
        for future in concurrent.futures.as_completed(future_to_name):
            name = future_to_name[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                results.append({
                    "server": name,
                    "transport": "?",
                    "status": "error",
                    "tools": 0,
                    "latency_ms": 0,
                    "error": str(e)[:100],
                })

    # Sort: errors/timeouts first, then by server name
    status_order = {"error": 0, "timeout": 1, "no-config": 2, "ok": 3}
    results.sort(key=lambda r: (status_order.get(r["status"], 9), r["server"]))

    return results


def format_health_report(results: list[dict]) -> str:
    """Format health check results as human-readable report."""
    if not results:
        return "No servers configured. Run: mcptoon init --auto"

    ok_count = sum(1 for r in results if r["status"] == "ok")
    error_count = sum(1 for r in results if r["status"] in ("error", "timeout"))
    total = len(results)

    lines = [f"── mcptoon health: {ok_count}/{total} alive, {error_count} dead ──", ""]

    status_icons = {
        "ok": "✓",
        "error": "✗",
        "timeout": "⏱",
        "no-config": "?",
    }

    for r in results:
        icon = status_icons.get(r["status"], "?")
        name = r["server"]
        transport = r["transport"]
        tools = r["tools"]
        latency = r["latency_ms"]
        status = r["status"]
        error = r.get("error", "")

        # Format: ✓ fetch [stdio] 3 tools 120ms ok
        line = f"  {icon} {name:25s} [{transport:5s}] {tools:3d} tools  {latency:6d}ms  {status}"
        if error and status != "ok":
            line += f"\n    → {error}"
        lines.append(line)

    lines.append("")
    if error_count == 0:
        lines.append(f"  All {total} servers healthy.")
    else:
        lines.append(f"  {error_count}/{total} servers unreachable. Remove with: mcptoon remove <name>")

    return "\n".join(lines)
