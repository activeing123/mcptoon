"""SessionStart hook for the mcptoon Claude Code plugin.

Goal: make ``mcptoon`` available without the user typing anything.
Fast path  - mcptoon already installed: print a one-line status and exit.
Slow path  - first session only: ``pip install mcptoon`` (zero-dependency,
128KB wheel, no third-party packages pulled in) and report the result.

This script is stdlib-only, prints no secrets, never raises, and always
exits 0 so a broken environment can never break the user's session.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

MARKER = pathlib.Path.home() / ".mcptoon" / ".claude_plugin_setup"


def _emit(message: str) -> None:
    # SessionStart hook stdout (exit 0) is surfaced to the model as context.
    print(f"[mcptoon] {message}")


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _installed() -> str | None:
    proc = _run(["mcptoon", "--version"], 10)
    if proc and proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip().splitlines()[0]
    return None


def main() -> int:
    version = _installed()
    if version:
        _emit(f"CLI ready ({version}). "
              "Use `mcptoon manifest` to compress tool discovery; "
              "`mcptoon call --auto` to invoke tools.")
        return 0

    if MARKER.exists():
        _emit("CLI missing although a previous setup marked it installed. "
              "Run /mcptoon-setup to repair.")
        return 0

    # First session: one-time auto-install (zero-dep wheel, seconds).
    pip = _run(
        [sys.executable, "-m", "pip", "install", "--quiet",
         "--disable-pip-version-check", "mcptoon"],
        55,
    )
    if pip and pip.returncode == 0:
        version = _installed() or "mcptoon"
        try:
            MARKER.parent.mkdir(parents=True, exist_ok=True)
            MARKER.write_text("installed", encoding="utf-8")
        except OSError:
            pass
        _emit(f"CLI installed automatically ({version}). "
              "If the mcptoon MCP server shows as failed, restart the session "
              "so the bridge can start. See the mcptoon skill for usage.")
    else:
        _emit("Auto-install failed (no pip, no Python, or offline). "
              "Run /mcptoon-setup for guided setup.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - hooks must never break a session
        sys.exit(0)
