# Contributing to mcptoon

Thanks for your interest in contributing! This guide will help you get started.

## Quick Start

```bash
# Clone
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon

# Install in development mode
pip install -e . --no-build-isolation

# Install dev dependencies
pip install pytest pytest-cov

# Run tests
python -m pytest tests/ -v

# Run the CLI
mcptoon help
```

## Development Workflow

1. **Fork** the repo and create your branch: `git checkout -b feature/my-feature`
2. **Write tests** for your changes (we aim for 100% coverage on new code)
3. **Run tests**: `python -m pytest tests/ -v`
4. **Commit** with a clear message: `git commit -m "Add support for SSE streaming"`
5. **Push** and open a Pull Request

### Commit Message Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add SSE streaming support for HTTP transport
fix: resolve Windows npx.cmd path issue
docs: add Chinese README
refactor: extract MCPClient from router
test: add edge case tests for TOON encoding
chore: update CI to Python 3.12
```

## Code Style

- **Python 3.10+** — use type hints, f-strings, match/case where appropriate
- **Zero dependencies** — this is a hard rule. If you need a third-party package, it doesn't belong in mcptoon
- **Docstrings** — every public function/class needs a docstring
- **Tests** — every new feature needs tests in `tests/`
- **Line length** — keep under 100 chars where possible

## Project Structure

```
src/mcptoon/
├── cli.py        # CLI entry point — keep thin, delegate to other modules
├── client.py     # MCPClient + MCPClientPool — transport layer
├── installer.py  # One-command MCP server installation + auto-handler
├── router.py     # Tool routing + poisoning/credential leak detection
├── config.py     # Server config management (JSON + TOML)
├── manifest.py   # Tool discovery with cache + cross-server search
├── discover.py   # Zero-config auto-discovery (4-layer)
├── output.py     # TOON / JSON / compact rendering — the magic
├── cache.py      # Schema cache (5-min TTL)
├── usage.py      # Local usage tracking
└── errors.py     # Error envelopes + fix suggestions
```

## Adding a New Output Format

1. Add encoder function in `output.py`
2. Add format name to `render()` function
3. Add CLI flag parsing in `cli.py`
4. Add tests in `tests/test_output.py`
5. Update README with format spec table

## Adding a New Transport

1. Implement `_yourtransport_request()` and `_yourtransport_notify()` in `client.py`
2. Add transport detection in `MCPClient.__init__()` and `MCPClientPool._make_client()`
3. Add config schema support in `config.py`
4. Add tests in `tests/test_client.py`

## Testing a New MCP Server Integration

1. Add the server: `mcptoon add <name> --stdio npx -y <package>`
2. Verify tools: `mcptoon manifest --toon`
3. Call a tool: `mcptoon call <name> <tool> '{"args":"here"}' --toon`
4. Check for credential leaks: `mcptoon call <name> <tool> '{}' --toon` (should be blocked if keys present)
5. Open a PR with an integration note in `docs/integrations/`

## Reporting Bugs

Use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md). Include:
- mcptoon version (`mcptoon --version` or `pip show mcptoon`)
- Python version and OS
- Minimal reproduction steps
- Expected vs actual behavior

## Suggesting Features

Use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.md). Tell us:
- What problem does this solve?
- How would you use it?
- Any alternative solutions you've considered?

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0. See [LICENSE](LICENSE) and [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Code of Conduct

Be respectful. Be helpful. We're all here because JSON eats too many tokens.
