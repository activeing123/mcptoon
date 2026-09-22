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
mcptoon usage — Lightweight usage tracking

Tracks tool calls per server for cost analysis.
Data stored in ~/.cache/mcptoon/usage.json
"""
import json
import os
import threading
import time

from .config import CACHE_DIR

_USAGE_FILE = CACHE_DIR / "usage.json"

# Concurrency guard: multiple agent processes/servers may record calls
# simultaneously (backported from the private layer, v0.5.6).
_usage_lock = threading.Lock()


def _load_usage() -> dict:
    if not _USAGE_FILE.exists():
        return {"calls": [], "total": 0}
    try:
        return json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"calls": [], "total": 0}


def count_tokens(payload) -> int:
    """Token cost of a payload, on the *same caliber* `mcptoon bench` uses.

    tiktoken cl100k_base when installed, otherwise ``len//4``. Delegates to
    ``bench._tokenizer`` so there is exactly one caliber in the codebase — the
    footer, `usage`, `stats` and `bench` can never quote two different numbers
    for the same payload. Never raises: a measurement failure returns 0.
    """
    if payload is None:
        return 0
    try:
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return 0
    if not text:
        return 0
    try:
        from .bench import _tokenizer
        encode, _name, _exact = _tokenizer()
        return max(1, int(encode(text)))
    except Exception:
        return max(1, len(text) // 4)


def _save_usage(data: dict):
    """Atomic write: unique tmp file + os.replace — readers never see a
    torn/partial usage.json even under concurrent writers."""
    tmp = None
    try:
        _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _USAGE_FILE.with_name(f"usage.json.tmp.{os.getpid()}.{id(data)}")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, _USAGE_FILE)
    except OSError:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def track_call(server: str, tool: str, ok: bool = True, tokens_est: int | None = None,
               payload=None):
    """Record a tool call.

    Crash-safe by contract: usage tracking must never break the actual
    tool call it is recording.

    ``payload`` is the tool result; when given and ``tokens_est`` is not, the
    token cost is counted on the ``bench`` caliber (tiktoken cl100k_base when
    available, else ``len//4``). Before v0.7.21 every caller passed no tokens, so
    ``mcptoon usage`` reported ``Tokens (est): 0`` on every machine — a tool that
    claims to save tokens and can never show one. Errors and unknown results
    still record 0 rather than guessing.
    """
    if tokens_est is None:
        tokens_est = count_tokens(payload)
    try:
        with _usage_lock:
            data = _load_usage()
            data["calls"].append({
                "server": server,
                "tool": tool,
                "ok": ok,
                "tokens": int(tokens_est or 0),
                "ts": time.time(),
            })
            # Keep last 1000 calls
            if len(data["calls"]) > 1000:
                data["calls"] = data["calls"][-1000:]
            data["total"] = data.get("total", 0) + 1
            _save_usage(data)
    except Exception:
        pass


def get_usage_stats() -> dict:
    """Get usage statistics."""
    data = _load_usage()
    calls = data.get("calls", [])

    by_server: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    total_tokens = 0
    ok_count = 0

    for c in calls:
        sk = f"{c['server']}:{c['tool']}"
        by_server[c["server"]] = by_server.get(c["server"], 0) + 1
        by_tool[sk] = by_tool.get(sk, 0) + 1
        total_tokens += c.get("tokens", 0)
        if c.get("ok"):
            ok_count += 1

    return {
        "total_calls": len(calls),
        "success_rate": f"{ok_count}/{len(calls)}" if calls else "0/0",
        "total_tokens_est": total_tokens,
        "by_server": dict(sorted(by_server.items(), key=lambda x: -x[1])),
        "top_tools": dict(sorted(by_tool.items(), key=lambda x: -x[1])[:10]),
    }


def reset_usage():
    """Clear all usage data."""
    _save_usage({"calls": [], "total": 0})
