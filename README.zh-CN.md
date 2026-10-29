<!-- mcp-name: io.github.activeing123/mcptoon -->
<div align="center" markdown="1">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/activeing123/mcptoon/main/docs/assets/lockup-h-split-dark.svg">
  <img src="https://raw.githubusercontent.com/activeing123/mcptoon/main/docs/assets/lockup-h-split-light.svg" alt="mcptoon" height="88">
</picture>

<h3 align="center">所有 Agent 的 MCP 工具与技能，一处搞定。</h3>

<p align="center">
  <b>你在任意一个 Agent 里配好的工具和技能，Cursor、Claude Code、Codex 等覆盖 103+ 款主流桌面与终端 Agent 都能直接用。</b><br>
  首创开箱即用的按需拉取机制，不再把 Schema 堆满会话，<b>立省 99% Token 上下文</b>。<br>
  零依赖，纯本地，不上云。
</p>

<!-- 核心权威徽章 -->
<p align="center">
  <a href="https://pypi.org/project/mcptoon/"><img src="https://img.shields.io/pypi/v/mcptoon?style=flat-square&color=238636&logo=pypi&logoColor=white" alt="PyPI 版本"></a>
  <a href="https://github.com/activeing123/mcptoon/stargazers"><img src="https://img.shields.io/github/stars/activeing123/mcptoon?style=flat-square&logo=github&color=58a6ff" alt="GitHub Stars"></a>
  <a href="https://github.com/activeing123/mcptoon/actions"><img src="https://img.shields.io/github/actions/workflow/status/activeing123/mcptoon/ci.yml?branch=main&style=flat-square&logo=githubactions&logoColor=white" alt="CI 构建"></a>
  <a href="#贡献指南"><img src="https://img.shields.io/badge/tests-3029%20passed-success?style=flat-square&logo=pytest&logoColor=white" alt="测试"></a>
  <a href="https://github.com/activeing123/mcptoon"><img src="https://img.shields.io/badge/dependencies-0%20(stdlib%20only)-blue?style=flat-square" alt="零第三方依赖"></a>
  <a href="https://github.com/activeing123/mcptoon/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-informational?style=flat-square" alt="许可证"></a>
</p>

<!-- 生态与目录收录徽章 -->
<p align="center">
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP_Spec-2026--07--28-blueviolet?style=flat-square" alt="MCP 规范"></a>
  <a href="https://allmcps.com/mcp/mcptoon?verify=7eb0d0d6-5d4e-41a3-a048-2fe3c91a36ed"><img src="https://img.shields.io/badge/AllMCPs-已收录-orange?style=flat-square" alt="AllMCPs"></a>
  <a href="https://mcpvault.io/servers/mcptoon/health"><img src="https://img.shields.io/badge/MCPVault-已认证-purple?style=flat-square" alt="MCPVault"></a>
  <a href="https://mcpservers.org/servers/activeing123/mcptoon"><img src="https://img.shields.io/badge/mcpservers.org-已收录-blue?style=flat-square" alt="mcpservers.org"></a>
</p>

<p align="center">
  <b><a href="https://mcptoon.github.io/">🌐 官方网站</a></b> · 
  <b><a href="https://mcptoon.github.io/tools/token-tax/zh/">🧮 30秒 Token 浪费计算器</a></b> · 
  <b><a href="https://github.com/activeing123/mcptoon/blob/main/README.md">🇺🇸 English README</a></b> · 
  <b><a href="https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md">📖 开发者文档</a></b>
</p>

<!-- 现代化 Benchmark SVG -->
<p align="center">
  <img src="https://raw.githubusercontent.com/activeing123/mcptoon/main/assets/benchmark.svg" alt="mcptoon Benchmark: 71,929 to 581 tokens (-99.2%)" width="100%" style="max-width: 960px; border-radius: 12px; margin: 16px 0;">
</p>

<p align="center">
  <sub>怀疑 255 工具是合成样本？<a href="https://github.com/activeing123/mcptoon/blob/main/docs/real-world-benchmark.md">这里有 7 个真实公开 MCP 服务器（209 工具）在真机上的实测 →</a>——640,606 → 905 token（−99.86%）。或者在你自己的目录上跑 <code>mcptoon bench</code>。</sub>
</p>

<!-- 产品演示视频。必须写成独占一行的裸地址（bare URL）：
     GitHub 会把这种形式改写成带签名的可播放播放器。若包进显式 video HTML 标签
     则不会被改写，Chrome 会拒绝那个会 302 跳转的 github.com 原始地址。 -->
https://github.com/user-attachments/assets/a40bff9a-7f47-4bd2-84ec-04508e5b2a81

<table>
<tr>
<td align="center" width="33%" valign="top">
<br><b>① 💥 工具、技能、文档太吃 token，不敢多装？</b><br><br>
装再多也不怕。工具 schema <b>7.2 万 → 581 token</b>。<br>
<sub>工具 −99.2% · 技能 −99.99% · 文档 4 万→1.7 万/次</sub>
</td>
<td align="center" width="33%" valign="top">
<br><b>② 🧩 装了好几个 Agent，配置 JSON 和技能两头都繁琐？</b><br><br>
它是<b>原生 CLI</b>：只要 Agent 能跑 shell 命令，就支持<b>全部功能</b>——不用起 MCP 服务、不用配置。<code>sync</code> 再帮 GUI 客户端写好 JSON（共 <b>103+ 款</b>）。<br>
<sub>不改 JSON、不重启</sub>
</td>
<td align="center" width="33%" valign="top">
<br><b>③ 🔍 面对全网成千上万个 MCP 工具，不知道哪个真好用？</b><br><br>
不用去网上到处翻安装教程。先<b>一键扫描接管你电脑里已有的工具</b>，剩下的直接用大白话搜索，一键安装、当场调用。<br>
<sub><code>mcptoon discover</code>（扫已装）→ <code>search</code>（搜全网）→ <code>call</code>（直接调）</sub>
</td>
</tr>
</table>

<p align="center">
  <sub>还内置：全网 API 即插即用 · 一键登录授权 (OAuth) · 现成模板直读 · 快捷别名直连 · 代码沙箱防搞坏电脑 — <a href="#all-commands">详见全部命令</a>。</sub>
</p>

<p align="center">
  <b><code>pip install mcptoon &amp;&amp; mcptoon quickstart</code></b> — 561KB，零依赖，零配置。
</p>

<p align="center">
  <sub>装完会自动提示有新版，一条命令 <code>mcptoon upgrade</code> 即更新。</sub>
</p>

