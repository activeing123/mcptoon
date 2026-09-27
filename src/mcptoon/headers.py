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

"""Environment-sourced HTTP header values (issue #24).

A remote MCP server that wants ``Authorization: Bearer <token>`` could only be
configured with the token written into the config file, the generated handler, or
the command line — all of which put a credential somewhere it can be read later.
This module lets a header *value* name an environment variable instead, and
resolves it at request time:

    [servers.baizhi.headers]
    Authorization = "Bearer ${BAIZHI_TOKEN}"

Four rules, and each one exists because the obvious alternative is unsafe:

1. **A value with no ``${`` is untouched.** There is no "interpolate everything"
   mode, so a config written before this existed keeps its exact meaning and
   renders byte-for-byte. A literal ``${NAME}`` is written ``$${NAME}``.
2. **Whole-token expansion only.** ``${NAME}`` with a braced name; a bare ``$`` is
   just a character. No shell is involved, so the parse is identical on Windows
   and POSIX — the shell would expand ``${NAME}`` before mcptoon ever saw it.
3. **Resolution is at request time**, never at load or save. So the secret is not
   written into the config, the generated handler or any output, and rotating the
   variable takes effect on the next call with no reinstall.
4. **Missing or empty is a hard error naming the variable.** Never a silently
   empty header: a server that installs and then 401s on every call is the
   failure mode to design against.

The resolution path is shared on purpose: the verification step in
``installer.install_http`` and the later calls through both the generated handler
and the gateway all end up in ``client.MCPClient``, which resolves here. One
implementation means a server cannot install successfully and then fail to call.
"""

from __future__ import annotations

import os
import re

__all__ = ["HeaderEnvError", "resolve_value", "resolve_headers", "needs_resolution"]

#: ``${NAME}`` where NAME is a conventional environment-variable name. Deliberately
#: strict: a ``${`` that does not close into a valid name is left alone rather than
#: half-expanded, so a typo cannot silently eat part of a token.
_TOKEN = re.compile(r"\$\$\{|\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

#: A value that will change under resolution, so callers can skip the work (and
#: the error) for the common literal case.
_MARKER = re.compile(r"\$\$\{|\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class HeaderEnvError(Exception):
    """A header named an environment variable that is missing or empty.

    Carries the variable ``name`` so a caller can report it without parsing the
    message, and formats a sentence a user can act on.
    """

    def __init__(self, name: str):
        self.name = name
        super().__init__(
            f"header needs environment variable ${{{name}}} but it is "
            f"unset or empty"
        )


def needs_resolution(value: str) -> bool:
    """Whether `value` contains anything this module would expand."""
    return isinstance(value, str) and _MARKER.search(value) is not None


def resolve_value(value: str) -> str:
    """Expand ``${NAME}`` in one header value.

    ``$${NAME}`` yields a literal ``${NAME}``. A ``${NAME}`` whose variable is
    unset or empty raises ``HeaderEnvError`` naming it. Any other ``$`` is
    ordinary text. Non-string values (a TOML integer, say) pass through as-is;
    they are not header material and guessing at them would be worse.
    """
    if not isinstance(value, str):
        return value

    def _sub(m: re.Match) -> str:
        if m.group(0) == "$${":
            # Escaped: emit the literal opener and let the rest of the value
            # through unchanged (the following ``NAME}`` is already literal text).
            return "${"
        name = m.group(1)
        env = os.environ.get(name)
        if env is None or env == "":
            raise HeaderEnvError(name)
        return env

    return _TOKEN.sub(_sub, value)


def resolve_headers(headers: dict | None) -> dict:
    """Resolve every value in a header mapping, at request time.

    Returns a new dict; the caller's (the config's) copy is never mutated, which
    is what keeps the resolved secret out of anything that might be written back
    to disk. Raises ``HeaderEnvError`` on the first missing/empty variable.
    """
    if not headers:
        return {}
    return {k: resolve_value(v) for k, v in headers.items()}
