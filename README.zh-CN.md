# mcptoon

<p align="center">
  <strong>别再给 LLM 喂 JSON 了。每次 MCP 工具调用省 40-60% token。</strong>
</p>

<p align="center">
  <a href="#安装"><img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue.svg" /></a>
  <a href="https://pypi.org/project/mcptoon/"><img alt="PyPI" src="https://img.shields.io/pypi/v/mcptoon.svg" /></a>
  <a href="LICENSE"><img alt="Apache 2.0" src="https://img.shields.io/badge/license-Apache%202.0-green.svg" /></a>
  <a href="#为什么选-mcptoon"><img alt="零依赖" src="https://img.shields.io/badge/依赖-零-orange.svg" /></a>
  <a href="README.md">English</a>
</p>

---

## 问题是什么？

你在用 [MCP](https://modelcontextprotocol.io/) 服务器——搜索、抓取、文件系统、GitHub——每次 AI Agent 调用工具，返回的都是一大坨 JSON。这些 JSON 吃掉你的上下文窗口。96 个工具的清单？**2,000+ token。** 搜索结果？**3,000+ token。** Agent 还没开始思考，上下文已经用了一半。

## 怎么解决？

**mcptoon** 是一个 CLI 客户端，可以连任何 MCP 服务器——但输出 **TOON**，一种 token 高效编码格式，压缩 JSON 40-60%：

```
❌ JSON（2,034 token）:
  [{"name":"search","description":"Search the web..."},
   {"name":"fetch","description":"Fetch a URL..."},
   {"name":"crawl","description":"Crawl a site..."}]

✅ TOON（812 token）:
  search fetch crawl
```

同样的数据。同样的语义。**token 少了 60%。**

## 为什么选 mcptoon？

| | mcptoon | 其他 MCP 客户端 |
|---|---|---|
| **输出格式** | TOON（省 40-60%） | 只有 JSON |
| **依赖** | **零**（纯标准库） | 5-20 个包 |
| **stdio 传输** | ✅ | ✅ |
| **HTTP 传输** | ✅（SSE + 会话） | 部分支持 |
| **安全防护** | 危险操作拦截 | ❌ |
| **用量统计** | ✅ | ❌ |
| **Schema 缓存** | ✅（5分钟 TTL） | ❌ |
| **自定义 Handler** | ✅（绕过 MCP） | ❌ |
| **Windows 支持** | ✅ | 经常坏 |

## 安装

```bash
pip install mcptoon
```

就这一步。零依赖，零配置。需要 Python 3.10+。

## 30 秒上手

```bash
# 1. 初始化示例服务器配置
mcptoon init

# 2. 添加任意 MCP 服务器——npx 开箱即用
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# 3. 查看所有工具（一行，约 15 token）
mcptoon manifest --toon
# → fetch:fetch

# 4. 调用工具——TOON 输出省 token
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon

# 5. 需要 JSON 给脚本用？一个 flag
mcptoon call fetch fetch '{"url":"https://example.com"}' --json
```

## TOON 格式——怎么工作的？

TOON（Token-Optimized Object Notation，token 优化对象编码）去掉了 JSON 的结构冗余，同时保留完整的语义信息：

| Python 值 | JSON | TOON | 省了 |
|---|---|---|---|
| `{"name":"search","count":3}` | `{"name":"search","count":3}` | `name:search|count:3` | 33% |
| `[1, 2, 3]` | `[1, 2, 3]` | `1 2 3` | 50% |
| `True` / `False` | `true` / `false` | `T` / `F` | 60% |
| `None` | `null` | `∅` | 50% |
| `"第一行\n第二行"` | `"第一行\n第二行"` | `第一行↲第二行` | — |

**真实场景——96 个工具的清单：**

```
JSON:     2,034 token
TOON:       812 token  ← 省 60%
Compact:     62 token  ← 省 97%（仅名称）
```

## Agent 集成

设一个环境变量，mcptoon 自动选择最优格式：

```bash
# Claude Code、CatPaw、Anthropic Agent（对 token 敏感）
export MCPTOON_AGENT_TYPE=claude   # → 自动 --toon

# OpenAI、脚本、CI 流水线
export MCPTOON_AGENT_TYPE=openai   # → 自动 --json

# 人类终端使用
export MCPTOON_AGENT_TYPE=human    # → 自动（友好打印）
```

### 在 Claude Code / CatPaw 技能文件中使用：

```markdown
用 Exa 搜索网页：
`mcptoon call exa search '{"query":"AI新闻"}' --toon`

列出可用工具：
`mcptoon manifest --toon`
```

你的 Agent 用一半的 token 拿到同样的信息。**这意味着：更长的对话、更多的工具调用、更低的成本。**

## 服务器配置

### stdio（大多数 MCP 服务器）

```bash
# 任何基于 npx 的 MCP 服务器——零摩擦
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github
```

### HTTP

```bash
mcptoon add myapi --http http://localhost:3001/mcp --header "Authorization: Bearer xxx"
```

### 配置文件：`~/.mcptoon/config.json`

```json
{
  "servers": {
    "fetch": {
      "transport": "stdio",
      "command": ["npx", "-y"],
      "args": ["@modelcontextprotocol/server-fetch"]
    },
    "myapi": {
      "transport": "http",
      "url": "http://localhost:3001/mcp",
      "headers": {"Authorization": "Bearer xxx"}
    }
  }
}
```

## 安全第一

mcptoon 默认拦截危险操作：

```bash
# ❌ 被拦截——"delete" 匹配危险模式
mcptoon call db delete_table '{"name":"users"}'
# Error [CONFIRMATION_REQUIRED]: Dangerous operation needs confirmation

# ✅ 需要显式确认
mcptoon call db delete_table '{"name":"users"}' --destructive
```

危险模式：`delete`、`remove`、`drop`、`destroy`、`purge`、`wipe`、`kill`、`force=true`、`confirm=true`。

## 用量分析

```bash
mcptoon usage
```

```
Total calls: 142
Success rate: 138/142
Tokens (est): 84,200

By server:
  fetch                   89
  github                  53

Top tools:
  fetch:fetch             45
  github:search_repos     38
```

## 进阶：自定义 Handler

对特定服务器完全绕过 MCP——直接调用任何 API：

```python
from mcptoon.router import register

@register("my-database", "db")
def handle(tool, args):
    if tool == "query":
        return {"rows": my_db.execute(args["sql"])}
    return None  # 回退到 MCP
```

## 架构

```
src/mcptoon/
├── cli.py        # 入口 + 参数解析
├── client.py     # 通用 MCP 客户端（HTTP + stdio）
├── router.py     # 工具调用路由 + 自定义 Handler
├── config.py     # 服务器配置管理（~/.mcptoon/config.json）
├── manifest.py   # 工具发现
├── output.py     # TOON / JSON / compact 渲染 ← 核心
├── cache.py      # Schema 缓存（5分钟 TTL）
├── usage.py      # 用量统计
└── errors.py     # 结构化错误封装
```

**零第三方依赖。** 纯 Python 标准库。任何有 Python 3.10+ 的系统都能装。

## 与其他工具对比

| 功能 | mcptoon | mcp-cli（代理模式） | mcporter |
|---|---|---|---|
| 输出格式 | TOON + JSON + compact | 只有 JSON | 只有 JSON |
| 依赖 | **0** | 代理服务器 + SDK | npm 生态 |
| stdio 传输 | ✅ | ❌ | ✅ |
| HTTP 传输 | ✅ | ✅（代理） | ✅ |
| Token 优化 | **40-60%** | 0% | 0% |
| 安全防护 | ✅ | ❌ | ❌ |
| 用量统计 | ✅ | ❌ | ❌ |
| Schema 缓存 | ✅ | ❌ | ❌ |
| Windows 支持 | ✅ | 经常坏 | ✅ |

## 贡献

参见 [CONTRIBUTING.md](CONTRIBUTING.md)。欢迎 PR！

## 许可证

Apache License 2.0——详见 [LICENSE](LICENSE)。商业使用 OK，修改 OK，但**必须保留署名**。

---

<p align="center">
  <sub>由受够了 JSON 吃掉上下文窗口的开发者构建。</sub><br>
  <sub>★ 如果 mcptoon 帮你省了 token，给个 Star。</sub>
</p>
