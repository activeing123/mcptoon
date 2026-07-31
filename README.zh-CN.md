<div align="center">

# mcptoon

**MCP 工具发现要 10,000+ token。mcptoon 只要 350。**

*所有 AI Agent 的统一 MCP 客户端。全平台通用。零依赖。*

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/依赖-零-orange)](#隐私)

[English](README.md) · [中文文档](README.zh-CN.md)

</div>

---

一轮典型的 MCP 对话里发生什么：

- 你的 Agent 连接 5 个 MCP 服务器。列出它们的工具：**~10,000 token** 的 JSON——`{"name":"...","description":"...","inputSchema":{"type":"object","properties":{...}}}` 每个工具重复一遍。
- 你的 Agent 调用 20 次工具。每次返回 500-3,000 token，包在 `{"content":[{"type":"text","text":"..."}]}` 里。
- 总计 MCP 开销：**40,000-70,000 token**——括号、引号、逗号、schema 声明——在任何实际思考开始之前。

128K 上下文窗口里，这是 30-55% 直接没了。不是在工作，是在烧语法。

mcptoon 解决这个问题。它是一个 CLI 客户端，连接任何 MCP 服务器（stdio 或 HTTP 传输），但输出 **TOON**（Token-Optimized Object Notation）而不是 JSON。

| 操作 | JSON token | mcptoon token | 省 |
|---|---|---|---|
| 工具发现（96 个工具） | ~2,000 | ~60 | **97%** |
| 工具结果（结构化数据） | ~800 | ~350 | **56%** |
| 工具结果（原始 HTML/文本） | ~1,000 | ~900 | **10%** |

TOON 去掉的是 JSON 语法——括号、引号、逗号、重复的类型声明。剩下的是**真实数据**：仓库名、star 数、搜索结果、网页内容。这些才是你真正需要的。

零依赖，纯 Python，50KB。因为它是 CLI 工具，所以**所有 AI Agent** 都能用——Claude Code、Codex、OpenCode、Cursor、CatPaw，任何能跑 shell 命令的东西。一个配置，一条命令，所有 Agent 都拿到 MCP 访问权限。

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
| `--compact` | 仅工具名，空格分隔 | 比 JSON 省 97% |
| `--json` | 标准 JSON（脚本、CI 用） | 基准线 |
| `--raw` | 原始响应，不解析 | 全量 |
| `--head N` | 仅前 N 条 | 可变 |
| `--max-chars N` | 硬截断到 N 字符 | 可变 |
| `--full` | 禁用默认 4000 字符截断 | 全量 |

设 `MCPTOON_AGENT_TYPE=claude`，所有调用自动用 `--toon`，不用手动加 flag。

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

## 和其他 MCP 客户端比

| | mcptoon | mcp-cli | mcporter | 原生 MCP SDK |
|---|---|---|---|---|
| 省 token | **发现省 97%，结果省 40-60%** | 0% | 0% | 0% |
| 支持所有 Agent | **是**（Claude Code、Codex、OpenCode、Cursor、任意） | 仅 Claude | 仅 Claude | 看情况 |
| 一份配置所有 Agent 共享 | **是** | 否 | 否 | 否 |
| 输出格式 | TOON + JSON + compact | JSON | JSON | JSON |
| 依赖 | **0** | 5-20 | npm | 3-8 |
| stdio 传输（MCP 服务器） | 有 | 无 | 有 | 有 |
| HTTP 传输（MCP 服务器） | 有 | 有（代理） | 有 | 有 |
| 危险操作拦截 | 有 | 无 | 无 | 无 |
| 用量统计 | 有（本地） | 无 | 无 | 无 |
| Schema 缓存 | 有（5分钟） | 无 | 无 | 无 |
| 自定义 Handler | 有 | 无 | 无 | 无 |
| 安装体积 | ~50KB | ~50MB+ | ~30MB | ~10MB |
| 平台支持 | **Windows、macOS、Linux** | Linux/macOS | macOS | 看情况 |

同样的 MCP 服务器，同样的 MCP 协议，同样的结果。工具发现省 97%，工具结果省 40-60%。Windows、macOS、Linux 全平台通用。

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

mcptoon 拦截匹配危险模式的操作（`delete`、`drop`、`purge`、`wipe`、`kill`、`force=true`、`confirm=true` 等），除非你显式传 `--destructive`。

```bash
$ mcptoon call db delete_table '{"name":"users"}'
Error [CONFIRMATION_REQUIRED]: Dangerous operation needs confirmation

$ mcptoon call db delete_table '{"name":"users"}' --destructive
# 执行
```

没有意外。不会被一个过于有创造力的 AI Agent 导致数据丢失。

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
├── router.py     # 工具调用路由, 自定义 handler, 安全检查
├── config.py     # 服务器配置 (~/.mcptoon/config.json + 覆盖)
├── manifest.py   # 工具发现 (带缓存)
├── output.py     # TOON / JSON / compact 渲染
├── cache.py      # Schema 缓存 (5分钟 TTL)
├── usage.py      # 本地用量统计
└── errors.py     # 结构化错误封装
```

总共约 1,700 行。零第三方 import。唯一的网络调用是到你配置的 MCP 服务器。

## 隐私

- **没有遥测。** 没有分析，没有崩溃报告，没有回传。什么都不离开你的机器。
- **不存凭证。** API key 从你的配置或环境变量直接传递。永不记录，永不缓存。
- **没有依赖。** 纯 Python 标准库。没有供应链要审计，没有包会被劫持，没有更新要追。

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
python -m pytest tests/ -v   # 98 个测试, 0.09s
```

零依赖是硬规则。新功能需要测试。见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

*mcptoon 是独立的第三方 MCP 客户端，不隶属于 Anthropic。*
