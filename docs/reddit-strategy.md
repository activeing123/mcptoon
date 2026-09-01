# mcptoon Reddit 推广策略 v1

> Status: accepted (grilled + domain-modeled, 2026-08-26)
> 上游依据：reddit 技能 + 一次 grill-with-docs 收敛的 design tree
> 目标：**GitHub star 增长**（间接漏斗，不做每条归因）

## 一句话

**在 r/cursor 与 r/ClaudeCode 精准回「配置地狱」切入点、辅以 token 成本数字型钩子，只提工具名不放链接，靠口碑间接促 star。**

---

## 收敛的 design tree（全分支已定）

| 决策 | 结论 |
|------|------|
| 目标 (goal) | GitHub star 增长；实质是**纯间接漏斗**——读者看回复→好奇→搜 mcptoon→找到 GitHub→可能 star。不做每条归因，看净增长 |
| 切入 (wedge) | **配置地狱为主 + token 成本为补充钩子**（研究后修正：token 数字型帖信号最锐，配置地狱量大） |
| 风控铁律 (risk) | **绝对不放链接，只提工具名**；r/mcp 社区完全不推广（只养号/纯交流） |
| 规模 (scale) | 精确小批量：每账号每天 3-5 条，同 subreddit 每天 ≤3，条间隔 ≥10min |
| 保鲜 (freshness) | **半自动**：三段式模板 + 按帖内容 LLM 改写，防止 AI 检测模式化推广 |
| 节奏 (cadence) | **只跟新帖不预排**（最像真人，产量不可控但安全） |
| 目标帖 (target) | 4 类配置地狱信号 + token 数字型补充（见下） |
| 排除 (exclude) | 无痛点的纯 Show&Tell / 广告；已删/锁/重复帖 |
| 落地话术 (landing) | **第一人称实操陈述**：『我做了个叫 mcptoon 的小工具，把单点真相同步到每个 agent』 |
| 数字 (numbers) | **只用 Reddit 原生数字**（83.3k=41.6%、45k/5MCPs、15% input、55k/93tools、50k/run）；**绝不用 71k/99.8%**（那是 mcptoon 自家框架，会被认出 shill） |
| subreddit 优先级 | **r/cursor + r/ClaudeCode 优先**；r/ClaudeAI 补充；r/mcp 谨慎克制（不推广） |

---

## 目标帖定义（scan/monitor 包含标准）

**主（配置地狱，Angle A）：**
1. 跨 agent 配置同步痛点（Cursor+Claude Desktop 之间 sync 痛苦、drift）
2. 配置格式/路径困惑（.mcp.json vs .claude.json vs AGENTS.md、JSON 格式错、路径变）
3. 服务器不启动/挂掉（failed to start、no tools found、tool not found、token/ENV 静默失败）
4. 配置过多难管理（装太多 server、找不到、重复、想精简怕 break）

**补充（token 成本，Angle B）：** 含实测数字的 token/context 帖（83.3k=41.6%、45k、15%、55k...），用同一套『跨 agent 归一 + schema 不进口袋』解法接住。

**排除：** 无痛点的纯 Show&Tell/广告；已删/锁/重复；极端热帖（回复必淹没）。

---

## 关键事实与防雷（研究证据）

1. **Angle A 各帖里很多 top 帖本身就是披着痛点的竞品自推**（"I got so fed up with MCP config hell that I built..."、"Router MCP"、"hypertool"）——观众对软广已疲劳，**回复必须真实有用，第一/第三人称实操，绝不"check out my tool"腔**。
2. Angle B（token 成本）在 **r/ClaudeCode 最富**（top 帖 5 个属它），且数字型帖被当成真实调研读。
3. `71k` / `99.8%` 不是 Reddit 原生说法，是 mcptoon 自创——**引用会被识破**。
4. r/mcp 是产品佬扎堆、对竞品自推最敏感的社区 → 铁律：**不在 r/mcp 推广**。
5. 当前账号：**Alarming-List-1313**（2 post / 0 comment karma，Chrome sanzhang profile 已登录）；AstronomerNo223 未登录任何已连浏览器。单账号精细操作。

---

## 落地话术三段式模板（配合按帖改写）

1. 【共情】接住这帖的具体痛（引它的原话/场景，如"在 Cursor 和 Claude Desktop 之间手同步 8 个 server 确实要命"）
2. 【通用解法】给一个不依赖工具的真解法（单点真相 single-source-of-truth → 按 agent 生成各自配置；或 schema 不进口袋的测量）
3. 【第一人称落地】『后来我做成了个叫 **mcptoon** 的小工具，就是为了把单点真相同步到每个 agent』——不带链接、不展开、不喊口号

---

## 操作化要点（reddit 技能扫描规则调整）

- scan/monitor 默认 subreddit：`r/cursor, r/ClaudeCode`（优先）+ `r/ClaudeAI`（补充），`r/mcp` 只养号不回推广
- 关键词并入 4 类配置地狱信号词 + token 数字型信号词
- 每条要发前：研读该帖具体内容 → 按帖定制（三段式 + 原生数字）→ 发布 → **用账号评论历史页验证**（勿用页面 body 检测，会误判）
- 数字只用原生；无原生数字的帖就不引数字
- r/mcp 一律不提 mcptoon

## 关联
- README（产品定位：配置地狱 + token 成本 + 跨 agent）
- ADR 0009（营销策略背景）
- docs/archive/config-hell-comparison.md（before/after 话术素材）
