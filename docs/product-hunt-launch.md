# Product Hunt 发布素材

## Tagline (一句话，60字符以内)
Token-optimized CLI proxy for MCP servers

## Description (描述，260字符以内)
mcptoon cuts MCP token waste by 80%. 255 tools = 91K tokens → 117 tokens. Zero dependencies, 250KB install, 486 tests. Works with Claude Code, Cursor, Codex.

## Topics (选择3-5个)
- Developer Tools
- Productivity
- Open Source
- Artificial Intelligence
- CLI

## 完整描述 (Product Hunt 的详情描述)

### What is mcptoon?
mcptoon is a token-optimized CLI proxy that sits between AI agents (Claude Code, Cursor, Codex) and MCP (Model Context Protocol) servers. It reduces token consumption by up to 80% by keeping tool schemas out of your context window.

### The Problem
When you connect MCP servers to your AI agent, each tool's schema gets injected into the context as JSON. With 255 tools, that's ~91,000 tokens of JSON — before any actual work happens. This wastes context, slows down responses, and costs money.

### The Solution
mcptoon acts as a middleman:
1. Your agent runs `mcptoon` commands instead of connecting to MCP servers directly
2. mcptoon manages all MCP server connections
3. Only compact results (not full schemas) enter your context
4. 90K tokens → 117 tokens

### Key Features
- 🔒 **Zero dependencies** — Python stdlib only, 250KB install
- ⚡ **Fast** — 0.3s install, 0.5s test suite (486 tests)
- 📦 **SLIM format** — Ultra-compact tool schema representation
- 🖥️ **Cross-platform** — Windows, macOS, Linux
- 🔧 **Works with** — Claude Code, Cursor, Codex CLI
- 📊 **Benchmark** — 255 tools, 90804 → 117 tokens (99.87% reduction)

### Stats
- GitHub Stars: 177+
- License: MIT
- Version: v0.5.1
- Language: Python
- Install: `pip install mcptoon`

### Who is it for?
- AI agent developers who use MCP tools
- Teams building with Claude Code, Cursor, or Codex
- Anyone who wants to reduce LLM token costs

### Links
- GitHub: https://github.com/activeing123/mcptoon
- PyPI: https://pypi.org/project/mcptoon
- Documentation: https://github.com/activeing123/mcptoon#readme

## 产品图片建议
1. Logo/Icon - mcptoon 文字logo
2. Benchmark 截图 - Before/After token 对比
3. Terminal 截图 - mcptoon serve 运行中
4. Architecture 图 - Agent → mcptoon → MCP servers

## 发布时间建议
- 周二或周三（太平洋时间 00:01 = 太平洋时间午夜）
- 提前24h通知支持者准备upvote
