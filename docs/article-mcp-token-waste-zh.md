---
title: MCP 正在浪费 4-32 倍的 Token——以及怎么修
published: false
description: 255 个 MCP 工具还没干活就吃掉 71,929 个 token，而一份纯名称清单只要 581 个。证据、算账和今天就能跑起来的修复方案，都在这篇文章里。
tags: mcp, ai, llm, python
---

先看两个数字，看完你今天的咖啡可能会凉半截：

**71,929 个 token** 对 **581 个 token**。同样的 255 个工具，同一台机器，同一天。

前一个数，是 50 个 MCP 服务器的全部工具以原始 JSON schema 的形式加载进上下文窗口时，你的 agent 每个会话都要付的价格。后一个数，是同样这份工具列表改用 CLI 发现机制后的成本。

换句话说：**一本 300 页的书 vs 一张便利贴**——每个会话一次，而且是在你的 agent 回答第一个问题之前就扣掉了。如果你在 Claude Code、Cursor 或类似工具里挂着多个 MCP 服务器，你现在就在按"书的价钱"付费，只是大概率没人告诉你。

我一开始也不信，所以用 tiktoken（OpenAI 官方分词器）亲手量了一遍，然后围绕这个结果做了个工具。下面把账本摊开给你看。

## 问题出在哪：每个工具都带着全套简历进场

Agent 连上 MCP 服务器时，服务器会递过来一份工具目录，每一项长这样：

```json
{
  "name": "search_repos",
  "description": "Search GitHub repositories by query",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The search query"
      },
      "per_page": {
        "type": "number",
        "description": "Results per page (default 30)"
      }
    },
    "required": ["query"]
  }
}
```

这只是一个工具。把每个参数、每段描述、每个嵌套的 `properties` 都乘上去，再乘以 255 个工具——协议对"你都能干什么"这个问题的回答，是一整份 API 参考文档，连类型带默认值带散文式描述，原封不动灌进上下文窗口。

关键是：**这些 schema 每个会话真正被用到只有两次**——模型挑工具的时候，以及填参数的时候。剩下 99% 的时间里，那面 7 万 token 的墙就杵在那儿占着黄金地段，让你的代码、对话历史和推理链在剩下的空间里抢地盘。

