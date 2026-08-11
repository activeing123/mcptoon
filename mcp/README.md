# MCP Server Support Matrix

> mcptoon works with **any** MCP server (stdio or HTTP). Pre-configured profiles make it even easier — just copy and go.

**Three tiers:**
- ✅ **Profile ready** — pre-configured, battle-tested, copy-paste ready
- 🔜 **Profile planned** — mcptoon supports it today (just `mcptoon add`), profile coming soon
- 💬 **Community requested** — users want it, waiting for profile contributor

**Total: 10 profiles ready · 50+ planned · growing**

---

## Quick start

```bash
pip install mcptoon

# Any MCP server works immediately — just add it:
mcptoon add my-server --stdio npx -y @modelcontextprotocol/server-fetch

# Or use a pre-configured profile (see tables below):
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon manifest --toon    # see all tools, 97% less tokens than JSON
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```

---

## ✅ Profile Ready (10 servers, 82 tools)

Battle-tested with real production usage: 255+ tools, 23+ servers, 30K+ calls.

### 🛠️ Developer

| Name | Package | Tools | Env vars | Our usage | Profile |
|------|---------|-------|----------|-----------|---------|
| **github** | @modelcontextprotocol/server-github | 26 | `GITHUB_PERSONAL_ACCESS_TOKEN` | 714 calls | [✅ Profile](stdio/github.json) |

### 🔍 Search & Web

| Name | Package | Tools | Env vars | Our usage | Profile |
|------|---------|-------|----------|-----------|---------|
| **fetch** | @modelcontextprotocol/server-fetch | 1 | None | 441 calls | [✅ Profile](stdio/fetch.json) |
| **exa** | exa-mcp-server | 1 | `EXA_API_KEY` | 789 calls | [✅ Profile](stdio/exa.json) |
| **brave-search** | @modelcontextprotocol/server-brave-search | 2 | `BRAVE_API_KEY` | 89 calls | [✅ Profile](stdio/brave-search.json) |
| **firecrawl** | firecrawl-mcp | 26 | `FIRECRAWL_API_KEY` | 69 calls | [✅ Profile](stdio/firecrawl.json) |

### 📁 File & Document

| Name | Package | Tools | Env vars | Config | Profile |
|------|---------|-------|----------|--------|---------|
| **filesystem** | @modelcontextprotocol/server-filesystem | 9 | None | Pass a directory path | [✅ Profile](stdio/filesystem.json) |

### 🧠 AI & Knowledge

| Name | Package | Tools | Env vars | Config | Profile |
|------|---------|-------|----------|--------|---------|
| **memory** | @modelcontextprotocol/server-memory | 9 | None | Zero config | [✅ Profile](stdio/memory.json) |
| **sequential-thinking** | @modelcontextprotocol/server-sequential-thinking | 1 | None | Zero config | [✅ Profile](stdio/sequential-thinking.json) |

### 🗄️ Database

| Name | Package | Tools | Env vars | Config | Profile |
|------|---------|-------|----------|--------|---------|
| **sqlite** | @modelcontextprotocol/server-sqlite | 5 | None | Pass a .db file path | [✅ Profile](stdio/sqlite.json) |

### 🔧 Utility

| Name | Package | Tools | Env vars | Config | Profile |
|------|---------|-------|----------|--------|---------|
| **time** | @modelcontextprotocol/server-time | 2 | None | Zero config | [✅ Profile](stdio/time.json) |

---

## 🔜 Profile Planned (50+ servers)

mcptoon supports these **today** — just `mcptoon add <name> --stdio npx -y <package>`. Pre-configured profiles are coming.

### 🛠️ Developer Tools

| Name | Package | Tools | Category | Priority |
|------|---------|-------|----------|----------|
| gitlab | @modelcontextprotocol/server-gitlab | ~15 | Code platform | High |
| git | @modelcontextprotocol/server-git | ~11 | Repository ops | High |
| sentry | @modelcontextprotocol/server-sentry | ~5 | Error monitoring | Medium |
| linear | @modelcontextprotocol/server-linear | ~10 | Issue tracking | Medium |
| docker | community server | ~8 | Container ops | Medium |
| kubernetes | community server | ~12 | K8s management | Medium |
| terminal | community server | ~3 | Shell access | Low |

### 🗄️ Database

| Name | Package | Tools | Category | Priority |
|------|---------|-------|----------|----------|
| postgres | @modelcontextprotocol/server-postgres | ~3 | SQL database | High |
| mongodb | community server | ~6 | NoSQL database | Medium |
| redis | community server | ~4 | Cache/key-value | Low |
| supabase | community server | ~8 | Backend-as-a-service | Medium |
| elasticsearch | community server | ~5 | Search engine | Low |
| qdrant | community server | ~4 | Vector search | Medium |
| chroma | community server | ~4 | Vector search | Medium |
| pinecone | community server | ~5 | Vector search | Low |

### 🔍 Search & Web

| Name | Package | Tools | Category | Priority |
|------|---------|-------|----------|----------|
| tavily | tavily-mcp | ~3 | AI search | High |
| perplexity | community server | ~2 | AI search | Medium |
| bing-search | community server | ~2 | Web search | Low |
| google-custom-search | community server | ~2 | Web search | Low |

### 🌐 Browser Automation

| Name | Package | Tools | Category | Priority |
|------|---------|-------|----------|----------|
| puppeteer | @modelcontextprotocol/server-puppeteer | ~8 | Browser automation | High |
| playwright | community server | ~10 | Browser automation | High |
| browserbase | community server | ~5 | Cloud browser | Low |

