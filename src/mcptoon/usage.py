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
mcptoon usage — Lightweight usage tracking

Tracks tool calls per server for cost analysis.
Data stored in ~/.cache/mcptoon/usage.json
"""
import json
import time
from pathlib import Path

from .config import CACHE_DIR

_USAGE_FILE = CACHE_DIR / "usage.json"


def _load_usage() -> dict:
    if not _USAGE_FILE.exists():
        return {"calls": [], "total": 0}
    try:
        return json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"calls": [], "total": 0}


def _save_usage(data: dict):
    try:
        _USAGE_FILE.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def track_call(server: str, tool: str, ok: bool = True, tokens_est: int = 0):
    """Record a tool call."""
    data = _load_usage()
    data["calls"].append({
        "server": server,
        "tool": tool,
        "ok": ok,
        "tokens": tokens_est,
        "ts": time.time(),
    })
    # Keep last 1000 calls
    if len(data["calls"]) > 1000:
        data["calls"] = data["calls"][-1000:]
    data["total"] = data.get("total", 0) + 1
    _save_usage(data)


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