这不是小众问题。[Firecrawl 团队 2026 年把 MCP 和普通 CLI 方式做了基准对比](https://firecrawl.dev/blog/mcp-vs-cli)：**同样的任务，CLI 大约花 ~200 token，MCP 要花 ~44K token**——根据任务形态不同，开销是 **4 到 32 倍**。[Scalekit 的独立分析](https://scalekit.com/blog/mcp-vs-cli-use)得出了同一个头条结论：同样的活儿，最多多付 32 倍的 token。

## 为什么这事真的大（不只是好看不好看的问题）

"token 贵"是最直觉的反驳，但真实的账比直觉更难看——因为 schema 开销不是一次性费用，它跟着**每一次请求**走。

在 **128K 上下文窗口**（Claude Sonnet、GPT-4o 这一档）里，71,929 个 token 的工具定义光语法就吃掉 **约 56% 的窗口**。第一句用户消息还没处理，一半以上的上下文已经没了。留给代码库、对话历史、推理链的空间只剩下一半——于是 agent 开始退化、忘掉前面的指令、更早截断文件内容。

在 **64K 窗口**（便宜快速的模型很常见）上，这就不是"更糟一点"的问题了，而是**数学上直接不可能**：工具根本装不下。要么把你辛辛苦苦配置好的服务器卸载掉腾地方，要么纯粹为了装下样板 JSON 去买大窗口的贵模型。第二条路才是安静的烧钱机器：你实际上是在订阅一个更大的模型，专门用来*扛 JSON*。

而且 schema 会随每个请求重复进入上下文，浪费是复利的。按主流模型定价算，几万冗余 token × 每会话几十次请求 × 天天开会话，最后都是真金白银花在标点符号和大括号上。没人给这笔开支做预算，因为账单上看不见——它只是……悄悄杀死你的上下文。

## 别光听我说：证据在这

这个故事最好的部分是：这不是我一个人的观点。互相独立的团队从完全不同的方向出发，都撞到了同一堵墙：

| 来源 | 结论 | 视角 |
|------|------|------|
| [SEP-1576](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1576)（MCP 官方提案） | 提出削减 schema 冗余、改进工具选择——协议自己承认膨胀问题 | 标准层 |
| [Anthropic 工程博客 — 用代码执行方式接入 MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) | 按需加载工具可砍掉最高 **98.7%** 的上下文开销（~150K → ~2K token） | 实验室 |
| [Firecrawl](https://firecrawl.dev/blog/mcp-vs-cli) | 同样任务：CLI ≈ 200 token vs MCP ≈ 44K——**4–32 倍开销** | 从业者 |
| [Scalekit](https://scalekit.com/blog/mcp-vs-cli-use) | 独立复核确认了 **32 倍**的最坏情况 | 从业者 |
| [MCP-Zero](https://arxiv.org/abs/2508.12553)（厦门大学 + 中科大） | 按需工具检索让检索成本**与工具总数无关**（恒定成本） | 学术 |
| Microsoft — dynamic tool discovery | Agent 设计指南：运行时动态发现工具，而不是预先塞进所有定义 | 厂商 |
| ProMCP（ACL ARR 2026） | 对 MCP agent 的 token 流和延迟做画像——量化预算到底去哪了 | 学术 |

再读一遍这张表。标准制定方、发明 MCP 的公司、两份从业者基准、两组学术团队，诊断结论完全一致：**急切的全量 schema 注入撑不住规模**。当 Anthropic 自家工程博客都在写如何把 15 万 token 砍到 2 千，"有没有问题"这场辩论已经结束了，剩下的只是"怎么修"。

## 解法：只为名字付费，不为 schema 买单

上面所有方案共享同一个洞察：**模型需要的是索引，不是百科全书。**

这就是 [mcptoon](https://github.com/activeing123/mcptoon) 的思路——我在参与的一个零依赖 CLI。它不把 schema 塞进上下文，而是让工具发现变成一份**纯名称清单**：

```bash
$ mcptoon manifest --compact
fetch: fetch(url) · github: search_repos(q), get_file(repo, path) · sqlite: query(sql) · ...
```

这就是全部列表。255 个工具，581 个 token。完整的 schema 留在磁盘上的 `~/.mcptoon/config.json` 里，**根本不进入上下文**。这一点至关重要——它不是压缩。压缩是把整个载荷发过去之后再解包，字节迟早还是落进你的窗口；而这里 schema 压根就不发送。模型读完索引，判断哪个工具合适，只在需要细节时再去要。

它是个旋钮，不是开关：

| 工具列表形式（tiktoken cl100k_base） | token 数 | 相比原始 JSON |
|--------------------------------------|---------:|--------------:|
| 原始 JSON schema，255 个工具          |   71,929 | —             |
| `--slim`（名称 + 参数类型）           |    8,282 | −88.5%        |
| `--compact`（仅名称）                 |      581 | **−99.2%**    |

*（基于真实环境中横跨 50 个 MCP 服务器的 255 工具配置实测。可用 `mcptoon manifest --compact --tokens` 复现。）*

输出侧同理。工具*结果*可以用 [TOON](https://github.com/toon-format/toon)（一种面向表格的 token 友好记法）编码，典型响应再省 **约 34%**——而且是可选参数，默认关闭，不会有意外。

## 底层是怎么跑的

架构无聊到近乎朴素，而这正是优点：一个小小的 CLI 坐在 **agent 和 MCP 服务器之间**。

```text
Agent ──执行──▶ mcptoon CLI ──仅在调用时拉起──▶ MCP server ──▶ 结果返回
                     │
                     └─ ~/.mcptoon/config.json （schema 就住在这里，磁盘上）
```

agent 会话里的实际流程长这样：

```bash
# 1. 发现：拿到的是名字索引，不是 schema 轰炸
$ mcptoon manifest --compact

# 2. 执行：精确调用某一个工具
$ mcptoon call fetch fetch '{"url":"https://example.com"}'
# CLI 拉起 fetch 服务器 → 执行调用 → 返回结果 → 服务器退出。不留残余。
```

这个设计白送三个性质：

1. **调用之前零服务器常驻。** 没有守护进程、没有代理进程、不占端口。`mcptoon call` 拉起服务器、拿答案、收摊。冷启动几百毫秒；想要长连接的热路径可以切到 `mcptoon serve` 模式。
2. **每个错误都是结构化且可执行的。** 调一个不存在的工具，你会得到 `"server 'fetchh' not found — did you mean 'fetch'?"`——这意味着 *agent 能自我纠正*，而不是卡死在那里等人类来救场。
3. **安全检查免费搭车。** 每个结果进入上下文之前都会过一遍提示注入字符串和密钥模式（`sk-…`、`AKIA…`、`ghp_…`）扫描；危险类工具名需要显式加 `--destructive` 才放行。

而且因为它是 CLI，**任何能执行命令的东西都能用**——包括完全不支持 MCP 的 agent、shell 脚本、CI 任务、定时任务。Shell 是所有 agent 都已经会说的那门语言。

## 60 秒上手

别信我的基准——在你自己的机器上量一遍：

```bash
pip install mcptoon     # 纯标准库，约 250KB，零依赖

mcptoon demo            # 现场并排演示：JSON vs mcptoon，真实 token 数
```

`demo` 会起一个示例 fetch 服务器，用两种方式打印同一份工具列表，并显示在你机器上算出的真实 token 数。无遥测、无账号、没有任何数据离开你的机器——总共约 6,800 行可读的 Python，一个下午就能审完。

如果你已经在各处散落着 MCP 配置，从这条命令开始更顺：

```bash
mcptoon quickstart      # 自动检测已有配置，导入并列出你的工具
```

## 更大的图景：一份配置管住所有 Agent

Token 浪费只是 MCP 征税的一半。另一半是配置漂移：Claude Code 要 `.claude.json`，Cursor 要 `.cursor/mcp.json`，Claude Desktop 要 `claude_desktop_config.json`，Codex 们各有各的花样。在 Cursor 里加了服务器，忘了 Claude；在 Claude 里修了个路径，弄坏了 Cursor。每周循环播放。

mcptoon 把这当成同一个问题：唯一事实来源，处处同步。

```bash
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github
mcptoon sync            # 把原生配置写进每一个检测到的 agent

mcptoon sync --watch    # 轮询配置文件，任何变更自动重新同步
```

`sync` 采用合并而非覆盖策略，你手动配过的服务器原地不动。开了 `--watch` 之后，改任何一处配置都会自动传播到机器上的每个 agent——跨 agent 的 MCP 管理，终于不用再背"哪个文件属于哪个工具"了。

## 点个 Star，使劲折腾，有问题尽管提

说句公道话：MCP 协议本身是好的。标准化的工具访问确实是刚需，生态爆发就是证明。但急切的全量 schema 注入是个错误的默认值，现在所有量过的人都同意这一点。修复模式——索引进上下文、schema 留磁盘、按需取详情——就是整个生态正在走的方向，无论是 SEP-1576 这类官方提案、Anthropic 的代码执行方案，还是朴素的 CLI。

如果你手上多 agent、多服务器并存，值得一试：

- ⭐ 如果这些数字让你心疼，去 GitHub 给 [mcptoon](https://github.com/activeing123/mcptoon) 点个 star——这真的能帮更多人找到它
- 跑一下 `mcptoon demo`，把你自己的前后对比数据贴在评论区——我很想看看你的工具组合要花多少钱
- 尽情提 issue。诡异的服务器？奇怪的配置格式？刁钻的边界情况？issue 区就是为这些存在的

上下文窗口是当今 AI 里最贵的地产。别再让它免费租给大括号住了。

---

*延伸阅读：[SEP-1576 — schema 冗余削减提案](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1576) · [Anthropic：有效的上下文工程与 MCP 代码执行](https://www.anthropic.com/engineering/code-execution-with-mcp) · [MCP-Zero：主动式工具获取](https://arxiv.org/abs/2508.12553)*
