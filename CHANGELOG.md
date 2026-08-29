# Changelog

All notable changes to mcptoon will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.1] — 2026-08-27

### Added — Latest MCP spec compatibility (2025-06-18)

- **`structuredContent` native parsing**: when a new-spec server returns
  structured output, `call_tool()` now prefers it over text content
  automatically — no flags needed. Old-spec servers behave exactly as before.
- **`mcptoon call <server> <tool> --envelope`**: new flag returning the
  complete MCP `tools/call` result envelope as JSON — `structuredContent`,
  `_meta`, `resultType`, `isError`, `content` all intact. Works with
  `--auto` routing too.
- **Library API**: `MCPClient.call_tool_full()` and `MCPClientPool.call_full()`
  for envelope-level access from Python.
- 8 new tests (548 total). README (EN + zh-CN) documents the compatibility
  matrix with a prominent spec badge.

## [0.6.0] — 2026-08-26

### Added — Usage dashboard & per-tool toggle

- **`mcptoon stats`**: token-savings dashboard with per-server/per-tool breakdowns.
- **`mcptoon toggle <server> <tool>`**: flip a single tool on/off without touching
  the server config; `toggle --list` shows what is disabled. Tool-level control
  no competitor offers at the CLI layer.
- `TOGGLE_FILE` (`~/.mcptoon/toggles.json`) with safe-load defaults.

## [0.5.6] — 2026-08-26

### Changed — Error envelope & usage-tracking hardening

- **Richer error envelope**: `make_error()` now records which component
  raised the error (`component`, legacy `source=` accepted as alias) and
  groups extra keyword context under `_error.detail` instead of spreading
  it at the top level of the result dict.
- **New helpers**: `error_code(obj)` / `error_message(obj)` for reading
  the envelope without touching its internals (`error_message` aliases
  `get_error_message`).
- **Concurrent-safe usage tracking**: `track_call()` is now guarded by a
  thread lock and writes atomically (unique tmp file + `os.replace`), so
  concurrent agent processes can never corrupt `usage.json`; tracking
  failures are swallowed so they never break a live tool call.

## [0.5.5] — 2026-08-25

### Added — Continuous sync (`mcptoon sync --watch`)

- **`--watch` flag**: `mcptoon sync --watch` keeps every detected agent's MCP
  config aligned with `~/.mcptoon/config.json`. Pure-stdlib polling
  (os.stat fingerprinting) — no watchdog dependency, identical behavior on
  Windows, macOS and Linux.
- **Drift detection**: external edits to agent config files are detected.
  Merge mode (default) re-syncs while preserving manually-added servers;
  `--watch-mode strict` warns instead of touching the file.
- **Debounced writes**: burst saves from editors collapse into one sync round.
- **Failure guard**: aborts with exit code 1 after 5 consecutive failed rounds.
- **Flags**: `--interval N`, `--quiet`, `--watch-mode merge|strict`.
- 18 new tests (total 531).
- New docs page: `docs/comparison.md` — setup, token and safety numbers for
  every approach to cross-agent MCP management, category by category.
- README rewritten in English and Chinese: zero-setup positioning,
  tiktoken-verified benchmarks, illustrated how-it-works diagram.
- PyPI/repo description aligned to the measured 99.8% figure (was 99.9%).

## [0.5.4] — 2026-08-24

### Added

- **`sync` command**: write mcptoon's unified config to each detected agent's
  native format (Claude Desktop, Cursor, Cline, Windsurf, VS Code Copilot,
  Codex), merging without clobbering manual entries.
- **`health` command**: check all configured servers with per-server timeout;
  JSON output plus non-zero exit code for CI/CD pipelines.
- Shell completion fixes.

## [0.5.3] — 2026-08-22

### Fixed — PyPI publish workflow

- **PyPI API Token BOM fix**: GitHub Secret `PYPI_API_TOKEN` was corrupted with a BOM character (`\ufeff`) causing `UnicodeEncodeError: 'latin-1' codec can't encode character` during publish. Token re-imported from Bitwarden without BOM.
- **Version sync**: `pyproject.toml` and `__init__.py` both updated to 0.5.3.
- Removed stale `# -*- coding: utf-8 -*-` from source files (Python 3 default).
- Trailing whitespace cleanup in `output.py`.

