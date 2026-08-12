# Changelog

All notable changes to mcptoon will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- `manifest --slim` support in manifest command
- Error messages with `--fix` suggestions
- TOML config file support (`~/.mcptoon/config.toml`)
- Integration guides for Claude Code, Cursor, OpenCode
- stdio MCP server auto-discovery (scan `node_modules/.bin/` for `mcp-*` packages)
- `mcptoon serve` — expose mcptoon itself as an MCP server
- `--watch` mode for long-running tool calls
- Connection pool reuse (keep stdio processes alive across calls)

## [0.2.3] — 2025-08-12

### Added
- **Credential leak detection** — Scans tool results for 12 credential patterns (AWS Access Keys, AWS Secret Keys, GitHub PATs, GitHub Fine-grained PATs, OpenAI API Keys, Anthropic API Keys, Slack Tokens, Google API Keys, Private Key Blocks, Generic Credentials, Bearer Tokens, JWT Tokens). Blocks results before they reach agent context. Credentials are masked in error messages (`sk-abc...wxyz`).
  ```bash
  $ mcptoon call github get_file --toon
  # Error: CREDENTIAL_LEAK — potential OpenAI API Key leak detected: sk-abc...wxyz
  ```
- **23 security-audited MCP server profiles** — Each profile now includes a `security` block declaring `credential_safe`, `env_vars_required` (with sensitivity levels), and `permissions` (read/write scope). 3 new profiles added: `aws`, `cloudflare`, `tmux`.
- **Benchmark data with SVG chart** — Measured benchmark across 255 tools / 23 servers. 99.87% token reduction on tool discovery. SVG chart and interactive HTML page in `assets/`.
- **Third-party research citations** — README now references Anthropic, OpenAI, Cursor, Latent Space, and Simon Willison sources validating the token waste problem.
- **46 credential leak detection tests** — Full coverage of all 12 patterns, masking behavior, false positive edge cases. Total tests: 187.

### Changed
- Bumped version to 0.2.3
- `call_tool()` in `router.py` now scans results for credential leaks in both custom handler and MCP protocol paths
- `pyproject.toml` description updated to reflect credential leak detection feature
- README test count updated from 160 to 187
- README line count updated to ~2,500

### Security
- Credential leak detection prevents API keys, tokens, and private keys from entering agent context via MCP tool results

## [0.2.2] — 2025-08-11

### Added
- **`--slim` output format** — Ultra-compact tool manifest encoding (`tool_name|param:type*`). 93% token savings vs JSON for full tool schemas. Types: `s`=string, `n`=number, `b`=boolean, `a[type]`=array, `o{keys}`=object. `*` marks required params.
  ```bash
  mcptoon manifest --slim
  # → search|q:s*|n:n
  # → fetch|url:s*
  ```
- **20 unit tests for `slim_toon()`** — Full coverage of all type encodings, required markers, union types, array item types, nested objects. Total tests: 160.
- **README documentation** — `--slim` added to output format table, SLIM mode section with usage examples
- **CLI help text** — `--slim` flag documented in both docstring and `_print_help()`

### Changed
- Bumped version to 0.2.2
- `render()` function now supports `fmt="slim"` in addition to `json`/`toon`/`compact`/`raw`
- Test count updated from 98 to 160

## [0.2.1] — 2025-08-11

### Added
- **`completion` command** — Generate shell auto-completion scripts for bash, zsh, fish, and PowerShell. Auto-completes subcommands, server names (from config), and `--format` values.
  ```bash
  mcptoon completion bash >> ~/.bashrc
  mcptoon completion zsh >> ~/.zshrc
  mcptoon completion fish > ~/.config/fish/completions/mcptoon.fish
  mcptoon completion powershell | Out-File -Append $PROFILE
  ```

## [0.2.0] — 2025-08-11

### Added — Battle-tested features from production use

- **`--stdin` flag** — Read JSON arguments from stdin, bypassing OS command-line length limits (32,767 chars on Windows, ARG_MAX on Unix). Essential for large payloads like page content, code files, or multi-document operations.
  ```bash
  echo '{"content":"...30KB+..."}' | mcptoon call server tool --stdin --toon
  ```
- **`doctor` command** — Self-diagnose: checks Python version, config file, cache directory, server connectivity, and environment. One command to verify your entire mcptoon setup.
  ```bash
  mcptoon doctor
  ```
- **`discover` command** — Server discovery with health check. Lists all configured servers with their transport type, tool count, and connectivity status.
  ```bash
  mcptoon discover
  mcptoon discover exa    # filter by name
  ```
- **`--format` export** — Export tool manifest in agent-specific formats for cross-agent compatibility:
  - `--format openai` → OpenAI function calling definitions
  - `--format openapi` → OpenAPI 3.0 specification
  - `--format mcp` → MCP `tools/list` format
  - `--format json` → Raw JSON
  - `--format human` → Human-readable
  ```bash
  mcptoon manifest --format openai > functions.json
  mcptoon manifest --format openapi > openapi-spec.json
  ```
- **Tool poisoning guard** — Detects prompt injection patterns in MCP tool results (e.g., "ignore previous instructions", hidden `<!-- assistant:` directives, `[INST]` tags). Returns `TOOL_POISONING` error instead of passing injection to the agent. Can be bypassed with `skip_poisoning_check=True` for trusted sources.
- **Fuzzy match "Did you mean?"** — When a tool name is not found, suggests similar tool names using Levenshtein distance. Both in `inspect` and `call` commands.
  ```
  $ mcptoon call exa sarch '{"query":"AI"}'
  Error [METHOD_NOT_FOUND]: Unknown tool: sarch
  Did you mean: search, search_all
  ```
- **`inspect` server-level listing** — `mcptoon inspect <server>` (without tool name) now lists all tools for that server.
- **Enhanced error envelope** — All errors now include `server` and `tool` context fields for better debugging.

### Changed
- Bumped version to 0.2.0
- `--format` flag takes priority over `--toon`/`--json`/`--compact` when specified
- Natural language fallback now recognizes `discover`, `doctor`, `诊断`, `检查` keywords

### Real-world motivation

These features were battle-tested in production with 255+ MCP tools across 23+ servers. Key lessons:
- **`--stdin`**: Real MCP calls with document content or code snippets regularly exceed OS command-line limits. This is the #1 issue users hit.
- **Tool poisoning**: MCP servers return arbitrary content. Without a guard, a malicious or compromised server can inject instructions into the agent's context.
- **`doctor`**: When something doesn't work, users need a single command to check everything — not 5 different commands.
- **Fuzzy match**: Tool names from different MCP servers follow no naming convention. `search` vs `search_all` vs `web_search` — the agent needs help.
- **Export formats**: Users want to use mcptoon with non-CLI agents (OpenAI function calling, OpenAPI-based tools). Export makes this trivial.

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
