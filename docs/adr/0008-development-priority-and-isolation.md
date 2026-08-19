# ADR 0008: 开发优先级与隔离策略 — 不破坏现有功能

**Date:** 2026-08-18
**Status:** Accepted

## Context

mcptoon 当前已发布到 PyPI，有 172 星和 6 个 fork，用户正在使用 CLI 模式。新增 `serve` 和 `demo` 功能时，必须确保现有功能零影响。

## Decision

### 隔离原则
1. **新模块独立文件** — `serve` 和 `demo` 作为新模块添加，不修改现有 cli.py 的已有函数
2. **入口点追加** — 在 cli.py 的 dispatch 中新增 `serve` 和 `demo` 分支，不动其他分支
3. **零修改现有代码** — manifest.py, router.py, client.py 等现有模块不修改，只在新模块中 import 复用
4. **新文件清单**：
   - `src/mcptoon/serve.py` — stdio bridge MCP server 端实现
   - `src/mcptoon/schema_simplifier.py` — schema 精简函数（ADR 0006）
   - `src/mcptoon/demo.py` — 零配置 demo 命令
   - `src/mcptoon/__init__.py` — 追加新模块导出
   - `cli.py` — 仅在 dispatch 区域追加 serve/demo 分支
   - `tests/test_serve.py` — serve 模式测试
   - `tests/test_demo.py` — demo 模式测试

### 开发优先级
| 优先级 | 任务 | 预估 | 原则 |
|--------|------|------|------|
| P0 | `mcptoon serve` stdio bridge | 2-3 天 | 新文件，不动现有 |
| P1 | `mcptoon demo` 零配置体验 | 半天-1 天 | 新文件，不动现有 |
| P2 | README 更新（serve 模式文档） | 2 小时 | P0 完成后 |
| P3 | PyPI 发新版 | 小 | P0+P1 完成后 |
| P4 | CI 修复 + 测试 | 小 | 如不阻塞则靠后 |

## Rationale

1. **用户安全** — 现有用户 `pip install mcptoon` 后现有 CLI 行为完全不变
2. **回滚容易** — 如果新模块有 bug，删除新文件即可，现有功能不受影响
3. **并行开发** — 推广 agent 可以继续使用现有 mcptoon，开发 agent 独立开发新功能
4. **测试隔离** — 新功能有独立测试文件，不影响现有 427 个测试

## Consequences

- 新增 3 个源文件 + 2 个测试文件
- cli.py 仅在 dispatch 区域追加 2 个分支（serve, demo），其他行不动
- `__init__.py` 追加导出，不修改现有导出
- 版本号从 0.x 升到 0.x+1（minor bump），不是 breaking change
