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
import unicodedata
from typing import Any
from collections.abc import Callable

from .client import MCPClientPool, MCPError, MCPInputRequired
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
# Based on OWASP LLM Top 10, Invariant Labs Tool Poisoning research,
# and MCP-ITP (arXiv:2601.07395) attack patterns
_POISONING_INDICATORS = [
    # ── Direct instruction override ──
    "ignore previous instructions",
    "ignore all previous",
    "ignore the above",
    "ignore prior instructions",
    "disregard the above",
    "disregard previous",
    "forget your instructions",
    "forget all previous",
    # ── Role hijacking ──
    # fix 2026-10-01: `"you are a "` 与 `"act as "` 这**两个裸子串已从本表移除**，
    # 下方 `_POISONING_REGEXES` 以"句首锚定"形式重新收编（见该文件内注释）。
    # 原因（实测误报）：它们是英语里极常见的普通短语，字面匹配会在正常技术文本上
    # 恒命中 —— 例 ollama issue #18676 正文
    #   "this makes `done` act as a parsing short-circuit rather than a terminal signal"
    # 与 #18715/#18620 中被引用的 system prompt 片段 ("you are a coding agent ...")。
    # 两处都不是注入，却把整份 issues 结果拦成 TOOL_POISONING，真数据一条都拿不到。
    "you are now",
    "pretend you are",
    "new role:",
    "new instructions:",
    "system prompt:",
    # ── Hidden instructions (HTML comments, tags) ──
    "<!-- assistant:",
    "<!-- ignore",
    "<!-- system",
    "<!-- important",
    "<!-- do ",
    "[INST]",
    "<<SYS>>",
    "<|im_start|",
    "<|system|",
    # ── Data exfiltration attempts ──
    # fix 2026-10-01: `"curl http"` / `"wget http"` 同样过宽 —— GitHub issue 与
    # release notes 里满是可复现用的 curl/wget 命令（实测 ollama #18718 与
    # v0.35.0/v0.34.3 发布说明均被它拦成 TOOL_POISONING，真数据一条都拿不到）。
    # 已收编到下方 `_POISONING_REGEXES`：仅当与"外传动作"同现时才算。
    "send this to",
    "post this to",
    "call this url",
    "fetch this url",
    "upload to ",
    "exfiltrate",
    # ── Credential harvesting ──
    "read your env",
    "cat ~/.ssh",
    "print your api key",
    "show your token",
    "read /etc/passwd",
    "cat /etc/shadow",
    # ── Privilege escalation ──
    "sudo ",
    "chmod 777",
    "rm -rf",
    "format c:",
    # ── MCP-specific tool poisoning patterns ──
    "tool result:",  # fake tool result injection
    "mcp server:",  # fake server directive
    "register tool",
    "add this tool",
]

# ── Chinese indicators (v0.7.3) ──
_POISONING_INDICATORS_ZH = [
    "忽略之前", "忽略以上", "忽略先前",
    "无视之前", "无视以上",
    "你的系统提示", "你的api key", "你的密钥",
]

# ── 句首锚定的角色劫持判定（2026-10-01 收窄） ──
# 这三个短语在英语里太常见，做**裸子串**匹配会在正常内容上恒命中（误报实例见上方
# `_POISONING_INDICATORS` 的 Role hijacking 注释）。这里改成：只有出现在**句首**
# （文本开头，或紧跟在 . / ! / ? / 换行 之后）才算 —— 真正的注入是写给模型的独立
# 指令，通常就落在句首；而误报那几例都是嵌在从句/被引文本里的普通描述。
#
# ⚠️ 性质声明（advisory）：本函数整体是**启发式安全网，不是安全边界**（见下方
# docstring）。这类宽泛判定**曾经误判过**，按 R5 纪律仅作提示性拦截，
# 宁可漏拦也不要把正常数据整块吞掉。
_POISONING_REGEXES = [
    re.compile(r"(?:^|[.!?。！？\n])\s*you are a\b"),
    re.compile(r"(?:^|[.!?。！？\n])\s*act as\b"),
    re.compile(r"(?:^|[.!?。！？\n])\s*you have been\b"),
    # curl/wget 本身无害（技术文档里满地都是），只有"传到本地以外的地址"且带
    # 外传/凭据意图时才是真注入信号。故要求：外传动作 + 非本地目标，两者同现。
    re.compile(r"curl\s+https?://[^\n]{0,200}", re.I),
    re.compile(r"wget\s+https?://[^\n]{0,200}", re.I),
]

# 与上面 curl/wget 正则配套的判定（2026-10-01 收窄）：
# ① 外传/凭据类动词 —— 光有 curl 不算，得有"把东西送出去/偷出来"的意图
_EXFIL_VERBS = (
    "send this", "post this", "upload this", "upload to", "exfiltrate",
    "leak the", "steal the", "your api key", "your token", "print your api key",
    "show your token", "read your env", "~/.ssh", "/etc/passwd",
)
# ② 本地目标不算外传：localhost / 127.0.0.1 / ::1 / 私有网段 / example.com
_LOCAL_TARGET_RE = re.compile(
    r"https?://(?:localhost|127\.0\.0\.1|\[?::1\]?|0\.0\.0\.0|"
    r"10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|"
    r"example\.com|example\.org|example\.net)", re.I)


