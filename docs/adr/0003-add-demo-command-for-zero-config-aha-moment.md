# ADR 0003: 新增 mcptoon demo 零配置一键体验命令

**Date:** 2026-08-18
**Status:** Proposed

## Context

当前 mcptoon 的首次体验路径：

| 场景 | 路径 | 问题 |
|------|------|------|
| 用户已有 MCP server | `pip install` → `quickstart` → 自动发现 + 配置 + 显示 manifest | ✅ 良好 |
| 用户没有 MCP server | `pip install` → `quickstart` → "No servers found" → 打印帮助 → 用户走了 | ❌ 第一步流失 |

目标用户是个人 AI agent 用户，其中很大一部分是"好奇来试试"的人，他们可能还没装过 MCP server。需要在 30 秒内给他们一个 aha moment。

## Decision

新增 `mcptoon demo` 命令——零配置一键体验。

## 设计

### 行为
1. 自动下载一个零依赖 MCP server（`@modelcontextprotocol/server-fetch`，无需 API key）
2. 添加到 mcptoon 配置
3. 调用一次工具（fetch 一个 URL）
4. 并排展示：JSON 原始输出 vs TOON 压缩输出 vs SLIM 压缩输出
5. 显示 token 对比数字："这个调用省了 X% tokens"
6. 引导下一步：`mcptoon quickstart` 发现你已有的 server

### 关键体验
- 30 秒内完成
- 零配置——不需要 API key、不需要预设
- 视觉冲击——看到 "90,804 tokens → 117 tokens" 的震撼对比

### 不做
- 不自动安装 npx（如果用户没装 Node.js，提示先装）
- 不做交互式菜单（纯 CLI 一行命令）
- 不持久化 demo server（除非用户选择保留）

## Rationale

1. **对比行业最佳实践** — n8n 有空模板引导，homebrew 可以直接 `brew install` 东西，fastmcp 3 行代码就能跑
2. **降低试用门槛** — "好奇来看看"的用户不需要先了解 MCP 生态
3. **aha moment = 数字震撼** — "90K → 117 tokens" 比任何文字描述都有说服力
4. **病毒传播锚点** — 用户截图发推特/Reddit 的素材就是这个数字对比

## Consequences

- 新增一个 `_cmd_demo` 函数到 cli.py
- 需要处理 npx 不存在的边界情况
- demo server 可以用临时配置（不写入持久配置文件，除非用户 `--keep`）
- README 快速开始部分增加 `mcptoon demo` 作为推荐第一步
