---
name: triage
description: Diagnose and fix broken MCP servers in mcptoon — doctor, health, per-server probes, and the common failure playbook.
---

# Triage MCP server failures with mcptoon

Work top-down; stop as soon as the layer with the fault is found.

## 1. Read the config layer first

```bash
mcptoon doctor
```

Catches: invalid JSON, unknown fields, missing binaries for stdio commands,
malformed URLs. Fix anything reported before deeper probing.

## 2. Check connectivity

```bash
mcptoon health            # every server, human-readable
mcptoon health --json     # CI/CD friendly, exit 1 if any dead
```

## 3. Probe the tool layer

```bash
mcptoon list                       # is the server even registered?
mcptoon manifest --compact         # do its tools appear at all?
mcptoon inspect <server> <tool>    # full schema of one tool
mcptoon call <server> <tool> '{}' --toon   # minimal live call
```

`list` shows it but `manifest` does not → the server answers initialize but
fails tools/list: read the server's own logs (run its command manually).

## Common failures → fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| doctor: binary not found | command not on PATH | fix PATH, or install the package, or use npx/uvx |
| health: timeout | server hangs on startup | raise timeout, or fix slow startup; try running the command directly |
| call: unknown tool | tool toggled off | check the toggle on that tool in config, then `mcptoon sync` |
| call: schema error | wrong args shape | `mcptoon inspect` the tool and match the inputSchema exactly |
| stdio: spawn ENOENT | bad command token | command must be one token on PATH or `./relative`; never a shell string |
| everything dead after edit | config overwritten by hand in agent dir | re-edit `~/.mcptoon/config.json`, run `mcptoon sync` |

## After fixing

```bash
mcptoon sync        # push the repaired config to all agents
mcptoon health      # prove it is green
```
