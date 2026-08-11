# MCP Profiles

Pre-configured MCP server profiles — battle-tested production servers + beginner-friendly zero-config servers.

## Why profiles?

Instead of reading docs to figure out how to configure each MCP server, just pick a profile and go:

```bash
# Copy a profile into your mcptoon config
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# Or manually copy the config section from the profile JSON into ~/.mcptoon/config.json
```

## Available profiles

### Production servers (battle-tested, 255+ tools, 23+ servers, 30K+ calls)

| Name | Package | Tools | Env vars | Our usage | Status |
|------|---------|-------|----------|-----------|--------|
| [fetch](stdio/fetch.json) | @modelcontextprotocol/server-fetch | 1 | None | 441 calls | ✅ Verified |
| [github](stdio/github.json) | @modelcontextprotocol/server-github | 26 | `GITHUB_PERSONAL_ACCESS_TOKEN` | 714 calls | ✅ Verified |
| [exa](stdio/exa.json) | exa-mcp-server | 1 | `EXA_API_KEY` | 789 calls | ✅ Verified |
| [brave-search](stdio/brave-search.json) | @modelcontextprotocol/server-brave-search | 2 | `BRAVE_API_KEY` | 89 calls | ✅ Verified |
| [firecrawl](stdio/firecrawl.json) | firecrawl-mcp | 26 | `FIRECRAWL_API_KEY` | 69 calls | ✅ Verified |

**Production total: 56 tools across 5 servers**

### Beginner servers (zero-config, official Anthropic MCP servers)

| Name | Package | Tools | Env vars | Config | Status |
|------|---------|-------|----------|--------|--------|
| [filesystem](stdio/filesystem.json) | @modelcontextprotocol/server-filesystem | 9 | None | Just pass a directory path | ✅ Verified |
| [memory](stdio/memory.json) | @modelcontextprotocol/server-memory | 9 | None | Zero config | ✅ Verified |
| [sequential-thinking](stdio/sequential-thinking.json) | @modelcontextprotocol/server-sequential-thinking | 1 | None | Zero config | ✅ Verified |
| [sqlite](stdio/sqlite.json) | @modelcontextprotocol/server-sqlite | 5 | None | Just pass a .db file path | ✅ Verified |
| [time](stdio/time.json) | @modelcontextprotocol/server-time | 2 | None | Zero config | ✅ Verified |

**Beginner total: 26 tools across 5 servers**

**Grand total: 82 tools across 10 servers**

### Usage ranking (production servers only)

Profiles are ranked by our actual production usage (255+ tools, 23+ servers, 30K+ calls):

1. **exa** (789 calls) — Semantic search, our most-used external MCP
2. **github** (714 calls) — GitHub API for repos, issues, PRs, code search
3. **fetch** (441 calls) — Simple URL fetcher, zero config needed
4. **brave-search** (89 calls) — Web + local business search
5. **firecrawl** (69 calls) — Web scraping, crawling, research papers

### Beginner recommendation

New to MCP? Start here — zero config, zero API keys:

1. **filesystem** — Let your AI read/write files in your project directory
2. **memory** — Give your AI persistent memory across conversations
3. **sequential-thinking** — Help your AI reason through complex problems
4. **time** — Current time and timezone conversion
5. **sqlite** — Query databases with natural language SQL

```bash
# Quick start — add all 5 beginner servers at once
mcptoon add filesystem --stdio npx -y @modelcontextprotocol/server-filesystem /your/project
mcptoon add memory --stdio npx -y @modelcontextprotocol/server-memory
mcptoon add sequential-thinking --stdio npx -y @modelcontextprotocol/server-sequential-thinking
mcptoon add time --stdio npx -y @modelcontextprotocol/server-time
mcptoon add sqlite --stdio npx -y @modelcontextprotocol/server-sqlite --db-path /your/data.db
```

## Profile format

Each profile JSON contains:

```json
{
  "name": "server-name",
  "display_name": "Human readable name",
  "description": "What it does",
  "package": "npm-package",
  "install": "npx -y npm-package",
  "config": {
    "transport": "stdio",
    "command": ["npx", "-y"],
    "args": ["npm-package"],
    "env": { "API_KEY": "<your-key>" }
  },
  "tools": ["tool1", "tool2"],
  "tool_count": 2,
  "verified": true,
  "verified_date": "2026-08-11",
  "platforms": { "windows": "ok", "macos": "ok", "linux": "ok" },
  "pitfalls": ["Known issues"],
  "notes": "Usage notes",
  "usage": "mcptoon add ...",
  "our_usage_rank": 1,
  "our_usage_calls": 100,
  "beginner_friendly": false
}
```

**Security: All API keys, tokens, and credentials are replaced with `<your-key>` placeholders. No secrets are stored in profiles.**

## Adding a new profile

1. Copy `_template.json` to `stdio/<name>.json`
2. Fill in the fields (run `mcptoon inspect <name> --full` to get tool list)
3. Test on Windows, macOS, and Linux
4. Set `verified: true` and `platforms` accordingly
5. Add a row to the table above
6. Commit and push

## Roadmap

Profiles are added based on real production usage and beginner demand. Next candidates:

- puppeteer (@modelcontextprotocol/server-puppeteer) — Browser automation
- google-maps (@modelcontextprotocol/server-google-maps) — Location/maps
- postgres (@modelcontextprotocol/server-postgres) — PostgreSQL queries
- slack (@modelcontextprotocol/server-slack) — Slack messaging
- notion (@modelcontextprotocol/server-notion) — Notion workspace