<!-- 核心痛点与长尾场景速查 (SEO & Fast Navigation) -->
<details>
<summary><b>🔍 常见痛点场景与解决方案速查（按需展开）</b></summary>
<br>
<table>
<tr><th>你的痛点场景 / 搜索意图</th><th>传统 MCP 的痛点</th><th>mcptoon 的优雅解法</th></tr>
<tr><td><b>上下文被挤爆 (Context Window Bloat)</b><br>装了 10+ 工具，问两句就提示 Context Limit 超限</td><td>每个工具的完整 JSON Schema 每轮重发（动辄 7 万+ Tokens）</td><td><b>紧凑名字索引</b>：常驻仅 ~2.2 Tokens/工具，调用时毫秒级按需拉取单个参数定义（立省 99.2%）</td></tr>
<tr><td><b>多客户端重复配置 (Multi-Agent Sync)</b><br>在 Cursor、Claude Code、Windsurf 间重复手写配置</td><td>每个客户端的 <code>mcpServers</code> 配置文件手动复制粘贴，容易漏配</td><td><b>一键接管全部</b>：<code>mcptoon sync --takeover</code> 自动扫描、一键同步全部 103+ 款客户端</td></tr>
<tr><td><b>命令行终端直调 (Headless MCP CLI)</b><br>只想在终端或自动化脚本里调某个工具，不想开重型 UI</td><td>必须启动完整的桌面 Agent 或编写专门的 Python 测试代码</td><td><b>纯标准库原生 CLI</b>：<code>mcptoon call &lt;server&gt; &lt;tool&gt;</code> 零依赖即开即调</td></tr>
<tr><td><b>候选工具过多导致模型变蠢 (Model Confusion)</b><br>候选工具超过 40 个，模型注意力分散、选错工具或产生幻觉</td><td>所有 Schema 一股脑塞给大模型，严重干扰业务思考</td><td><b>两阶段离线挑选</b>：<code>mcptoon select "&lt;任务&gt;"</code> 秒级锁定最匹配的 Top 3 工具给模型</td></tr>
<tr><td><b>跨 Agent 技能共享 (Agent Skills Hub)</b><br>好用的提示词规则与私有技能无法在各个 Agent 之间流通</td><td>各个项目目录手动拷贝多份，维护困难、版本互相漂移</td><td><b>单源软链分发 + 版本门禁</b>：<code>mcptoon skills sync</code>，常驻指针仅 39 Tokens，零拷贝零漂移</td></tr>
</table>
</details>

</div>

---

### 🚀 快速上手（选择你喜欢的方式）

<table>
<tr>
<td width="50%" valign="top">

<h4>🤖 现代化方式：直接跟 Agent 对话（免记命令）</h4>

mcptoon 安装后**会自动将官方技能（`/mcptoon`）注入到所有检测到的 Agent 目录中**。小白完全不需要背诵任何命令，在 **Cursor, Claude Code, Windsurf, DSH** 聊天框直接对话：

```markdown
# 随时唤醒内置技能，有问题直接问：
"加载 /mcptoon 技能，看一下我现在都有哪些 MCP 工具？"
"帮我找一个能把网页转成 Markdown 的 MCP 工具并执行。"
"刚才工具返回的日志被截断了，用 mcptoon 把完整原件调出来。"
"算一下今天 mcptoon 帮我省了多少 Token？"
"帮我体检自查一下：所有 MCP 服务器连通性正常吗？"
```
*Agent 会自动调取 `/mcptoon` 技能手册，在后台替你完成所有操作！*

</td>
<td width="50%" valign="top">

<h4>⚡ 终端极客方式：30 秒搞定</h4>

```bash
# 1. 一键安装（零依赖，561KB）
pip install mcptoon

# 2. 一键检测并自动配置已安装的 Agent
# （同时自动将 `/mcptoon` 技能分发到各大 Agent 目录中）
mcptoon quickstart

# 3. 查看极简工具索引（省 99.2% Token）
mcptoon manifest

# 4. 路由任务对应的技能或规范章节（<5ms）
mcptoon skills resolve "写 git 提交信息"
mcptoon docs resolve "版本发布门禁怎么运作"
```

</td>
</tr>
</table>

