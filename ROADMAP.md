# mcptoon 产品路线图 & 更新计划

> **唯一权威路线图。所有版本计划以此文件为准。**
> **最后更新**: 2026-08-26
> **当前版本**: v0.6.0 | 540 tests | 0 依赖 | ~7,200 行
> **目标版本**: v1.0.0
> **竞品对标**: mcpm.sh v2.15.0 / ToolHive v0.44.0
> **版本策略**: 每个版本只做 1-3 个小功能，快速迭代，频繁发布

---

## 🗺️ 路线图总览

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 v0.6.1         v0.6.2         v0.6.3         v0.6.4         v0.7.0         v0.8.0
 ──────         ──────         ──────         ──────         ──────         ──────
 ⬜ Profile     ⬜ 凭证安全     ⬜ 安装源追踪   ⬜ 扩展同步     ⬜ Tunnel共享   ⬜ 语义搜索
   系统          存储           +更新          13+IDE         +TUI           +容器隔离
 ──────         ──────         ──────         ──────         ──────         ──────
 1-2天           1天            1-2天          1天            3-5天          5-7天
 对标mcpm.sh    对标ToolHive   对标mcpm.sh    追平mcpm.sh    差异化领先      企业级
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 📊 功能矩阵（mcptoon vs 竞品 vs 计划）

```
功能维度                  mcptoon   mcpm.sh   ToolHive   我们的计划
─────────────────────────────────────────────────────────────────
Token 优化 99.8%          ✅ 99.8%   ❌        ✅ 85%     ✅ 保持领先
工具级 Toggle             ✅ 独有    ❌ Server级 ❌        ✅ 保持领先
实时 Watch 监听           ✅ 独有    ❌        ❌         ✅ 保持领先
投毒检测+凭据防护         ✅        ❌        ✅容器级    ✅ 保持
零依赖安装               ✅        ❌ Node.js ❌ Go      ✅ 保持
跨Agent同步              ✅ 6 IDE   ✅ 13+IDE ✅ 4 IDE   🔧 v0.6.4 扩展到13+
Profile工作区隔离         ❌        ✅        ✅ MCPGroup 🔧 v0.6.1
凭证安全存储             ❌ 明文    ❌        ✅ Keyring  🔧 v0.6.2
安装源追踪+更新          ❌        ✅        ❌         🔧 v0.6.3
Tunnel共享               ❌        ✅        ❌         🔧 v0.7.0
交互式TUI                ❌        ❌        ✅ thv tui  🔧 v0.7.0
语义搜索                 ❌ 关键词  ❌        ✅ Embed   🔧 v0.8.0
容器隔离                 ❌        ❌        ✅ Docker   📋 v0.8.0
审计日志/OTel            ❌        ❌        ✅          📋 v0.9.0
策略引擎/RBAC            ❌        ❌        ✅ Cedar    📋 v0.9.0
K8s Operator             ❌        ❌        ✅ CRD      📋 v1.0.0
```

---

## 🎯 竞争定位

```
                        轻量 CLI                         重量级平台
                        ←────────────────────────────────────→

  mcptoon ★       mcpm.sh ★★★        ToolHive ★★★★★
  ┌──────────┐    ┌──────────────┐    ┌──────────────────┐
  │ Token王  │    │ Profile王    │    │ 企业王           │
  │ 工具控制 │    │ Registry     │    │ 容器+K8s+策略    │
  │ 零依赖   │    │ 更新管理     │    │ 审计+OTel        │
  │ Watch    │    │ 多Client     │    │ SSO+RBAC        │
  │ 投毒检测 │    │ Tunnel共享   │    │ vMCP聚合        │
  └──────────┘    └──────────────┘    └──────────────────┘
        ↑                ↑                    │
        └──── 我们的目标：在轻量CLI区间做到最好 ──┘
              不跟 ToolHive 比企业
              不跟 mcpm.sh 比 Registry
              比的是：Token效率 + 精细控制 + 零依赖
```

---

## 📅 里程碑计划

