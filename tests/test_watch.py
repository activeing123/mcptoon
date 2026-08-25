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

"""Tests for mcptoon sync --watch (continuous sync).

All tests are fully injected: no real user directories are touched.
sync_fn is a stub, paths live in tmp_path, sleeps are real but tiny,
loops are bounded by max_cycles or KeyboardInterrupt simulation.
"""
import threading
import time
from pathlib import Path

import pytest

from mcptoon.watch import (
    watch,
    fingerprint,
    collect_watch_paths,
    DEFAULT_INTERVAL,
    DEBOUNCE,
    MAX_CONSECUTIVE_FAILURES,
)


def _ok_results():
    return [
        {"agent": "cursor", "path": "x", "servers_synced": 2, "written": True, "error": None},
        {"agent": "cline", "path": "y", "servers_synced": 2, "written": True, "error": None},
    ]


def _touch(p: Path, content: str = '{"x": 1}'):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


class TestFingerprint:
    def test_present_file(self, tmp_path):
        f = tmp_path / "a.json"
        _touch(f)
        fp = fingerprint(f)
        assert fp is not None
        assert isinstance(fp[0], int) and isinstance(fp[1], int)

    def test_missing_file_is_none(self, tmp_path):
        assert fingerprint(tmp_path / "nope.json") is None

    def test_change_detected(self, tmp_path):
        f = tmp_path / "a.json"
        _touch(f)
        fp1 = fingerprint(f)
        time.sleep(0.02)  # ensure mtime_ns moves on coarse filesystems
        _touch(f, '{"x": 2}')
        fp2 = fingerprint(f)
        assert fp1 != fp2


class TestCollectPaths:
    def test_canonical_first_then_agents(self, monkeypatch, tmp_path):
        import mcptoon.watch as w

        monkeypatch.setattr(
            w, "detect_installed_agents",
            lambda: [
                {"id": "cursor", "config_path": str(tmp_path / "cursor.json")},
                {"id": "codex", "config_path": str(tmp_path / "AGENTS.md")},
            ],
        )
        cfg = tmp_path / "config.json"
        paths = collect_watch_paths(config_path=cfg)
        assert paths[0] == cfg
        # codex excluded, cursor included, no duplicates
        assert sum(1 for p in paths if "AGENTS" in str(p)) == 0
        assert any("cursor" in str(p) for p in paths)