# Zero-width and invisible characters used to split keywords past substring
# matching (U+200B ZWSP, U+200C ZWNJ, U+200D ZWJ, U+2060 WJ, U+FEFF BOM)
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")
# Fullwidth ASCII variants (U+FF01-U+FF5E) → homoglyph obfuscation
_FULLWIDTH_RE = re.compile(r"[\uff01-\uff5e]")


def _normalize_for_scan(text: str) -> str:
    """Normalize obfuscation tricks before indicator matching (v0.7.3).

    1. NFKC fold (fullwidth → ascii), lowercased
    2. strip zero-width chars that would otherwise split keywords
    """
    folded = unicodedata.normalize("NFKC", text).lower()
    return _ZERO_WIDTH_RE.sub("", folded)


def _check_poisoning(result: Any) -> str | None:
    """Detect prompt injection in tool results.

    Returns reason string if poisoning detected, None otherwise.
    This is a heuristic check — not a security boundary, but a safety net.

    v0.7.3 hardening:
      - scans the full text (was: first 5000 chars only — truncation bypass)
      - NFKC-normalizes (defeats fullwidth homoglyphs)
      - strips zero-width chars (defeats 'ig\u200bnore' splitting)
      - zero-width DENSITY is itself a signal (hiding something)
      - Chinese indicator list added
    """
    if result is None:
        return None

    # Convert result to string for scanning
    try:
        text = str(result)
    except Exception:
        return None

    # Zero-width density check (before stripping, on the original text)
    zw_count = len(_ZERO_WIDTH_RE.findall(text))
    if zw_count >= 3:
        return (f"potential prompt injection detected: "
                f"{zw_count} zero-width characters in output")

    normalized = _normalize_for_scan(text)

    for indicator in _POISONING_INDICATORS:
        if indicator.lower() in normalized:
            return f"potential prompt injection detected: contains '{indicator}'"
    for indicator in _POISONING_INDICATORS_ZH:
        if indicator in normalized:
            return f"potential prompt injection detected: contains '{indicator}'"
    # 句首锚定的宽泛角色劫持判定（2026-10-01 收窄后新增，见 _POISONING_REGEXES）
    for rx in _POISONING_REGEXES:
        if not rx.search(normalized):
            continue
        if rx.pattern.startswith(("curl", "wget")):
            # curl/wget 单独出现是正常技术内容（发布说明/复现步骤里满地都是）。
            # 仅当 ① 含外传意图 ② 且目标不是本机/私有地址 时才判为注入。
            match = rx.search(normalized)
            if not match or _LOCAL_TARGET_RE.search(match.group()):
                continue
            if not any(w in normalized for w in _EXFIL_VERBS):
                continue
        return f"potential prompt injection detected: matches pattern '{rx.pattern}'"

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


# ─── Global pool reuse (avoids re-spawning subprocesses on every call) ───
_global_pool: MCPClientPool | None = None
_global_pool_config: dict | None = None


def _get_pool() -> MCPClientPool:
    """Get or create a global MCPClientPool.

    Reuses the pool across calls in the same process.
    In serve mode, the bridge has its own pool; this is for CLI mode.
    """
    global _global_pool, _global_pool_config
    servers = load_config()
    if _global_pool is None or _global_pool_config != servers:
        if _global_pool is not None:
            try:
                _global_pool.close()
            except Exception:
                pass
        _global_pool = MCPClientPool(servers)
        _global_pool_config = servers
    return _global_pool


# ─── Main router ───