### Milestone 1: v0.6.1 — Profile 系统（工作区隔离）
**目标日期**: 2026-08-28（2 天内）
**核心价值**: 按项目隔离 MCP 工具集，对标 mcpm.sh 最大优势

| # | 功能 | 优先级 | 预估 | 状态 | 负责 |
|---|------|--------|------|------|------|
| 1.1 | `mcptoon profile ls` — 列出所有 Profile | P0 | 0.5d | ⬜ 未开始 | Agent |
| 1.2 | `mcptoon profile create <name>` — 创建 Profile | P0 | 0.5d | ⬜ 未开始 | Agent |
| 1.3 | `mcptoon profile switch <name>` — 切换活跃 Profile | P0 | 0.5d | ⬜ 未开始 | Agent |
| 1.4 | `mcptoon profile rm <name>` — 删除 Profile | P0 | 0.5d | ⬜ 未开始 | Agent |
| 1.5 | `mcptoon profile run <name> -- http` — 以指定 Profile 启动 | P0 | 0.5d | ⬜ 未开始 | Agent |
| 1.6 | 向后兼容：无 Profile 时行为不变 | P0 | 0.5d | ⬜ 未开始 | Agent |
| 1.7 | 测试 + README + Release v0.6.1 | P0 | 0.5d | ⬜ 未开始 | Agent |

**验收标准**:
- [ ] `mcptoon profile create frontend` 创建 Profile
- [ ] `mcptoon profile switch frontend` 切换成功
- [ ] `mcptoon manifest` 显示当前 Profile 的工具
- [ ] 无 Profile 时行为与 v0.6.0 完全一致
- [ ] 新增 10+ 测试用例
- [ ] README 补充 Profile 文档

---

### Milestone 2: v0.6.2 — 凭证安全存储
**目标日期**: 2026-08-30（2 天内）
**核心价值**: API Key 走 OS 安全存储，不再明文

| # | 功能 | 优先级 | 预估 | 状态 | 负责 |
|---|------|--------|------|------|------|
| 2.1 | `mcptoon config set-key <name>` — 安全存储 API Key | P0 | 1d | ⬜ 未开始 | Agent |
| 2.2 | `mcptoon config get-key <name>` — 读取 API Key | P0 | 0.5d | ⬜ 未开始 | Agent |
| 2.3 | `mcptoon config list-keys` — 列出已存储的 Key 名称 | P0 | 0.5d | ⬜ 未开始 | Agent |
| 2.4 | OS Keyring + 加密文件 fallback | P0 | 1d | ⬜ 未开始 | Agent |
| 2.5 | 测试 + README + Release v0.6.2 | P0 | 0.5d | ⬜ 未开始 | Agent |

**验收标准**:
- [ ] `mcptoon config set-key exa` 交互输入后安全存储
- [ ] `mcptoon config list-keys` 显示 `exa`（不含明文值）
- [ ] Windows/macOS/Linux 三平台兼容
- [ ] 新增 8+ 测试用例

---

### Milestone 3: v0.6.3 — 安装源追踪 + 自动更新
**目标日期**: 2026-09-02（2 天内）
**核心价值**: 检测已安装 MCP Server 的新版本

| # | 功能 | 优先级 | 预估 | 状态 | 负责 |
|---|------|--------|------|------|------|
| 3.1 | `~/.mcptoon/sources.json` 追踪已安装 server | P0 | 1d | ⬜ 未开始 | Agent |
| 3.2 | `mcptoon update --check` — 检测可用更新 | P0 | 1d | ⬜ 未开始 | Agent |
| 3.3 | `mcptoon update <server>` — 更新指定 server | P0 | 1d | ⬜ 未开始 | Agent |
| 3.4 | 测试 + README + Release v0.6.3 | P0 | 0.5d | ⬜ 未开始 | Agent |

**验收标准**:
- [ ] 安装时自动写入 `sources.json`
- [ ] `mcptoon update --check` 显示可用更新列表
- [ ] `mcptoon update exa` 执行更新
- [ ] 新增 6+ 测试用例