## [0.5.2] — 2026-08-20

### Fixed — README and PyPI metadata corrections

- **Test count corrected**: README badge and text updated from 427 → 486 (tests added in v0.5.1 but count not updated)
- **Benchmark reference fixed**: Removed reference to non-existent `_benchmark.py` script
- **PyPI metadata fixed**:
  - `pyproject.toml` description updated to match GitHub description (99.87% token savings, not outdated 97%)
  - `[project.urls]` added with Homepage, Repository, Documentation, Changelog, Issues, PyPI links (was missing entirely)
  - TOML structure fixed: `requires-python`, `keywords`, `classifiers`, `dependencies` were incorrectly placed under `[project.urls]` section
- **GitHub repo description updated**: From "97% less tokens" to "99.87% less tokens on tool discovery"

## [0.5.1] — 2026-08-19

### Added — serve HTTP mode + demo command + 20 critical bug fixes

- **`mcptoon serve --listen` HTTP mode** — mcptoon serve now supports HTTP mode for remote/multi-agent access. Agents can connect via HTTP POST to `/mcp` endpoint. Health check at `/health`.
  ```bash
  mcptoon serve --listen :8080          # HTTP mode on port 8080
  mcptoon serve --http                   # Shorthand for --listen :8080
  mcptoon serve --listen 0.0.0.0:9090   # Bind to all interfaces
  ```
  - Multiple agents can connect simultaneously (unlike stdio which is single-connection)
  - JSON-RPC over HTTP, compatible with MCP HTTP transport
  - Health check: `GET /health` returns `{"status":"ok","servers":N,"tools":N}`

- **`mcptoon demo` command** — Zero-config one-command demo for the "aha moment":
  1. Starts a demo MCP server (fetch, no API key needed)
  2. Calls a tool and shows JSON vs TOON vs SLIM token comparison
  3. Shows the 255 tools benchmark (90,804 → 117 tokens)
  ```bash
  mcptoon demo                # Full demo, step by step
  mcptoon demo --quick        # Fast: skip step-by-step
  mcptoon demo --keep         # Keep demo server in config
  ```

- **Parallel manifest loading** — `MCPServerBridge` now uses `ThreadPoolExecutor` with 20 concurrent workers for manifest loading. 100 servers load in ~5s instead of 500s serial.
- **Per-call timeout** — Each tool call has a 30s timeout (configurable via `MCPTOON_CALL_TIMEOUT`), preventing hung servers from blocking the bridge.
- **Remote MCP support** — HTTP/SSE MCP servers are now handled transparently by the bridge.
- **18 new tests** for demo command — Total: 425 tests.

### Changed
- **Removed all 23 bundled server profiles** — mcptoon now ships zero bundled content. Users add exactly the servers they want via `mcptoon add` / `mcptoon install`. The `mcp/` directory and `_match_profiles()` discovery layer have been removed. This eliminates cognitive overhead: nothing pre-configured, nothing to ignore, nothing to explain.
- Discovery reduced from 5-layer to 4-layer (removed profile matching layer).
- Architecture simplified from 3-layer to 2-layer (CLI + actual MCP servers).
- `MCPClientPool._get_client` refactored to move `client.initialize()` outside the lock, allowing parallel server initializations.

### Fixed — 20 critical bug fixes