def call_tool(
    server: str,
    tool: str,
    args: dict | None = None,
    is_destructive: bool = False,
    skip_poisoning_check: bool = False,
    return_envelope: bool = False,
    input_responses: dict | None = None,
    request_state: str | None = None,
) -> Any:
    """Route a tool call to the appropriate handler or MCP server.

    Routing chain:
      1. Custom handler (if registered) → return if non-None
      2. MCPClientPool → call via MCP protocol (reuses global pool)
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
        return_envelope: Return the complete MCP tools/call result envelope
            (structuredContent, _meta, resultType, isError, content) instead
            of the extracted content. Only affects the MCP path — custom
            handlers have no protocol envelope and return as before.

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
    handler_error = None
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
                usage.track_call(server, tool, ok=not is_error(result), payload=result)
                return result
        except Exception as exc:
            # Remember the real failure and fall through to MCP below. If the
            # server also turns out not to be an MCP server, report *this*
            # error instead of the misleading "not configured" one.
            handler_error = exc

    # 2. MCP protocol — reuse global pool
    servers = load_config()
    if server not in servers:
        if handler is not None:
            # A local handler owns this server, but it did not produce a result
            # for this tool. Reporting UNKNOWN_SERVER here is misleading (it
            # blames the server for what is usually a wrong tool name).
            if handler_error is not None:
                return make_error(
                    "TOOL_ERROR",
                    f"Tool '{tool}' failed on server '{server}': "
                    f"{type(handler_error).__name__}: {handler_error}",
                    "router", retry=False, server=server, tool=tool,
                )
            return make_error(
                "UNKNOWN_TOOL",
                f"Tool '{tool}' is not available on server '{server}' "
                f"(this server is not an MCP server either).",
                "router", retry=False, server=server, tool=tool,
            )
        return make_error(
            "UNKNOWN_SERVER",
            f"Server '{server}' not configured. Run: mcptoon init",
            "router", retry=False,
        )

    try:
        pool = _get_pool()
        if return_envelope:
            result = pool.call_full(server, tool, args,
                                    input_responses=input_responses,
                                    request_state=request_state)
        else:
            result = pool.call(server, tool, args, input_responses=input_responses,
                               request_state=request_state)

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

        usage.track_call(server, tool, ok=not is_error(result), payload=result)
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
        # MRTR (2026-07-28): surface the interim result's input requests so
        # callers can answer them and retry with input_responses.
        if isinstance(e, MCPInputRequired):
            err["input_requests"] = e.input_requests
            if e.request_state is not None:
                err["request_state"] = e.request_state
        return err
    except Exception as e:
        usage.track_call(server, tool, ok=False)
        return make_error("CALL_ERROR", str(e)[:200], "router", retry=False, server=server, tool=tool)


def call_tool_auto(
    tool: str,
    args: dict | None = None,
    is_destructive: bool = False,
    skip_poisoning_check: bool = False,
    return_envelope: bool = False,
) -> Any:
    """Auto-route a tool call to the server that has this tool.

    Tries to find the tool across all configured servers, then calls it
    on the first matching server. If multiple servers have the same tool
    name, prefers the one most recently used (from usage stats).

    Args:
        tool: Tool name (without specifying server)
        args: Tool arguments dict
        is_destructive: Acknowledge dangerous operation
        skip_poisoning_check: Skip poisoning detection
        return_envelope: Return the complete MCP result envelope (MCP path only)

    Returns:
        Tool result, or error dict if tool not found on any server.

    Example:
        >>> result = call_tool_auto("search", {"query": "AI"})
        # Automatically calls exa.search, brave-search.search, etc.
    """
    # 1. 先查本地 handlers（注册的私有 handler）
    for server_name, handler_func in _HANDLERS.items():
        try:
            module = getattr(handler_func, "__module__", "")
            if not module:
                continue
            import sys as _sys
            mod = _sys.modules.get(module)
            if mod and hasattr(mod, "SCHEMA"):
                for td in mod.SCHEMA:
                    if td.get("name", "").lower() == tool.lower():
                        return call_tool(server_name, tool, args, is_destructive,
                                         skip_poisoning_check, return_envelope)
        except Exception:
            continue

    # 2. 再查 MCP 服务器配置
    from . import manifest as manifest_mod

    servers_with_tool = manifest_mod.find_tool_across_servers(tool)

    if not servers_with_tool:
        # Try fuzzy match across all servers
        all_tools = manifest_mod.get_manifest(use_cache=True)
        suggestions = []
        for sname, tools in all_tools.items():
            for t in tools:
                if "error" not in t and t.get("name", "").lower() == tool.lower():
                    suggestions.append(sname)
        # Also check handlers for fuzzy match
        for server_name, handler_func in _HANDLERS.items():
            module = getattr(handler_func, "__module__", "")
            if not module:
                continue
            import sys as _sys
            mod = _sys.modules.get(module)
            if mod and hasattr(mod, "SCHEMA"):
                for td in mod.SCHEMA:
                    if tool.lower() in td.get("name", "").lower():
                        suggestions.append(server_name)
        if not suggestions:
            # Broader fuzzy search
            results = manifest_mod.search_tools(tool, limit=5)
            suggestions = list({r["server"] for r in results})

        return make_error(
            "TOOL_NOT_FOUND",
            f"Tool '{tool}' not found on any configured server.",
            "router", retry=False, tool=tool,
            suggestions=suggestions[:5] if suggestions else [],
        )

    # If multiple servers have this tool, try the one with most recent usage
    chosen = servers_with_tool[0]
    if len(servers_with_tool) > 1:
        # Check usage stats to pick the most-used server
        try:
            stats = usage.get_usage_stats()
            best_count = -1
            for sname in servers_with_tool:
                count = stats.get("by_server", {}).get(sname, 0)
                if count > best_count:
                    best_count = count
                    chosen = sname
        except Exception:
            chosen = servers_with_tool[0]

    return call_tool(chosen, tool, args, is_destructive, skip_poisoning_check, return_envelope)
