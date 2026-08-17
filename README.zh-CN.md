<div align="center">

# mcptoon

**加 255 个 MCP 工具 → 90,804 token 没了。用 mcptoon → 117 token。**

*100+ MCP 服务器一直配着。零上下文污染。不用加载。不用卸载。一个 CLI，所有 Agent 通用。*

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/依赖-零-orange)](#隐私)
[![GitHub Stars](https://img.shields.io/github/stars/activeing123/mcptoon?style=social)](https://github.com/activeing123/mcptoon)
[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white)](https://pypi.org/project/mcptoon/)

**如果帮你省了 token，请点个 star——让更多人发现它。**

[English](README.md) · [中文文档](README.zh-CN.md) · [📦 服务器 Profile](mcp/README.md) · [🌐 生态](ECOSYSTEM.md)

</div>

---

## 问题

每个 MCP Agent 都会把**所有工具的 schema 塞进你的上下文**——在任何工作开始之前。

```
加 10 个 MCP 服务器（特别是 puppeteer/playwright 这类浏览器工具）
  → 每个服务器返回 tools/list，带完整 JSON schema
  → 所有 schema 注入你的上下文
  → 消耗 50,000-100,000+ token
  → 128K 上下文：还没问问题，40-80% 就没了

加 100 个服务器 → 200,000+ token → 上下文死了。
```

于是你不用的时候卸载服务器，用的时候再加载。来回折腾。永远如此。

想加个新 MCP 服务器？手动编辑 JSON 配置文件（`claude_desktop_config.json` 之类的）。一个语法错误、路径写错、环境变量没设——MCP 就加载不了。你调几个小时。

**你在管 MCP 服务器，不是在做正事。**

## 解决方案

mcptoon 让你**所有 MCP 服务器都配着**——但它们的 schema **永远不进 Agent 的上下文**。

### 😤 5 个痛点。✅ 5 个杀招。

#### 😤 上下文撑死 → ✅ 0 token，永远

加 10 个 MCP 服务器——特别是 puppeteer（47 个工具，2.3万 token 的 schema）或 playwright（52 个工具，2.8万 token）这种浏览器工具。还没问一个问题，5-10万 token 的 `{"type":"object","properties":...}` 就占满了你的上下文。你的 AI 忘了刚才在聊什么。于是你卸载服务器腾空间。要用的时候再装回来、等它起、重新配。你在上下文窗口里玩俄罗斯方块。这就是为什么大家说"MCP 超过 5 个就没法用了。"

→ **mcptoon：100 个服务器配着，上下文占 0 token。** 随时用任意工具。不玩方块。

#### 😤 配置地狱 → ✅ 一条命令，完事

想加个服务器？手写 `claude_desktop_config.json`。少个逗号 → 加载不了。路径写错 → 加载不了。环境变量没设 → 加载不了。有时候它加载了，但工具静默不出现——没报错，没日志，就是什么都没有。你盯着空白工具列表调一个小时。

→ **mcptoon：`mcptoon add myserver --stdio npx -y @package`。** 一条命令。哪里坏了？`mcptoon doctor` 检查 Python 版本、配置语法、服务器连通性——直接告诉你。

#### 😤 Agent 没法自服务 → ✅ AI 自己装工具

你的 AI 干活干到一半，说"我需要 GitHub 搜索才能完成这个任务"。它装不了工具——它是 AI，不是管理员。于是**你**停下来，去改 JSON，重启 Agent，等它重连。你的 AI 忘了刚才在干嘛。节奏断了。

→ **mcptoon：你的 AI 自己跑 `mcptoon add github ...` 就行**，继续干活。不需要人介入。上下文不丢。

#### 😤 换个 Agent 全部重来 → ✅ 一份配置，所有 Agent

Claude Code 配了 15 个 MCP 服务器。换 Cursor——配置格式不同、文件位置不同，15 个全部从头来。换 OpenCode。又来一遍。换 Codex。又来一遍。同样的服务器，4 倍工作量，4 倍写错逗号的概率。

→ **mcptoon：一份配置文件，所有 Agent 通用。** `~/.mcptoon/config.json`。几秒切换。配置跟着你走。

#### 😤 为 JSON 垃圾付钱 → ✅ TOON，小 30-97%

每个 MCP 返回长这样：`{"content":[{"type":"text","text":"{\"name\":\"react\",\"stars\":219000}"}]}`——80 个 token 的括号、引号、类型声明，就为传 6 个 token 的真实数据。一个 session 调 200 次工具 = 1.5万 token 纯语法浪费。

→ **mcptoon：返回 `name: react\nstars: 219000`——同样的数据，结果少 30-60% token（标准 TOON），schema 少 93%（SLIM）。** 工具发现：少 97-100%。[tiktoken 验证](#toon-原理)。

---

**100 个 MCP 服务器。0 上下文浪费。随时用任意工具。不用加载。不用卸载。不用怕 JSON 配置写错。**

### 怎么做到的？CLI 模式。

mcptoon 是个 CLI 工具，不是 MCP 客户端库。你的 Agent 不连接 MCP 服务器——它只跑 `mcptoon` 命令。MCP schema 存在磁盘上的 `~/.mcptoon/config.json` 里，不进你的上下文窗口。只有你主动要的紧凑输出才进上下文——而 TOON 编码让它比 JSON 小 30-97%。

### 行业验证：CLI > MCP

独立研究证实 mcptoon 的 CLI 路线优于 MCP 协议注入：

| 来源 | 发现 |
|------|------|
| [CLI vs MCP 基准测试（75 个任务）](https://www.cn486.com/news/4135995/) | CLI Agent 全面碾压 MCP Agent：**token 成本低 10-32 倍**，可靠性 ~100% vs MCP 的 72% |
| Perplexity | 从 Agent 架构中完全移除 MCP 支持——token 开销太大 |
| Anthropic 内部研究 | Shell 脚本比等效的 MCP 工具调用**省 98.7% token** |
| Latent Space | "MCP 协议在 20-30 个工具左右形成扩展悬崖"——mcptoon 没有这个限制 |

**行业正在从 MCP 注入 → CLI 执行迁移。mcptoon 从第一天就是 CLI 优先。**

---

## GitHub 用户看到什么 vs 你本地有什么

mcptoon 有**双轨架构**——公开的 GitHub 仓库干净且自包含，你的本地安装可以有私有扩展：

```
GitHub 仓库（公开）                   你的机器（本地）
┌────────────────────────────┐       ┌────────────────────────────┐
│  src/mcptoon/              │       │  src/mcptoon/              │
│  ├─ cli.py                 │       │  ├─ cli.py                 │  ← 同一份代码
│  ├─ client.py              │       │  ├─ client.py              │
│  ├─ installer.py           │       │  ├─ installer.py           │
│  ├─ router.py              │       │  ├─ router.py              │
│  └─ output.py (TOON)       │       │  └─ output.py (TOON)       │
│                            │       │                            │
│  mcp/ (23 个 Profile)      │       │  mcp/ (23 个 Profile)      │  ← 同样的 Profile
│  tests/ (429 个测试)       │       │  ~/.mcptoon/config.json    │  ← 你的服务器
│  docs/, README 等          │       │  local/ (私有层)           │  ← 你的扩展
│                            │       │  ├─ handlers/ (30+)        │
│  ✘ 没有私有 handler        │       │  ├─ router.py (桥接)       │
│  ✘ 没有本地凭证            │       │  └─ cli_pro.py            │
└────────────────────────────┘       └────────────────────────────┘
```

**什么推到 GitHub：** 干净的、零依赖 CLI 核心——13 个 Python 文件、约 4500 行、429 个测试、23 个服务器 Profile。没有私有 handler、没有凭证、没有本地配置。

**什么留在本地：** 你的个人 `~/.mcptoon/config.json`、你安装的 MCP 服务器，以及可选的 `local/` 目录（私有 handler 放这里）。`.gitignore` 排除了所有这些。

### GitHub 用户能自己安装工具吗？

**能——这正是重点。** mcptoon 是*工具管理器*，不是工具包。GitHub 用户这样开始：

```bash
# 1. 安装 mcptoon（CLI 核心，零依赖）
pip install mcptoon

# 2. 添加你想要的任何 MCP 服务器——一条命令：
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# 3. 或者自动发现你机器上已有的服务器：
mcptoon init --auto

# 4. 或者从 npm/pip/HTTP 安装并自动生成 handler：
mcptoon install brave-search --npm @anthropic/mcp-server-brave-search
mcptoon install my-tool --pip mcp-my-tool
mcptoon install remote-api --url https://example.com/mcp

# 5. 查看你的工具（255 个工具只需 117 token）：
mcptoon manifest --compact

# 6. 调用任意工具：
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```

**mcptoon 永远不捆绑 MCP 服务器。** 用户只安装自己需要的——从 npm、pip 或 HTTP 端点。`mcp/stdio/*.json` 里的 23 个预置 Profile 只是约 1KB 的 JSON 模板，描述*怎么连接*——不是服务器本身。服务器只在实际调用工具时通过 `npx` 按需启动。

| mcptoon 发什么 | mcptoon 不发什么 |
|---|---|
| CLI 核心（13 个文件，约 200KB） | MCP 服务器二进制文件 |
| 23 个服务器 Profile 模板（约 1KB/个） | API key 或凭证 |
| 429 个测试 + benchmark 套件 | 用户的私有配置 |
| 集成指南 + 生态文档 | 第三方依赖 |

---

## 30 秒开始

```bash
pip install mcptoon
```

零依赖，Python 3.10+，约 200KB。Windows、macOS、Linux 全支持。

```bash
# ─── 30 秒上手 ───
mcptoon quickstart                      # 发现 + 配置 + 展示工具
mcptoon init --auto                     # 自动发现你机器上的 MCP 服务器
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# ─── 查看工具 ───
mcptoon manifest --compact              # → 所有工具名，255 个工具只需 117 token
mcptoon manifest --slim                 # → 工具 schema，比 JSON 小 93%
mcptoon manifest --toon                 # → 标准 TOON 格式

# ─── 调用工具 ───
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
mcptoon call --auto search '{"query":"AI"}' --toon  # 自动找服务器

# ─── 自检 ───
mcptoon doctor
```

### 一键安装新 MCP 服务器

在 GitHub 上发现了新的 MCP？一条命令安装——mcptoon 自动连接、发现工具、生成 handler、注册。不需要重启。

```bash
# 从 npm 安装
mcptoon install brave-search --npm @anthropic/mcp-server-brave-search

# 从 pip 安装
mcptoon install my-tool --pip mcp-my-tool

# HTTP/SSE 服务器
mcptoon install remote-api --url https://example.com/mcp

# 列出已安装
mcptoon install --list

# 卸载
mcptoon install --remove brave-search
```

### 使用预置 Profile

23 个经过实战测试的服务器 Profile 在 `mcp/stdio/*.json` 里。每个是约 1KB 的 JSON 文件，描述如何连接——安全审计过，声明了 `credential_safe`、`env_vars_required`、`permissions`。

```bash
# 浏览 Profile：
cat mcp/stdio/github.json

# 使用任意 Profile——只需添加服务器：
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# 设置你的 API key：
export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxx

# 使用它：
mcptoon call github search_repos '{"query":"mcp"}' --toon
```

**没看到你的服务器？** mcptoon 支持*任何* MCP 服务器，有没有 Profile 都行：

```bash
mcptoon add my-server --stdio npx -y @any/mcp-server
mcptoon manifest --toon    # 直接就能用
```

查看全部 23 个 Profile：[mcp/README.md](mcp/README.md)

---

## 所有 Agent 都能用

mcptoon 是 CLI 工具。你的 Agent 能跑 shell 命令，就能用 mcptoon。不需要 SDK 集成，不需要插件，不需要每个 Agent 单独配。

你把 MCP 服务器配置**一次**，存在 `~/.mcptoon/config.json`。所有 Agent 共享同样的服务器、同样的工具、同样的省 token 效果。

| Agent | 怎么用 |
|---|---|
| **Claude Code** | 在 SKILL.md 或自定义指令里写 `mcptoon` 命令 |
| **Codex (OpenAI)** | 在 AGENTS.md 或 prompt 指令里加 `mcptoon` |
| **OpenCode** | 在自定义命令或 system prompt 里用 `mcptoon` |
| **Cursor** | 在 .cursorrules 或自定义 prompt 里加 `mcptoon` |
| **CatPaw** | 在技能文件里写 `mcptoon` 命令 |
| **任何 Agent** | 能跑 shell 命令就能调 `mcptoon` |

### Agent 自服务

你的 AI 可以自己添加 MCP 工具——不需要人介入：

```bash
# AI 想要网页抓取？直接加：
mcptoon add firecrawl --stdio npx -y firecrawl-mcp

# AI 想要 GitHub 访问？一条命令：
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# 验证一切正常：
mcptoon doctor

# 立刻使用：
mcptoon call github search_repos '{"query":"token optimization"}' --toon
```

不需要 JSON 配置文件。不需要调试 RPC。不需要重启服务器。只需 CLI 命令。

---

## 看效果

**JSON（287 token）**——其他所有 MCP 客户端返回的：

```json
[
  {"name": "search_web", "description": "Search the web for information",
   "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Search query"}, "num_results": {"type": "number", "default": 5}}, "required": ["query"]}},
  {"name": "fetch_url", "description": "Fetch content from a URL",
   "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}
]
```

**TOON（5 token）**——mcptoon 返回的：

```
search_web fetch_url
```

**SLIM（带 schema，14 token）**——需要参数细节时：

```
search_web|query:s*|num_results:n
fetch_url|url:s*
```

工具发现省 98%，完整 schema 省 93%，信息零丢失。

### 实测 benchmark（255 个工具，5 种格式）

| 工具数 | JSON | 标准 TOON | mcptoon | SLIM | Compact |
|-------|------|----------|---------|------|---------|
| 5 | 1,897 | 981 (-48%) | 785 (-59%) | 111 (-94%) | 16 (-99%) |
| 10 | 3,567 | 1,757 (-51%) | 1,391 (-61%) | 235 (-93%) | 34 (-99%) |
| 25 | 9,009 | 4,491 (-50%) | 3,580 (-60%) | 595 (-93%) | 97 (-99%) |
| 50 | 17,790 | 8,776 (-51%) | 6,981 (-61%) | 1,203 (-93%) | 117 (-99%) |
| 93 | 33,191 | 16,426 (-51%) | 13,086 (-61%) | 2,231 (-93%) | 117 (-100%) |
| 150 | 53,350 | 26,326 (-51%) | 20,958 (-61%) | 3,626 (-93%) | 117 (-100%) |
| 200 | 71,135 | 35,106 (-51%) | 27,952 (-61%) | 4,842 (-93%) | 117 (-100%) |
| **255** | **90,804** | **44,863 (-51%)** | **35,735 (-61%)** | **6,174 (-93%)** | **117 (-100%)** |

**标准 TOON** (`--toon`)：比 JSON **小 51%**（可逆）。
**mcptoon 格式** (`--mcptoon`)：比 JSON **小 61%**（可逆）。
**SLIM 格式** (`--slim`)：完整 schema **小 93%**。
**Compact** (`--compact`)：工具名 **小 100%**。

复现：`python _benchmark.py` → 输出 `assets/benchmark_data.json`

### 第三方研究与上下文经济学

| 来源 | 发现 | 为什么重要 |
|--------|---------|---------------|
| [Anthropic《Context Windows for Agents》](https://docs.anthropic.com/en/docs/build-with-claude/context-windows) | "上下文窗口是稀缺资源。每个 schema token 都是从用户实际任务中偷走的 token。" | MCP schema 是 Agent 工作流中上下文浪费的 #1 来源 |
| [OpenAI《Function Calling Guide》](https://platform.openai.com/docs/guides/function-calling) | 工具定义消耗的上下文 token 与 schema 复杂度成正比 | 100+ 工具的完整 schema 可以吃掉 128K 上下文窗口的 40-80% |
| [Cursor 团队《Context Engineering》](https://cursor.com/blog/context-engineering) | "好 Agent 和坏 Agent 的区别几乎总是上下文管理，而不是模型智能。" | 在传输层优化 token（如 TOON）直接提升 Agent 质量 |
| [Latent Space《MCP Ecosystem Analysis》](https://www.latent.space/p/mcp) | "MCP 协议在每个请求中注入完整 JSON schema——这是设计如此，但在 20-30 个工具左右形成扩展悬崖。" | 确认了 mcptoon 解决的问题：20-30 个工具就是痛点，不是 100+ |
| [Simon Willison《LLM Tooling》](https://simonwillison.net/2024/Nov/19/llms/) | "JSON 是发送给 LLM 的结构化数据中 token 效率最低的格式。" | 验证了 TOON 的方向：任何非 JSON 编码都能省 token |

---

## TOON 原理

mcptoon 支持两种 token 高效格式：

### 标准 TOON (`--toon`)

实现了 [TOON (Token-Oriented Object Notation)](https://github.com/toon-format/toon) 规范——为 LLM 设计的开放格式。用 YAML 风格缩进表示对象，CSV 风格表格表示统一数组。

| JSON | 标准 TOON | 原理 |
|---|---|---|
| `{"name":"search","count":3}` | `name: search\ncount: 3` | 换行替代花括号+引号 |
| `[{"id":1,"name":"Alice"}]` | `[1]{id,name}:\n  1,Alice` | 字段声明一次 + CSV 行 |
| `[1, 2, 3]` | `[3]:\n  1\n  2\n  3` | 方括号表示数组 |
| `true` / `false` / `null` | `true` / `false` / `null` | 保持原样（都是 1 token） |

**可逆**：`decode(encode(x)) == x`。URL、时间戳、特殊字符都安全保留。

### 旧版 mcptoon 格式 (`--mcptoon`)

mcptoon 原创的管道分隔格式。比标准 TOON 简单但结构化程度更低。

| JSON | mcptoon | 原理 |
|---|---|---|
| `{"name":"search","count":3}` | `name:search\|count:3` | 竖线替代花括号+引号 |
| `[1, 2, 3]` | `1 2 3` | 空格替代方括号+逗号 |
| `"https://example.com"` | `https\c//example.com` | 冒号转义为 `\c`（可逆） |

**可逆**，用 `mcptoon_decode()`。转义序列：`\c`=冒号，`\p`=竖线，`\\`=反斜杠。

### SLIM 格式 (`--slim`)

mcptoon 专属的超紧凑工具 schema 编码。无外部对应。

```
search|q:s*|n:n
fetch|url:s*
```

**tiktoken 验证**：`{"type":"object","properties":{...}}` → `q:s*`（省 83% token）。

## 输出格式

| Flag | 输出 | Token 用量 |
|---|---|---|
| `--compact` | 仅工具名，空格分隔 | 比 JSON 省 **97-100%** |
| `--slim` | 超紧凑工具 schema (name\|param:type*) | 比 JSON 省 **93%** |
| `--toon` | 标准 TOON（toon-format/toon 规范） | 比 JSON 省 **30-60%**（可逆） |
| `--mcptoon` | 旧版 mcptoon 管道格式 | 比 JSON 省 **20-40%**（可逆） |
| `--json` | 标准 JSON（脚本、CI 用） | 基准线 |
| `--raw` | 原始响应，不解析 | 全量 |
| `--head N` | 仅前 N 条 | 可变 |
| `--max-chars N` | 硬截断到 N 字符 | 可变 |
| `--full` | 禁用默认 4000 字符截断 | 全量 |

设 `MCPTOON_AGENT_TYPE=claude`，所有调用自动用 `--toon`，不用手动加 flag。

---

## 架构 —— 三层解耦

mcptoon 基于**三层解耦架构**。每一层独立——换一层不碰其他层。

```
┌─────────────────────────────────────────────────┐
│  第 1 层: mcptoon CLI (~200KB, 零依赖)            │
│  ─────────────────────────────────────────────   │
│  在 Agent 的 shell 里运行。所有输出做 token      │
│  优化。schema 永远不进上下文。永远不。            │
└──────────────────────┬──────────────────────────┘
                       │ 读 JSON 模板（在磁盘上）
┌──────────────────────▼──────────────────────────┐
│  第 2 层: MCP 服务器 Profile (~1KB/个)            │
│  ─────────────────────────────────────────────   │
│  23 个 JSON 模板在 mcp/stdio/*.json。             │
│  不是已安装的软件——只是连接规格。                 │
│  安全审计: credential_safe、env_vars、             │
│  permissions 每个 Profile 都声明。                 │
│  加你自己的——直接用。                             │
└──────────────────────┬──────────────────────────┘
                       │ 按需启动 via npx
┌──────────────────────▼──────────────────────────┐
│  第 3 层: 实际 MCP 服务器 (npm 包)                │
│  ─────────────────────────────────────────────   │
│  真正的 MCP 服务器 (@modelcontextprotocol/       │
│  server-* 等)。只有你实际调用工具时才启动。        │
│  配置时不安装。启动时不加载。不用就零开销。        │
└─────────────────────────────────────────────────┘
```

**为什么三层？**

- **第 1 层 (CLI)** 保持极小——约 200KB，零依赖。没有 MCP SDK 臃肿。
- **第 2 层 (Profile)** 是可编辑 JSON——加、删、fork 不碰代码。每个约 1KB 文件只描述*怎么连接*，不是服务器本身。
- **第 3 层 (服务器)** 惰性启动——只有 `mcptoon call` 实际执行时才 spin up。没有空闲进程。没有启动税。

这意味着：
- 100 个服务器配好 → 0 个在运行，直到你用其中一个
- 删一个 Profile → 其余照常工作
- 加一个 Profile → 不改代码，不重新构建
- mcptoon 不捆绑 MCP 服务器——你装你用的

### 安全审计的 Profile

每个 Profile 声明其安全姿态：

```json
// mcp/stdio/puppeteer.json
{
  "name": "puppeteer",
  "security": {
    "audited": true,
    "credential_safe": true,
    "env_vars_required": [],
    "permissions": ["read: web pages, DOM", "write: form inputs, JS execution"]
  },
  "bundled": false,
  "install_method": "on-demand"
}
```

23 个 Profile：fetch, github, exa, brave-search, firecrawl, filesystem, memory, sequential-thinking, sqlite, time, puppeteer, playwright, postgres, slack, notion, git, gitlab, tavily, google-maps, docker, aws, cloudflare, tmux。详见 [`mcp/README.md`](mcp/README.md)。

→ **[完整生态计划](ECOSYSTEM.md)**

---

## 功能

**经过实战测试**：255+ MCP 工具，55+ 服务器，30K+ 真实调用。429 个测试全部通过。10/10 E2E 测试通过。

- **`mcptoon install`** — 一键从 npm/pip/HTTP 安装 MCP 服务器并自动生成 handler
- **`mcptoon quickstart`** — 一键上手：发现 + 配置 + 展示工具
- **`mcptoon doctor`** — 自检（Python 版本、配置、服务器连通性）
- **`mcptoon discover`** — 零配置自动发现（配置扫描 + 环境检测 + 网络探测）
- **`mcptoon search`** — 跨服务器工具搜索，多因子评分
- **`mcptoon call --auto`** — 自动路由工具调用到正确的服务器
- **`--stdin`** — 通过 stdin 传递大 payload，绕过 OS 命令行长度限制
- **Prompt 注入防护** — 检测 MCP 结果中的注入模式
- **凭据泄露检测** — 扫描结果中的 API key、AWS key、GitHub PAT、OpenAI/Anthropic key、Slack token、JWT、私钥
- **模糊匹配** — 拼错时提示"你是要找: search, search_all?"
- **跨 Agent 导出** — `--format openai|openapi|mcp` 给非 CLI Agent 用
- **Schema 缓存** — 5 分钟 TTL，避免重复 `tools/list` 往返
- **用量统计** — 本地调用统计和 token 估算
- **危险操作拦截** — 默认拦截 `delete`/`drop`/`purge`，除非加 `--destructive`
- **Shell 补全** — bash、zsh、fish、PowerShell
- **TOML 配置** — `~/.mcptoon/config.toml` 支持

### 安全三层防护

| 层 | 做什么 | 示例 |
|-------|-------------|----------|
| **危险操作拦截** | 默认拦截 `delete`/`drop`/`purge`/`kill` | `docker_remove` → 拦截，除非加 `--destructive` |
| **Prompt 注入防护** | 扫描结果中的注入模式 | `"ignore previous instructions"` → 拦截 |
| **凭据泄露检测** | 扫描结果中的暴露 API key/token | `sk-abc...xyz` → 拦截，错误信息中脱敏 |

```bash
# 凭据泄露检测实例：
$ mcptoon call github get_file --toon
# Error: CREDENTIAL_LEAK — potential OpenAI API Key leak detected: sk-abc...wxyz
# 结果永远不会进入你的 Agent 上下文。
```

---

## Python API

```python
from mcptoon.client import MCPClient
from mcptoon.output import toon_encode, toon_decode, mcptoon_encode

with MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-fetch"]) as c:
    tools = c.list_tools()
    print(toon_encode(tools))         # 标准 TOON 输出
    result = c.call_tool("fetch", {"url": "https://example.com"})
    print(toon_encode(result))        # 标准 TOON 输出
    # 可逆：解码回 Python dict
    decoded = toon_decode(toon_encode(result))
    assert decoded == result          # ✅ 可逆
```

## 配置

```bash
# stdio（任何 npx MCP 服务器）
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# HTTP
mcptoon add myapi --http http://localhost:3001/mcp --header "Authorization: Bearer xxx"
```

配置文件在 `~/.mcptoon/config.json`。项目级覆盖在 `./.mcptoon.json`。TOML 支持 `~/.mcptoon/config.toml`。

## 隐私

- **没有遥测。** 没有分析，没有崩溃报告，没有回传。什么都不离开你的机器。
- **不存凭证。** API key 从你的配置或环境变量直接传递。永不记录，永不缓存。
- **没有依赖。** 纯 Python 标准库。没有供应链要审计，没有包会被劫持。
- **凭据泄露检测。** 扫描工具返回结果中的暴露 API key/token —— 在进入 Agent 上下文前拦截。

## 架构

```
src/mcptoon/
├── cli.py        # CLI 入口 + 参数解析
├── client.py     # MCPClient — stdio + HTTP 传输
├── installer.py  # 一键 MCP 服务器安装 + 自动 handler 生成
├── router.py     # 工具调用路由, 自定义 handler, 注入防护 + 凭据泄露检测
├── config.py     # 服务器配置 (JSON + TOML)
├── manifest.py   # 工具发现 (带缓存 + 跨服务器搜索)
├── discover.py   # 零配置自动发现 (5 层)
├── output.py     # 标准 TOON + 旧版 mcptoon + JSON / compact / slim 渲染
├── cache.py      # Schema 缓存 (5分钟 TTL)
├── usage.py      # 本地用量统计
└── errors.py     # 结构化错误封装 + 修复建议
```

约 4500 行。429 个测试 + 10/10 E2E。零第三方 import。约 200KB 源码。

## 贡献

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 429 个测试, 0.5s
```

零依赖是硬规则。新功能需要测试。见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

Apache 2.0。商业使用、修改、分发都行。保留 LICENSE 和 NOTICE 文件。TOON 格式是开放的——你可以在自己的工具中实现。见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。

---

<div align="center">

*mcptoon 是独立的第三方 MCP 客户端，不隶属于 Anthropic。*

**觉得有用？点个 star 帮更多人发现它。**

</div>