- **`installer.py` TypeError** — Removed invalid `name=` argument passed to `MCPClient()` constructor (2 call sites).
- **Version mismatch** — `pyproject.toml` was stuck at `0.2.3` while `__init__.py` had `0.5.0`. Synced to `0.5.0`.
- **HTTP serve stdout race condition** — Replaced global `sys.stdout` swap with thread-local `_response_capture` buffer. Concurrent HTTP requests no longer clobber each other's responses.
- **Streamable HTTP support** — `_parse_http_body()` now handles multi-event SSE streams (picks last response with `result`/`error`). `_http_request()` checks `Content-Type` header and handles both `text/event-stream` and `application/json`.
- **HTTP error handling** — `HTTPError` responses now parsed as JSON error objects before raising, allowing structured error propagation.
- **`resources/read` and `prompts/get`** — Bridge now responds to these MCP methods (previously returned `method not found`).
- **`logging/setLevel`** — Bridge acknowledges client logging level changes.
- **JSON-RPC batch support** — HTTP handler now accepts arrays of requests and returns array of responses.
- **`notifications/cancelled`** — Bridge now handles cancellation notifications gracefully.
- **HTTP authentication** — Added `--auth <token>` flag and `MCPTOON_AUTH_TOKEN` env var. When set, requests must include `Authorization: Bearer <token>` header.
- **Connection pool resource leak** — When two threads race to create the same client, the losing client is now properly closed (was: silently leaked subprocess).
- **`router.py` pool reuse** — Router now reuses a global `MCPClientPool` instead of creating a new pool (spawning all subprocesses) on every `call_tool()` invocation.
- **Cache file locking** — `cache.py` rewritten with in-process `threading.Lock` + atomic file writes (`os.replace`). Prevents data corruption from concurrent writes.
- **stdio multi-line response** — `_stdio_request()` now reads lines in a loop until it finds a JSON-RPC response with an `id` field, skipping notification lines and debug output. Previously only read one line, breaking on multi-line responses.
- **Auto-reconnect for stdio** — `_reconnect_if_dead()` checks if process has exited before each request and restarts it automatically. Clears tools cache on reconnect.
- **`close()` robustness** — Added `proc.wait(timeout=1)` after `kill()` and `finally: self._proc = None` to ensure cleanup even on exception.
- **Timeout subprocess kill** — When a tool call times out, the underlying subprocess is now killed (was: thread abandoned but subprocess kept running).
- **Demo token counting** — `_show_token_comparison()` now uses `tiktoken` if available for accurate token counts, with `len//4` fallback. Previously used only `len//4`.
- **Health endpoint honesty** — `_handle_health()` now returns `"starting"` when not initialized, `"degraded"` when some servers failed, `"error"` when all failed. Previously always returned `"ok"`.
- **Handler template imports** — Generated handler files now import from `mcptoon.client.MCPClient` instead of non-existent `daemon.py`/`mcp_client.py` modules.
- **Server alias resolution** — `resolve_server_name()` now checks config dynamically for prefix matches (e.g. `fs` → `filesystem`), not just static aliases.
- **`.gitignore`** — Added `local/`, `__pycache__/`, `_*.py`, `_*.txt` to prevent temp files and private layer from being committed.
- **Cleaned 40+ temporary scripts** — Removed `_1000stars.py`, `_benchmark.py`, `_check_shadowban.py`, etc. from project root.
- **`test_v02_features.py` syntax error** — Fixed method name with space (`test_slim_format Renders_tools` → `test_slim_format_renders_tools`).
- **`test_serve.py` health test** — Updated to accept `"starting"` status for uninitialized bridges.

### Planned
- awesome-mcp-clients PR submission
- `--watch` mode for long-running tool calls
- Connection pool reuse (keep stdio processes alive across calls)

## [0.5.0] — 2026-08-17

### Added — Install command + local handler architecture + forwarding layer

- **`mcptoon install` command** — One-command MCP server installation with auto-handler generation. Connects to the server, discovers tools, generates a Python handler, and registers it. No restart needed.
  ```bash
  mcptoon install brave-search --npm @anthropic/mcp-server-brave-search
  mcptoon install my-tool --pip mcp-my-tool
  mcptoon install remote-api --url https://example.com/mcp
  mcptoon install --list
  mcptoon install --remove brave-search
  ```

- **Local handler architecture** — Public core (`src/mcptoon/`) + private layer (`local/`) separation. The `local/` directory contains:
  - `cli_pro.py` — Enhanced CLI entry point with handler injection
  - `handlers/` — 30+ auto-generated handlers for MCP servers
  - `router.py` — Bridge router that checks local handlers before falling back to MCP
  - `daemon.py` — Background daemon for connection pooling
  - `core.py` — Remote execution core for SSH-based MCP calls

- **Forwarding layer** — `universal_call.py` forwards old CLI commands to the new `cli_pro.py` entry point, ensuring zero-disruption migration for existing skills and scripts.

