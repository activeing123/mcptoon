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
mcptoon packs — "skill packs": one command installs a whole workflow.

A pack is a named bundle of MCP tools plus a prefilled prompt, so
``mcptoon install --pack web-research`` wires up a working setup (browser + fetch +
search, with instructions) in one step instead of three ``install`` calls.

What a pack is NOT, and deliberately so:

  * it never ships tool source — every tool is delegated to the existing
    ``install_npm`` / ``install_pip`` / ``install_http`` / ``install_by_name``,
    so a pack adds no new install mechanism and no new supply-chain surface;
  * it is data, not code — the catalog is ``packs.json`` (a builtin copy plus an
    optional ``~/.mcptoon/packs.json`` that overrides by name);
  * it writes only under ``~/.mcptoon/packs/<name>/`` (the prefilled prompt) and
    the user's own install bookkeeping. The single exception is a tool entry
    marked ``"self": true`` — that is the mcptoon gateway itself, and it is
    registered through the documented ``sync --self`` path (see
    ``_register_self``), because "add mcptoon as a tool" can only mean writing
    that entry into the agents' configs. It is always the user's own machine and
    their own agents, and ``mcptoon off`` removes it again.

Zero dependencies: standard library only.
"""
import json
from pathlib import Path

from .config import CONFIG_DIR
from .installer import (
    install_by_name,
    install_http,
    install_npm,
    install_pip,
)

#: Name of the builtin catalog that ships inside the package.
_BUILTIN_NAME = "packs.json"


class PackError(Exception):
    """A pack catalog could not be read or a pack is malformed."""


def builtin_path() -> Path:
    """Path to the catalog shipped with the package."""
    return Path(__file__).with_name(_BUILTIN_NAME)


def user_catalog_path() -> Path:
    """Path to the user's catalog (``~/.mcptoon/packs.json``)."""
    return CONFIG_DIR / "packs.json"


def packs_root() -> Path:
    """Directory a pack's prefilled prompt is written under."""
    return CONFIG_DIR / "packs"


def _read_catalog(path: Path, *, required: bool) -> list[dict]:
    if not path.is_file():
        if required:
            raise PackError(f"pack catalog not found: {path}")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PackError(f"could not read pack catalog {path}: {e}") from e
    packs_list = data.get("packs")
    if not isinstance(packs_list, list):
        raise PackError(f"{path} has no 'packs' list")
    return packs_list


def load_builtin() -> list[dict]:
    """The packs that ship with mcptoon."""
    return _read_catalog(builtin_path(), required=True)


def load_catalog(user_path: Path | None = None) -> list[dict]:
    """Builtin packs merged with the user's, user winning on a name clash."""
    merged: dict[str, dict] = {}
    order: list[str] = []
    for pack in load_builtin():
        name = pack.get("name")
        if not name:
            continue
        if name not in merged:
            order.append(name)
        merged[name] = pack
    upath = user_path if user_path is not None else user_catalog_path()
    for pack in _read_catalog(upath, required=False):
        name = pack.get("name")
        if not name:
            continue
        if name not in merged:
            order.append(name)
        merged[name] = pack
    return [merged[n] for n in order]


def find_pack(catalog: list[dict], name: str) -> dict | None:
    return next((p for p in catalog if p.get("name") == name), None)


def _tool_kind(tool: dict) -> tuple[str, str | None]:
    """Return ``(kind, payload)`` for a tool entry, or ``("", None)`` if unknown."""
    if tool.get("self"):
        # The gateway itself. Not a package: it is `mcptoon serve`, registered via
        # the documented `sync --self` path. This is the one pack entry that writes
        # to agent configs, and only because "add mcptoon as a tool" means exactly
        # that — see the module docstring.
        return "self", "mcptoon"
    if tool.get("npm"):
        return "npm", tool["npm"]
    if tool.get("pip"):
        return "pip", tool["pip"]
    if tool.get("url"):
        return "http", tool["url"]
    if tool.get("registry"):
        return "by_name", tool["registry"]
    return "", None


def install_pack(pack: dict, *, packs_root: Path | None = None,
                 dry_run: bool = False) -> dict:
    """Install every tool in ``pack`` and write its prompt.

    A tool that fails is recorded and the rest continue — a broken third-party
    package must not leave half a workflow silently installed with no report.
    """
    name = pack.get("name") or "pack"
    tools = pack.get("tools") or []
    report = {"pack": name, "title": pack.get("title", name),
              "dry_run": dry_run, "tools": [], "prompt": None, "ok": True}

    # `self` is not installed like the others: it is registered through the
    # documented `sync --self` path, once, after the package tools land.
    self_requested = any(t.get("self") for t in tools)

    for tool in tools:
        tname = tool.get("name") or ""
        kind, payload = _tool_kind(tool)
        if kind == "self":
            # Skip here; handled once below so `sync --self` runs after the tools.
            continue
        entry = {"name": tname, "kind": kind, "ok": False, "detail": ""}
        if dry_run:
            entry["ok"] = bool(kind)
            entry["detail"] = "planned" if kind else "unrecognized tool entry"
        elif not kind:
            entry["detail"] = "unrecognized tool entry (need npm/pip/url/registry/self)"
        else:
            try:
                result = _dispatch(kind, payload, tname)
                entry["ok"] = True
                entry["detail"] = str(result)[:200]
            except Exception as e:  # one bad tool must not abort the pack
                entry["detail"] = f"{type(e).__name__}: {str(e)[:160]}"
        if not entry["ok"]:
            report["ok"] = False
        report["tools"].append(entry)

    if self_requested:
        entry = {"name": "mcptoon", "kind": "self", "ok": False, "detail": ""}
        if dry_run:
            entry["ok"] = True
            entry["detail"] = "planned (registers the mcptoon gateway in your agents)"
        else:
            try:
                entry["ok"] = _register_self()
                entry["detail"] = "gateway registered in agent configs" if entry["ok"] \
                    else "no agent config found to register into"
            except Exception as e:
                entry["detail"] = f"{type(e).__name__}: {str(e)[:160]}"
        report["tools"].append(entry)

    prompt = pack.get("prompt")
    if prompt and not dry_run:
        dest = (packs_root or packs_root()) / name
        dest.mkdir(parents=True, exist_ok=True)
        pfile = dest / "PROMPT.md"
        pfile.write_text(prompt, encoding="utf-8")
        report["prompt"] = str(pfile)
    return report


def _register_self() -> bool:
    """Register the mcptoon gateway via the documented `sync --self` path.

    Returns True when at least one agent config was written. Reusing `sync_to_all`
    (rather than hand-writing configs) keeps one code path for the gateway entry,
    so `mcptoon off` removes what this added.
    """
    from .sync import sync_to_all
    results = sync_to_all(include_self=True)
    return any(r.get("written") for r in results)


def _dispatch(kind: str, payload: str, tname: str) -> dict:
    if kind == "npm":
        return install_npm(payload, tname)
    if kind == "pip":
        return install_pip(payload, tname)
    if kind == "http":
        return install_http(payload, tname)
    return install_by_name(payload, tname)
