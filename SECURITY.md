# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | ✅ Active support  |

## Reporting a Vulnerability

If you discover a security vulnerability in mcptoon:

1. **DO NOT** open a public GitHub issue
2. Email: security@yourdomain.com (replace with your email)
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
