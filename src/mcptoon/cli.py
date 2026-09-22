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

The user-facing command list lives in exactly one place: `_print_help()` below.
Do not restate it here. This module used to carry a second copy of the whole help
text, and by the time anyone looked it had drifted: it still advertised
`mcptoon uninstall` in its Usage block, listed `policy` twice, and never mentioned
`config`, `stats` or `toggle` — the three commands that exist to let a user turn
the per-turn savings line off. Two copies of a front door is one copy too many,
and the stale one is the one people end up reading.
"""

import json
import sys
import os
from pathlib import Path

from . import config as cfg
from . import manifest as manifest_mod
from . import output
from . import usage as usage_mod
from .router import call_tool
from .errors import is_error


# Every long option this CLI implements, global or per-subcommand — including the
# ones parsed inside demo.py / serve.py, which the central parser passes through
# untouched. tests/test_cli_flags.py scans the whole package for flag literals, so
# the list cannot drift from reality in either direction: forget one and a real
# flag gets warned as unknown; add a phantom and the dead-entry test fails.
KNOWN_FLAGS = frozenset(
    {
        "--agent", "--archive", "--auth", "--auto", "--all", "--compact", "--copy",
        "--derived", "--destructive", "--dry",
        "--dry-run", "--endpoint", "--envelope", "--fallback-json", "--force", "--format",
        "--full", "--head", "--desc",
        "--header", "--health", "--help", "--http", "--input-responses", "--interval",
        "--json", "--keep", "--k", "--list", "--listen", "--max-chars", "--mcptoon",
        "--no-keep-config",
        "--model",
        "--no-configs",
        "--no-env", "--no-local", "--no-network", "--no-self", "--no-sync", "--npm", "--pip",
        "--quiet", "--quick", "--query", "--raw", "--remove", "--request-state", "--roots", "--search",
        "--self",
        "--slim",
        "--stdin", "--stdio", "--timeout", "--tombstone", "--toon", "--tools-k", "--url", "--usage",
        "--version", "--version-gate", "--watch",
        "--watch-mode", "--write", "--yes",
    }
)


# Subcommands that print their own help text and therefore handle -h/--help
# themselves; every other command falls back to the general help. Adding a command
# here without a help handler in its own module silently loses that help — see
# tests/test_serve.py and tests/test_serve_perf.py, which pin serve's, and
# tests/test_help_shortcircuit.py, which pins this set's purpose.
_COMMANDS_WITH_OWN_HELP = frozenset({"demo", "demo-server", "serve"})


def unknown_flag_warnings(args):
    """Return the long options in args that mcptoon does not implement.

    Unknown options used to be dropped silently, which let a flag that never
    existed ("--tokens") sit in the README as the documented way to reproduce
    the token numbers. Callers print a warning; the token is still passed
    through so subcommand behaviour does not change.
    """
    found = []
    for a in args:
        if a.startswith("--"):
            base = a.split("=", 1)[0]
            if base not in KNOWN_FLAGS:
                found.append(base)
    return found


# Commands whose whole job is to make noise already; the one-time welcome would
# only be in the way (and `serve` speaks over stdio, so stdout must stay clean).
# `off` and `uninstall` are here for a different reason: a farewell should not be
# preceded by "hi, here's what I configured for you" — greeting someone on the way
# out is the same obliviousness this release is about.
_WELCOME_EXEMPT = frozenset({"serve", "demo", "demo-server", "completion",
                             "help", "-h", "--help", "off", "uninstall"})


def _maybe_welcome(command: str, fmt: str) -> None:
    """Introduce mcptoon once per machine — the answer to "it installed silently".

    A pip install cannot print anything, so a tool that never speaks looks like
    something that installed a trojan. The first real command therefore greets
    once, names what it found, and hands over one next action; the marker file
    means never again. Silent when: not the first run, `welcome off`, a
    machine-readable format was asked for (JSON/TOON/slim), or the command
    already prints its own noise.
    """
    if command in _WELCOME_EXEMPT:
        return
    if fmt != "auto":
        return
    try:
        if not cfg.welcome_enabled() or cfg.welcome_seen():
            return
    except Exception:
        return

    try:
        servers = cfg.list_servers()
    except Exception:
        servers = []
    n_servers = len(servers)

    tool_count = 0
    try:
        manifest = manifest_mod.get_manifest(use_cache=True)
        tool_count = _manifest_tool_count(manifest)
    except Exception:
        tool_count = 0

    line = "─" * 54
    print(line)
    print("  👋 mcptoon is installed — first run on this machine.")
    print(line)
    if n_servers:
        found = f"{n_servers} MCP server(s)"
        if tool_count:
            found += f", {tool_count} tool(s)"
        print(f"  Found: {found} already configured.")
    else:
        print("  Found: no MCP servers yet.")
    print("")
    print("  Next:")
    if n_servers:
        print("    mcptoon sync --self   # register the gateway in your agents,")
        print("                          # then sync the rest of your config")
    else:
        print("    mcptoon quickstart    # find servers already on this machine")
    print("    mcptoon status        # what's here, and what it saves")
    print("")
    print("  It only touches your agents when you run `mcptoon sync --self`.")
    print("  Undo any time: mcptoon off  ·  full cleanup: mcptoon uninstall --dry")
    print("  This note shows once. Silence it any time: mcptoon config set welcome off")
    print(line)
    print("")

    cfg.mark_welcome_seen()


def _run(state: dict) -> None:
    args = sys.argv[1:]

    if not args:
        _print_help()
        sys.exit(0)

    if args[0] in ("--version", "-V"):
        print(f"mcptoon {__import__('mcptoon').__version__}")
        return

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
            for bad in unknown_flag_warnings([a]):
                print(
                    f"mcptoon: unknown option '{bad}' ignored - see 'mcptoon --help'",
                    file=sys.stderr,
                )
            cmd_args.append(a)
        i += 1

    if not cmd_args:
        _print_help()
        sys.exit(0)

    command = cmd_args[0]
    rest = cmd_args[1:]
    state["command"] = command

    # Asking for help must never run the command you asked about: `mcptoon
    # quickstart --help` used to discover servers and write them into config, and
    # `mcptoon serve --help` used to open a stdio bridge and hang until timeout.
    if command not in _COMMANDS_WITH_OWN_HELP and any(a in ("-h", "--help") for a in rest):
        _print_help()
        return

    # First real command on this machine introduces mcptoon once (see _maybe_welcome).
    _maybe_welcome(command, fmt)

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
    elif command in ("status", "brief"):
        _cmd_status(rest, fmt)
    elif command == "stats":
        _cmd_stats(rest, fmt)
    elif command == "footer-facts":
        _cmd_footer_facts(rest, fmt)
    elif command == "toggle":
        _cmd_toggle(rest, fmt)
    elif command == "policy":
        _cmd_policy(rest, fmt)
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
    elif command == "demo-server":
        _cmd_demo_server(rest)
    elif command == "sync":
        _cmd_sync(rest, fmt)
    elif command == "off":
        _cmd_off(rest, fmt)
    elif command == "uninstall":
        _cmd_uninstall(rest, fmt)
    elif command == "health":
        _cmd_health(rest, fmt)
    elif command == "plugin":
        _cmd_plugin(rest, fmt)
    elif command == "skills":
        from .skills import _cmd_skills
        _cmd_skills(rest, fmt)
    elif command == "bench":
        from .bench import run_bench
        run_bench(rest, fmt)
    elif command == "config":
        _cmd_config(rest, fmt)
    elif command in ("help", "-h", "--help"):
        _print_help()
    else:
        # Try natural language: "mcptoon 有什么工具"
        _try_natural(command, rest, fmt, head_n, max_chars, full)


def main() -> None:
    """Entry point: run the CLI, then emit the savings footer.

    The footer cannot sit at the end of `_run`, because 41 places in this module
    leave through `sys.exit()` — `mcptoon manifest` among them — and a raised
    `SystemExit` skips everything written after the dispatch. Catching it here is
    the one seam that sees every exit path.

    Emitted only on success (`code` falsy): after a failed command the terminal
    already carries a diagnostic and one more line is noise. `_run` records the
    resolved command in `state`; the paths that never resolve one — `mcptoon
    --version`, or no arguments at all — leave it empty and stay silent, which
    keeps the version string parseable by scripts.

    Deliberately not `atexit`: that would also fire after an unhandled traceback
    and for any other caller of `_run`, and it could not tell success from
    failure.
    """
    state: dict = {}
    try:
        _run(state)
    except SystemExit as exc:
        if not exc.code:
            _emit_footer(state.get("command", ""))
        raise
    _emit_footer(state.get("command", ""))


# Commands whose streams are a protocol, not a human terminal, plus the one
# command that has already printed the same block.
_FOOTER_SILENT_COMMANDS = frozenset({"serve", "demo-server", "footer-facts"})


def _emit_footer(command: str) -> None:
    """Print the savings line to stderr after a command finishes.

    The CLI half of the universal-surface design described in the `footer`
    module: every agent that can run a shell sees command output, so a tail here
    reaches Codex, DSH, Gemini CLI, Aider and everything else that has a
    terminal — no per-agent configuration, no reliance on the model remembering
    a directive.

    stderr rather than stdout, deliberately. stdout is machine-readable for
    `--json`, `--toon` and piped output, and a courtesy line that corrupts
    `mcptoon status --json | jq` would be a worse bug than the invisibility it
    fixes. Terminals and agent tool surfaces both display stderr.

    Silent for the MCP stdio servers (`serve`, `demo-server`), where one stray
    write can desynchronise the JSON-RPC stream, and for `footer-facts`, which
    already printed this exact block on stdout.

    Never raises: a footer is a courtesy, and a command must not fail because
    its footer could not be built.
    """
    if not command or command.startswith("-") or command in _FOOTER_SILENT_COMMANDS:
        return
    try:
        from . import footer as footer_mod

        if not footer_mod.enabled():
            return
        print(footer_mod.block(), file=sys.stderr)
    except Exception:
        return


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
    # Check for --envelope mode (complete MCP result envelope, new-protocol servers)
    return_envelope = "--envelope" in rest
    if return_envelope:
        rest = [a for a in rest if a != "--envelope"]

    # Check for --input-responses '<json>' (MCP 2026-07-28 MRTR retry)
    input_responses = None
    request_state = None
    for i, a in enumerate(rest):
        if a == "--input-responses" and i + 1 < len(rest):
            try:
                input_responses = json.loads(rest[i + 1])
            except json.JSONDecodeError as e:
                print(f"Error parsing --input-responses JSON: {e}", file=sys.stderr)
                sys.exit(1)
            rest = rest[:i] + rest[i + 2:]
            break

    # Check for --request-state '<token>' (MCP 2026-07-28 MRTR correlation)
    for i, a in enumerate(rest):
        if a == "--request-state" and i + 1 < len(rest):
            request_state = rest[i + 1]
            rest = rest[:i] + rest[i + 2:]
            break

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
        result = call_tool_auto(tool, args, is_destructive=is_destructive,
                                return_envelope=return_envelope)

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
        print("Usage: mcptoon call <server> <tool> [JSON_ARGS] [--destructive] [--stdin] [--envelope] [--input-responses JSON] [--request-state TOKEN]")
        print("       mcptoon call --auto <tool> [JSON_ARGS] [--destructive] [--stdin] [--envelope]")
        print("")
        print("Examples:")
        print('  mcptoon call fetch fetch \'{"url":"https://example.com"}\' --toon')
        print('  mcptoon call exa search \'{"query":"AI"}\' --json')
        print('  mcptoon call --auto search \'{"query":"AI"}\'  # auto-find server')
        print('  mcptoon call db query \'{"sql":"SELECT 1"}\' --envelope  # full MCP result envelope')
        print("  mcptoon call db query '{}' --input-responses '{\"answer\": 42}' --request-state 'st-42'  # MRTR retry (2026-07-28)")
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

    result = call_tool(server, tool, args, is_destructive=is_destructive,
                       return_envelope=return_envelope,
                       input_responses=input_responses,
                       request_state=request_state)

    if is_error(result):
        err = result["_error"]
        print(f"Error [{err['code']}]: {err['message']}", file=sys.stderr)
        if err.get("retry"):
            print("  (retryable)", file=sys.stderr)
        # MRTR (MCP 2026-07-28): the tool asked for more input — show the
        # requests and how to answer them.
        if err["code"] == "INPUT_REQUIRED" and result.get("input_requests"):
            print("  The tool needs more input (multi round-trip request):", file=sys.stderr)
            for req in result["input_requests"]:
                name = req.get("method", "?") if isinstance(req, dict) else str(req)
                print(f"    - {name}", file=sys.stderr)
            state_hint = ""
            if result.get("request_state"):
                state_hint = f" --request-state '{result['request_state']}'"
            print(f'  Answer them and retry: mcptoon call ... --input-responses \'{{"method": "value"}}\'{state_hint}',
                  file=sys.stderr)
        # Fuzzy match suggestions for unknown tools
        if err["code"] == "UNKNOWN_TOOL" and result.get("suggestions"):
            print(f"Did you mean: {', '.join(result['suggestions'])}", file=sys.stderr)
        # Fix suggestions for common errors
        fix = _fix_suggestion(err["code"], server, tool)
        if fix:
            print(f"  Fix: {fix}", file=sys.stderr)
        sys.exit(1)

    _render_result(result, _effective_fmt(server, tool, fmt),
                   head_n, max_chars, full, fallback_json)


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
# Policy command — per-tool compression overrides
# ═══════════════════════════════════════════════════

def _effective_fmt(server, tool, fmt):
    """Per-tool compression policy applies only when no format flag was given.

    Explicit flags (--json/--toon/...) always win; the policy is the
    *default* for tools whose results need special handling.
    """
    if fmt != "auto":
        return fmt
    try:
        return cfg.resolve_output_format(server, tool, fmt)
    except Exception:
        return fmt


def _cmd_policy(rest, fmt):
    """Per-tool compression policy: pin how a tool's results are compressed.

    Usage:
        mcptoon policy                                list configured policies
        mcptoon policy set <server> <tool> <policy>   pin one tool's format
        mcptoon policy set <server> * <policy>        server-wide default
        mcptoon policy clear <server> <tool>          remove a policy

    Policies:
        raw|json              never compress (images, base64, binary)
        toon|compact|slim     force this format regardless of the default
        auto                  remove the policy (back to default)
    """
    if not rest or rest[0] in ("--list", "list"):
        policies = cfg.list_policies()
        if not policies:
            print("No compression policies configured - default behaviour applies everywhere.")
            print("")
            print("Set one:")
            print("  mcptoon policy set <server> <tool> raw   # never compress (images, base64)")
            print("  mcptoon policy set <server> <tool> toon  # always render as TOON")
            return
        print("Per-tool compression policies:")
        for key, policy in policies.items():
            print(f"  {key:40s} -> {policy}")
        return

    sub = rest[0]
    if sub == "set":
        if len(rest) < 4:
            print("Usage: mcptoon policy set <server> <tool-or-*> <raw|json|auto|toon|compact|slim>")
            sys.exit(1)
        server, tool, policy = rest[1], rest[2], rest[3]
        if cfg.set_compression_policy(server, tool, policy):
            if policy == "auto":
                print(f"Cleared: {server}:{tool} uses the default behaviour again.")
            else:
                meaning = ("never compressed" if policy in ("raw", "json")
                           else f"always rendered as {policy}")
                print(f"Policy set: {server}:{tool} -> {policy} ({meaning})")
        else:
            print(f"Unknown policy '{policy}'. Valid: {', '.join(cfg.VALID_POLICIES)}")
            sys.exit(1)
    elif sub == "clear":
        if len(rest) < 3:
            print("Usage: mcptoon policy clear <server> <tool-or-*>")
            sys.exit(1)
        cfg.set_compression_policy(rest[1], rest[2], None)
        print(f"Cleared: {rest[1]}:{rest[2]} uses the default behaviour.")
    else:
        print(f"Unknown subcommand '{sub}'. Use: list | set | clear")
        sys.exit(1)


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
        mcptoon quickstart              # discover + configure + sync + show slim manifest
        mcptoon qs                      # alias
        mcptoon quickstart --http URL    # include HTTP MCP endpoint
        mcptoon quickstart --dry        # don't write config, just show
        mcptoon quickstart --no-self    # sync servers only, don't register the gateway
    """
    is_dry = "--dry" in rest
    include_self = "--no-self" not in rest
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
        print("    mcptoon add everything --stdio npx -y @modelcontextprotocol/server-everything")
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

    # Step 3: Sync into every detected agent — including mcptoon itself.
    #
    # This is the step that turns "installed" into "visible". Without it the
    # gateway's `mcptoon serve` entry is never written anywhere, so the MCP
    # `instructions` handshake that announces mcptoon to the model never fires
    # and the install leaves no trace. Registering it here (and in `sync`) is
    # what a user actually notices.
    if not is_dry:
        from .sync import sync_to_all, format_sync_report
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  Registering mcptoon in your agents...")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        try:
            results = sync_to_all(dry_run=False, include_self=include_self)
            print(format_sync_report(results, dry_run=False))
            written = sum(1 for r in results if r.get("written"))
            if written:
                print("")
                print("  ✓ Your agents can now see mcptoon itself (`mcptoon serve`).")
        except Exception as e:  # never let a sync failure abort onboarding
            print(f"  Could not sync to agents yet: {e}")
            print("  Run 'mcptoon sync --self' when ready")
        print("")

    # Step 4: Show summary
    print(result.summary())

    # Step 5: The "aha moment" — show slim manifest
    tool_count = None
    if not is_dry:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  Your tools (names only \u2014 the default manifest tier):")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        try:
            manifest = manifest_mod.get_manifest(use_cache=False)
            tool_count = _manifest_tool_count(manifest)
            slim_output = manifest_mod.format_manifest(manifest, full=False)
            if slim_output.strip():
                print(slim_output)
            else:
                print("  (tools will appear after servers are started)")
        except Exception as e:
            print(f"  Could not fetch tools yet: {e}")
            print("  Run 'mcptoon manifest --slim' after servers are started")

    print("")
    if not is_dry:
        _quickstart_celebration(tool_count, result.count)
    else:
        print("Next steps (once you write the config):")
        print("  mcptoon quickstart          # write config + celebrate")
        print("  mcptoon manifest --slim     # see all available tools")
        print("  mcptoon doctor              # check connectivity")


