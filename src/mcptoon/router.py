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
mcptoon router — Tool call routing

Routes tool calls to the appropriate MCP server via MCPClientPool.
Supports custom handlers via decorator pattern.
Includes tool poisoning detection, credential leak detection, and fuzzy match suggestions.
"""
import re
from typing import Any, Callable

from .client import MCPClientPool, MCPError
from .config import load_config, resolve_server_name
from .errors import make_error, is_error
from . import usage


# ─── Custom handler registry ───

_HANDLERS: dict[str, Callable] = {}


def register(server_name: str, *aliases: str):
    """Decorator: register a custom handler for a server.

    Custom handlers bypass MCPClient and can call any API directly.

    Example:
        @register("my-service")
        def handle_my_service(tool, args):
            if tool == "greet":
                return {"message": f"Hello {args.get('name', 'World')}!"}
            return None  # fall through to MCP
    """
    def decorator(func):
        _HANDLERS[server_name] = func
        for alias in aliases:
            _HANDLERS[alias] = func
        return func
    return decorator


# ─── Tool annotations: dangerous operations ───

_DANGEROUS_PATTERNS = [
    "delete", "remove", "drop", "destroy", "purge", "wipe",
    "rm_", "del_", "clear", "reset", "force", "kill",
]


def _check_dangerous(server: str, tool: str, args: dict | None = None) -> str | None:
    """Check if operation is dangerous. Returns reason string or None."""
    if not tool:
        return None
    tool_lower = tool.lower()
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in tool_lower:
            return f"tool name matches dangerous pattern: '{pattern}'"
    if args and isinstance(args, dict):
        for key in ("force", "confirm"):
            if key in args and args[key] is True:
                return f"argument contains dangerous flag: {key}=true"
    return None


# ─── Tool poisoning detection ───

# Patterns that indicate prompt injection in tool results
_POISONING_INDICATORS = [
    # Instruction-like content in results
    "ignore previous instructions",
    "ignore all previous",
    "disregard the above",
    "you are now",
    "new instructions:",
    "system prompt:",
    # Hidden instructions
    "<!-- assistant:",
    "<!-- ignore",
    "[INST]",
    "<<SYS>>",
    # Data exfiltration attempts
    "send this to",
    "post this to",
    "call this url",
]


def _check_poisoning(result: Any) -> str | None:
    """Detect prompt injection in tool results.

    Returns reason string if poisoning detected, None otherwise.
    This is a heuristic check — not a security boundary, but a safety net.
    """
    if result is None:
        return None

    # Convert result to string for scanning
    try:
        text = str(result).lower()
    except Exception:
        return None

    # Only check first 5000 chars (performance)
    text = text[:5000]

    for indicator in _POISONING_INDICATORS:
        if indicator.lower() in text:
            return f"potential prompt injection detected: contains '{indicator}'"

    return None


# ─── Credential leak detection ───

# Patterns that indicate exposed API keys, tokens, or private keys
_CREDENTIAL_PATTERNS = [
    # AWS
    (re.compile(r'AKIA[0-9A-Z]{16}'), 'AWS Access Key ID'),
    (re.compile(r'aws_secret_access_key\s*[=:]\s*[A-Za-z0-9/+=]{40}', re.I), 'AWS Secret Access Key'),
    # GitHub
    (re.compile(r'gh[ps]_[A-Za-z0-9]{36}'), 'GitHub PAT'),
    (re.compile(r'github_pat_[A-Za-z0-9_]{82}'), 'GitHub Fine-grained PAT'),
    # OpenAI / Anthropic
    (re.compile(r'sk-[A-Za-z0-9]{48}'), 'OpenAI API Key'),
    (re.compile(r'sk-ant-[A-Za-z0-9]{93,}'), 'Anthropic API Key'),
    # Slack
    (re.compile(r'xox[baprs]-[A-Za-z0-9-]{10,}'), 'Slack Token'),
    # Google
    (re.compile(r'AIza[0-9A-Za-z\-_]{35}'), 'Google API Key'),
    # Private keys
    (re.compile(r'-----BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----'), 'Private Key Block'),
    # Generic credential patterns
    (re.compile(r'(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|password|passwd|pwd)\s*[=:]\s*["\'][A-Za-z0-9+/=_\-]{16,}["\']'), 'Generic Credential'),
    # Bearer tokens
    (re.compile(r'Bearer\s+[A-Za-z0-9\-_\.]{20,}'), 'Bearer Token'),
    # JWT
    (re.compile(r'eyJ[A-Za-z0-9\-_]{10,}\.eyJ[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}'), 'JWT Token'),
]


def _check_credential_leak(result: Any) -> str | None:
    """Detect exposed API keys, passwords, and secrets in tool results.

    Returns reason string if credential leak detected, None otherwise.
    This is a heuristic check — scans for common credential patterns.
    """
    if result is None:
        return None

    try:
        text = str(result)
    except Exception:
        return None

    # Check first 10K chars (performance)
    text = text[:10000]

    for pattern, cred_type in _CREDENTIAL_PATTERNS:
        match = pattern.search(text)
        if match:
            # Mask the credential: show first 6 + last 4 chars
            raw = match.group()
            if len(raw) > 14:
                masked = raw[:6] + '...' + raw[-4:]
            else:
                masked = raw[:4] + '...'
            return f"potential {cred_type} leak detected: {masked}"

    return None


# ─── Main router ───

def call_tool(
    server: str,
    tool: str,
    args: dict | None = None,
    is_destructive: bool = False,
    skip_poisoning_check: bool = False,
) -> Any:
    """Route a tool call to the appropriate handler or MCP server.

    Routing chain:
      1. Custom handler (if registered) → return if non-None
      2. MCPClientPool → call via MCP protocol
      3. Error

    Safety features:
      - Dangerous operation blocking (unless is_destructive=True)
      - Tool poisoning detection (unless skip_poisoning_check=True)
      - Credential leak detection (unless skip_poisoning_check=True)
      - Fuzzy match suggestions on unknown tools

    Args:
        server: Server name (short name OK, will be resolved)
        tool: Tool name
        args: Tool arguments dict
        is_destructive: Acknowledge dangerous operation
        skip_poisoning_check: Skip poisoning detection (for trusted sources)

    Returns:
        Tool result (dict, list, or scalar)
    """
    server = resolve_server_name(server)
    args = args or {}

    # Safety check
    if not is_destructive:
        danger = _check_dangerous(server, tool, args)
        if danger:
            return make_error(
                "CONFIRMATION_REQUIRED",
                f"Dangerous operation needs confirmation: {danger}",
                "router", retry=False, server=server, tool=tool,
            )

    # 1. Custom handler
    handler = _HANDLERS.get(server)
    if handler:
        try:
            result = handler(tool, args)
            if result is not None:
                # Check for poisoning and credential leaks
                if not skip_poisoning_check:
                    poison = _check_poisoning(result)
                    if poison:
                        return make_error(
                            "TOOL_POISONING",
                            f"Tool result may contain prompt injection: {poison}",
                            "router", retry=False, server=server, tool=tool,
                        )
                    leak = _check_credential_leak(result)
                    if leak:
                        return make_error(
                            "CREDENTIAL_LEAK",
                            f"Tool result may contain exposed credentials: {leak}",
                            "router", retry=False, server=server, tool=tool,
                        )
                usage.track_call(server, tool, ok=not is_error(result))
                return result
        except Exception as e:
            # Fall through to MCP
            pass

    # 2. MCP protocol
    servers = load_config()
    if server not in servers:
        return make_error(
            "UNKNOWN_SERVER",
            f"Server '{server}' not configured. Run: mcptoon init",
            "router", retry=False,
        )

    try:
        pool = MCPClientPool(servers)
        result = pool.call(server, tool, args)
        pool.close()

        # Check for poisoning and credential leaks in result
        if not skip_poisoning_check:
            poison = _check_poisoning(result)
            if poison:
                return make_error(
                    "TOOL_POISONING",
                    f"Tool result may contain prompt injection: {poison}",
                    "router", retry=False, server=server, tool=tool,
                )
            leak = _check_credential_leak(result)
            if leak:
                return make_error(
                    "CREDENTIAL_LEAK",
                    f"Tool result may contain exposed credentials: {leak}",
                    "router", retry=False, server=server, tool=tool,
                )

        usage.track_call(server, tool, ok=not is_error(result))
        return result
    except MCPError as e:
        usage.track_call(server, tool, ok=False)
        # Provide suggestions for unknown tools
        suggestions = []
        if e.code in ("METHOD_NOT_FOUND", "UNKNOWN_TOOL", "TOOL_NOT_FOUND"):
            try:
                from . import manifest as manifest_mod
                suggestions = manifest_mod.fuzzy_match_tool(server, tool)
            except Exception:
                pass
        err = make_error(e.code, e.message, "mcp", retry=e.retry, server=server, tool=tool)
        if suggestions:
            err["suggestions"] = suggestions
        return err
    except Exception as e:
        usage.track_call(server, tool, ok=False)
        return make_error("CALL_ERROR", str(e)[:200], "router", retry=False, server=server, tool=tool)
