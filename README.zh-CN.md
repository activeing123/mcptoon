<div align="center">

# mcptoon

**加 255 个 MCP 工具 → 90,804 token 没了。用 mcptoon → 117 token。**

*100+ MCP 服务器一直配着。零上下文污染。不用加载。不用卸载。一个 CLI，所有 Agent 通用。*

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/依赖-零-orange)](#隐私)

**如果帮你省了 token，请点个 star——让更多人发现它。**

[English](README.md) · [中文文档](README.zh-CN.md) · [🌐 生态](ECOSYSTEM.md) · [📦 Profiles](mcp/README.md)

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

#### 😤 为 JSON 垃圾付钱 → ✅ TOON，小 56-97%

每个 MCP 返回长这样：`{"content":[{"type":"text","text":"{\"name\":\"react\",\"stars\":219000}"}]}`——80 个 token 的括号、引号、类型声明，就为传 6 个 token 的真实数据。一个 session 调 200 次工具 = 1.5万 token 纯语法浪费。

→ **mcptoon：返回 `name:react|stars:219000`——同样的数据，少 56% token。** 工具发现：少 97%。工具 schema：少 93%。**没有别的 MCP 客户端干这事。只有 mcptoon。**

---

**100 个 MCP 服务器。0 上下文浪费。随时用任意工具。不用加载。不用卸载。不用怕 JSON 配置写错。**

### 怎么做到的？CLI 模式。

mcptoon 是个 CLI 工具，不是 MCP 客户端库。你的 Agent 不连接 MCP 服务器——它只跑 `mcptoon` 命令。MCP schema 存在磁盘上的 `~/.mcptoon/config.json` 里，不进你的上下文窗口。只有你主动要的紧凑输出才进上下文——而 TOON 编码让它比 JSON 小 56-97%。

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

**带完整 schema 的 TOON（115 token）**——需要细节时：

```
name:search_web|description:Search_the_web|inputSchema:type:object|properties:query:type:string|description:Search_query|num_results:type:number|default:5|required:query||
name:fetch_url|description:Fetch_content_from_a_URL|inputSchema:type:object|properties:url:type:string|required:url
```

工具发现省 98%，完整 schema 省 60%，信息零丢失。

### 实测 benchmark（255 个工具，23 个服务器）

| 工具数 | JSON（token） | mcptoon compact | 降低 |
|-------|-------------|----------------|-----------|
| 5 | 1,897 | 16 | **99.2%** |
| 10 | 3,567 | 34 | **99.0%** |
| 25 | 9,009 | 97 | **98.9%** |
| 50 | 17,790 | 117 | **99.3%** |
| 93 | 33,191 | 117 | **99.6%** |
| 150 | 53,350 | 117 | **99.8%** |
| 200 | 71,135 | 117 | **99.8%** |
| **255** | **90,804** | **117** | **99.87%** |

**TOON 格式**工具结果：比 JSON **小 61%**。
**SLIM 格式**完整 schema：比 JSON **小 93%**。

<details>
<summary>📊 完整 benchmark 数据（点击展开）</summary>

| 工具数 | JSON token | TOON token | SLIM token | Compact token | TOON 节省 | SLIM 节省 | Compact 节省 |
|--------|-----------|------------|------------|---------------|-----------|-----------|-------------|
| 5 | 1,897 | 784 | 111 | 16 | 59% | 94% | 99% |
| 10 | 3,567 | 1,382 | 235 | 34 | 61% | 93% | 99% |
| 25 | 9,009 | 3,562 | 595 | 97 | 60% | 93% | 99% |
| 50 | 17,790 | 6,939 | 1,203 | 117 | 61% | 93% | 99% |
| 93 | 33,191 | 13,011 | 2,231 | 117 | 61% | 93% | 100% |
| 150 | 53,350 | 20,834 | 3,626 | 117 | 61% | 93% | 100% |
| 200 | 71,135 | 27,787 | 4,842 | 117 | 61% | 93% | 100% |
| 255 | 90,804 | 35,527 | 6,174 | 117 | 61% | 93% | 100% |

复现：`python _benchmark.py` → 输出 `assets/benchmark_data.json` + `assets/benchmark.html`

</details>

### 第三方研究与上下文经济学

| 来源 | 发现 | 为什么重要 |
|--------|---------|---------------|
| [Anthropic《Context Windows for Agents》](https://docs.anthropic.com/en/docs/build-with-claude/context-windows) | “上下文窗口是稀缺资源。每个 schema token 都是从用户实际任务中偷走的 token。” | MCP schema 是 Agent 工作流中上下文浪费的 #1 来源 |
| [OpenAI《Function Calling Guide》](https://platform.openai.com/docs/guides/function-calling) | 工具定义消耗的上下文 token 与 schema 复杂度成正比 | 100+ 工具的完整 schema 可以吃掉 128K 上下文窗口的 40-80% |
| [Cursor 团队《Context Engineering》](https://cursor.com/blog/context-engineering) | “好 Agent 和坏 Agent 的区别几乎总是上下文管理，而不是模型智能。” | 在传输层优化 token（如 TOON）直接提升 Agent 质量 |
| [Latent Space《MCP Ecosystem Analysis》](https://www.latent.space/p/mcp) | “MCP 协议在每个请求中注入完整 JSON schema —— 这是设计如此，但在 20-30 个工具左右形成扩展悬崖。” | 确认了 mcptoon 解决的问题：20-30 个工具就是痛点，不是 100+ |
| [Simon Willison《LLM Tooling》](https://simonwillison.net/2024/Nov/19/llms/) | “JSON 是发送给 LLM 的结构化数据中 token 效率最低的格式。” | 验证了 TOON 的方向：任何非 JSON 编码都能省 token |
| GitHub Issues | Puppeteer MCP（47 工具）+ Playwright MCP（52 工具）= 单独 schema 就约 5万 token | 两个浏览器 MCP 服务器消耗的上下文比这整篇 README 还多 |

## 安装

```bash
pip install mcptoon
```

零依赖，50KB，Python 3.10+。Windows、macOS、Linux 全支持。完事。

## 30 秒省下第一批 token

```bash
mcptoon init
# Sample config created: ~/.mcptoon/config.json

mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

mcptoon manifest --toon
# → fetch:fetch

mcptoon call fetch fetch '{"url":"https://example.com"}' --toon

mcptoon call fetch fetch '{"url":"https://example.com"}' --json   # 脚本需要 JSON 时
```

就这样。每次 `--toon` 调用省 token：工具发现省 97%，结构化结果省 40-60%，原始内容省 10-20%。

## TOON 怎么工作的

TOON 去掉 JSON 为机器解析所需的结构脚手架——括号、引号、逗号、重复的类型声明——这些对 LLM 不增加任何语义价值。

| JSON | TOON | 原理 |
|---|---|---|
| `{"name":"search","count":3}` | `name:search\|count:3` | 竖线替代花括号+引号+冒号 |
| `[1, 2, 3]` | `1 2 3` | 空格替代方括号+逗号 |
| `true` / `false` | `T` / `F` | 1 字符 vs 4-5 字符 |
| `null` | `∅` | 1 符号 vs 4 字符 |
| `"第一行\n第二行"` | `第一行↲第二行` | ↲ 替代转义序列 |
| `{"a":{"b":[1,2]}}` | `a:b:1_2` | 递归压缩 |

AI 拿到的是同样的数据，可以从 TOON 完整重建结构。我们只是不再让你为 `{"type":"object","properties":` 反复付 token 了。

## 输出格式

| Flag | 输出 | Token 用量 |
|---|---|---|
| `--toon` | 紧凑编码，完整语义 | 比 JSON 省 40-60% |
| `--slim` | 超紧凑工具 schema (name\|param:type*) | 比 JSON 省 **93%** |
| `--compact` | 仅工具名，空格分隔 | 比 JSON 省 97% |
| `--json` | 标准 JSON（脚本、CI 用） | 基准线 |
| `--raw` | 原始响应，不解析 | 全量 |
| `--head N` | 仅前 N 条 | 可变 |
| `--max-chars N` | 硬截断到 N 字符 | 可变 |
| `--full` | 禁用默认 4000 字符截断 | 全量 |

设 `MCPTOON_AGENT_TYPE=claude`，所有调用自动用 `--toon`，不用手动加 flag。

### SLIM 模式 (v0.2.2+)

当你需要工具 schema 但想最大化节省 token 时，用 `--slim`：

```bash
$ mcptoon manifest --slim
search|q:s*|n:n
fetch|url:s*
create|meta:o{title,tags}|tags:a[s]
```

格式：`tool_name|param:type*|param:type`
- `s`=字符串 `n`=数字 `b`=布尔 `a[type]`=数组 `o{keys}`=对象
- `*` 标记必填参数
- 描述和 schema 包装已去除

**比 JSON 省 93% token**。适合需要知道参数类型但不想浪费 token 的 LLM Agent。

## 示例

### GitHub 仓库搜索 — 287 → 115 token（省 60%）

```
$ mcptoon call github search_repos '{"query":"mcp"}' --toon
total_count:234|items:name:mcp-server|full_name:anthropic/mcp-server|stargazers_count:1234|description:Official_MCP_server name:mcp-client|full_name:anthropic/mcp-client|stargazers_count:567|description:MCP_client_library
```

```
$ mcptoon call github search_repos '{"query":"mcp"}' --compact
mcp-server mcp-client
```

### 96 个工具的清单发现 — 2,034 → 62 token（省 97%）

```
$ mcptoon manifest --toon
fetch:fetch filesystem:read_file filesystem:write_file github:search_repos github:create_issue ...
```

你的 Agent 知道所有 96 个可用工具，还剩 97% 的上下文去实际使用它们。

### 网页抓取 — 去掉 MCP 包装

```
$ mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
<!DOCTYPE html><html><head><title>Example</title>...</html>
```

没有 `{"content":[{"type":"text","text":"..."}]}` 包装。只有内容。

## 架构 —— 三层解耦

mcptoon 基于**三层解耦架构**。每一层独立——换一层不碰其他层。

```
┌─────────────────────────────────────────────────┐
│  第 1 层: mcptoon CLI (~50KB, 零依赖)            │
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

- **第 1 层 (CLI)** 保持极小——50KB，零依赖。没有 MCP SDK 臃肿。
- **第 2 层 (Profile)** 是可编辑 JSON——加、删、fork 不碰代码。每个 ~1KB 文件只描述*怎么连接*，不是服务器本身。
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

### Claude Code

```bash
export MCPTOON_AGENT_TYPE=claude   # 自动用 --toon
```

```markdown
# ~/.claude/skills/mcp-tools/SKILL.md

搜索网页：
`mcptoon call exa search '{"query":"AI 新闻"}'`

列出可用工具：
`mcptoon manifest --toon`

抓取 URL：
`mcptoon call fetch fetch '{"url":"https://example.com"}'`
```

### Codex (OpenAI)

```markdown
# AGENTS.md 或 system prompt

用 mcptoon 调用 MCP 工具，比 JSON 省 60% token。

- 列出工具：`mcptoon manifest --toon`
- 调用工具：`mcptoon call <server> <tool> '{"args":"here"}' --toon`
- 查看工具详情：`mcptoon inspect <server> <tool>`
```

### OpenCode

```bash
# OpenCode 配置或 system prompt
export MCPTOON_AGENT_TYPE=claude
```

```
## 可用 MCP 工具
运行 `mcptoon manifest --toon` 查看所有工具。
运行 `mcptoon call <server> <tool> '<json_args>' --toon` 调用工具。
```

### 为什么要统一一层？

没有 mcptoon，你得给每个 Agent 单独配 MCP 服务器——Claude Code 的 `claude_desktop_config.json`、Cursor 的 MCP 设置、OpenCode 的配置……同样的服务器，不同的格式，不同的设置。

有了 mcptoon，配一次就行。`~/.mcptoon/config.json` 是唯一的配置源。每个 Agent 都用同样的 `mcptoon` 命令。加个服务器，所有 Agent 立刻看到。删个服务器，到处都没了。

而且：不管用哪个 Agent，每次调用工具发现省 97%、工具结果省 40-60%。

## Python API

```python
from mcptoon.client import MCPClient
from mcptoon.output import toon

with MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-fetch"]) as c:
    tools = c.list_tools()
    print(toon(tools))         # 紧凑 TOON
    result = c.call_tool("fetch", {"url": "https://example.com"})
    print(toon(result))
```

## 自定义 Handler — 绕过 MCP

```python
from mcptoon.router import register

@register("my-database", "db")
def handle_db(tool, args):
    if tool == "query":
        return {"rows": my_db.execute(args["sql"])}
    return None  # 回退到 MCP
```

`mcptoon call db query '{"sql":"SELECT * FROM users"}'` 直接到你的 handler，不需要 MCP 服务器。

## 🌐 生态建设

mcptoon 不只是 CLI 工具——它是一个 **token 高效的 MCP 生态系统**：

| 组件 | 是什么 | 状态 |
|------|--------|------|
| 📦 **[服务器 Profile](mcp/README.md)** | 23 个现成 MCP 服务器 Profile（186+ 工具） | 23 → 100+ |
| 🔧 **TOON 格式** | Token 优化标记法（开放规范） | v1 内置于 mcptoon → 独立规范 |
| 📚 **集成指南** | Agent 专属配置文档 | 10 个 Agent 规划中 |
| 🏷️ **Powered by 徽章** | MCP 服务器使用 mcptoon 的标识 | 即将推出 |
| 🔌 **多语言 SDK** | JS/Go/Rust 的 TOON 实现 | v1.0 后 |

**参与贡献：** 添加 Profile · 写集成指南 · 在你的语言中实现 TOON

→ **[完整生态计划](ECOSYSTEM.md)**

---

## 配置

```bash
# stdio（任何 npx MCP 服务器）
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# HTTP
mcptoon add myapi --http http://localhost:3001/mcp --header "Authorization: Bearer xxx"
```

配置文件在 `~/.mcptoon/config.json`。项目级覆盖在 `./.mcptoon.json`。环境变量 `MCPTOON_SERVERS`（JSON 字符串）优先级最高。

```json
{
  "servers": {
    "fetch": {
      "transport": "stdio",
      "command": ["npx", "-y"],
      "args": ["@modelcontextprotocol/server-fetch"]
    },
    "github": {
      "transport": "stdio",
      "command": ["npx", "-y"],
      "args": ["@modelcontextprotocol/server-github"],
      "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"}
    }
  }
}
```

## 安全

mcptoon 三层安全防护：

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

$ mcptoon call db delete_table '{"name":"users"}'
Error [CONFIRMATION_REQUIRED]: Dangerous operation needs confirmation

$ mcptoon call db delete_table '{"name":"users"}' --destructive
# 执行
```

没有意外。不会被一个过于有创造力的 AI Agent 导致数据丢失。凭据不会因为 MCP 工具返回结果而泄露。

## 用量统计

```bash
$ mcptoon usage
Total calls: 142
Success rate: 138/142
Tokens (est): 84,200

By server:
  fetch       89
  github      53

Top tools:
  fetch:fetch             45
  github:search_repos     38
```

存储在本地 `~/.cache/mcptoon/usage.json`。永不传输。

## 架构

```
src/mcptoon/
├── cli.py        # CLI 入口 + 参数解析
├── client.py     # MCPClient — stdio + HTTP 传输, MCPClientPool
├── router.py     # 工具调用路由, 自定义 handler, 注入防护 + 凭据泄露检测
├── config.py     # 服务器配置 (~/.mcptoon/config.json + 覆盖)
├── manifest.py   # 工具发现 (带缓存)
├── output.py     # TOON / JSON / compact 渲染
├── cache.py      # Schema 缓存 (5分钟 TTL)
├── usage.py      # 本地用量统计
└── errors.py     # 结构化错误封装
```

总共约 2,500 行。187 个测试。零第三方 import。唯一的网络调用是到你配置的 MCP 服务器。

## 隐私

- **没有遥测。** 没有分析，没有崩溃报告，没有回传。什么都不离开你的机器。
- **不存凭证。** API key 从你的配置或环境变量直接传递。永不记录，永不缓存。
- **没有依赖。** 纯 Python 标准库。没有供应链要审计，没有包会被劫持，没有更新要追。
- **凭据泄露检测。** 扫描工具返回结果中的暴露 API key/token —— 在进入 Agent 上下文前拦截。

本地文件：`~/.mcptoon/config.json`（你的配置）、`~/.cache/mcptoon/schema_cache.json`（5 分钟缓存）、`~/.cache/mcptoon/usage.json`（统计）。删掉任何一个，mcptoon 按需重建。

发现安全漏洞？发邮件到 `security@activeing123.github.io`，不要公开提 issue。48 小时回复，7 天修复。见 [SECURITY.md](SECURITY.md)。

## 许可证

Apache 2.0。商业使用、修改、分发都行。保留 LICENSE 和 NOTICE 文件，声明你的修改。TOON 格式是开放的——你可以在自己的工具中实现，只需署名 mcptoon。见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。

## 贡献

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 187 个测试, 0.2s
```

零依赖是硬规则。新功能需要测试。见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

*mcptoon 是独立的第三方 MCP 客户端，不隶属于 Anthropic。*
