# mcptoon 产品路线图 & 更新计划

> **唯一权威路线图。所有版本计划以此文件为准。**
> **最后更新**: 2026-09-01
> **当前版本**: v0.7.2 | 631 tests | 0 依赖 | Agent Plugins Spec 1.0.0
> **目标**: 让"零配置 + Token 效率"成为轻量 CLI 区间的事实标准
> **版本策略**: 产品上小步维护，**战略重心 = 推广与转化**（2026-08-27 用户定调）

---

## 🧭 战略方向（2026-08-27 重定位，已确认）

> **CLI-first，推广优先于堆功能。**

- 产品护城河已清晰且竞品无法快速复制：99.8% Token 节省（names-only manifest）、
  工具级 Toggle、实时 Watch、零依赖、投毒检测。
- 一切"功能堆叠型"路线（Profile 系统 / 多 IDE 扩展同步 / 企业审计 / K8s）**已否决**，
  详见文末「已否决方向」——重新提议前必须先回答"它如何帮助推广或小白上手"。
- 产品工作只保留两类：**小白爽感增强**（demo / quickstart / 一键安装体验）
  与 **MCP 规范跟进**（保持最新协议兼容是我们的技术信誉来源）。

---

## 📦 发布渠道状态（2026-09-01 更新）

| 渠道 | 状态 | 地址 |
|------|------|------|
| GitHub | ✅ v0.7.2，CI 全绿 | github.com/activeing123/mcptoon |
| PyPI | ✅ 0.7.2 | pypi.org/project/mcptoon/0.7.1 |
| MCP Registry | ✅ 收录 v0.7.0（0.7.1 元数据更新：用户指示过几天再更） | registry.modelcontextprotocol.io |
| Glama | ✅ 收录 + Dockerfile 构建检查通过（python -m 方案，见 .scratch 存档） | glama.ai/mcp/servers/activeing123/mcptoon |
| awesome-mcp-servers | 🟡 PR #12910 就绪等合（listed+badge 双条件已满足） | github.com/punkpeye/awesome-mcp-servers/pull/12910 |
| 其他 | 🟡 mcpb #299 / claude-plugins #5653 / awesome-mcp-clients #283+#290 等审；mcp.so 爬虫观察中（topics 已布）；PulseMCP 暂停、mcpservers.org/mcp.so 收费 $39 不投、Smithery 转 MCPB 暂缓 | — |

---

## 🗺️ 当前工作流（三阶段漏斗，物料已就绪）

```
阶段一 · 让人停下来        阶段二 · 让人懂           阶段三 · 让人用上
────────────────────   ────────────────────   ────────────────────
插排一图流 hero ✅      长文 ×3（痛点/方案/教程）   quickstart 成就感 ✅
15 秒短视频（脚本✅）    dev.to/Medium 英文母版✅   demo 一键对比 ✅
X/Reddit 一图+一句话     知乎/掘金/公号投放         一键安装脚本（待做）
```

- **待执行**：长文润色发布、短视频渲染（hyperframes 可用）、
  「小白使用手册」独立页、一键安装脚本、渠道分发。
- **推广物料审核流**：全部产物先落本地 → 用户审核 → 批准后才推 GitHub/发布。

---

## 🔧 产品待办（只做两类）

### A. 小白爽感增强（服务推广漏斗）
| # | 项 | 状态 | 备注 |
|---|----|------|------|
| A1 | `mcptoon quickstart` 输出"成就感"改造（找到 N 个工具 → 大字庆祝 + 使用引导） | ✅ v0.7.2 | "🎉 N tools ready across M servers!" + Now you can |
| A2 | `mcptoon demo` 输出小白化（前后对比大数字 + "现在你可以…"） | ✅ v0.7.2 | SAME data X% fewer + Now you can 清单 |
| A3 | 一键安装脚本（install.ps1 / install.sh：检测 Python → 安装 → quickstart） | ✅ v0.7.2 | README 双语已挂一行命令 |
| A4 | 「小白使用手册」独立页（图 + 三步 + FAQ + 反馈入口） | ⬜ | 篇三长文配套 |

### A+. Agent Plugins 生态（v0.7.1 新增，随 v0.7.1 已落地）
| # | 项 | 状态 | 备注 |
|---|----|------|------|
| P1 | Agent Plugins Spec 1.0.0 全支持（scan/install/list/remove） | ✅ v0.7.1 | GitHub Release v0.7.1 |
| P2 | 官方示例插件 `plugin/mcptoon-skills`（connect/authoring/triage 三技能，"吃自己的狗粮"） | ✅ 2026-09-01 | scan ✅ install ✅ serve 桥接 ✅ |
| P3 | 插件目录页 / `plugin install` 从 URL/zip 直装 | ⬜ | 等生态起量再投 |

