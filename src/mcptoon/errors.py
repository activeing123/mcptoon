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

"""mcptoon errors — structured error envelope.

Canonical envelope shape:

    {"_error": {
        "code": "AUTH_FAILED",       # machine-readable error code
        "message": "...",            # human-readable message
        "retry": False,              # whether retrying may help
        "component": "router",       # optional: which component raised it
        "detail": {"server": ...},   # optional: extra structured context
    }}

History note: before unification, extras were spread at the top level of
the result dict and the component field was called ``source``. The
``source=`` keyword is still accepted as a backwards-compatible alias.
Prefer the ``error_code()`` / ``error_message()`` helpers over touching
the envelope directly.
"""

__all__ = [
    "make_error",
    "is_error",
    "get_error_message",
    "error_message",
    "error_code",
]


def make_error(code: str, message: str, source: str = "", retry: bool = False,
               component: str = "", **extra) -> dict:
    """Create a structured error envelope.

    ``component`` and legacy ``source`` mean the same thing: which part
    of the system produced the error. Extra keyword arguments are grouped
    under ``_error["detail"]`` so the top level stays clean for routing
    metadata (e.g. ``suggestions``).
    """
    inner = {
        "code": code,
        "message": message,
        "retry": retry,
    }
    comp = component or source
    if comp:
        inner["component"] = comp
    if extra:
        inner["detail"] = extra
    return {"_error": inner}


def is_error(obj) -> bool:
    """Check if obj is an error envelope."""
    return isinstance(obj, dict) and "_error" in obj


def error_code(obj) -> str:
    """Extract the error code from an envelope ('' if not an error)."""
    if is_error(obj):
        return obj["_error"].get("code", "")
    return ""


def get_error_message(obj) -> str:
    """Extract error message from an error envelope or any object."""
    if isinstance(obj, dict):
        if "_error" in obj:
            return obj["_error"].get("message", "")
        if "error" in obj:
            if isinstance(obj["error"], dict):
                return obj["error"].get("message", str(obj["error"]))
            return str(obj["error"])
    return str(obj)[:200]


#: Alias kept for the private layer's historical name.
error_message = get_error_message
