# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.5.x   | ✅ Active support  |
| < 0.5   | ❌ Not supported   |

## Reporting a Vulnerability

If you discover a security vulnerability in mcptoon:

1. **DO NOT** open a public GitHub issue
2. Use GitHub's private vulnerability reporting: go to the **Security** tab → **Report a vulnerability**
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

You will receive a response within 48 hours. If the vulnerability is confirmed, a fix will be released within 7 days.

## Security Features

mcptoon includes built-in safety mechanisms:

### Dangerous Operation Blocking
Tools matching patterns like `delete`, `remove`, `drop`, `destroy`, `purge`, `wipe`, `kill` are blocked by default. Users must explicitly pass `--destructive` to execute them.

### No Credential Storage
mcptoon does not store API keys or credentials. All credentials are provided via:
- Environment variables
- Config file (`~/.mcptoon/config.json`) — user-managed, never transmitted
- HTTP headers — passed directly to MCP servers, not logged

### No Telemetry
mcptoon does not phone home. Usage tracking is local-only (`~/.cache/mcptoon/usage.json`) and never transmitted anywhere.

### Zero Dependencies
The entire codebase uses only Python standard library. No supply chain risk from third-party packages.

### No Background Processes
mcptoon runs as a one-shot CLI command. It starts, executes, prints output, and exits. No daemon, no background service, no lingering process.

### Network Transparency
The **only** network connections mcptoon makes are to MCP servers **you** configure. mcptoon itself never connects to any external service, API, or endpoint.

### Local Data Files
All data stays on your machine:

| File | Purpose | Location |
|------|---------|----------|
| `~/.mcptoon/config.json` | Server configuration (you create/edit) | User home dir |
| `~/.cache/mcptoon/schema_cache.json` | Tool schema cache (5-min TTL) | Cache dir |
| `~/.cache/mcptoon/usage.json` | Local usage statistics | Cache dir |

You can delete any of these files at any time. mcptoon will recreate them as needed.
