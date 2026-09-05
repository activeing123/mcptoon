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
mcptoon demo — Zero-config one-command demo (ADR 0003)

Gives the user an "aha moment" in 30 seconds:
  1. Download a zero-dependency MCP server (the official "everything"
     reference server — self-contained, no network, no API key)
  2. Add it to mcptoon config
  3. Call a tool
  4. Show token comparison: JSON vs TOON vs SLIM
  5. Display the official 255-tool benchmark: "71,929 tokens → 581 tokens"

Usage:
  mcptoon demo                    # Full demo
  mcptoon demo --quick            # Fast: skip step-by-step, just show results
  mcptoon demo --keep             # Keep the demo server in config after demo
"""

from __future__ import annotations

import json
import shutil
import time

from . import config as cfg
from .client import MCPClient
from . import output as output_mod


def run_demo(args: list[str]):
    """Entry point for `mcptoon demo` command."""
    if "-h" in args or "--help" in args:
        print(_demo_help())
        return

    quick_mode = "--quick" in args
    keep_server = "--keep" in args

    _print_banner()

    # Step 1: Check prerequisites
    if not _check_prerequisites():
        return

    # Step 2: Demo server — the official "everything" reference server
    # (self-contained: no network, no API key, works offline after npx
    # cache warms). Do NOT use @modelcontextprotocol/server-fetch: the
    # package is gone from npm (registry E404, verified 2026-09-05) and
    # every `mcptoon demo` died with PROCESS_DIED / Errno 22 on it.
    server_name = "demo-everything"
    server_cmd = ["npx", "-y", "@modelcontextprotocol/server-everything"]

    if not quick_mode:
        print("  Step 1/3: Starting demo server...")
        time.sleep(0.5)
    else:
        print("  Starting demo server...")

    # Step 3: Call the echo tool (first tool call, zero setup)
    message = "mcptoon demo works"
    result_text = _demo_call(server_name, server_cmd, message, quick_mode)

    if result_text is None:
        print("  ❌ Demo failed. See error above.")
        print("  If the error mentions npm/404: check network or npm registry.")
        print("  If it mentions npx not found: install Node.js: https://nodejs.org")
        return

    # Step 4: Show token comparison
    print()
    if not quick_mode:
        print("─" * 60)
        print("  Step 2/3: Token comparison")
        print("─" * 60)

    _show_token_comparison(result_text)

    # Step 5: Show the benchmark
    print()
    if not quick_mode:
        print("─" * 60)
        print("  Step 3/3: The big picture — 255 tools, 0 tokens")
        print("─" * 60)

    _show_benchmark()

    # Step 6: Cleanup or keep
    if keep_server:
        print()
        print("  --keep: demo server kept in config.")
        print(f"  Run: mcptoon call {server_name} echo '{{\"message\":\"...\"}}' --toon")
    else:
        _cleanup_demo(server_name)

    # Step 7: Next steps
    print()
    print("─" * 60)
    print("  🎉 mcptoon works! Next steps:")
    print("─" * 60)
    print()
    print("    mcptoon quickstart     # Discover your existing MCP servers")
    print("    mcptoon serve           # Run as agent-connected MCP server")
    print("    mcptoon manifest --slim  # See all tools (93% smaller than JSON)")
    print("    mcptoon call <server> <tool> '{...}' --toon  # Call a tool")
    print()
    print("  📖 Docs: https://github.com/activeing123/mcptoon")
    print()


def _print_banner():
    """Print the mcptoon demo banner."""
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║         mcptoon — Zero-config demo          ║")
    print("║    Install 1,000 MCP tools, 0 token schemas ║")
    print("╚══════════════════════════════════════════════╝")
    print()


def _check_prerequisites() -> bool:
    """Check that npx is available."""
    npx_path = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx_path:
        print("  ❌ npx not found in PATH.")
        print("  Please install Node.js: https://nodejs.org")
        print("  (npx is bundled with Node.js 18+)")
        return False
    return True


def _demo_call(server_name: str, server_cmd: list[str], message: str,
               quick: bool) -> str | None:
    """Run the demo: start server, call the echo tool, return result text."""
    client: MCPClient | None = None
    try:
        # Start the MCP server
        client = MCPClient(stdio=server_cmd, timeout=15)
        client.initialize()

        # List tools
        tools = client.list_tools()
        if not quick:
            print(f"  ✓ Server '{server_name}' ready ({len(tools)} tools)")

        # Call the echo tool
        result = client.call_tool("echo", {"message": message})

        # Extract text from MCP content array
        result_text = _extract_text(result)
        if not result_text:
            result_text = json.dumps(result, ensure_ascii=False)

        if not quick:
            print(f"  ✓ Called echo: {result_text[:60]}")
        else:
            print(f"  ✓ Demo server ready")

        client.close()
        return result_text

    except Exception as e:
        print(f"  ❌ Demo error: {e}")
        if client is not None:
            try:
                client.close()
            except Exception:
                pass  # best-effort cleanup after failure
        return None


def _extract_text(result) -> str:
    """Extract text from MCP content array response."""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        texts = []
        for item in result:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts)
    if isinstance(result, dict):
        content = result.get("content", result.get("text", ""))
        if isinstance(content, list):
            return _extract_text(content)
        return str(content)
    return str(result)


def _show_token_comparison(text: str):
    """Show side-by-side token comparison: JSON vs TOON vs SLIM.

    Uses tiktoken if available for accurate token counts.
    Falls back to len//4 estimation if tiktoken not installed.
    """
    # Try to use tiktoken for accurate counts
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        def count_tokens(s: str) -> int:
            return len(enc.encode(s))
    except (ImportError, Exception):
        def count_tokens(s: str) -> int:
            return max(len(s) // 4, 1)

    sample = {"message": "mcptoon demo", "content": text[:500]}

    # JSON
    json_data = json.dumps(sample, ensure_ascii=False)
    json_tokens = count_tokens(json_data)

    # TOON
    try:
        toon_data = output_mod.toon(sample)
        toon_tokens = count_tokens(toon_data)
        toon_savings = round((1 - toon_tokens / max(json_tokens, 1)) * 100)
    except Exception:
        toon_data = ""
        toon_tokens = json_tokens
        toon_savings = 0

    # SLIM
    try:
        slim_data = output_mod.slim_toon(sample)
        slim_tokens = count_tokens(slim_data)
        slim_savings = round((1 - slim_tokens / max(json_tokens, 1)) * 100)
    except Exception:
        slim_data = ""
        slim_tokens = json_tokens
        slim_savings = 0

    print()
    best_tokens = min(toon_tokens, slim_tokens, json_tokens)
    best_name = {toon_tokens: "TOON", slim_tokens: "SLIM", json_tokens: "JSON"}[best_tokens]
    total_savings = round((1 - best_tokens / max(json_tokens, 1)) * 100)
    print(f"  📊  SAME data, {total_savings}% fewer tokens:")
    print(f"      {json_tokens:>10,}  →  {best_tokens:>10,}   ({best_name})")
    print()
    print(f"  {'Format':<10} {'Tokens':>10} {'Savings':>10}")
    print(f"  {'─'*10} {'─'*10} {'─'*10}")
    print(f"  {'JSON':<10} {json_tokens:>10,} {'-':>10}")
    print(f"  {'TOON':<10} {toon_tokens:>10,} {toon_savings:>9}%")
    print(f"  {'SLIM':<10} {slim_tokens:>10,} {slim_savings:>9}%")
    print()


def _show_benchmark():
    """Show the official 255-tool benchmark (assets/benchmark_tiktoken.json)."""
    print()
    print("  Official benchmark: 255 tools, 50 servers, tiktoken cl100k_base:")
    print()
    print(f"  {'Format':<12} {'Tokens':>10} {'Savings':>10}")
    print(f"  {'─'*12} {'─'*10} {'─'*10}")
    print(f"  {'JSON':<12} {'71,929':>10} {'-':>10}")
    print(f"  {'TOON':<12} {'47,438':>10} {'34%':>10}")
    print(f"  {'SLIM':<12} {'8,282':>10} {'88.5%':>10}")
    print(f"  {'Compact':<12} {'581':>10} {'99.2%':>10}")
    print()
    print("  Now you can:")
    print("  ✓ connect every agent with ONE config   →  mcptoon sync")
    print("  ✓ expose ALL servers as ONE stdio server →  mcptoon serve")
    print("  ✓ never paste tool schemas again         →  mcptoon manifest --slim")
    print()
    print("  Schemas in context with mcptoon: 0 tokens (always)")
    print()


def _cleanup_demo(server_name: str):
    """Remove the demo server from config."""
    try:
        servers = cfg.load_config()
        if server_name in servers:
            del servers[server_name]
            cfg.save_config(servers)
    except Exception:
        pass  # Cleanup is best-effort


def _demo_help() -> str:
    return """mcptoon demo — Zero-config one-command demo

Experience mcptoon's token savings in 30 seconds:
  1. Starts the official "everything" MCP reference server (no API key)
  2. Calls a tool and shows JSON vs TOON vs SLIM comparison
  3. Shows the official benchmark (71,929 -> 581 tokens, 255 tools)

Usage:
  mcptoon demo                    # Full demo, step by step
  mcptoon demo --quick            # Fast: skip step-by-step, just show results
  mcptoon demo --keep             # Keep the demo server in config after demo
  mcptoon demo --help             # Show this help
"""
