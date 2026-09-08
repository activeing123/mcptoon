---
description: Set up or repair the mcptoon CLI for this machine (install, verify, diagnose)
---

# mcptoon setup

Help the user set up mcptoon by executing these steps yourself (do not ask
the user to run commands) and reporting the real outputs:

1. Check Python: `python --version` (needs >= 3.10). If missing, tell the
   user to install Python from python.org and stop there.
2. Install/upgrade: `python -m pip install --upgrade mcptoon`. It is a
   zero-dependency 128KB wheel — if it pulls in third-party packages,
   something is wrong; report it.
3. Verify: `mcptoon --version`, then `mcptoon doctor` for config and
   connectivity status. Paste a short summary of the doctor output.
4. Show the win: run `mcptoon manifest --compact --tokens` and report the
   tool count and token figure it prints for the user's own configuration.
5. Explain the bridge: the plugin's `.mcp.json` starts `mcptoon serve` for
   Claude Code automatically. If the MCP server list shows mcptoon as
   failed right after the very first install, restart the session once so
   the newly installed CLI is on PATH.

If anything fails, show the exact error and suggest the next step — never
leave the user with a bare traceback.
