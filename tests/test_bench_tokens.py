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

"""Tests for `python -m mcptoon.bench_tokens` — the README-caliber table in the wheel.

The claim this module makes is that a `pip install mcptoon` user can reproduce the
README's token numbers without a clone. The load-bearing behaviours are therefore
the failure messages (tiktoken absent, cache empty) and that both encodings appear —
a table that silently drops a column would under-report the pitch.
"""
from __future__ import annotations

import builtins
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from mcptoon import bench_tokens

HAS_TIKTOKEN = importlib.util.find_spec("tiktoken") is not None
ROOT = Path(__file__).resolve().parents[1]

CACHE = {
    "exa": {"tools": [
        {"name": "search", "description": "Search the web",
         "inputSchema": {"properties": {"query": {"type": "string"}}}},
        {"name": "find_similar", "description": "Find similar pages",
         "inputSchema": {"properties": {"url": {"type": "string"}}}},
    ]},
    "github": {"tools": [
        {"name": "create_issue", "description": "Create an issue",
         "inputSchema": {"properties": {"title": {"type": "string"}}}},
    ]},
}


@pytest.fixture
def cache_dir(tmp_path):
    """A temp cache dir holding the sample catalog, patched where the module reads it."""
    (tmp_path / "schema_cache.json").write_text(json.dumps(CACHE), encoding="utf-8")
    with patch.object(bench_tokens, "_cache_dir", lambda: tmp_path):
        yield tmp_path


def test_empty_cache_returns_2_with_manifest_hint(tmp_path, capsys):
    """An empty cache is a hint, not a traceback — the fix is one command.

    Deliberately simulates tiktoken being *absent*: with nothing cached the tool
    must name `mcptoon manifest`, not `pip install tiktoken`. The check order is
    load-bearing — CI installs the tree without tiktoken, so a machine that has
    not run `mcptoon manifest` yet would otherwise be told to install the wrong
    dependency (and the real first step would be unreachable).
    """
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "tiktoken":
            raise ImportError("simulated: tiktoken not installed")
        return real_import(name, *a, **kw)

    with patch.object(builtins, "__import__", fake_import):
        with patch.object(bench_tokens, "_cache_dir", lambda: tmp_path):
            code = bench_tokens.main([])
    assert code == 2
    err = capsys.readouterr().err
    assert "mcptoon manifest" in err
    assert "schema_cache.json" in err


def test_missing_tiktoken_returns_2_and_names_the_fix(cache_dir, capsys):
    """tiktoken stays optional; absent, it must say how to install it, not crash.

    Uses a populated cache so the run clears the (now earlier) cache check and
    actually reaches the tiktoken import — otherwise an empty default cache would
    answer with the `mcptoon manifest` hint instead and this assertion would
    silently depend on whatever the developer's cache happens to hold.
    """
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "tiktoken":
            raise ImportError("simulated: tiktoken not installed")
        return real_import(name, *a, **kw)

    with patch.object(builtins, "__import__", fake_import):
        code = bench_tokens.main([])
    assert code == 2
    assert "pip install tiktoken" in capsys.readouterr().err


def test_load_tools_reads_the_cache_file(cache_dir):
    tools = bench_tokens.load_tools()
    assert set(tools) == {"exa", "github"}
    assert len(tools["exa"]) == 2


def test_load_tools_is_empty_without_a_cache(tmp_path):
    with patch.object(bench_tokens, "_cache_dir", lambda: tmp_path):
        assert bench_tokens.load_tools() == {}


@pytest.mark.skipif(not HAS_TIKTOKEN, reason="tiktoken not installed")
def test_table_reports_both_encodings_and_savings(cache_dir, capsys):
    code = bench_tokens.main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "cl100k_base" in out
    assert "o200k_base" in out
    assert "--compact name index" in out
    assert "(baseline)" in out
    assert "smaller" in out


@pytest.mark.skipif(not HAS_TIKTOKEN, reason="tiktoken not installed")
def test_json_output_is_machine_readable(cache_dir, capsys):
    code = bench_tokens.main(["--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["servers"] == 2
    assert payload["tools"] == 3
    assert set(payload["counts"]["--compact name index"]) == {"cl100k_base", "o200k_base"}


def test_scripts_shim_delegates_to_the_package(tmp_path):
    """`scripts/bench_tokens.py` must be the same measurement, not a stale copy.

    Run it against an empty cache: the package's hint proves the shim reached the
    packaged main() rather than a private reimplementation.
    """
    env = dict(os.environ, MCPTOON_CACHE_DIR=str(tmp_path))
    proc = subprocess.run(
        [sys.executable, "scripts/bench_tokens.py"],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 2
    assert "mcptoon manifest" in proc.stderr


def test_scripts_has_no_second_implementation():
    """Guard against the shim regrowing a copy: it must import the package's main."""
    src = (ROOT / "scripts" / "bench_tokens.py").read_text(encoding="utf-8")
    assert "from mcptoon.bench_tokens import main" in src
    assert "def as_json_blob" not in src