- **`call --auto` now searches local handlers first** — Router prioritizes local handlers before MCP servers, ensuring faster response for registered tools.

- **Daemon fallback** — If daemon fails to start, `call` automatically falls back to single-shot mode for maximum reliability.

- **Skill Direct-Invoke mode** — Skills can directly call CLI commands without loading MCP schemas into context, achieving 0-token MCP usage.

- **ADR documentation** — Architecture Decision Records added in `docs/adr/`:
  - `0001-cli-mode-over-mcp-protocol.md` — Why CLI mode beats MCP protocol injection
  - `0002-public-core-private-layer-separation.md` — Dual-track architecture decision
  - `0003-toon-format-as-primary-output.md` — TOON as the default output format
  - `0004-forwarding-layer-for-backward-compatibility.md` — Forwarding layer for seamless transition

- **E2E test suite** — 10/10 tests passing, covering: echo, gbrain search, gbrain list_pages, servers, doctor, manifest, inspect (×2), call --auto, forwarding layer, install --list.

### Changed
- Bumped version to 0.5.0
- `router.py` now checks local handlers before MCP servers in `call_tool_auto`
- `daemon.py` startup path fixed for Windows, wait time reduced
- `installer.py` moved from `local/` to `src/mcptoon/` (public core)
- `installer.py` adapted to use `MCPClient` from public core

### Fixed
- Daemon startup path error on Windows
- `call --auto` not searching local handlers
- `UNKNOWN_SERVER` errors for gbrain, exa, tinyfish, github
- Double `try/except` nesting in handler bridge
- SSH remote script path for Windows targets

## [0.4.1] — 2026-08-14

### Added — Zero-config discovery + cross-server search + auto-routing + fallback-json + TOML

- **`discover.py` module** — Five-layer auto-discovery of MCP servers, zero dependency:
  1. **Config scanning** — imports from Claude Desktop, Cursor, Cline, Windsurf configs
  2. **Environment detection** — detects `GITHUB_TOKEN`, `BRAVE_API_KEY`, `EXA_API_KEY`, etc.
  3. **Local tool detection** — checks `npx`/`uvx`/`docker`/`sqlite3` in PATH, git repo
  4. **HTTP endpoint detection** — checks `MCP_HTTP_URL` env var for HTTP MCP endpoints
  5. **Profile matching** — matches bundled profiles against satisfied env vars

- **`mcptoon search <query>`** — Cross-server tool search with multi-factor scoring
- **`mcptoon call --auto <tool> [args]`** — Cross-server auto-routing
- **`--fallback-json` flag** — Degradation safety net
- **TOML config support** — `~/.mcptoon/config.toml`
- **`quickstart` command** — One-command onboarding
- **`init --auto` command** — Zero-config setup

### Tests — 97 new tests (309 → 407 total)

### Changed
- Bumped version to 0.4.1
- `discover` command now runs full auto-discovery (was: health check only)
- `init` command now accepts `--auto` flag for zero-config setup

## [0.4.0] — 2026-08-12