def _manifest_tool_count(manifest) -> int:
    """Best-effort tool count from a get_manifest() result."""
    try:
        if isinstance(manifest, dict):
            tools = manifest.get("tools")
            if isinstance(tools, list):
                return len(tools)
            return len(manifest)
        if isinstance(manifest, list):
            return len(manifest)
    except Exception:
        pass
    return 0


def _quickstart_celebration(tool_count, server_count):
    """A1: the payoff block after a successful quickstart.

    Zero-config feel: big number, one-line status, one clear next action.
    """
    line = "━" * 54
    if tool_count:
        print(line)
        print(f"  🎉  {tool_count} tools ready across {server_count} servers!")
        print(line)
    else:
        print(line)
        print(f"  🎉  {server_count} MCP servers configured — you're set!")
        print(line)
    print("")
    print("  Now you can:")
    print("    mcptoon status  # what's here, and what it saves")
    print("    mcptoon serve   # or expose ALL servers as ONE stdio server")
    print("")
    print("  Next steps:")
    print("  mcptoon manifest --slim     # see all available tools")
    print("  mcptoon call <server> <tool> '{...}'   # call a tool")
    print("  mcptoon doctor             # check connectivity")
    if server_count <= 3:
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


def _cmd_footer_facts(_rest, fmt):
    """One line of real numbers for the per-turn savings footer. Never blocks.

    Usage:
        mcptoon footer-facts
        mcptoon footer-facts --json
    This exists because the agent-side directive tells the model to close a turn
    with one line of savings, and the obvious implementation — run
    `mcptoon status` — is unusable in a chat loop: `status` refreshes a stale
    schema cache by spawning every configured MCP server, measured at ~23s here
    against ~1.9s warm. A footer that occasionally costs 23 seconds is worse than
    no footer, so this reads the cache at whatever age it has and never opens a
    connection. When the cache is missing or older than the freshness TTL it says
    so in `note` rather than refreshing, because a number the caller can date is
    honest and a 23-second pause is not.

    The figures live in `footer.facts()` rather than here, because three surfaces
    now need them: this command, the tail of every other command, and the first
    tool result of an MCP session. Keeping one implementation is what makes all of
    them agree — see the `footer` module docstring for why the line stopped being
    the model's job to remember.
    """
    from . import footer as footer_mod

    f = footer_mod.facts()

    if fmt == "json":
        print(json.dumps(f, indent=2, ensure_ascii=False))
        return

    # Human line — the whole point is that this is pasteable into a turn.
    print(footer_mod.line(f))
    n = footer_mod.note(f)
    if n:
        print(f"note: {n}")