**它到底在不在帮你省？** 新装后 mcptoon 可能停在 **直连** 状态——装了但没接进 Agent，一分不省。看 [哪种模式最省？](#哪种模式最省)，或直接跑 `mcptoon mode`。

### ⚡ 全能力全景速览

| 💥 省 token（为什么 ①） | 🧩 配一次，全 Agent 通用（为什么 ②） |
| :--- | :--- |
| • ✅ **名字索引瘦身 (−99.2%)**：255 个工具 → **581 token**，完整 schema 用时才拉<br>• ✅ **结果无损压缩**：可逆，任何句柄都能 `retrieve` 取回原文<br>• ✅ **会话内去重**：同一轮里一模一样的输出自动变引用<br>• ✅ **技能同样处理**：一个 39 token 指针 + 一次查询，替掉每个 `SKILL.md`<br>• ✅ **文档也压**：`docs` 投喂 1 章而非 19 章 —— **每次查询 4 万 → 1.7 万 token**<br>• ✅ **数字不虚标**：`bench` 用真 `tiktoken` 核算 | • ✅ **原生 CLI**：只要 Agent 能跑 shell，跑 `mcptoon` 就拿到**全部功能** —— 不用起服务、不用配置<br>• ✅ **GUI 客户端也行**：`sync` 帮你写好 JSON —— Claude、Cursor、Cline、Windsurf、VS Code、Claude Code，**本机 6 个，共支持 103+ 款**<br>• ✅ **已核实清单**：42 款直接跑 CLI，61 款挂一个 `mcptoon serve` 入口<br>• ✅ **技能也同步**：一套目录分发到每个 Agent 的文件夹（`skills sync`）<br>• ✅ **已有的直接导入**：从 Claude / Cursor / Cline / Windsurf 拉服务器<br>• ✅ **一条命令起步**：`quickstart` = 发现 + 配置 + 列出工具<br>• ✅ **细粒度控制**：`toggle` 开关、`policy` 定每个工具的输出档、技能用 `--version-gate` / `--tombstone` |

| 🔍 发现与调用（为什么 ③） | 🔌 不只是 MCP：直通任意 API |
| :--- | :--- |
| • ✅ **跨生态全网检索**：大白话 `search` 搜索 17,000+ 个 MCP 服务器注册表，找工具不迷路<br>• ✅ **先捡已装的**：`discover` 扫现有客户端配置 —— **无需重装**<br>• ✅ **调什么都行**：`call` 直调，或 `call --auto` 自动找服务器<br>• ✅ **参数按需拉**：`inspect` 只在真要调时拉 schema<br>• ✅ **按任务挑**：`select "<任务>"` 只回最相关的几个<br>• ✅ **随处导出**：`manifest --format openai\|openapi\|mcp` | • ✅ **OpenAPI / Swagger**：任意 REST API 变命令（`openapi list\|call`）<br>• ✅ **GraphQL**：任意端点变命令（`graphql list\|call`）<br>• ✅ **内置 OAuth**：PKCE 登录、客户端凭证、动态客户端注册<br>• ✅ **MCP 资源与提示词**：`resources`、`prompts`、`complete`<br>• ✅ **连接存名**：`bake` —— 密钥只按引用存（`env:` / `file:`）<br>• ✅ **代码沙箱**：`exec` —— 只有 stdout 进上下文 |

| 🛡️ 安全、轻量、隐私 | 📚 文档与体检 |
| :--- | :--- |
| • ✅ **零第三方依赖**：纯标准库，`pyproject.toml` 干净<br>• ✅ **561KB，2 秒装完**<br>• ✅ **100% 本地**：不上云、无遥测、可断网<br>• ✅ **三道闸**：每次调用查危险操作 + 提示注入 + 凭据泄露<br>• ✅ **XDG 规范**：沙箱友好，`--dir` 隔离 | • ✅ **文档路由**：`docs` 给 Markdown 树建索引，投喂 1 章而非 19 章（4 万 → 1.7 万 token）<br>• ✅ **文档内检索**：`kb` 只回段落不回整篇（95KB → 3 段）<br>• ✅ **自愈体检**：`doctor` 修 stdio 管道与环境，`health` 探每个服务器<br>• ✅ **当场证明**：`bench` / `demo` 在本机跑真实数字<br>• ✅ **透明播报**：`footer-facts` 每轮打印实时节省 |

<sub>全部命令与参数见 [All commands](#all-commands)。</sub>

---

## 为什么要用 mcptoon：解决上下文吃满（Context Window Bloat）与配置撕裂

**mcptoon 是一个专为大语言模型 Agent 打造的零依赖本地工具网关与技能管理器**。在原生 MCP 协议架构下，每一个 Agent（包括 Claude Code、Cursor、Windsurf、Codex 等）在每次向大模型发起对话时，都必须把已安装工具的完整 JSON Schema 参数定义完整加载进系统提示词，并在每一轮长会话中持续重复发送。

根据我们的真实机器实测数据：仅仅挂载 255 个常见 MCP 工具，其参数描述就高达 **71,929 Tokens**，还没开始执行任务就已经吃光了 128K 注意力窗口的一半以上。这不仅造成严重的 Token 账单浪费，还会淹没模型的注意力导致工具选错与参数幻觉。mcptoon 通过紧凑的名字索引将 71,929 Tokens 极致压缩至 **581 Tokens（降幅达 99.2%）**，让大模型只在真正调用时毫秒级按需拉取单个 Schema。

## 怎么做到节省 99% Token？按需动态加载（On-Demand Tool Retrieval）机制

mcptoon 把这些描述**留在磁盘上、不放进上下文**，只交给 Agent 一份紧凑视图：

- **给名字索引，不给完整 schema。** 挑工具只需要名字——255 个工具压成 **581 tokens（−99.2%）**。完整 schema 用 `mcptoon inspect` 按需取，只在真正调用某个工具时才取。
- **技能同理。** 常驻一条指针（**39 tokens**）+ 一次查询（**791 tokens**），取代加载每一份 `SKILL.md` 全文——**1,572,330 → 39 + 791（−99.99%）**。
- **结果也一样。** `--toon` 把工具*结果*重新编码成标准 TOON。混合样本实测比 JSON 小
  **5.7%**，按结果形状在 **1.8%–48.6%** 之间——记录列表几乎不变，单条记录能减半。
  不是稳定的 34%，见 `assets/benchmark_results.json`。

什么都不丢：完整 schema 和完整技能全文，永远只差一条命令。省下的只有上下文窗口。

mcptoon 是一个 **561KB、零依赖的原生 CLI**，管理你电脑上的每个 MCP 工具和 Agent 技能——并让它们在你所有 Agent 之间共享，而你一行配置都不用写。

## 不只我们一家这么说

这些数字是我们测的——但「把每个工具的 schema 都塞进上下文很贵」不是只有我们在说：

- **[Anthropic 工程博客](https://www.anthropic.com/engineering/code-execution-with-mcp)** —— 工具 schema 淹没上下文是真实成本；一个例子从 150,000 token 降到 2,000
- **[Firecrawl 基准](https://firecrawl.dev/blog/mcp-vs-cli)** —— 同一件事：命令行 1,365 token，MCP 44,026 token（32 倍）
- **[Scalekit 基准](https://scalekit.com/blog/mcp-vs-cli-use)** —— 命令行便宜 10–32 倍，可靠性 100% 对比 MCP 的 72%
- **[MCP-Zero（arXiv:2506.01056）](https://arxiv.org/abs/2506.01056)** —— 按需取工具，成本与工具总数几乎无关

mcptoon 是今天就能用的那个：能跑 shell 的 Agent 全都覆盖，认得出的主流桌面客户端各写一行登记。

---

## 两条路径

<table>
<tr>
<td width="50%" valign="top">

<h3>🧑‍💻 我只是 AI 工具的用户</h3>

装一次，你电脑上每个 AI——**Claude Desktop、Claude Code、Codex、Cursor、Windsurf、Cline、VS Code Copilot、Gemini CLI、Qwen Code、Zed、Crush、opencode 等任意 Agent**——就都能共用你原有的全部工具和技能。任何 Agent 的配置，你都不用写。

**[→ 安装即用](#30-秒上手)**

</td>
<td width="50%" valign="top">

<h3>🔧 我在做 MCP / Agent 开发</h3>

当脚本用。`mcptoon` 是一个纯 CLI，输出稳定的 JSON，还能用 `mcptoon serve` 起一个 MCP 端点——接进你自己的 agent、CI 或应用。

**[→ 命令与格式](#全部命令)**

</td>
</tr>
</table>

量你自己的数字：`pip install mcptoon && mcptoon bench` —— 它报的是你本机的目录，不是下面这份固定的 255 工具样本。

| | 没有 mcptoon | 用 mcptoon |
|---|---|---|
| **进上下文的描述** | 每个工具 + 技能的完整描述，每轮重发 | 一份紧凑视图——255 个工具只要 **581 tokens**（−99.2%，无损） |
| **加一个工具或技能** | 在每个 Agent 里手写 JSON | 一条命令，不碰任何 Agent 配置 |
| **哪些 Agent 能用上** | 只有你配过的那些 | 机器上每个 Agent——它们直接跑 `mcptoon` |
| **去哪找工具和技能** | 手动翻 GitHub | `install --search`（**17,000+ 个 MCP 服务器**）+ `skills search` |
| **从零开始** | 一个工具一个工具地接 | 4 个内置起步包——一条命令搭出可用组合 |

技能同理：**1,572,330 tokens** 的 `SKILL.md` 全文 → 常驻 **39** + 每次查询 **791**（−99.99%）。调用结果加 `--toon` 再省 **~6%**（随形状 1.8%–48.6%）。

---

## 路径一 · 我只是 AI 工具的用户

你有一个桌面 AI——Claude、Codex、Cursor、Windsurf、Cline、VS Code Copilot，**还有另外 97 个**（[103 个完整名单 →](#所有-ai-agent-都能用)）。今天，加一个工具或技能，就得去手改那个 Agent 的 JSON。mcptoon 把这步去掉：

1. **装一次。**
   ```bash
   pip install mcptoon && mcptoon quickstart
   ```
   `quickstart` 会找到你的 MCP 服务器、写好配置，并在它检测到的每个 Agent 里注册 mcptoon。
   （不跑 `quickstart` 也没关系：你跑的第一条命令会自愈——把 mcptoon 自己的技能装进每个 Agent 并建好技能索引，每台机器只做一次。）

2. **工具和技能只在一个地方加**——这里，不是每个 Agent 里。
   ```bash
   mcptoon install --search github     # 找并安装任意 MCP 服务器
   mcptoon skills search "做个 PDF"     # 按技能能做什么来找
   ```

3. **任何 Agent 都能用。** 你的 Agent 像跑其它命令一样跑 `mcptoon`——不用配置、不用重启。见 [所有 AI Agent 都能用](#所有-ai-agent-都能用)。

**想要开箱即用？** 四个内置起步包——`essentials`、`web-research`、`code-review`、`docs`——一条命令搭出一套能用的工具组合：

```bash
mcptoon install --pack essentials
```

---

## 路径二 · 我在做 MCP / Agent 开发

mcptoon 是一个纯 CLI，输出可脚本化；需要时还能起一个 MCP 端点。

```bash
mcptoon manifest --format json      # 机器可读的工具索引
mcptoon call <server> <tool> '{}'   # 调任意工具，JSON 或 --toon 输出
mcptoon call <server> <tool> ... --transport sse|streamable  # HTTP 传输偏好（默认 auto）
mcptoon serve                       # 把所有已配置的服务器收在同一个 MCP 端点后
```

- **输出稳定**——默认 JSON，`--toon` 结果再小一点（随形状 1.8%–48.6%，混合样本 5.7%），`--format mcp` 导出标准 MCP JSON。
- **`mcptoon serve`**——stdio 或 HTTP、连接池、按 Agent 分发的 key，给那些坚持要走代理的客户端。
- **零依赖**——纯 Python 标准库，任何环境都能塞进去（CI、容器、内网）。

完整参考：[DEVELOPERS.md](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md) 与 [全部命令](#全部命令)。

---

## 目录

- [为什么要用 mcptoon](#为什么要用-mcptoon)
- [省 token 的原理](#省-token-的原理)
- [不只我们一家这么说](#不只我们一家这么说)
- [两条路径](#两条路径)
- [路径一 · 我只是 AI 工具的用户](#路径一--我只是-ai-工具的用户)
- [路径二 · 我在做 MCP / Agent 开发](#路径二--我在做-mcp--agent-开发)
- [30 秒上手](#30-秒上手)
- [它做什么](#它做什么)
- [工具从哪来](#工具从哪来搜-17000一条命令装上)
- [三笔账](#三笔账为什么不能混着比)
- [安装方式](#安装方式)
- [所有 AI Agent 都能用](#所有-ai-agent-都能用) — **103 个客户端**（CLI 42 · serve 61）
- [为什么是 CLI，不是代理](#为什么是-cli不是代理)
- [哪种模式最省？](#哪种模式最省)
- [全部命令](#全部命令)
- [信任与安全](#信任与安全)
- [引用与致谢](#引用与致谢)
- [贡献](#贡献)
- [许可证](#许可证)

---

## 30 秒上手

```bash
pip install mcptoon                          # 纯标准库，561KB，零依赖

# 一条命令：扫出你的 MCP 服务器、写好配置、把网关登记进你所有 Agent，并告诉它发现了什么：
mcptoon quickstart

# 查看所有可用工具（默认就是名字索引，255 个工具只需 581 token）：
mcptoon manifest

# 调用工具（默认输出 JSON；想更省加 --toon）。
# `everything` 只有你本来就装了才会有；否则先加内置的零依赖演示服务器
# （不需要 Node、不联网），再调它：
mcptoon add demo --stdio python -m mcptoon demo-server
mcptoon call demo echo_message '{"message":"hi"}'
```

`quickstart` 也是让 mcptoon **被看见**的那一步：它把 `mcptoon serve` 作为一个名为 `mcptoon` 的保留服务器写进每个 Agent 的配置，于是你的 Agent 能看见 mcptoon 本身。已经同步过？用 `mcptoon sync --self` 重新登记（不带 `--self` 的 `mcptoon sync` 只写你自己的服务器）；任何时候用 `mcptoon status` 看状态。

**两条路都通 —— 而且不用你选。** mcptoon **首先是个 CLI**：能敲命令的 Agent 直接跑 `mcptoon`，这是最省的一条路——schema 根本不进上下文。`quickstart` 还会把 mcptoon 自己的 MCP 条目（`mcptoon serve`）登记进每个收得下的 Agent，让只认 MCP 服务器的客户端也能用上你的工具。MCP 那条默认走 `compact` 档：不把上游工具清单塞进模型上下文，改成让它走 `mcptoon_manifest → inspect → call`。`mcptoon status` 两条账一起看。

**而且它完全可逆。** 安装会登记网关，默认还会「接管」——把你已有的服务器改走网关、摘掉它们原来的直连记录（不摘的话，同一批工具会同时以直连和网关两种身份出现，反而更贵）。这一步会列清单、要你确认一次，而且能撤销：**`mcptoon restore` 摘掉网关记录、把你的服务器原样放回去**；你之后往配置里加的东西一概不动。`mcptoon off` 是更轻的开关——只摘网关记录，服务器留在原地。两者都能加 `--dry` 预览；`mcptoon uninstall --dry` 会先打印完整移除计划。

还不想装？那就先看它干活（需要 Node）：

```bash
uvx mcptoon demo --quick
```

它会启动官方 "everything" 参考服务器，调一个工具，把 token 账打在屏幕上——不要 API key，不动你的服务器，不往磁盘写任何东西。

---

## 它做什么

### 工具：schema 按需取

完整 schema 压成名字索引。要用哪个，先 `mcptoon inspect` 查它的真实参数，再 `call`。你付的是一份清单的钱，不是每一轮的钱。

### 技能：常驻一份指针

不再全量加载。常驻一行指针（39 token），一次查询返回最相关的技能（791 token）。视图是**链接**（Windows 上是 junction，不需要管理员），所以改一处，处处生效，没有第二份副本会走样。

### 一次安装，全部共享

装一次 mcptoon，机器上每个 AI 都拿到你全部的工具和技能。之后新增，立即生效——不用重启 Agent，不用逐个写 JSON。

### 怎么添加工具

```bash
mcptoon install brave-search --npm @modelcontextprotocol/server-brave-search
mcptoon install my-tool --pip mcp-my-tool
mcptoon install remote-api --url https://example.com/mcp
mcptoon add my-server --stdio npx -y @any/mcp-package
mcptoon install --list                       # 看装了哪些
mcptoon install --remove brave-search        # 卸载其中一个
```

从 npm / pip / HTTP，一条命令加一个服务器。或者让 mcptoon 扫描你机器上已有的：`mcptoon discover`。

需要 token 的远端服务器从环境变量里取，凭据不落盘：

```bash
mcptoon install remote-api --url https://example.com/mcp \
  --header 'Authorization: Bearer ${BAIZHI_TOKEN}'   # BAIZHI_TOKEN 设在你的环境变量里
```

`${NAME}` 在**请求时**才解析，所以配置、生成的 handler、日志里留的都是模板——轮换变量后下一次调用即用新值，无需重装。变量缺失或为空会**报错并点名变量**，绝不会变成空 header。

---

## 工具从哪来——跨 17,000+ MCP 服务器搜索，一条命令装上

开一台新机器，第一个问题不是「怎么省 token」，是「我到底该装哪些工具」。传统做法是去 GitHub 到处翻 `mcpServers` 片段，再手抄进 JSON。

mcptoon **不预装任何工具，也不把清单打包进程序**。它直连上游注册表，你要什么就搜什么：

```bash
mcptoon install --search github     # 搜，只列不装
mcptoon install --search postgres
mcptoon install github              # 搜到就直接装
```

结果带 `✓`（注册表验证过）、类型标签（`npm` / `pypi` / `hosted` / `remote`）和调用量。数据来自两个上游，**实时查、不落库**：

| 来源 | 是什么 | 规模 |
|---|---|---|
| [Smithery](https://smithery.ai) | 最大的 MCP 注册表 | **17,000+** 条 |
| [官方 MCP Registry](https://registry.modelcontextprotocol.io) | 官方元注册表 | 可安装的 npm / pypi 包 |

**为什么不在程序里内置清单**：内置就得发版才能更新，还会把别人的源码带进你的供应链。mcptoon 只存**指针**——搜到之后写一行配置进你自己的 `~/.mcptoon/config.json`，第三方源码永远不落进 mcptoon。

装完分发给所有 Agent：

```bash
mcptoon sync          # 把新工具推给每个检测到的 Agent
mcptoon manifest      # 看全部工具（名字索引，最省 token）
```

**怎么看结果**：索引里既有官方 `@modelcontextprotocol/*` 服务器，也有个人发布的包。`✓` 表示注册表验证过这条记录——这是提醒你，给凭据之前先看一眼源码。

**技能那一半**：`skills search <关键词>` 直连开放的技能索引（skills.sh）——按技能能做什么来找，再用 `skills add <git-url>` 装。mcptoon 装的是**你指定**的技能仓库——目录就是开放的生态本身。

**起步技能包**：如果你不想一个工具一个工具地挑，内置四个包——`essentials`、`web-research`、`code-review`、`docs`——每个都打包了几个工具外加一段现成提示词。`mcptoon install --packs` 列出它们；`mcptoon install --pack essentials` 安装其中一个。两个研究类包都不需要 API key。

---

## 三笔账：为什么不能混着比

mcptoon 省下的 token 分三处，混在一起比数字没有意义。

下面的数字来自三种不同规模的目录——**255 个工具的合成样本**（固定头条基准）、一台 **1,109 个工具**的机器、以及你自己机器上的真实数量。别拿一张表的百分比去比另一张表的 token 数；每张表都写明了它量的是哪份目录。

「省了多少」有两个读法，回答的是两个不同的问题。**网关口径**——完整 schema 对比 agent 默认 `compact` 暴露下真正加载的东西——才是装上 mcptoon 买到的那个数，是诚实的头条（它随目录规模变大：工具越多，省得越多）。**瘦身 schema 口径**（同一批工具、描述更短）是更小的次要口径（88.5%），对应 `manifest --slim`。`mcptoon status` 把两者并排打印，来自同一次测量，因此永远不会各说各话。

### 第一笔 · 工具发现（`manifest`）：默认省 99.2%

`mcptoon manifest` 不带参数就是这一档。想要更多：`--slim`（名字加参数类型，8,282 token，−88.5%）或 `--full`（完整 schema）。

### 第二笔 · 调用结果（`call`）：可选，`--toon` 省约 6%

这笔账在工具返回结果**之后**到期。`mcptoon call` 默认输出 JSON，**默认不省**。想省就加 `--toon`。

### 第三笔 · 技能目录（`skills`）：1,572,330 → 常驻 39 + 每次查询 791

```bash
mcptoon skills manifest                      # 39 token，常驻
mcptoon skills resolve "做个 PDF" --k 5      # 791 token，返回最相关的 5 个
```

**一张表，三笔全在里面（写这份 README 的机器上实测）：**

| 路径 | Agent 加载什么 | token | 对比全量 |
|---|---|---:|---:|
| 工具 schema（212） | 每份完整 schema | 640,787 | — |
| | `manifest`（名字索引） | 914 | 99.85% |
| | `manifest --slim` | 3,056 | 99.52% |
| 技能文件（480） | 每个 `SKILL.md` 全文 | 1,572,330 | — |
| | `skills manifest`（指针） | 39 | 99.99% |
| | `skills resolve --k 5` | 791 | 99.94% |

固定口径的头条基准——一份**合成样本**（255 个工具、50 个服务器，`tiktoken cl100k_base`）。它不是你的目录；你自己的数看 `mcptoon status`：

| 格式 | token | 省 |
|---|---:|---:|
| JSON | 71,929 | — |
| TOON | 47,438 | 34% |
| SLIM | 8,282 | 88.5% |
| Compact | 581 | 99.2% |

用 `mcptoon bench` 量你自己的目录（报的是你的工具，不是这份固定样本）。上面那张三格式表也可原样复现——无需克隆仓库：

```bash
mcptoon manifest                 # 先填充 schema 缓存
python -m mcptoon.bench_tokens   # 同样的 JSON / --slim / --compact 三个数，量你自己的工具
```

方法学见 [docs/tiktoken-benchmarks.md](https://github.com/activeing123/mcptoon/blob/main/docs/tiktoken-benchmarks.md)。

---

## 安装方式

```bash
pip install mcptoon
```

> **Linux（Debian/Ubuntu 23.04+ 及所有遵循 PEP 668 的发行版）、以及 macOS 的
> Homebrew Python**：直接 `pip install` 到*系统* Python 会被拒绝，报
> `error: externally-managed-environment`。这是发行版在自我保护，不是 mcptoon 的问题。
> 改用干净装法：
>
> ```bash
> pipx install mcptoon     # 隔离安装 CLI，推荐
> # 或者装进你自己控制的虚拟环境：
> python3 -m venv ~/.mcptoon-venv && ~/.mcptoon-venv/bin/pip install mcptoon
> ```
>
> `pip install --break-system-packages mcptoon` 也能装上，但它会写进系统 Python——
> 优先用 `pipx` 或 venv。Windows 上 `pip install mcptoon` 直接可用。

<details>
<summary>其它安装方式</summary>

```bash
# 不想装进环境，直接跑（需要 Node）
uvx mcptoon demo --quick

# 隔离安装 CLI（绕开 Linux / Homebrew Python 的 PEP 668 报错）
pipx install mcptoon

# 克隆源码（开发用）
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation

# Claude Code 插件
/plugin marketplace add activeing123/mcptoon
```

</details>

### Nix

由 [numtide/llm-agents.nix](https://github.com/numtide/llm-agents.nix) 打包——机器人跟着每个 PyPI
版本自动走，不需要人手钉版本：

```bash
# 直接从 flake 运行，不用安装
nix run github:numtide/llm-agents.nix#mcptoon -- --help
```

插件和技能也在 [sudosubin/agents.nix](https://github.com/sudosubin/agents.nix) 里提供：
`pkgs.agent-plugins.github.activeing123.mcptoon.<plugin-name>` 与
`pkgs.agent-skills.github.activeing123.mcptoon.<skill-name>`。

---

## 跨 Agent 共享：在 Cursor、Claude Code、Windsurf 等 103+ 客户端统一管理 MCP

mcptoon 只用两条路够到 Agent，下面每个客户端都落在其中一条上。不用你选——`quickstart` 两条都登记，哪台能收哪条就收哪条：

- **CLI 腿——Agent 自己跑 `mcptoon`。** 任何有 shell 的（命令行 Agent，或带终端的编程 IDE）**零配置**：它自己跑 `mcptoon call`、`mcptoon search`、`mcptoon skills resolve`。**一个字节都不写进它。**
- **serve 腿——客户端跑不了 shell。** 聊天类、图形界面客户端改用挂载 MCP，那就给它**一条入口**：把 `mcptoon serve` 当成一个 MCP 服务器。一行，一处。

**全市场覆盖。** 共 **103** 个客户端，名单取自
[awesome-mcp-clients](https://github.com/punkpeye/awesome-mcp-clients)，加上该清单之后才出现的编程 Agent（查各家厂商文档补入）；开发者用的**库**（mcp-agent、mcp-client-go）不计入，因为用户不直接运行它们。证据逐条标注——我们写明**查证过什么**，不写"假设如此"。

**CLI 腿——42 个，零配置**（它们自己跑 `mcptoon`）：

AdaL · Aider · Amazon Q Developer · auggie · Autohand Code CLI · Claude Code · Claude Code Open ·
ClaudeMind · Cline · Codex · ContextKit · Continue · Copilot CLI · Copilot-MCP · Crush · Cursor ·
Dexto · Dolphin-MCP · Enola · Gemini CLI · Goose · JDBCX · Junie · KiloCode · Kiro · McPico ·
MCPOmni Connect · mistral-vibe · Nerve · Octomind · opencode · OpenHands · PraisonAI · Qwen Code ·
Roo Code · Slack MCP Client · SwarmClaw · Trae · VS Code GitHub Copilot · Warp · Windsurf · Zed

**serve 腿——61 个，一条 `mcptoon serve` 入口**（没有 shell，改用挂载 MCP）：

5ire · Agent Bridge · Agent-cli · AgentOne · AIaW · Ano · AnythingLLM · Argo-LocalAI · askit-mcp ·
AstrBot · BoltAI · BrowseWiz · Canvas MCP Client · CarrotAI · Chainlit · ChatMCP · Cherry Studio ·
Claude Desktop · console-chat-gpt · DeepChat · DocsGPT · eechat · Enconvo · Fastchat MCP · FLUJO ·
Glue · HyperChat · kibitz · Klavis AI · LangBot · LibreChat · LobeHub · Lutra · MCP Chatbot ·
MCP CLI client · MCP Playground · MCP Simple Slackbot · MCP SuperAssistant · MCPCLIHost · MCPHost ·
Memex · MindPal · NextChat · OpenClaw · oterm · Qordinate · Runbear · SeekChat · Simple AI ·
Superinterface · Tambo · Taskade · Tester MCP Client · Tiles Notebook · Tome · Vercade · WhatsMCP ·
Witsy · y-cli · Yume · Zin-MCP-Client

**证据状态**——`sync --self` 只往我们**对着厂商文档核对过**的 12 个宿主写登记行；上表其余宿主都靠 CLI 或 `mcptoon serve` 接入，不需要宿主专属文件，也就没有"逐台核验"这回事。

### 逐台看：mcptoon 到底写了什么

mcptoon 是 **CLI 工具**——是管理器，不是常驻代理或服务——也不是客户端库。你的 Agent 从不直连上游 MCP 服务器：它要么跑 `mcptoon` 命令，要么经 mcptoon 自己的 MCP 条目（`mcptoon serve`）够到它们。对收文件的宿主，具体写在哪就是下面这张表：

| Agent | 怎么接 |
|---|---|
| Claude Desktop | `mcptoon sync --self` 往 `claude_desktop_config.json` 加一条 `mcptoon` 记录 |
| Claude Code | `mcptoon sync --self` 写它的配置，并往 `~/.claude/CLAUDE.md` 写一条指针 |
| Codex | `mcptoon sync --self` 往 `~/.codex/AGENTS.md` 写一条指针 |
| Gemini CLI | `mcptoon sync --self` 往 `~/.gemini/GEMINI.md` 写一条指针 |
| Qwen Code | `mcptoon sync --self` 往 `~/.qwen/QWEN.md` 写一条指针 |
| Zed | `mcptoon sync --self` 往 Zed 的 `AGENTS.md` 写一条指针 |
| Crush | `mcptoon sync --self` 往 `~/.config/crush/CRUSH.md` 写一条指针 |
| opencode | `mcptoon sync --self` 往 `~/.config/opencode/AGENTS.md` 写一条指针 |
| Cursor | `mcptoon sync --self` 写进 Cursor 的 MCP 配置；或写进 `AGENTS.md` |
| Windsurf | `mcptoon sync --self` 写 `mcp_config.json` |
| Cline | `mcptoon sync --self` 写 Cline 的 MCP 配置 |
| VS Code Copilot | `mcptoon sync --self` 写 VS Code 的 MCP 配置 |
| 任何能跑 shell 的 Agent | 直接调 `mcptoon`，零配置 |

```bash
# Agent 干活干到一半需要 GitHub 访问？它自己跑：
mcptoon add github --url https://api.githubcopilot.com/mcp/
# 完事。不用编辑 JSON。不用重启。上下文不丢。
```

`mcptoon serve` 是另一个方向：把你所有已配置的服务器藏在一个 MCP 端点后面，带连接池和按 Agent 分发的密钥，给那些坚持要代理的客户端用。两条你不用二选一——CLI 始终是主入口，桥在收得下的宿主上跟它并排铺好。

---

## 为什么是 CLI，不是代理

MCP 的前提是：每个能力都是一个*服务器*，你的 Agent 必须被配置成能连上它——所以加一个新工具，就要为每个 Agent 手改一份不同格式的 JSON、全部重启、并且让每个 Agent 重新付一遍完整 schema 的钱。

而命令行是每个 Agent 本来就有的那一个接口。而且这个形态本身就实测更便宜，跟 mcptoon 做了什么无关：

- [Firecrawl](https://firecrawl.dev/blog/mcp-vs-cli)：同一件事，**命令行 1,365 token vs MCP 44,026 token——32 倍**
- [Scalekit](https://scalekit.com/blog/mcp-vs-cli-use)：命令行**便宜 10–32 倍，可靠性 100% vs MCP 的 72%**

代理形态也有——`mcptoon serve` 把所有已配置服务器藏在一个 MCP 端点后面——而 `quickstart` 会把它和 CLI 一起铺好，你不需要在两者之间选。这一节讲的是 mcptoon 的立身形态，不是一个要你去拨的开关。

---

## 哪种模式最省？

mcptoon 把工具交给 Agent 有三种方式，花的 token 差别很大。只有一种最省，而且它不是新装后的默认状态。（下表 token 数字来自 255 工具样本；你自己的目录不一样——`mcptoon mode` 会打印你的真实数字。）

| 模式 | Agent 实际加载什么 | 每轮固定开销 | 什么时候用 |
|---|---|---|---|
| **CLI**（最省） | 不跑命令就什么都不加载；一跑就只取名字索引（255 个工具 **581 token**）加上它要的那一个 schema | **0** | 任何能跑 shell 的 Agent |
| **serve** | 加载 mcptoon 自己的网关工具，而不是全部上游 schema（就是上文那个网关口径——随目录规模变大） | 每轮一笔小的固定开销 | 只能看见 MCP 服务器的客户端 |
| **直连** | 每个工具的完整 schema 全塞进去（255 工具样本 **71,929 token**） | **最大** | 装了 mcptoon 之后，不该再用 |

**CLI 最省，因为它闲置时是零。** 不调工具的回合一分不花，真调的那一回合也只要几百 token。`serve` 是紧挨着的第二名——每轮一笔小的固定开销。**直连**是 mcptoon 装了但没接进 Agent 时付的账，而新装后正好停在这个状态——这就是为什么你不跑一次 `mcptoon quickstart`，会觉得它像不存在。

这份 README 里的"99%"，是**定义侧**的省——来自"不加载全部 schema"。CLI 和 serve 都拿得到；直连拿不到。结果压缩是另一笔、也小得多的账（见上文第二笔），从来不是安装的理由。

想看你当前在哪个模式、你自己目录里每种模式各花多少：跑 `mcptoon mode`；想打一行徽标：`mcptoon statusline`。

---

## 全部命令

```bash
mcptoon quickstart              # 一键上手（发现 + 配置 + 登记网关）
mcptoon discover                # 扫描本机已有的 MCP 服务器（--write 保留，--health 探活）
mcptoon import                  # 从 Claude Desktop / Cursor / Cline / Windsurf 导入服务器
mcptoon init                    # 生成示例配置（--auto 自动发现并填好）
mcptoon list                    # 列出已配置的服务器
mcptoon manifest                # 所有工具名（默认 compact；255 个工具 = 581 token）
mcptoon manifest --sort alpha|usage|recent       # 排序（usage = 你最常调用的排前面）
mcptoon manifest --top 3 --verbose              # 每个服务器只列 N 个；--verbose 附带描述
mcptoon inspect <server> <tool> # 查看某个工具的真实参数
mcptoon search <query>          # 跨服务器搜工具
mcptoon select "<任务>"          # 为某个任务挑最该用的 3 个工具（工具超 ~40 个模型就开始选错）
mcptoon call <server> <tool> '{"args":"here"}'   # 调工具
mcptoon exec python "print(len(open('big.log').readlines()))"  # 跑代码，只有 stdout 进上下文
mcptoon exec python --file analyze.py            # 同上，从脚本文件跑
mcptoon exec --langs                             # 本机到底能跑哪几种语言
mcptoon openapi list <spec>                      # 把任意 OpenAPI/Swagger REST API 变成命令
mcptoon openapi call <spec> <cmd> pet-id=2       # 调一个接口（参数写 name=value）
mcptoon openapi call <spec> <cmd> --base-url U   # 覆盖服务器地址（生产/测试切换）
mcptoon openapi call <spec> <cmd> --cache-ttl 0 --cache-key v2  # 重新拉 spec；不同版本分开缓存
mcptoon graphql list <endpoint>                  # 把任意 GraphQL 端点变成命令
mcptoon graphql call <endpoint> <cmd> --fields "name id"  # 调一个查询/mutation
mcptoon auth login <name> --auth-url U --token-url U --client-id ID  # OAuth 登录（PKCE）
mcptoon auth creds <name> --token-url U --client-id ID  # OAuth 客户端凭证
mcptoon auth login <name> ... --register REG_URL --client-name mine  # 动态客户端注册（RFC 7591）——不用手填 client-id
mcptoon openapi call <spec> <cmd> --auth oauth:<name>   # 用已存的 token
mcptoon resources list [server]                  # 列服务器的 MCP 资源
mcptoon resources read <server> <uri>            # 按 URI 读一个资源
mcptoon prompts list [server]                    # 列服务器的提示词模板
mcptoon prompts get <server> <name> a=1          # 带参数渲染一个提示词
mcptoon complete <server> <ref>:<arg>=<prefix>   # 让服务器补全参数值
mcptoon bake create <name> --openapi <spec>      # 把连接存成一个名字
mcptoon bake create <name> --openapi <spec> --auth-header 'K: env:VAR'  # 密钥只按引用存（env:/file:）
mcptoon bake run <name> <action> ...             # 复用存好的连接
mcptoon bake install <name> --bin ~/.local/bin   # 生成启动脚本（只带 bake 名字，不带 URL/密钥）
mcptoon add <name> --stdio|--http <cmd|url>     # 添加任意 MCP 服务器
mcptoon remove <name>           # 删除一个服务器
mcptoon install <name> --npm|--pip|--url <pkg>  # 安装 + 自动生成 handler
mcptoon install --search <kw>   # 搜上游注册表（只列不装）
mcptoon update                  # 刷新各服务器缓存的工具面，报告漂移
mcptoon upgrade                 # 把 mcptoon 自身升级到 PyPI 最新版
mcptoon plugin install <dir>    # 安装 Agent Plugins 1.0.0 插件
mcptoon sync                    # 把配置同步到每个检测到的 Agent
mcptoon health                  # 健康检查每个 MCP 服务器
mcptoon serve                   # 作为一个 MCP 服务器运行（stdio/HTTP）
mcptoon skills list             # 技能目录（--usage 加命中计数）
mcptoon skills sync <src>       # 把技能目录分发到每个 Agent 的技能文件夹
mcptoon skills resolve "<任务>" # 技能 BM25 短名单（离线，无 LLM）
mcptoon docs index <目录>       # 索引一棵 Markdown 树，让 Agent 不再整读
mcptoon docs resolve "<查询>"   # 查该读哪几个文件（返回路径，离线）
mcptoon docs list               # 列出已索引的每个文档（按 slug）
mcptoon docs doctor             # 对照磁盘检查文档索引
mcptoon kb index <path>         # 索引文档，之后可在文档内部搜
mcptoon kb fetch <url>          # 抓取 URL 并索引（24 小时 TTL 缓存）
mcptoon kb search "<查询>"       # 返回命中的段落，不是整个文件（porter + trigram，RRF）
mcptoon kb list                 # 已索引的来源、大小、时间
mcptoon kb stats                # 块数、库大小、是否支持 trigram
mcptoon session                 # 本次会话发生了什么（压缩后用来接上下文）
mcptoon bench                   # 在本机验证省了多少（工具 + 技能一张表）
mcptoon demo                    # 一条命令，在本机现场演示
mcptoon demo-server             # 同样的自证，零下载（11 个标准库工具）
mcptoon doctor                  # 自检：Python、配置、连通性
mcptoon status                  # 一屏：配了什么、网关通没通、省了多少
mcptoon stats                   # token 省量看板（对比原始 JSON）
mcptoon report                  # 省量总账：工具 + 技能 + 累计
mcptoon savings                 # 跨过的省钱里程碑（1B？≈1.2 万本小说？）
mcptoon credit                  # 一屏看懂：你的模式、真实省量、一个动作
mcptoon mode                    # 当前交付模式（cli/serve/direct）及各自开销
mcptoon statusline              # 一行省量徽标，供状态栏/回合头用
mcptoon usage                   # 本地调用统计
mcptoon activity                # 谁在用它、什么时候、调了什么（最近 20 次）
mcptoon footer-facts            # 一行省量，供聊天页脚用（永不阻塞）
mcptoon retrieve <handle>       # 取回任意 --smart 句柄背后的原文
mcptoon config                  # 查看网关设置（footer、welcome、lang）
mcptoon toggle <server> <tool>  # 启用/停用单个工具（--list 全列）
mcptoon policy                  # 逐工具的压缩策略（raw / toon / slim）
mcptoon completion ps           # shell 补全（bash/zsh/fish/powershell）
mcptoon off                     # 从你的 Agent 里摘掉网关记录（可逆）
mcptoon restore                 # 摘网关、把你的服务器放回去
mcptoon uninstall               # 完整清理——先打印计划（--dry 预览）
```

完整命令清单见 [DEVELOPERS.md](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md)。

### 格式家族：四个档，默认 compact

全部可选；默认已经是最省的档。

| 档 | 输出 | 对比原生 schema | 出处 |
|---|---|---|---|
| **compact（默认）** | 只有名字 `search_web` | **小 99.2%** | 通用设计 |
| **slim** | 名字 + 参数类型 `search_web\|query:s*` | 小 88.5% | **mcptoon 原创** |
| **full** | 带参数的完整 schema | 基线 | 原生 MCP |
| **toon**（结果） | 可逆的结构化编码 | 混合样本小 5.7%（按形状 1.8-48.6%） | 开放 TOON 标准 |

**为什么默认 compact？** 决定「用哪个工具」只需要名字（255 个工具 581 token）；参数细节在调用时才有用，按需再取。默认给完整 schema，就等于把省下的 99.2% 又还回去了。

**给 Agent 的规矩：用 `manifest` 挑，调之前先 `inspect`。** 在 41 个真实工具上实测：只靠名字猜参数，有效调用率约 10%；而每一轮只对真正要用的 2–3 个工具跑一次 `inspect`，命中率 100%——和把每份 schema 都注入完全一样，成本却只是一小部分。

---

## 信任与安全

**它只是一个 561KB 的原生 CLI——不喜欢，随时删掉；留着它，你永远不必再为任何 Agent 的工具和技能配置操心。** mcptoon 确实会碰你的 Agent 配置，所以它从设计上就做到透明——也让你随时能干净地离开。

每个工具结果在进入你 Agent 之前，都要过三道防护：

| 防护（默认开启） | 它做什么 |
|---|---|
| **危险操作拦截** | 危险调用会被拒绝，除非你显式加 `--destructive` |
| **提示注入防护** | 扫描结果里的注入模式（如 "ignore previous instructions"）并拦截 |
| **凭据泄露检测** | 结果里带 API key 或 token，会在进入上下文之前被拦下 |

- **可逆。** `mcptoon restore` 撤销接管（摘网关、还你服务器）；`mcptoon off` 只摘网关记录；`mcptoon uninstall --dry` 先打印完整移除计划。你的服务器不会被删，除非你显式要求。
- **没有遥测。** 没有分析、没有崩溃报告、没有回传。
- **本地优先。** 你的工具、技能和文件都留在你机器上。唯一出门的是 `install --search`，它向注册表要一份目录清单——从不发送你的数据。
- **不存凭证。** API key 从你的配置或环境变量直接传递。
- **没有依赖。** 纯 Python 标准库——供应链里没有东西要审计。CI 用 `scripts/check_zero_deps.py` 强制这条。
- **没有守护进程。** 纯 CLI——没有常驻进程，没有监听端口。
- **自研格式不破坏兼容。** 线上协议永远是标准 JSON-RPC；compact/slim/toon 只影响 mcptoon 给 Agent 的输出渲染。`--toon` 解码若失败会自动回退 JSON，一条 `--full` 就还原原生 schema。没有锁定。

**范围，一句话：** mcptoon 是索引 + 配置管理器——它把你引到每个工具自己的源码，你可以按它自己的条件去审阅。

---

## 引用与致谢

- **[TOON 标准](https://github.com/toon-format/toon)** —— v4.1（MIT），vendored 自 python-toon，已在 NOTICE 里署名
- **[ToonDeck](https://github.com/activeing123/toondeck)** —— mcptoon 的图形界面（pre-alpha）：同一个引擎，点鼠标代替敲命令

**谁在做这个项目：** mcptoon 是由 [@activeing123](https://github.com/activeing123) 维护的独立第三方项目，不隶属于 Anthropic。

---

## 贡献

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 3029 passed, 2 skipped
```

三条硬规则：零依赖（CI 强制）、新功能必须带测试、Windows 是一等目标。新手可以先看 [CONTRIBUTING.md](https://github.com/activeing123/mcptoon/blob/main/CONTRIBUTING.md) 和 [DEVELOPERS.md](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md)。

代码规模：**56 个模块、41,055 行 Python**，零第三方依赖。

---

## 支持

mcptoon 是个人业余项目，个人使用一直免费。要是它砍掉了你的上下文账单：

- **[在 GitHub 上赞助](https://github.com/sponsors/activeing123)** —— 一次性或按月都行。
- **[给个 star](https://github.com/activeing123/mcptoon)** —— 别的开发者就是靠这个找到小工具的。

**团队功能还没做。** 一份服务器清单同步到全队每台机器；谁在什么时候加载了什么工具的记录。没有报价、没有候补名单页——发邮件到
[activeing123@gmail.com](mailto:activeing123@gmail.com?subject=mcptoon%20team%20features)
，真有人要就往前排。

---

## 许可证

Apache 2.0。见 [LICENSE](https://github.com/activeing123/mcptoon/blob/main/LICENSE) 与 [NOTICE](https://github.com/activeing123/mcptoon/blob/main/NOTICE)。

---

<div align="center" markdown="1">

*mcptoon 是独立的第三方 MCP 客户端，不隶属于 Anthropic。*

**要是它帮你省下了上下文，点个 star，别的开发者才找得到这种小工具。**

[![Star History Chart](https://api.star-history.com/svg?repos=activeing123/mcptoon&type=Date)](https://star-history.com/#activeing123/mcptoon&Date)

</div>