### Added
- **Standard TOON adoption** — Implemented `toon_encode()` / `toon_decode()` following the [TOON (Token-Oriented Object Notation)](https://github.com/toon-format/toon) spec. Uses YAML-style indentation for objects and CSV-style tabular layout for uniform arrays. Round-trip safe: `decode(encode(x)) == x`.
  ```python
  from mcptoon.output import toon_encode, toon_decode
  toon_encode({"name": "search", "count": 3})
  # → "name: search\ncount: 3"
  toon_encode([{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])
  # → "[2]{id,name}:\n  1,Alice\n  2,Bob"
  ```
- **TOON decoder** — `toon_decode()` reverses `toon_encode()`. Handles all types: strings (with CSV quoting/escaping), numbers, booleans, null, nested objects, uniform arrays, scalar arrays, mixed arrays.
- **31 cross-validation tests** — `tests/test_toon_cross_validate.py` validates TOON spec conformance: object encoding, scalar values, string escaping, array CSV-style, round-trip safety, token efficiency. Total tests: 293.
- **CLI flag separation** — `--toon` and `--mcptoon` are now properly separated in the CLI arg parsing chain (fixed `if` → `elif` bug).
- **`__main__.py` support** — `python -m mcptoon` now works as an alternative to the `mcptoon` command. Required for some CI/CD environments and Docker containers.
- **Error fix suggestions** — CLI errors now include actionable fix suggestions. 10 error codes covered: `SERVER_NOT_FOUND`, `CONFIG_MISSING`, `TOOL_NOT_FOUND`, `UNKNOWN_TOOL`, `CONNECTION_FAILED`, `TIMEOUT`, `DANGEROUS_OP`, `CREDENTIAL_LEAK`, `TOOL_POISONING`, `PARSE_ERROR`.
  ```bash
  $ mcptoon call nonexistent tool '{}'
  Error [SERVER_NOT_FOUND]: Server not found: nonexistent
    Fix: Try: mcptoon list | mcptoon add <name> --stdio npx -y <package> | mcptoon doctor
  ```
- **16 new tests** — `tests/test_v04_features.py` covers `__main__.py` and error fix suggestions. Total tests: 309.

### Changed
- Bumped version to 0.4.0
- `output.py` now exports `toon_encode` / `toon_decode` as the standard TOON API, alongside legacy `mcptoon_encode` / `mcptoon_decode`
- `pyproject.toml` classifier updated to `Production/Stable`
- Benchmark updated to v4: now compares 5 formats (JSON vs Standard TOON vs mcptoon vs SLIM vs Compact)
- CI lint step updated to use `toon_encode` / `mcptoon_encode` instead of deprecated `toon` alias
- `errors.py` copyright year updated to 2025-2026

### Fixed
- **cli.py flag parsing bug** — `--toon` was parsed with `if` instead of `elif`, causing it to be in a separate if-chain from `--json`/`--compact`. Fixed to `elif`.
- **Legacy mcptoon format data loss** — Strings containing colons, pipes, or newlines were corrupted. Now properly escaped with `\c` (colon), `\p` (pipe), `\\` (backslash), `\n` (newline). Round-trip safe with `mcptoon_decode()`.

### Benchmark Results (v4, 255 tools)

| Tools | JSON | Std TOON | mcptoon | SLIM | Compact |
|-------|------|----------|---------|------|---------|
| 5 | 1,897 | 981 (-48%) | 785 (-59%) | 111 (-94%) | 16 (-99%) |
| 50 | 17,790 | 8,776 (-51%) | 6,981 (-61%) | 1,203 (-93%) | 117 (-99%) |
| 93 | 33,191 | 16,426 (-51%) | 13,086 (-61%) | 2,231 (-93%) | 117 (-100%) |
| 255 | 90,804 | 44,863 (-51%) | 35,735 (-61%) | 6,174 (-93%) | 117 (-100%) |

## [0.3.0] — 2026-08-12

### Fixed
- **TOON scalar substitution honesty** — Removed `∅` (null→∅) and `↲` (newline→↲) substitutions that tiktoken-verified as **worse** than original (2 tokens vs 1). Kept `true`/`false` as-is (1 token either way). Savings now come from structural compression only (removing JSON braces, quotes, brackets). Verified with tiktoken o200k_base + cl100k_base.
- **README benchmark data** — Updated all TOON savings claims with tiktoken-verified numbers. Added tokenizer version notes. Honest about what saves tokens (structure) vs what doesn't (scalar substitution).

### Changed
- `_toon_scalar()`: `null` stays `null` (not `∅`), `true`/`false` stay as-is (not `T`/`F`), newlines kept as-is (not `↲`), colons → `_` (not `＿`)

## [0.2.3] — 2026-08-12

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

## [0.2.2] — 2026-08-11

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

## [0.2.1] — 2026-08-11

### Added
- **`completion` command** — Generate shell auto-completion scripts for bash, zsh, fish, and PowerShell. Auto-completes subcommands, server names (from config), and `--format` values.
  ```bash
  mcptoon completion bash >> ~/.bashrc
  mcptoon completion zsh >> ~/.zshrc
  mcptoon completion fish > ~/.config/fish/completions/mcptoon.fish
  mcptoon completion powershell | Out-File -Append $PROFILE
  ```

## [0.2.0] — 2026-08-11

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