### B. MCP 规范跟进（技术信誉）
| # | 项 | 状态 |
|---|----|------|
| B1 | 跟踪官方 SEP（动态工具发现、schema 缩减等），落地则进 0.8.0 | 👀 持续 |
| B2 | 规范新修订发布时 48 小时内兼容性声明（0.7.0 先例：发布当天即适配） | 📌 承诺 |

---

## 📅 版本规划（精简后）

```
v0.7.1  ✅ Agent Plugins Spec 1.0.0（实际发布内容，替代原"小白爽感"计划）
v0.7.2  ✅ A1+A2+A3 小白爽感版 + skills→prompts + 官方插件
v0.8.0  手册页 + 一键安装正式化 + SEP 新规范落地（如有）            — 视规范节奏
后续    仅按"是否帮助推广/上手"准入新功能
```

---

## 📈 竞品动态追踪

| 竞品 | 最新版本 | 最后更新 | 威胁等级 | 备注 |
|------|---------|---------|---------|------|
| mcpm.sh | v2.15.0 | 2026-05-22 | 🟡 中 | 开发停滞（Profile 优势存在但不再迭代）|
| ToolHive | v0.44.0 | 2026-08-18 | 🟡 中 | 企业级，与我们定位不同 |
| mcp-router | 未知 | 2026-08-25 | 🟡 中 | 桌面 GUI，无 CLI |
| mcp-hub | — | 2025-08 | 🟢 低 | 休眠 |

---

## 🏆 独有优势（必须保持）

| 优势 | 竞品现状 | 我们的壁垒 |
|------|---------|-----------|
| 99.8% Token 节省 | ToolHive 最高 85% | names-only manifest，竞品做不到 |
| 工具级 Toggle | 竞品仅 Server 级 | 精细控制单个工具开关 |
| 实时 Watch 监听 | 竞品无 | 毫秒级配置同步 |
| 零依赖安装 | mcpm 需 Node / ToolHive 需 Go | `pip install mcptoon` 即用 |
| MCP 规范时效 | 无人当天跟进 | 0.7.0 发布当天适配 2026-07-28 |

---

## 🚫 已否决方向（2026-08-27 用户决策，勿再自动提议）

| 原 milestone | 内容 | 否决理由 |
|--------------|------|---------|
| v0.6.1 计划 | Profile 工作区隔离 | 不服务推广/上手；堆功能 |
| v0.6.2 计划 | 凭证安全存储 | 同上 |
| v0.6.3 计划 | 安装源追踪+更新 | 同上 |
| v0.6.4 计划 | 扩展同步 13+ IDE | 同上 |
| v0.7.0 旧计划 | Tunnel 共享 + TUI | 同上（实际 0.7.0 已改做规范适配）|
| v0.8.0 旧计划 | 语义搜索 + 容器隔离 | 同上 |
| v0.9.0/v1.0.0 | 审计/OTel、RBAC、K8s Operator、Gateway | 企业向，与 CLI-first 冲突 |

*重新提议门槛：必须论证"如何直接提升曝光、转化或小白上手"，且经用户批准。*

---

## 📝 更新日志

### 2026-09-01
- ✅ skills→prompts：serve 把插件 SKILL.md 暴露为 MCP prompts（f7f6381，已入 main，CI 全绿）
- ✅ Glama Dockerfile 构建检查通过（buildSteps=uv pip + CMD `python -m mcptoon serve`）
- ✅ GitHub Topics 15 个布点；目录盘点：mcp.so/PulseMCP 观察中、付费目录不投
- ✅ 官方示例插件 `plugin/mcptoon-skills`（connect/authoring/triage）建好并全链路验证

### 2026-08-30
- ✅ v0.7.0 三渠道同步发布：GitHub main / PyPI（带 mcp-name 标记）/ MCP Registry 官方收录
- ✅ GitHub Actions 12 矩阵全绿；隐私审计通过（95 文件零泄漏，serve.py 内部词清理）
- ✅ servers#4700 政策性关闭 → 官方指路 Registry，已上架（正路打通）
- ✅ 营销物料包完成（本地待审）：插排 hero 双语 SVG + README 首屏改造方案 + 4 篇长文草稿
- ✅ 本路线图按 08-27 战略重写（否决项显式归档）

### 2026-08-29
- ✅ v0.7.0 功能完成：MCP 2026-07-28 规范适配（server/discover 协商、无状态 _meta、
  Mcp-Method/Mcp-Name 头、MRTR requestState 回显、-32022 回退）
- ✅ 21 个新测试（569 总），双语 README 规范矩阵、CHANGELOG

### 2026-08-27
- ✅ 战略重定位（用户决策）：CLI-first，推广优先于堆功能
- ✅ v0.6.1 发布：MCP 2025-06-18 规范兼容（structuredContent / call_tool_full）

### 2026-08-26
- ✅ 竞品深度调研 + 16 维矩阵；v0.6.0 发布（stats/toggle）；dev.to 首文；5 目录收录提交