---

### Milestone 4: v0.6.4 — 扩展同步目标
**目标日期**: 2026-09-04（2 天内）
**核心价值**: 追平 mcpm.sh 的 13+ Client 支持

| # | 功能 | 优先级 | 预估 | 状态 | 负责 |
|---|------|--------|------|------|------|
| 4.1 | 补齐 Goose 同步 | P0 | 0.5d | ⬜ 未开始 | Agent |
| 4.2 | 补齐 Roo Code 同步 | P0 | 0.5d | ⬜ 未开始 | Agent |
| 4.3 | 补齐 Gemini CLI / Codex CLI / Qwen CLI 同步 | P0 | 1d | ⬜ 未开始 | Agent |
| 4.4 | 测试 + README + Release v0.6.4 | P0 | 0.5d | ⬜ 未开始 | Agent |

**验收标准**:
- [ ] `mcptoon sync` 支持 13+ IDE
- [ ] README "Works with" 列表更新
- [ ] 新增 4+ 测试用例

---

### Milestone 5: v0.7.0 — Tunnel 共享 + TUI
**目标日期**: 2026-09-15（10 天内）
**核心价值**: 团队协作 + 交互式体验

| # | 功能 | 优先级 | 预估 | 状态 | 负责 |
|---|------|--------|------|------|------|
| 5.1 | `mcptoon share` — ngrok/cloudflared 隧道 | P1 | 2d | ⬜ 未开始 | Agent |
| 5.2 | `mcptoon tui` — Textual/rich 终端 UI | P1 | 3-5d | ⬜ 未开始 | Agent |
| 5.3 | 测试 + README + Release v0.7.0 | P1 | 0.5d | ⬜ 未开始 | Agent |

**验收标准**:
- [ ] `mcptoon share` 生成可分享的 HTTP 端点
- [ ] `mcptoon tui` 启动交互式界面
- [ ] 新增 10+ 测试用例

---

### Milestone 6: v0.8.0 — 语义搜索 + 容器隔离
**目标日期**: 2026-10-15（30 天内）
**核心价值**: 企业级能力初步

| # | 功能 | 优先级 | 预估 | 状态 | 负责 |
|---|------|--------|------|------|------|
| 6.1 | 语义搜索（本地 Embedding 向量搜索） | P1 | 2-3d | ⬜ 未开始 | Agent |
| 6.2 | 可选容器隔离（Docker/Podman） | P2 | 5-7d | ⬜ 未开始 | Agent |
| 6.3 | 测试 + README + Release v0.8.0 | P1 | 0.5d | ⬜ 未开始 | Agent |

---

### Milestone 7: v0.9.0 — 审计 + 策略
**目标日期**: 2026-11-15（30 天内）
**核心价值**: 企业合规基础

| # | 功能 | 优先级 | 预估 | 状态 | 负责 |
|---|------|--------|------|------|------|
| 7.1 | 审计日志 + OpenTelemetry | P2 | 3-5d | ⬜ 未开始 | Agent |
| 7.2 | 策略引擎（基础 RBAC） | P2 | 3-5d | ⬜ 未开始 | Agent |
| 7.3 | 测试 + README + Release v0.9.0 | P2 | 0.5d | ⬜ 未开始 | Agent |

---

### Milestone 8: v1.0.0 — 企业级发布
**目标日期**: 2026-12-31（80 天内）
**核心价值**: 正式进入企业市场

| # | 功能 | 优先级 | 预估 | 状态 | 负责 |
|---|------|--------|------|------|------|
| 8.1 | K8s Operator | P2 | 5-7d | ⬜ 未开始 | Agent |
| 8.2 | Gateway 代理模式 | P2 | 5-7d | ⬜ 未开始 | Agent |
| 8.3 | 企业文档 + 部署指南 | P2 | 2d | ⬜ 未开始 | Agent |
| 8.4 | PyPI + Docker Hub 正式发布 | P2 | 1d | ⬜ 未开始 | Agent |

