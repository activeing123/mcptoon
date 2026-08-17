# ADR-0004: Forwarding Layer for Backward Compatibility

## Status
Accepted (2026-08-16)

## Context
从旧版 `universal_call.py`（MCP Proxy 模式）迁移到新版 `cli_pro.py`（CLI 模式）时，已有数百个技能文件引用了旧版路径和命令格式。直接修改所有技能文件成本太高。

## Decision
将 `universal_call.py` 改写为转发壳（forwarding layer）：
1. 接收旧版命令格式（`discover`→`servers`, `tools`→`manifest`, `--mcptoon`→`--toon`）
2. 转发到新版 `cli_pro.py` 执行
3. 如果新版崩溃/超时，自动 fallback 到旧版 `universal_call.py.bak`
4. 记录 fallback 事件到 `~/.mcp-cli/fallback_log.jsonl`

## Consequences
- ✅ 所有技能文件零修改即可使用新版
- ✅ 安全网：新版有问题自动回退旧版
- ✅ 渐进迁移：可以逐步修改技能文件
- ⚠️ 多一层转发增加 ~50ms 延迟
- ⚠️ 需要维护两个版本直到确认新版稳定
