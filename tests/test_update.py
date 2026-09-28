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

"""Tests for `mcptoon update` — the tool-surface refresh.

Two layers, deliberately:

  * pure unit tests for `diff` / `_sig` — the definition of "what moved", which
    must not depend on a live server;
  * an end-to-end pass against the real `echo_server.py`, because the whole point
    of the command is that it talks to a server and writes what it learned back.
    A mock would prove the mock works.

The end-to-end layer is what catches the regressions that matter here: a stale
cache the command failed to refresh, a `--check` that wrote anyway, a drift that
was reported but not persisted.
"""
import io
import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon import cache as cache_mod  # noqa: E402
from mcptoon import update as update_mod  # noqa: E402


def _tool(name, required=(), props=()):
    return {
        "name": name,
        "description": f"{name} tool",
        "inputSchema": {
            "type": "object",
            "required": list(required),
            "properties": {p: {"type": "string"} for p in props},
        },
    }


# ─── pure: what counts as "moved" ───

class TestDiff:
    def test_identical_surface_is_unchanged(self):
        tools = [_tool("echo", ["message"], ["message"])]
        assert update_mod.diff(tools, tools) == ([], [], [])

    def test_added_and_removed(self):
        old = [_tool("echo", ["message"], ["message"])]
        new = [_tool("echo", ["message"], ["message"]), _tool("ping")]
        added, removed, changed = update_mod.diff(old, new)
        assert added == ["ping"] and removed == [] and changed == []
        assert update_mod.diff(new, old) == ([], ["ping"], [])

    def test_a_new_required_arg_is_changed_not_added(self):
        """The load-bearing case: a tool that starts requiring an argument is
        still the same tool, so it must show as changed — not added, and never
        silently equal."""
        old = [_tool("search", ["query"], ["query"])]
        new = [_tool("search", ["query", "lang"], ["query", "lang"])]
        assert update_mod.diff(old, new) == ([], [], ["search"])

    def test_renamed_property_is_changed(self):
        old = [_tool("fetch", ["url"], ["url"])]
        new = [_tool("fetch", ["url"], ["url", "timeout"])]
        assert update_mod.diff(old, new) == ([], [], ["fetch"])

    def test_order_does_not_matter(self):
        a = [_tool("a"), _tool("b"), _tool("c")]
        b = [_tool("c"), _tool("a"), _tool("b")]
        assert update_mod.diff(a, b) == ([], [], [])

    def test_error_placeholders_are_not_tools(self):
        """A server that failed is cached as ``[{"error": ...}]``; that must not
        read as a tool being removed."""
        assert update_mod.diff([], [{"error": "boom"}]) == ([], [], [])

    def test_malformed_tool_does_not_crash(self):
        """Servers send null inputSchema; diff must survive it."""
        assert update_mod.diff([None, "x"], [{"name": "y"}]) == (["y"], [], [])


class TestSig:
    def test_signature_covers_name_required_and_props(self):
        assert update_mod._sig(_tool("t", ["a"], ["a", "b"])) == ("t", ("a",), ("a", "b"))

    def test_null_schema_is_safe(self):
        assert update_mod._sig({"name": "t", "inputSchema": None}) == ("t", (), ())

    def test_non_dict_is_placeholder(self):
        assert update_mod._sig(None) == ("?", (), ())


# ─── end-to-end against the real echo server ───

ECHO_PATH = Path(__file__).parent / "echo_server.py"


@pytest.fixture
def echo_env():
    """Isolated config + cache dirs with echo_server as the only server.

    Both dirs are redirected so a test can never touch the developer's real
    ~/.mcptoon or schema cache.
    """
    config_dir = tempfile.mkdtemp(prefix="mcptoon-upd-cfg-")
    cache_dir = tempfile.mkdtemp(prefix="mcptoon-upd-cache-")
    (Path(config_dir) / "config.json").write_text(
        json.dumps({"servers": {"echo": {"transport": "stdio",
                                         "command": [sys.executable, str(ECHO_PATH)]}}}),
        encoding="utf-8")
    keys = ("MCPTOON_CONFIG_FILE", "MCPTOON_CACHE_DIR")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["MCPTOON_CONFIG_FILE"] = str(Path(config_dir) / "config.json")
    os.environ["MCPTOON_CACHE_DIR"] = cache_dir
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _run(rest, fmt="auto"):
    """Run the command in-process, returning (stdout, SystemExit code or None)."""
    buf = io.StringIO()
    code = None
    with contextlib.redirect_stdout(buf):
        try:
            update_mod.run(rest, fmt)
        except SystemExit as e:
            code = e.code
    return buf.getvalue(), code


