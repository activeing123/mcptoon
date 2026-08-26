# mcptoon 产品路线图 & 更新计划

> **唯一权威路线图。所有版本计划以此文件为准。**
> **最后更新**: 2026-08-26
> **当前版本**: v0.6.0 | 540 tests | 0 依赖 | ~7,200 行
> **目标版本**: v1.0.0
> **竞品对标**: mcpm.sh v2.15.0 / ToolHive v0.44.0

---

## 🗺️ 路线图总览

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  v0.7.0 (P0短板补齐)          v0.8.0 (P1竞争力)           v1.0.0 (企业级)
  ─────────────────           ─────────────────           ─────────────────
  ⬜ Profile 系统             ⬜ Tunnel 共享               ⬜ 容器隔离
  ⬜ 凭证安全管理             ⬜ 语义搜索                  ⬜ 审计日志
  ⬜ 安装源追踪+更新          ⬜ TUI 交互界面              ⬜ 策略引擎/RBAC
  ⬜ 扩展同步目标(13+IDE)     ⬜ 自然语言命令增强          ⬜ K8s Operator
  ─────────────────           ─────────────────           ─────────────────
  预估: 1-2 周                预估: 2-3 周                预估: 4-6 周
  目标: 对标 mcpm.sh          目标: 差异化领先            目标: 企业市场
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
跨Agent同步              ✅ 6 IDE   ✅ 13+IDE ✅ 4 IDE   🔧 v0.7.0 扩展到13+
Profile工作区隔离         ❌        ✅        ✅ MCPGroup 🔧 v0.7.0
凭证安全存储             ❌ 明文    ❌        ✅ Keyring  🔧 v0.7.0
安装源追踪+更新          ❌        ✅        ❌         🔧 v0.7.0
Tunnel共享               ❌        ✅        ❌         🔧 v0.8.0
语义搜索                 ❌ 关键词  ❌        ✅ Embed   🔧 v0.8.0
交互式TUI                ❌        ❌        ✅ thv tui  🔧 v0.8.0
容器隔离                 ❌        ❌        ✅ Docker   📋 v1.0.0
审计日志/OTel            ❌        ❌        ✅          📋 v1.0.0
策略引擎/RBAC            ❌        ❌        ✅ Cedar    📋 v1.0.0
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

### Milestone 1: v0.7.0 — P0 短板补齐（对标 mcpm.sh）
**目标日期**: 2026-09-09（2 周内）
**核心价值**: 补齐 Profile/凭证/更新三大缺失，直接对标 mcpm.sh 核心功能

| # | 功能 | 优先级 | 预估 | 状态 | 负责 |
|---|------|--------|------|------|------|
| 1.1 | Profile 系统（create/switch/rm/ls/edit/run） | P0 | 2-3d | ⬜ 未开始 | Agent |
| 1.2 | 凭证安全存储（OS Keyring + 加密文件 fallback） | P0 | 1d | ⬜ 未开始 | Agent |
| 1.3 | 安装源追踪（sources.json）+ `mcptoon update` | P0 | 1-2d | ⬜ 未开始 | Agent |
| 1.4 | 扩展同步目标（Goose/Roo Code/Gemini CLI/Codex CLI/Qwen CLI） | P0 | 1d | ⬜ 未开始 | Agent |
| 1.5 | 全量回归测试 + README 更新 | P0 | 0.5d | ⬜ 未开始 | Agent |
| 1.6 | GitHub Release v0.7.0 + dev.to 中文文章发布 | P0 | 0.5d | ⬜ 未开始 | Agent |

**验收标准**:
- [ ] `mcptoon profile create/switch/rm/ls` 正常工作
- [ ] `mcptoon config set-key/get-key/list-keys` 安全存储凭证
- [ ] `mcptoon update --check` 检测可用更新
- [ ] sync 支持 13+ IDE
- [ ] 560+ 测试全部通过
- [ ] README 补充新功能文档

---

### Milestone 2: v0.8.0 — P1 差异化领先
**目标日期**: 2026-09-30（再 3 周）
**核心价值**: 在 mcpm.sh 没有的领域建立差异化壁垒

| # | 功能 | 优先级 | 预估 | 状态 | 负责 |
|---|------|--------|------|------|------|
| 2.1 | Tunnel 共享（`mcptoon share`，ngrok/cloudflared） | P1 | 2d | ⬜ 未开始 | Agent |
| 2.2 | 语义搜索（本地 Qwen3-Embedding 向量搜索） | P1 | 2-3d | ⬜ 未开始 | Agent |
| 2.3 | 交互式 TUI（Textual/rich 终端 UI） | P1 | 3-5d | ⬜ 未开始 | Agent |
| 2.4 | 自然语言命令增强（LLM-powered intent parsing） | P1 | 1-2d | ⬜ 未开始 | Agent |
| 2.5 | dev.to 中英文系列文章（3-5 篇） | P1 | 1d | ⬜ 未开始 | Agent |
| 2.6 | GitHub Release v0.8.0 | P1 | 0.5d | ⬜ 未开始 | Agent |

**验收标准**:
- [ ] `mcptoon share` 生成可分享的 HTTP 端点
- [ ] `mcptoon search "数据库操作"` 语义匹配相关工具
- [ ] `mcptoon tui` 启动交互式界面
- [ ] 600+ 测试全部通过

---

### Milestone 3: v1.0.0 — 企业级发布
**目标日期**: 2026-11-15（再 6 周）
**核心价值**: 进入企业市场，对标 ToolHive 的企业级能力

| # | 功能 | 优先级 | 预估 | 状态 | 负责 |
|---|------|--------|------|------|------|
| 3.1 | 可选容器隔离（Docker/Podman 运行 MCP Server） | P2 | 5-7d | ⬜ 未开始 | Agent |
| 3.2 | 审计日志 + OpenTelemetry 集成 | P2 | 3-5d | ⬜ 未开始 | Agent |
| 3.3 | 策略引擎（基础 RBAC：读/写/执行权限控制） | P2 | 3-5d | ⬜ 未开始 | Agent |
| 3.4 | Gateway 代理模式（运行时拦截+审计） | P2 | 5-7d | ⬜ 未开始 | Agent |
| 3.5 | 企业文档 + 部署指南 | P2 | 2d | ⬜ 未开始 | Agent |
| 3.6 | PyPI + Docker Hub 正式发布 | P2 | 1d | ⬜ 未开始 | Agent |

**验收标准**:
- [ ] `mcptoon serve --container docker` 容器化运行
- [ ] 审计日志可查询、可导出
- [ ] RBAC 策略可配置、可执行
- [ ] Gateway 模式拦截危险操作

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
- ✅ 制定 v0.7.0-v1.0.0 三阶段路线图
- ✅ 创建本计划文档
- ✅ dev.to 英文爆款文章发布
- ✅ PR #12910 挂载 Glama badge
- ✅ 5 个目录收录 Issue/PR 已提交
- ✅ mcptoon stats + toggle 命令实现
- ✅ GitHub Release v0.6.0 创建

### 2026-08-XX（待更新）
- ⬜ 开始 Profile 系统开发

---

## 🔗 相关文档

- 竞品调研: `competitive-intel-mcp-manager-tools.md`
- 竞品数据库: `.scratch/mcp-competitors/competitive_db.md`
- 设计文档: `.scratch/mcptoon-p0-plan/design.md`
- 功能规格: `.scratch/mcptoon-p0-plan/spec.md`
