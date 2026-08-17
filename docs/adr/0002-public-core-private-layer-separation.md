# ADR-0002: Public Core + Private Layer Separation

## Status
Accepted (2026-08-16)

## Context
mcptoon 需要同时满足两个目标：
1. 发布到 GitHub/PyPI 作为开源项目（不含私有凭据）
2. 本地使用包含私有 handlers（gbrain/mempalace/tinyfish 等）和私有配置

## Decision
采用双层架构：
- **公开核心** (`src/mcptoon/`)：零依赖，纯 stdlib，可发布到 PyPI
- **私有扩展层** (`local/`)：私有 handlers、配置、installer，不提交到 GitHub

公开核心通过 `router.register()` 机制提供扩展点，私有层通过 `import handlers` 自动注册。

## Consequences
- ✅ 公开仓库干净，不含私有信息
- ✅ 本地功能完整，私有 handler 正常工作
- ✅ 社区贡献者只看到公开核心
- ⚠️ install 功能在 local/ 层，GitHub 用户暂时用不到
- ⚠️ 需要文档说明如何写自己的 handler（公开核心已支持）