class TestWatchLoop:
    def test_initial_baseline_no_sync_call(self, tmp_path):
        cfg = tmp_path / "config.json"
        _touch(cfg)
        calls = []
        code = watch(paths=[cfg], max_cycles=1, sync_fn=lambda: calls.append(1) or [],
                     interval=0.01)
        assert code == 0
        assert calls == []

    def test_canonical_change_triggers_sync(self, tmp_path):
        cfg = tmp_path / "config.json"
        _touch(cfg)
        calls = []
        out = []

        def mutate_after_baseline():
            time.sleep(0.05)
            _touch(cfg, '{"servers": {"fetch": {}}}')

        t = threading.Thread(target=mutate_after_baseline)
        t.start()
        code = watch(paths=[cfg], max_cycles=8, interval=0.01,
                     sync_fn=lambda: calls.append(1) or _ok_results(),
                     _out=out.append)
        t.join()
        assert code == 0
        assert len(calls) >= 1
        joined = "\n".join(out)
        assert "synced:" in joined

    def test_quiet_suppresses_info_but_not_errors(self, tmp_path):
        cfg = tmp_path / "config.json"
        _touch(cfg)

        def bad_results():
            return [{"agent": "cursor", "path": "x", "servers_synced": 0,
                     "written": False, "error": "Write failed"}]

        out = []

        def mutate():
            time.sleep(0.05)
            _touch(cfg, "{}")

        t = threading.Thread(target=mutate)
        t.start()
        watch(paths=[cfg], max_cycles=8, interval=0.01, quiet=True,
              sync_fn=bad_results, _out=out.append)
        t.join()
        joined = "\n".join(out)
        assert "synced:" not in joined
        assert "error" in joined.lower()

    def test_merge_mode_resyncs_on_agent_drift(self, tmp_path):
        cfg = tmp_path / "config.json"
        agent = tmp_path / "cursor.json"
        _touch(cfg)
        _touch(agent)
        calls = []
        out = []

        def drift():
            time.sleep(0.05)
            _touch(agent, '{"mcpServers": {}}')

        t = threading.Thread(target=drift)
        t.start()
        watch(paths=[cfg, agent], max_cycles=8, interval=0.01, mode="merge",
              sync_fn=lambda: calls.append(1) or _ok_results(), _out=out.append)
        t.join()
        assert len(calls) >= 1
        assert any("after drift" in line for line in out)

    def test_strict_mode_warns_without_syncing(self, tmp_path):
        cfg = tmp_path / "config.json"
        agent = tmp_path / "cursor.json"
        _touch(cfg)
        _touch(agent)
        calls = []
        out = []

        def drift():
            time.sleep(0.05)
            _touch(agent, '{"mcpServers": {}}')

        t = threading.Thread(target=drift)
        t.start()
        watch(paths=[cfg, agent], max_cycles=8, interval=0.01, mode="strict",
              sync_fn=lambda: calls.append(1) or _ok_results(), _out=out.append)
        t.join()
        assert calls == []
        assert any("strict" in line for line in out)

    def test_new_file_appearing_is_picked_up(self, tmp_path):
        cfg = tmp_path / "config.json"
        late = tmp_path / "late.json"
        _touch(cfg)
        calls = []
        out = []

        def appear():
            time.sleep(0.05)
            _touch(late)

        t = threading.Thread(target=appear)
        t.start()
        watch(paths=[cfg, late], max_cycles=10, interval=0.01,
              sync_fn=lambda: calls.append(1) or _ok_results(), _out=out.append)
        t.join()
        assert len(calls) >= 1  # None -> fingerprint counts as change

    def test_consecutive_failures_abort_with_exit_1(self, tmp_path, monkeypatch):
        """Each change-triggered failed sync counts; 5 in a row aborts."""
        import mcptoon.watch as w
        monkeypatch.setattr(w, "DEBOUNCE", 0.0)  # speed up: no real debounce wait

        cfg = tmp_path / "config.json"
        _touch(cfg)

        def bad():
            return [{"agent": "c", "path": "x", "servers_synced": 0,
                     "written": False, "error": "boom"}]

        def churn():
            for k in range(10):
                time.sleep(0.03)
                _touch(cfg, '{"v": ' + str(k) + '}')

        out = []
        t = threading.Thread(target=churn)
        t.start()
        code = watch(paths=[cfg], max_cycles=80, interval=0.005,
                     sync_fn=bad, _out=out.append)
        t.join()
        assert code == 1
        assert any("giving up" in line for line in out)

    def test_keyboard_interrupt_returns_zero(self, tmp_path):
        cfg = tmp_path / "config.json"
        _touch(cfg)
        calls = []

        def raising_sleep(_s):
            raise KeyboardInterrupt

        code = watch(paths=[cfg], max_cycles=None, interval=0.01,
                     sync_fn=lambda: calls.append(1) or [],
                     _sleep=raising_sleep, _out=lambda *_: None)
        assert code == 0

    def test_max_cycles_bounds_loop(self, tmp_path):
        cfg = tmp_path / "config.json"
        _touch(cfg)
        start = time.monotonic()
        watch(paths=[cfg], max_cycles=3, interval=0.01,
              sync_fn=list, _out=lambda *_: None)
        assert time.monotonic() - start < 2.0

    def test_bad_mode_raises(self, tmp_path):
        cfg = tmp_path / "config.json"
        _touch(cfg)
        with pytest.raises(ValueError):
            watch(paths=[cfg], max_cycles=1, mode="bogus",
                  _out=lambda *_: None)

    def test_debounce_absorbs_burst_saves(self, tmp_path):
        """Two rapid saves inside the debounce window yield ONE sync call."""
        cfg = tmp_path / "config.json"
        _touch(cfg)
        calls = []
        out = []

        def burst():
            time.sleep(0.03)
            _touch(cfg, '{"v": 1}')
            time.sleep(0.005)
            _touch(cfg, '{"v": 2}')

        t = threading.Thread(target=burst)
        t.start()
        time.sleep(0.001)
        watch(paths=[cfg], max_cycles=12, interval=0.01,
              sync_fn=lambda: calls.append(1) or _ok_results(),
              _out=out.append)
        t.join()
        assert len(calls) == 1


class TestDefaults:
    def test_default_interval_sane(self):
        assert 0.5 <= DEFAULT_INTERVAL <= 5.0

    def test_debounce_small(self):
        assert DEBOUNCE <= 1.0

    def test_failure_threshold_documented(self):
        assert MAX_CONSECUTIVE_FAILURES == 5


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
