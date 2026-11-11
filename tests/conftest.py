"""Redirect every user-path root the CLI reads, for the whole test session.

Why this file exists: the suite must not touch the developer's machine. mcptoon
resolves its user paths from ``Path.home()`` **at import time** (``config.HOME_DIR``
→ ``CONFIG_DIR``/``CACHE_DIR``) and from ``%APPDATA%`` at call time
(``discover._appdata()``). A test that records a usage entry or registers a server
therefore writes the developer's real ``~/.mcptoon/config.json`` and
``~/.cache/mcptoon/usage.json`` unless those roots are moved first — found on
2026-09-29 when a run of ``test_serve_perf``/``test_envelope`` grew the real
``usage.json`` by 171 bytes.

Set at **session** scope, before any test module imports ``mcptoon``, so the
import-time constants are computed against the temp home. Tests that redirect
these themselves (``test_cli_smoke``, ``test_uninstall_end_to_end``,
``test_skill_package``, ``test_v072_delight``, …) still work: they overwrite the
values with their own temp dir, which is finer-grained than this one.

``MCPTOON_CACHE_DIR`` would not be enough here: ``usage._USAGE_FILE`` is bound to
``config.CACHE_DIR`` (the import-time constant), not to ``_cache_dir()``, so only
moving HOME actually moves it.
"""
import os
import tempfile
from pathlib import Path

_home = Path(tempfile.mkdtemp(prefix="mcptoon-pytest-home-"))
os.environ["HOME"] = str(_home)
os.environ["USERPROFILE"] = str(_home)                       # Windows Path.home()
os.environ["APPDATA"] = str(_home / "AppData" / "Roaming")   # discover._appdata()
os.environ["LOCALAPPDATA"] = str(_home / "AppData" / "Local")
os.environ["XDG_CONFIG_HOME"] = str(_home / ".config")

# `MCPTOON_HOME` pins the layout for the whole suite (issue #25).
#
# Before XDG support landed, `config.CONFIG_DIR` was always `$HOME/.mcptoon`, so
# setting HOME was enough to isolate the suite. Now that `XDG_CONFIG_HOME` is
# honoured, the line above would silently move every path to `$HOME/.config/…`
# and shift the expectations of ~1900 tests at once — a green-to-red avalanche
# with no behaviour change behind it. An explicit root keeps the layout the
# tests were written against; tests that want XDG behaviour set their own
# environment (see tests/test_xdg.py).
os.environ["MCPTOON_HOME"] = str(_home / ".mcptoon")

# `DSH_HOME` is the second root that does not follow `HOME`.
#
# DSH is relocatable through this variable, and `sync._dsh_agents_path` reads it to
# decide where DSH's pointer belongs — so a pointer write follows the *real* DSH home
# even with `HOME` moved. Measured 2026-11-11: adding the DSH row to `_AGENT_SPECS`
# and running the suite appended the skill-pointer block to the live
# `$DSH_HOME/AGENTS.md` (1628 → 2368 bytes, i.e. the developer's own agent
# instructions). Pointing it at a temp path — one that deliberately does not exist,
# so DSH reads as "not installed" — makes a test that writes "for every host" write
# nothing outside the temp tree. A test that wants a present DSH sets its own value.
os.environ["DSH_HOME"] = str(_home / ".dsh")

# Which agent launched pytest must not decide what the suite asserts.
#
# `footer.caller_can_shell` and `mode.detect_host` read the *calling* agent's env
# markers, so a developer running pytest from inside DSH (or Claude Code, or a
# Cursor terminal) would hand the suite a different reader than CI does — the same
# class of leak as `DSH_HOME` above, one layer up. Cleared here, "unknown caller" is
# the deterministic default; a test that wants a shell reader patches
# `footer.caller_can_shell` or sets the marker itself.
for _marker in ("DSH_SHELL", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CODEX_HOME",
                "CURSOR_TRACE_ID", "TERM_PROGRAM"):
    os.environ.pop(_marker, None)
