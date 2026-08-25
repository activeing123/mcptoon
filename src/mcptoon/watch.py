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
mcptoon sync --watch — continuous sync, zero-dependency polling.

Keeps every detected agent's MCP config aligned with mcptoon's canonical
config (~/.mcptoon/config.json). Uses plain os.stat fingerprinting instead
of OS event APIs so it stays pure-stdlib on Windows, macOS and Linux.

Behavior:
  - canonical config changes  -> re-sync to all installed agents
  - an agent config changes   -> merge mode (default): re-sync, manual
                                 servers preserved by the merge logic
                                 strict mode: warn, never overwrite
  - new agent config appears  -> picked up automatically

Usage:
    from mcptoon.watch import watch
    exit_code = watch(interval=2.0, mode="merge")

CLI:
    mcptoon sync --watch
    mcptoon sync --watch --interval 5 --quiet --watch-mode strict
"""
import sys
import time
from pathlib import Path

from .config import CONFIG_DIR
from .sync import sync_to_all, detect_installed_agents

DEFAULT_INTERVAL = 2.0
DEBOUNCE = 0.3
MAX_CONSECUTIVE_FAILURES = 5


def fingerprint(path: Path):
    """Return (mtime_ns, size) for a file, or None if unreadable/missing."""
    try:
        st = path.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def collect_watch_paths(config_path=None) -> list[Path]:
    """Paths to watch: canonical config + every agent's native config.

    Codex (AGENTS.md append-once) is intentionally excluded: its writer
    self-stabilizes and there is nothing meaningful to re-sync.
    """
    paths = [Path(config_path) if config_path else CONFIG_DIR / "config.json"]
    seen = {str(paths[0])}
    for agent in detect_installed_agents():
        if agent.get("id") == "codex":
            continue
        p = Path(agent["config_path"])
        if str(p) not in seen:
            paths.append(p)
            seen.add(str(p))
    return paths


def _ts():
    return time.strftime("%H:%M:%S")


def watch(interval: float = DEFAULT_INTERVAL,
          mode: str = "merge",
          quiet: bool = False,
          config_path=None,
          paths: list | None = None,
          max_cycles: int | None = None,
          sync_fn=None,
          _sleep=time.sleep,
          _out=print) -> int:
    """Poll watched paths; re-sync on any change.

    Args:
        interval: seconds between polls.
        mode: "merge" (re-sync on drift, manual servers preserved) or
              "strict" (warn on external agent-config edits, don't touch).
        quiet: only print warnings/errors, not routine sync lines.
        config_path: override path of the canonical config (for tests).
        paths: override the full watch list (for tests).
        max_cycles: stop after N polls (for tests); None = forever.
        sync_fn: replacement for sync_to_all (for tests).
        _sleep: injectable sleep (tests avoid real waiting).
        _out: injectable print.

    Returns process exit code: 0 normal, 1 after repeated write failures.
    """
    if mode not in ("merge", "strict"):
        raise ValueError(f"unknown watch mode: {mode!r} (use 'merge' or 'strict')")
    if sync_fn is None:
        sync_fn = sync_to_all

    watch_paths = list(paths) if paths is not None else collect_watch_paths(config_path)
    canonical = Path(config_path) if config_path else (
        watch_paths[0] if watch_paths else CONFIG_DIR / "config.json")

    def say(msg):
        if not quiet:
            _out(msg)

    def warn(msg):
        # Warnings and errors always surface, even with --quiet.
        _out(msg)

    say(f"mcptoon sync --watch: watching {len(watch_paths)} file(s), "
        f"interval {interval:g}s, mode {mode}. Ctrl+C to stop.")

    last: dict = {}
    failures = 0
    cycle = 0

    try:
        while max_cycles is None or cycle < max_cycles:
            current = {p: fingerprint(p) for p in watch_paths}
            changed = [p for p, fp in current.items() if fp != last.get(p)]
            # Snapshot-diff-update: record state FIRST, then act on the diff.
            # (Keeps the baseline cycle from re-reporting every file forever.)
            last = current

            if cycle == 0:
                # Baseline pass: record state, take no action. The user is
                # expected to have run plain `mcptoon sync` beforehand.
                say(f"baseline: {sum(1 for fp in current.values() if fp)} "
                    f"file(s) present")
            elif changed:
                canonical_changed = any(str(p) == str(canonical) for p in changed)
                agent_drift = [p for p in changed
                               if str(p) != str(canonical)]

                if canonical_changed:
                    # Debounce: editors save in bursts; wait once, then take a
                    # fresh snapshot so we act on the settled state.
                    _sleep(DEBOUNCE)
                    current = {p: fingerprint(p) for p in watch_paths}
                    last = current  # absorb burst saves into the baseline
                    results = sync_to_all() if sync_fn is sync_to_all else sync_fn()
                    errs = sum(1 for r in results if r.get("error"))
                    written = sum(1 for r in results if r.get("written"))
                    servers = sum(r.get("servers_synced", 0) for r in results)
                    if errs:
                        failures += 1
                        warn(f"[{_ts()}] sync finished with {errs} error(s) "
                             f"({failures}/{MAX_CONSECUTIVE_FAILURES} toward abort)")
                        for r in results:
                            if r.get("error"):
                                warn(f"[{_ts()}]   ! {r.get('agent')}: "
                                     f"{r.get('error')}")
                    else:
                        failures = 0
                        say(f"[{_ts()}] synced: {written} agent(s) updated, "
                            f"{servers} server entr{'y' if servers == 1 else 'ies'}")
                elif agent_drift:
                    if mode == "strict":
                        for p in agent_drift:
                            warn(f"[{_ts()}] drift detected (strict): {p} was "
                                 f"modified outside mcptoon - leaving it alone")
                    else:
                        results = sync_to_all() if sync_fn is sync_to_all else sync_fn()
                        errs = sum(1 for r in results if r.get("error"))
                        if errs:
                            failures += 1
                            warn(f"[{_ts()}] re-sync after drift: {errs} error(s)")
                        else:
                            failures = 0
                            say(f"[{_ts()}] re-synced after drift "
                                f"(manual servers preserved)")

            # Unchanged steady state: fall through to sleep.

            if failures >= MAX_CONSECUTIVE_FAILURES:
                warn(f"[{_ts()}] giving up after {failures} consecutive failed "
                     f"sync rounds")
                return 1

            _sleep(interval)
            cycle += 1
    except KeyboardInterrupt:
        say("stopped.")
        return 0

    return 0


def main(argv=None) -> int:
    """Entry point for `mcptoon sync --watch ...` flag block."""
    argv = list(sys.argv[1:] if argv is None else argv)
    interval = DEFAULT_INTERVAL
    mode = "merge"
    quiet = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--interval" and i + 1 < len(argv):
            try:
                interval = float(argv[i + 1])
            except ValueError:
                pass
            i += 2
            continue
        if a.startswith("--interval="):
            try:
                interval = float(a.split("=", 1)[1])
            except ValueError:
                pass
            i += 1
            continue
        if a.startswith("--watch-mode"):
            if "=" in a:
                mode = a.split("=", 1)[1]
            elif i + 1 < len(argv):
                mode = argv[i + 1]
                i += 1
            i += 1
            continue
        if a == "--quiet":
            quiet = True
        i += 1
    return watch(interval=interval, mode=mode, quiet=quiet)


if __name__ == "__main__":
    sys.exit(main())
