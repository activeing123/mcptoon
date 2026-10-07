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