class TestUpdateEndToEnd:
    def test_first_run_seeds_the_cache(self, echo_env):
        out, code = _run([])
        assert code is None
        assert "cached" in out
        assert "cached for the first time" in out
        cached = cache_mod.get_cached_tools_any_age("echo")[0]
        assert cached is not None
        assert {t["name"] for t in cached} == {"echo", "add", "delete_item"}

    def test_second_run_is_unchanged(self, echo_env):
        _run([])
        out, code = _run([])
        assert "unchanged" in out and code is None

    def test_stale_cache_is_detected_and_refreshed(self, echo_env):
        # Seed an old surface: only `echo`, and `echo` lost its required arg.
        cache_mod.set_cached_tools("echo", [_tool("echo", [], ["message"])])
        out, code = _run([])
        assert code is None
        # +add +delete_item appear; echo's required arg came back → changed.
        assert "+add,delete_item" in out.replace(" ", "") or (
            "add" in out and "delete_item" in out)
        assert "~echo" in out
        fresh = cache_mod.get_cached_tools_any_age("echo")[0]
        assert {t["name"] for t in fresh} == {"echo", "add", "delete_item"}
        assert fresh and next(t for t in fresh if t["name"] == "echo")[
            "inputSchema"]["required"] == ["message"]

    def test_check_reports_but_writes_nothing(self, echo_env):
        cache_mod.set_cached_tools("echo", [_tool("echo", [], ["message"])])
        before = cache_mod.get_cached_tools_any_age("echo")[0]
        out, code = _run(["--check"])
        assert code == 1, "drift in --check mode must exit non-zero"
        assert "would refresh" in out
        after = cache_mod.get_cached_tools_any_age("echo")[0]
        assert after == before, "--check must not write the cache"

    def test_check_on_a_clean_tree_exits_zero(self, echo_env):
        _run([])  # seed
        out, code = _run(["--check"])
        assert code is None and "Everything up to date" in out

    def test_json_shape(self, echo_env):
        cache_mod.set_cached_tools("echo", [_tool("echo", [], ["message"])])
        out, code = _run(["--json"], fmt="json")
        data = json.loads(out)
        assert data["checked"] is False
        row = data["servers"][0]
        assert row["server"] == "echo" and row["status"] == "updated"
        assert "add" in row["added"] and "echo" in row["changed"]

    def test_unknown_server_exits_one(self, echo_env):
        out, code = _run(["nope"])
        assert code == 1 and "not found" in out.lower()

    def test_unreachable_server_is_reported_not_fatal(self, echo_env):
        """One broken server must not abort the sweep: the healthy one still updates."""
        cfg_path = Path(os.environ["MCPTOON_CONFIG_FILE"])
        cfg_path.write_text(json.dumps({"servers": {
            "echo": {"transport": "stdio",
                     "command": [sys.executable, str(ECHO_PATH)]},
            "dead": {"transport": "stdio",
                     "command": [sys.executable, "-c", "import sys; sys.exit(3)"]},
        }}), encoding="utf-8")
        out, code = _run([])
        assert "dead" in out and "unreachable" in out
        assert code == 1
        # The healthy server was still refreshed.
        assert cache_mod.get_cached_tools_any_age("echo")[0] is not None


class TestRefreshInstalled:
    def test_regenerates_the_handler_for_an_installed_server(self, echo_env, tmp_path, monkeypatch):
        """An installed server whose tools moved must have its handler rewritten,
        not just its cache — the handler bakes a SCHEMA."""
        from mcptoon import installer

        old_file = installer._INSTALLED_FILE
        tmp = tempfile.mkdtemp(prefix="mcptoon-upd-inst-")
        installer._INSTALLED_FILE = str(Path(tmp) / "pro_installed.json")
        # Keep the generated handler out of the source tree (it is a gitignored
        # private layer in production; a test must not write there either).
        monkeypatch.setattr(installer, "_handlers_dir", lambda: str(tmp_path))
        try:
            installer._save_installed({"echo": {
                "command": sys.executable,
                "args": [str(ECHO_PATH)],
                "env": [],
                "source": "custom",
                "tools": ["echo"],            # stale: server really has three
                "tools_with_schema": [],
                "tool_count": 1,
                "installed_at": "2020-01-01T00:00:00",
            }})
            assert update_mod._refresh_installed(
                "echo", [_tool("echo"), _tool("add"), _tool("delete_item")],
                write=True) is True
            rec = installer._load_installed()["echo"]
            assert rec["tools"] == ["echo", "add", "delete_item"]
            assert rec["tool_count"] == 3
            assert "updated_at" in rec
            handler = tmp_path / "echo.py"
            assert handler.exists(), "the handler must be regenerated alongside the record"
            assert "delete_item" in handler.read_text(encoding="utf-8")
        finally:
            installer._INSTALLED_FILE = old_file

    def test_absent_record_returns_false(self, echo_env):
        from mcptoon import installer

        old_file = installer._INSTALLED_FILE
        installer._INSTALLED_FILE = str(Path(tempfile.mkdtemp()) / "none.json")
        try:
            assert update_mod._refresh_installed("echo", [_tool("echo")], write=True) is False
        finally:
            installer._INSTALLED_FILE = old_file