### 💬 Communication

| Name | Package | Tools | Category | Priority |
|------|---------|-------|----------|----------|
| slack | @modelcontextprotocol/server-slack | ~5 | Team messaging | High |
| discord | community server | ~4 | Community chat | Medium |
| email (imap) | community server | ~6 | Email access | Medium |
| reddit | community server | ~3 | Social media | Low |
| twitter/x | community server | ~4 | Social media | Low |

### 📁 File & Document

| Name | Package | Tools | Category | Priority |
|------|---------|-------|----------|----------|
| google-drive | @modelcontextprotocol/server-google-drive | ~8 | Cloud storage | Medium |
| notion | community server | ~10 | Knowledge base | High |
| obsidian | community server | ~6 | Note-taking | Medium |
| dropbox | community server | ~5 | Cloud storage | Low |
| confluence | community server | ~6 | Enterprise wiki | Low |

### 📋 Project Management

| Name | Package | Tools | Category | Priority |
|------|---------|-------|----------|----------|
| jira | community server | ~8 | Issue tracking | Medium |
| airtable | community server | ~6 | Database-spreadsheet | Low |
| asana | community server | ~5 | Task management | Low |
| trello | community server | ~4 | Kanban board | Low |

### 🎨 Creative & Design

| Name | Package | Tools | Category | Priority |
|------|---------|-------|----------|----------|
| blender | blender-mcp | ~15 | 3D modeling | Medium |
| figma | community server | ~6 | UI design | Low |
| mermaid | community server | ~3 | Diagrams | Low |
| everart | @modelcontextprotocol/server-everart | ~2 | Image generation | Low |

### ☁️ Cloud & DevOps

| Name | Package | Tools | Category | Priority |
|------|---------|-------|----------|----------|
| aws | community server | ~10 | AWS services | Medium |
| azure | community server | ~8 | Azure services | Low |
| cloudflare | community server | ~7 | Edge/cloud | Medium |
| vercel | community server | ~4 | Deployment | Low |
| netlify | community server | ~3 | Deployment | Low |

### 📊 Data & Analytics

| Name | Package | Tools | Category | Priority |
|------|---------|-------|----------|----------|
| google-maps | @modelcontextprotocol/server-google-maps | ~4 | Location/maps | Medium |
| spotify | community server | ~6 | Music data | Low |
| youtube | community server | ~5 | Video data | Low |
| alpha-vantage | community server | ~3 | Finance data | Low |

### 🧠 AI & Knowledge

| Name | Package | Tools | Category | Priority |
|------|---------|-------|----------|----------|
| everything | @modelcontextprotocol/server-everything | ~11 | MCP demo/test | Low |

---

## 💬 Community Requested

Servers that users have asked for. Want to help? Pick one and contribute a profile!

| Name | Requested by | Status | Contribute |
|------|-------------|--------|------------|
| *None yet — be the first!* | — | — | [Open an issue](https://github.com/activeing123/mcptoon/issues/new?labels=profile-request&title=Profile+request:+<name>) |

### How to request a server

1. [Open a new issue](https://github.com/activeing123/mcptoon/issues/new?labels=profile-request&title=Profile+request:+SERVER_NAME)
2. Use label `profile-request`
3. Include: server name, npm package, what it does, why you need it
4. We'll add it to the list and prioritize based on demand

### How to contribute a profile

1. Copy `mcp/_template.json` → `mcp/stdio/<name>.json`
2. Fill in the fields
3. Test: `mcptoon add <name> --stdio npx -y <package> && mcptoon manifest --toon`
4. Open a PR — we'll verify and merge

See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.

---

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

---

## Why profiles?

Without a profile, you need to: find the server package → read its docs → figure out env vars → write the config.

With a profile, you just: `mcptoon add <name> --stdio npx -y <package>` — everything is pre-configured.

**But remember: mcptoon works with ANY MCP server, profile or not.** If your server isn't listed here, just add it manually:

```bash
mcptoon add my-server --stdio npx -y @any/mcp-server --env MY_API_KEY=xxx
mcptoon manifest --toon    # works immediately
```

---

## Categories at a glance

| Category | Ready | Planned | Total |
|----------|-------|---------|-------|
| 🛠️ Developer Tools | 1 | 6 | 7 |
| 🗄️ Database | 1 | 8 | 9 |
| 🔍 Search & Web | 4 | 4 | 8 |
| 🌐 Browser Automation | 0 | 3 | 3 |
| 💬 Communication | 0 | 5 | 5 |
| 📁 File & Document | 1 | 5 | 6 |
| 📋 Project Management | 0 | 4 | 4 |
| 🎨 Creative & Design | 0 | 4 | 4 |
| ☁️ Cloud & DevOps | 0 | 5 | 5 |
| 📊 Data & Analytics | 0 | 4 | 4 |
| 🧠 AI & Knowledge | 2 | 1 | 3 |
| 🔧 Utility | 1 | 0 | 1 |
| **Total** | **10** | **49** | **59** |

---

## Token savings by category

Every server benefits from mcptoon's token optimization:

| Operation | JSON tokens | mcptoon tokens | Savings |
|-----------|-------------|----------------|---------|
| Tool discovery (per server) | ~200-400 | ~5-15 | **97%** |
| Tool schema (per tool) | ~80-150 | ~5-10 | **93%** |
| Tool results (structured) | ~500-3000 | ~200-1200 | **56%** |

A typical 5-server setup saves **40,000-70,000 tokens** per conversation.