---

## 📈 竞品动态追踪

| 竞品 | 最新版本 | 最后更新 | 威胁等级 | 备注 |
|------|---------|---------|---------|------|
| mcpm.sh | v2.15.0 | 2026-05-22 | 🔴 高 | 开发减速（3月未更新），Profile系统是核心优势 |
| ToolHive | v0.44.0 | 2026-08-18 | 🟡 中 | 企业级，与我们定位不同 |
| mcp-router | 未知 | 2026-08-25 | 🟡 中 | 桌面GUI，无CLI能力 |
| 5ire | 未知 | 2026-08-25 | 🟢 低 | AI助手，非管理工具 |
| mcp-hub | v? | 2025-08 | 🟢 低 | 已休眠1年 |

---

## 🏆 独有优势（必须保持）

| 优势 | 竞品现状 | 我们的壁垒 |
|------|---------|-----------|
| **99.8% Token 节省** | ToolHive 最高 85% | names-only manifest，竞品做不到 |
| **工具级 Toggle** | 竞品仅 Server 级 | 精细控制单个工具开关 |
| **实时 Watch 监听** | 竞品无此功能 | 毫秒级配置同步 |
| **零依赖安装** | mcpm.sh 需要 Node.js，ToolHive 需要 Go | `pip install mcptoon` 即用 |
| **投毒检测+凭据防护** | 轻量级，竞品需容器 | 零依赖安全层 |

---

## 📝 每日更新日志

### 2026-08-26
- ✅ 完成竞品深度调研（mcpm.sh v2.15.0 / ToolHive v0.44.0 / mcp-router / 5ire）
- ✅ 输出功能矩阵对比报告（16 个维度 × 4 竞品）
- ✅ 识别 12 个短板（4 P0 / 4 P1 / 4 P2）
- ✅ 制定 v0.6.1-v1.0.0 八阶段路线图（版本细分，每版 1-3 功能）
- ✅ 创建本计划文档
- ✅ dev.to 英文爆款文章发布
- ✅ PR #12910 挂载 Glama badge
- ✅ 5 个目录收录 Issue/PR 已提交
- ✅ mcptoon stats + toggle 命令实现
- ✅ GitHub Release v0.6.0 创建
- ✅ CI 修复：删除 3 个未使用 import + 升级到 Node.js 24 兼容
- ✅ GitHub token 更新（Bitwarden MCPCLI_GITHUB_TOKEN）
- ✅ GBrain/MemPalace 记忆保存验证（--file 全文存储，100% 完整性）

### 2026-08-27
- ✅ 方向重定位（用户决策）：CLI-first，推广优先于堆功能；Profile/IDE同步/企业特性方向否决
- ✅ 分析官方新版 MCP Server 开发指南视频 → 提取新协议要点（structuredContent/_meta/resultType）
- ✅ v0.6.1 发布：新 MCP 规范（2025-06-18）兼容
  - `structuredContent` 原生解析（自动优先，零配置）
  - `mcptoon call --envelope` 完整结果信封透传（含 --auto）
  - 库 API：`MCPClient.call_tool_full()` / `MCPClientPool.call_full()`
  - 8 个新测试（548 总数），README EN/zh-CN 规范徽章 + 兼容矩阵 + SEO/GEO 关键词强化
  - GitHub Release v0.6.1 → PyPI 发布成功（第一次真正 0.6.x 上 PyPI）
  - rebase 到远端 README 重构（9 个 docs 提交）并保留兼容内容

### 2026-08-XX（待更新）
- ⬜ ROADMAP 按推广优先方向重写（删除 Profile/同步扩展/K8s 等已否决项）

---

## 🔗 相关文档

- 竞品调研: `competitive-intel-mcp-manager-tools.md`
- 竞品数据库: `.scratch/mcp-competitors/competitive_db.md`
- 设计文档: `.scratch/mcptoon-p0-plan/design.md`
- 功能规格: `.scratch/mcptoon-p0-plan/spec.md`
