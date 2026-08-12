# -*- coding: utf-8 -*-
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

"""mcptoon errors — structured error envelope."""

def make_error(code: str, message: str, source: str = "", retry: bool = False, **extra) -> dict:
    """Create a structured error dict."""
    err = {
        "_error": {
            "code": code,
            "message": message,
            "source": source,
            "retry": retry,
        }
    }
    err.update(extra)
    return err


def is_error(obj) -> bool:
    """Check if obj is an error envelope."""
    return isinstance(obj, dict) and "_error" in obj


def get_error_message(obj) -> str:
    """Extract error message from error envelope or any object."""
    if isinstance(obj, dict):
        if "_error" in obj:
            return obj["_error"].get("message", "")
        if "error" in obj:
            if isinstance(obj["error"], dict):
                return obj["error"].get("message", str(obj["error"]))
            return str(obj["error"])
    return str(obj)[:200]