def _cmd_stats(_rest, fmt):
    """Token savings dashboard — shows how much mcptoon saves vs raw JSON.

    Usage:
        mcptoon stats              Human-readable dashboard
        mcptoon stats --json       JSON output
    """
    from . import schema_simplifier
    from .bench import _tokenizer

    manifest = manifest_mod.get_manifest(use_cache=True)
    usage = usage_mod.get_usage_stats()

    # One ruler for every savings figure in the CLI. This dashboard used to divide
    # character counts by 4 while `mcptoon status` used tiktoken, so the two
    # commands a user runs back-to-back answered "how much does this save?" with
    # two different numbers — and this one is literally titled the savings
    # dashboard. It was invisible until `stats` was added to `--help`, which is
    # its own lesson about discoverability hiding defects.
    encode, caliber, _exact = _tokenizer()

    def _tokens(text: str) -> int:
        return max(1, int(encode(text)))

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
            full_tok = _tokens(full_json)
            slim_tok = _tokens(slim_json)
            total_full_tokens += full_tok
            total_slim_tokens += slim_tok
            server_full += full_tok
            server_slim += slim_tok
        by_server_full[server] = server_full
        by_server_slim[server] = server_slim

    # NOTE: this deliberately sums per-tool measurements, which is exactly what
    # `mcptoon status` does — the two commands are now required to print the same
    # numbers for the same catalog. Do not "improve" one of them to measure the
    # whole manifest in a single dump: that is a different (and larger) quantity,
    # and having a third number that matches neither command is worse than having
    # one that matches both.
    saved = total_full_tokens - total_slim_tokens
    pct = (saved / total_full_tokens * 100) if total_full_tokens > 0 else 0
    disabled = cfg.list_disabled_tools()

    if fmt == "json":
        data = {
            "total_tools": total_tools,
            # Kept under their original names so existing consumers do not break;
            # the values are now measured with the shared tokenizer instead of
            # chars/4, which is a correction rather than a contract change.
            "full_tokens_est": total_full_tokens,
            "slim_tokens_est": total_slim_tokens,
            "tokens_saved": saved,
            "savings_pct": round(pct, 1),
            "token_caliber": caliber,
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
        print(f"  Caliber:              {caliber}")
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


def _cmd_status(_rest, fmt):
    """One screen: what's here, what it saves, and how to undo it.

    The "is it doing anything?" answer for a tool that installs silently. Four
    facts a newcomer needs and nothing else; every number is read, never guessed.
    The savings figure uses the SAME caliber as `bench` (tiktoken cl100k_base) —
    quoting a different number here than `bench` prints is how a tool loses the
    argument that its numbers are real.

    Usage:
        mcptoon status
        mcptoon status --json
    """
    from . import schema_simplifier
    from .bench import _tokenizer

    servers = cfg.list_servers()
    n_servers = len(servers)

    # One tokenizer, one caliber — the same call `bench` makes.
    encode, caliber, _exact = _tokenizer()

    # Tools + savings, from the cached catalog (never spawns servers).
    try:
        manifest = manifest_mod.get_manifest(use_cache=True)
    except Exception:
        manifest = {}

    total_tools = 0
    full_tokens = 0
    slim_tokens = 0
    for _server, tools in manifest.items():
        if not tools:
            continue
        for t in tools:
            if not isinstance(t, dict) or "error" in t:
                continue
            total_tools += 1
            full_tokens += max(1, int(encode(json.dumps(t, ensure_ascii=False))))
            slim_tokens += max(1, int(encode(json.dumps(
                schema_simplifier.simplify_tool_def(t), ensure_ascii=False))))
    saved = max(0, full_tokens - slim_tokens)
    pct = round(saved / full_tokens * 100, 1) if full_tokens else 0.0

    try:
        stats = usage_mod.get_usage_stats()
        calls = int(stats.get("total_calls", 0))
    except Exception:
        calls = 0

    # Is the gateway itself registered in any agent config? Read-only check.
    wired = _gateway_wired_in()

    if fmt == "json":
        print(json.dumps({
            "servers": n_servers,
            "tools": total_tools,
            "tokens_full": full_tokens,
            "tokens_slim": slim_tokens,
            "tokens_saved_est": saved,
            "savings_pct": pct,
            "token_caliber": caliber,
            "calls_recorded": calls,
            "gateway_registered": wired,
            "footer_enabled": cfg.footer_enabled(),
        }, indent=2, ensure_ascii=False))
        return

    line = "─" * 54
    print(line)
    print("  mcptoon — status")
    print(line)
    if n_servers:
        print(f"  Managing           : {n_servers} MCP servers, {total_tools} tools")
    else:
        print("  Managing           : nothing yet — run `mcptoon quickstart`")
    if total_tools:
        print(f"  Tool definitions   : {full_tokens:,} → {slim_tokens:,} tokens "
              f"(saved {saved:,}, {pct:.0f}%)  [{caliber}]")
    print(f"  Calls recorded     : {calls}")
    if wired:
        print("  Gateway in agents  : yes — agents can see mcptoon itself")
    else:
        print("  Gateway in agents  : no — run `mcptoon sync --self` to register it")
    print(line)
    print("  Take it back any time:")
    print("    mcptoon off          remove the gateway from your agents")
    print("    mcptoon uninstall    full cleanup (preview with --dry)")
    print("  Prove the numbers: mcptoon bench   ·   what it did: mcptoon usage")
    print("")


def _cmd_off(rest, fmt):
    """Remove the gateway entry from every agent config — the reversible "off".

    Keeps mcptoon installed and your server definitions intact; it only stops
    the gateway from being handed to your agents. `mcptoon sync --self` puts it
    back. This is the answer to "I want it to stop touching my agents".

    Usage:
        mcptoon off
        mcptoon off --dry     preview without writing
    """
    from .sync import remove_gateway_from_all

    dry_run = "--dry" in rest or "--dry-run" in rest
    results = remove_gateway_from_all(dry_run=dry_run)
    present = [r for r in results if r.get("removed")]

    if fmt == "json":
        print(json.dumps({
            "dry_run": dry_run,
            "removed_from": [r.get("agent") for r in present],
            "count": len(present),
        }, indent=2, ensure_ascii=False))
        return

    line = "─" * 54
    print(line)
    print("  mcptoon off" + ("  (DRY RUN — nothing written)" if dry_run else ""))
    print(line)
    if not present:
        print("  Gateway is not registered in any agent. Nothing to remove.")
    else:
        for r in present:
            verb = "would remove" if dry_run else "removed"
            print(f"  {'→' if dry_run else '✓'} {r.get('agent_name', r.get('agent')):25s} {verb} the gateway entry")
        print("")
        if dry_run:
            print(f"  Preview: {len(present)} agent(s) would lose the gateway entry.")
        else:
            print(f"  Done: {len(present)} agent(s) no longer see mcptoon. Your servers are untouched.")
            print("  Put it back with: mcptoon sync --self")
    print(line)
    print("")


def _safe_rmtree(path) -> bool:
    """Delete a directory only if it is one mcptoon itself created.

    A destructive command should not be one bad constant away from deleting
    something else. If `MCPTOON_CACHE_DIR` (or a future refactor) ever resolved to
    a parent — the user's home, a drive root — an unguarded `rmtree` would take the
    user's world with it. `mcptoon` is the only directory name this project
    creates, so anything else is refused and reported rather than deleted.

    Returns True when the directory was removed.
    """
    p = Path(path)
    if p.name != "mcptoon":
        return False
    import shutil

    shutil.rmtree(p, ignore_errors=True)
    return not p.exists()


def _cmd_uninstall(rest, fmt):
    """Full, reversible cleanup — print exactly what will be removed, then remove it.

    A tool the user cannot get rid of is indistinguishable from one that never
    asked. This is the exit door: it removes the gateway from every agent config
    and deletes mcptoon's own files, and it PRINTS the plan first so the user can
    audit it. `--dry` shows the same plan and stops.

    Usage:
        mcptoon uninstall
        mcptoon uninstall --dry       preview only
        mcptoon uninstall --yes       skip the interactive confirmation
    """
    from .sync import remove_gateway_from_all

    dry_run = "--dry" in rest or "--dry-run" in rest
    assume_yes = "--yes" in rest or "-y" in rest
    keep_config = "--no-keep-config" not in rest

    # mcptoon's own files, resolved through config.state_paths() so env overrides
    # (MCPTOON_CONFIG_FILE and friends) are honoured. Crucially this NEVER deletes
    # your server definitions by default: config.json / config.toml hold the MCP
    # servers *you* configured. Deleting a user's config while claiming to "clean
    # up" is exactly the surprise this tool exists to avoid.
    paths = cfg.state_paths()
    bookkeeping = paths["bookkeeping"]
    server_configs = paths["servers"]
    if not keep_config:
        bookkeeping = [*bookkeeping, *server_configs]

    agents = remove_gateway_from_all(dry_run=True)
    agent_hits = [r for r in agents if r.get("removed")]
    dirs_present = [d for d in paths["cache"] if Path(d).exists()]
    files_present = [f for f in bookkeeping if Path(f).exists()]
    config_kept = [f for f in server_configs if Path(f).exists()]

    line = "─" * 54
    print(line)
    print("  mcptoon uninstall" + ("  (DRY RUN — nothing removed)" if dry_run else ""))
    print(line)
    print("  This will:")
    if agent_hits:
        for r in agent_hits:
            print(f"    · remove the gateway entry from {r.get('agent_name', r.get('agent'))}"
                  f"  ({r.get('path')})")
    else:
        print("    · (no agent config currently has the gateway entry)")
    for d in dirs_present:
        print(f"    · delete directory  {d}")
    for f in files_present:
        print(f"    · delete file       {f}")
    if config_kept:
        kept_names = ", ".join(Path(f).name for f in config_kept)
        print(f"    · KEEP {kept_names}  (your server definitions — delete with --no-keep-config)")
    if not dirs_present and not files_present and not agent_hits and not config_kept:
        print("    · nothing to remove — mcptoon left no trace here")
    print("")
    print("  Your own MCP server definitions are never touched (unless you pass")
    print("  --no-keep-config).")
    print(line)

    if dry_run:
        print("  Dry run — nothing was removed. Re-run without --dry to apply.")
        print("")
        return

    if not assume_yes:
        # Non-interactive stdin (CI, piped) means we cannot ask: refuse rather
        # than delete silently. --yes is the explicit opt-in.
        #
        # Note this guard is a courtesy, not the safety property. On Windows the NUL
        # device reports `isatty() == True`, so `stdin=DEVNULL` slips past it and
        # reaches the prompt below, where EOF makes the answer empty — which is not
        # "yes". Both routes refuse; neither deletes. Keep it that way: do not treat
        # `isatty()` as proof that somebody is there to answer.
        if not sys.stdin.isatty():
            print("  Refusing to delete without confirmation. Re-run with --yes.")
            print("")
            return
        try:
            answer = input("  Remove all of the above? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in ("y", "yes"):
            print("  Cancelled — nothing was removed.")
            print("")
            return

    removed_agents = remove_gateway_from_all(dry_run=False)
    n_agents = sum(1 for r in removed_agents if r.get("removed"))
    refused = []
    for d in dirs_present:
        if not _safe_rmtree(d):
            refused.append(d)
    for f in files_present:
        try:
            Path(f).unlink(missing_ok=True)
        except OSError:
            pass
    print("")
    print(f"  ✓ Removed the gateway from {n_agents} agent config(s).")
    n_dirs = len(dirs_present) - len(refused)
    print(f"  ✓ Deleted {n_dirs} director{'y' if n_dirs == 1 else 'ies'} "
          f"and {len(files_present)} file(s).")
    for d in refused:
        print(f"  ! Refused to delete {d} — not a directory mcptoon owns.")
    if config_kept:
        print(f"  ✓ Kept your server definitions: {', '.join(Path(f).name for f in config_kept)}")
    print("  mcptoon the package is still installed — remove it with:")
    print("    pip uninstall mcptoon")
    print(line)
    print("")


def _gateway_wired_in() -> bool:
    """True if `mcptoon serve` appears as a server entry in any agent config.

    Read-only and best-effort: a malformed agent config is treated as "not wired"
    rather than crashing the status command.
    """
    from .sync import (SELF_SERVER_NAME, _claude_desktop_path, _cline_path,
                       _cursor_path, _vscode_copilot_path, _windsurf_path)
    paths = [*_cursor_path(), _claude_desktop_path(), _cline_path(),
             _windsurf_path(), _vscode_copilot_path()]
    for path in paths:
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        # Cursor/Claude/Cline/Windsurf: {"mcpServers": {...}}; VS Code: {"mcp": {"servers": {...}}}
        for section in (data.get("mcpServers"), (data.get("mcp") or {}).get("servers")):
            if isinstance(section, dict) and SELF_SERVER_NAME in section:
                return True
    return False


def _cmd_config(rest, fmt):
    """Read or write gateway settings (footer, welcome, lang).

    Usage:
        mcptoon config                 Show every setting
        mcptoon config get <key>       Print one value
        mcptoon config set <key> <v>   Persist one value
    """
    from .config import SETTING_DEFAULTS, VALID_LANGS, load_settings, resolve_lang, set_setting

    action = rest[0].lower() if rest else "show"

    if action in ("", "show", "list"):
        values = load_settings()
        if fmt == "json":
            print(json.dumps(values, indent=2, ensure_ascii=False))
            return
        print("mcptoon settings")
        for key in sorted(values):
            print(f"  {key:12s} = {values[key]}")
        print()
        print("  footer on|off controls the one-line token-savings disclosure.")
        print("  lang auto|zh|en picks the language of that line;"
              " auto follows the OS language.")
        return

    if action == "get":
        if len(rest) < 2:
            print("Usage: mcptoon config get <key>")
            return
        key = rest[1].lower()
        if key not in SETTING_DEFAULTS:
            print(f"Unknown setting: {key}. Known: {', '.join(sorted(SETTING_DEFAULTS))}")
            return
        print(load_settings()[key])
        return

    if action == "set":
        if len(rest) < 3:
            print("Usage: mcptoon config set <key> <value>")
            return
        key, value = rest[1].lower(), rest[2].lower()
        if key == "footer" and value not in ("on", "off"):
            print("footer accepts only: on | off")
            return
        if key == "lang" and value not in VALID_LANGS:
            print("lang accepts only: auto | zh | en")
            return
        try:
            set_setting(key, value)
        except ValueError as e:
            print(str(e))
            return
        print(f"{key}: {value}   (saved)")
        if key == "footer" and value == "off":
            print("The gateway will stop adding the savings line on the next connection.")
        if key == "lang":
            # Print what the setting resolves to *now*, not what was typed: with
            # `auto` those differ, and "auto" alone leaves the user guessing which
            # machine signal won.
            print(f"The savings line will speak: {resolve_lang()}")
        return

    print(f"Unknown config action: {action}")
    print("Usage: mcptoon config [get <key> | set <key> <value>]")


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

    # Star hint: once per machine, only on a fully healthy doctor run, and
    # never in CI or when suppressed (MCPTOON_NO_STAR_HINT=1). Terminal-only:
    # the structured outputs other commands serve to scripts are untouched.
    if issues == 0 and _should_show_star_hint():
        print()
        print("  Found this useful? A GitHub star helps others find mcptoon:")
        print("  https://github.com/activeing123/mcptoon")
        _mark_star_hint_shown()


def _star_hint_marker():
    return cfg.CACHE_DIR / "star-hint-shown"


def _should_show_star_hint() -> bool:
    """Show the star hint at most once per machine, never in CI."""
    if os.environ.get("CI") or os.environ.get("MCPTOON_NO_STAR_HINT"):
        return False
    try:
        return not _star_hint_marker().exists()
    except OSError:
        return False  # fail quiet: never nag on odd filesystems


def _mark_star_hint_shown():
    try:
        cfg.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _star_hint_marker().write_text("shown", encoding="utf-8")
    except OSError:
        pass


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
            "  mcptoon add everything --stdio npx -y @modelcontextprotocol/server-everything\n"
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
    commands="init quickstart list manifest inspect call add remove usage discover doctor policy completion help sync health serve demo demo-server install search"

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
    local commands=(init list manifest inspect call add remove usage discover doctor policy completion help sync health serve demo demo-server install search)
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
complete -c mcptoon -n '__fish_use_subcommand' -a 'init quickstart list manifest inspect call add remove usage discover doctor policy completion help sync health serve demo demo-server install search'
complete -c mcptoon -n '__fish_seen_subcommand_from call inspect' -a '(mcptoon list 2>/dev/null | sed "s/  //;s/ \[.*//")'
complete -c mcptoon -n '__fish_seen_subcommand_from --format' -a 'openai openapi mcp json human'
'''

_PS_COMPLETION = '''
$scriptBlock = {
    param($wordToComplete, $commandAst, $cursorPosition)
    $commands = 'init','quickstart','list','manifest','inspect','call','add','remove','usage','discover','doctor','completion','help','sync','health','serve','demo','demo-server','install','search'
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
# Agent Plugins command (spec 1.0.0)
# ═══════════════════════════════════════════════════

def _cmd_plugin(rest, fmt):
    """mcptoon plugin — Agent Plugins 1.0.0 support (scan / install / list / remove)."""
    if not rest:
        print("Usage: mcptoon plugin <scan|install|list|remove> [args]")
        print("")
        print("Subcommands:")
        print("  scan <dir>        Validate a plugin package (read-only)")
        print("  install <dir>     Install a plugin into every agent (v0.7.1)")
        print("  list              List installed plugins (v0.7.1)")
        print("  remove <name>     Remove a plugin (v0.7.1)")
        sys.exit(1)

    sub = rest[0]
    if sub == "scan":
        _cmd_plugin_scan(rest[1:], fmt)
    elif sub == "install":
        _cmd_plugin_install(rest[1:])
    elif sub == "list":
        _cmd_plugin_list(fmt)
    elif sub == "remove":
        _cmd_plugin_remove(rest[1:])
    else:
        print(f"Unknown plugin subcommand: {sub}", file=sys.stderr)
        print("Available: scan | install | list | remove", file=sys.stderr)
        sys.exit(1)


def _cmd_plugin_install(args):
    """mcptoon plugin install <dir> [--force] [--no-sync]"""
    from .plugin import install_plugin

    force = "--force" in args
    sync_agents = "--no-sync" not in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print("Usage: mcptoon plugin install <plugin-dir> [--force] [--no-sync]")
        sys.exit(1)

    result = install_plugin(positional[0], force=force, sync_agents=sync_agents)
    if not result["ok"]:
        if result.get("stage") == "scan":
            print("❌ Plugin failed validation — fix these and retry:", file=sys.stderr)
            for f in result["fatal"]:
                print(f"  ❌ [{f['code']}] {f['message']}", file=sys.stderr)
        else:
            print(f"❌ {result.get('message', 'install failed')}", file=sys.stderr)
        sys.exit(1)

    print(f"✅ Installed plugin: {result['name']} v{result['version']}")
    print(f"  Plugin dir:  {result['dest']}")
    print(f"  Data dir:    {result['data_dir']}  (kept across upgrades)")
    print(f"  Servers:     {', '.join(result['servers']) or '(none)'}")
    if result["skills"]:
        print(f"  Skills:      {', '.join(result['skills'])}")
    sync = result.get("sync")
    if isinstance(sync, dict) and "synced_agents" in sync:
        print(f"  Synced to:   {sync['synced_agents']}/{sync['total_agents']} agents")
    elif isinstance(sync, dict) and sync.get("error"):
        print(f"  ⚠ sync failed: {sync['error']} — run `mcptoon sync` manually")
    else:
        print("  Sync:        skipped (--no-sync) — run `mcptoon sync` when ready")
    sys.exit(0)


def _cmd_plugin_list(fmt):
    """mcptoon plugin list"""
    import json as _json

    from .plugin import list_plugins

    plugins = list_plugins()
    if fmt == "json":
        print(_json.dumps(plugins, indent=2, ensure_ascii=False))
        return
    if not plugins:
        print("No plugins installed. Try: mcptoon plugin install <dir>")
        return
    print(f"── Installed plugins: {len(plugins)} ──")
    for p in plugins:
        print(f"  {p['name']}  v{p['version']}  ({len(p['servers'])} servers)")
        print(f"    installed: {p['installed_at']}")
        for s in p["servers"]:
            print(f"    · {s}")


def _cmd_plugin_remove(args):
    """mcptoon plugin remove <name> [--no-sync]"""
    from .plugin import remove_plugin

    sync_agents = "--no-sync" not in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print("Usage: mcptoon plugin remove <name> [--no-sync]")
        sys.exit(1)

    result = remove_plugin(positional[0], sync_agents=sync_agents)
    if not result["ok"]:
        print(f"❌ {result['message']}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ Removed plugin: {result['name']}")
    for s in result["removed_servers"]:
        print(f"  − {s}")
    if result.get("data_dir_kept"):
        print(f"  Data dir kept: {result['data_dir_kept']}")
    sync = result.get("sync")
    if isinstance(sync, dict) and "synced_agents" in sync:
        print(f"  Synced removal to: {sync['synced_agents']}/{sync['total_agents']} agents")
    sys.exit(0)


def _cmd_plugin_scan(args, fmt):
    """mcptoon plugin scan <dir> — validate an Agent Plugins package."""
    import json as _json

    from .plugin import scan_plugin

    if not args:
        print("Usage: mcptoon plugin scan <plugin-dir>")
        sys.exit(1)

    report = scan_plugin(args[0])

    if fmt == "json":
        print(_json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0 if report["ok"] else 1)

    plugin = report["plugin"]
    name = plugin.get("name") or "(unknown)"
    version = f" v{plugin.get('version')}" if plugin.get("version") else ""

    print(f"── Agent Plugin scan: {report['dir']} ──")
    print(f"  Plugin:  {name}{version}")
    skills = report["skills"]
    print(f"  Skills:  {len(skills)}" + (f" ({', '.join(skills)})" if skills else ""))
    servers = report["servers"]
    skipped = report["skipped_servers"]
    print(f"  Servers: {len(servers)} valid, {len(skipped)} skipped")
    for s in servers:
        print(f"    · {s['name']}  [{s['type']}]")
    for s in skipped:
        print(f"    ✗ {s['name']}  skipped — {s['reason']}")

    for w in report["warnings"]:
        print(f"  ⚠ [{w['code']}] {w['message']}")
    for f in report["fatal"]:
        print(f"  ❌ [{f['code']}] {f['message']}")

    if report["ok"]:
        n_warn = len(report["warnings"])
        tail = f" ({n_warn} warning{'s' if n_warn != 1 else ''})" if n_warn else ""
        print(f"\n  ✅ Valid plugin — ready for mcptoon plugin install{tail}")
        sys.exit(0)
    else:
        print(f"\n  ❌ Plugin rejected — {len(report['fatal'])} fatal issue(s)")
        sys.exit(1)


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
    print(f"""mcptoon v{__import__('mcptoon').__version__} — one gateway for all your MCP tools
                       compressed · visible · reversible

Start here:
    mcptoon quickstart                    One-command setup (discover + config + wire agents)
    mcptoon status                        What's here, what it saves, how to undo it
    mcptoon off                           Remove the gateway from your agents (reversible)
    mcptoon uninstall                     Full cleanup (--dry to preview)

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
    mcptoon search <query>                Search tools across all servers
    mcptoon call <server> <tool> [ARGS]   Call a tool
    mcptoon call --auto <tool> [ARGS]     Call a tool (auto-find server)
    mcptoon call <server> <tool> --stdin  Read args from stdin (large payloads)
    mcptoon init                          Create sample config
    mcptoon init --auto                   Auto-discover all MCP servers
    mcptoon init --auto --http <url>      Auto-discover + add HTTP MCP endpoint
    mcptoon add <name> [options]          Add a server
    mcptoon remove <name>                 Remove a server
    mcptoon usage                         Show usage stats
    mcptoon status                        One-screen: what's here and what it saves
    mcptoon stats                         Token-savings dashboard (vs raw JSON)
    mcptoon footer-facts                  One line of savings for a chat footer
    mcptoon config                        Show gateway settings (footer, welcome)
    mcptoon config set footer off         Silence the per-turn savings line
    mcptoon toggle <server> <tool>        Enable/disable one tool (--list to show)
    mcptoon policy                        Per-tool compression policy (raw/toon/slim)
    mcptoon doctor                        Self-diagnose config + connectivity
    mcptoon completion <shell>            Generate shell completion (bash|zsh|fish|ps)
    mcptoon install <name> --npm <pkg>    Install MCP server from npm
    mcptoon install <name> --pip <pkg>    Install MCP server from pip
    mcptoon install <name> --url <url>    Install HTTP/SSE MCP server
    mcptoon install --list                List installed servers
    mcptoon install --remove <name>       Remove an installed server

    mcptoon plugin scan <dir>             Validate an Agent Plugins 1.0.0 package
    mcptoon plugin install <dir>          Install a plugin into every agent
    mcptoon plugin list                   List installed plugins
    mcptoon plugin remove <name>          Remove a plugin

    mcptoon serve                         Run as MCP server (stdio bridge for agents)
    mcptoon serve --http --auth           HTTP mode; bare --auth auto-generates a token
    mcptoon demo                          Zero-config one-command demo
    mcptoon demo --quick                  Results only, skip the step-by-step narration
    mcptoon demo --keep                   Leave the demo server in config afterwards
    mcptoon demo-server                   Self-contained MCP demo server (11 tools, no network)
    mcptoon add demo --stdio python -m mcptoon demo-server
    mcptoon --version                     Print the installed version and exit
    mcptoon sync                          Sync config to all agents (Claude Desktop, Cursor, etc.)
    mcptoon sync --dry                    Preview without writing
    mcptoon sync --agent <id>             Sync to one agent only
    mcptoon sync --self                   Also register the mcptoon gateway itself in each agent
    mcptoon health                        Health check all MCP servers
    mcptoon health --json                 JSON output for CI/CD (exit 1 if dead)

    mcptoon skills list                   List the agent skill catalog (--usage adds hit counts)
    mcptoon skills resolve <query>        BM25 shortlist of skills (offline, no LLM)
    mcptoon skills sync [SRC] [VIEW...]   Distribute a skill catalog to every agent's folder
    mcptoon skills add|remove <name>      Create a skill in the source / retire it to the archive

    mcptoon bench                         Prove the savings on your own machine (tools + skills)
    mcptoon bench --json                  Machine-readable; --roots/--query/-k tune the skills half

Output flags:
    --toon         Standard TOON (toon-format/toon spec, saves ~34% vs JSON)
    --mcptoon      Legacy mcptoon pipe format (saves 20-40% tokens)
    --slim         Ultra-compact tool manifests (saves 88.5% tokens, measured)
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
    mcptoon manifest --toon               # standard TOON format
    mcptoon manifest --mcptoon            # legacy pipe format
    mcptoon manifest --slim               # ultra-compact tool schemas
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


def _cmd_demo_server(rest):
    """Run the built-in, self-contained demo MCP server over stdio."""
    from .demo_server import run_demo_server
    run_demo_server(rest)


def _cmd_sync(rest, fmt):
    """Sync mcptoon config to AI agent config files.

    Usage:
        mcptoon sync                 # sync to all detected agents
        mcptoon sync --dry           # preview without writing
        mcptoon sync --agent cursor  # sync to specific agent only
        mcptoon sync --agent claude-desktop
        mcptoon sync --agent windsurf
        mcptoon sync --self          # ALSO register `mcptoon serve` in each agent
        mcptoon sync --no-self       # explicit servers-only (the default)
        mcptoon sync --watch         # keep syncing as configs change
        mcptoon sync --watch --interval 5 --quiet --watch-mode strict
    """
    from .sync import sync_to_all, sync_to_agent, format_sync_report

    dry_run = "--dry" in rest or "--dry-run" in rest
    # Default OFF, unlike `quickstart`: `sync` is a routine, repeatable command, and
    # silently injecting a *new* server entry into an agent's config on every routine
    # run would be a surprise. `--self` opts in; `quickstart` (the install path) turns
    # it on by default, and `mcptoon status` points here when the gateway is missing.
    include_self = "--self" in rest

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
        result = sync_to_agent(agent_id, dry_run=dry_run, include_self=include_self)
        report = format_sync_report([result], dry_run=dry_run)
    else:
        results = sync_to_all(dry_run=dry_run, include_self=include_self)
        report = format_sync_report(results, dry_run=dry_run)

    print(report)
    if include_self and not dry_run:
        print("")
        print("  Gateway registered: agents can now see mcptoon itself (`mcptoon serve`).")
        print("  Undo any time: mcptoon off")


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
