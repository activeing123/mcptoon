# Changelog

All notable changes to mcptoon will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- PyPI publication
- stdio MCP server auto-discovery (scan `node_modules/.bin/` for `mcp-*` packages)
- `mcptoon serve` — expose mcptoon itself as an MCP server
- Tab completion for bash/zsh/fish/powershell
- `--watch` mode for long-running tool calls

## [0.1.0] — 2025-07-27

### Added
- **TOON output format** — Token-Optimized Object Notation, saves 40-60% tokens vs JSON
- **Dual transport support** — stdio (subprocess JSON-RPC) and HTTP (SSE + session)
- **Universal MCP client** — `MCPClient` class with context manager support
- **Connection pool** — `MCPClientPool` for managing multiple MCP servers
- **CLI interface** — `mcptoon` command with `init`, `list`, `manifest`, `inspect`, `call`, `add`, `remove`, `usage`
- **Server configuration** — `~/.mcptoon/config.json` with project-level override (`.mcptoon.json`)
- **Schema cache** — 5-minute TTL to avoid repeated `list_tools` round-trips
- **Usage tracking** — local-only call statistics per server and tool
- **Safety guard** — blocks dangerous operations (delete, remove, drop, etc.) unless `--destructive` flag is passed
- **Custom handlers** — `@register` decorator to bypass MCP for specific servers
- **Windows compatibility** — automatic `.cmd` resolution for npx/node executables
- **Adaptive format** — `MCPTOON_AGENT_TYPE` env var auto-selects output format per agent type
- **Output truncation** — `--max-chars N` and `--full` flags for output length control
- **98 unit tests** — full coverage of output encoding, client parsing, router, and config
- **Zero dependencies** — pure Python 3.10+ standard library
- Apache 2.0 license with NOTICE file for attribution protection

### Known Limitations
- HTTP transport does not support streaming responses (only first SSE event is processed)
- No reconnection logic for dropped stdio connections
- Schema cache is not invalidated when server config changes
