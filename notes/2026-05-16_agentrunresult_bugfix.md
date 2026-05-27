# AgentRunResult.data → .output 字段修复

## 背景/需求

运行 Web UI 的**标题 A/B 测试**（`🎩 生成备选标题`）和**配图 Prompt 生成**（`🖼️ 生成小红书封面配图 Prompt`）功能时，抛错：

```
生成失败: 'AgentRunResult' object has no attribute 'data'
```

## 问题根因

`pydantic-ai` 的 `AgentRunResult` 对象用于存放 Agent 同步调用的结果，其字段名在不同版本中有变化。当前项目使用的版本中，结果数据放在 `.output` 属性上，而非 `.data`。

但 `web_ui.py` 中新增的两个辅助函数 `generate_titles()` 和 `generate_cover_prompt()` 仍沿用了旧写法 `r.data`，导致运行时 `AttributeError`。

> 注：`agent_core.py` 中的 `ContentAgent.run()` 是正确的（`result.output`），说明这个坑之前踩过，但 web_ui.py 的新代码没同步改过来。

## 核心修复

### `web_ui.py` 第 402 行 — `generate_titles()`

```python
# 修复前
r = title_agent.run_sync(prompt)
results[platform] = r.data

# 修复后
r = title_agent.run_sync(prompt)
results[platform] = r.output
```

### `web_ui.py` 第 447 行 — `generate_cover_prompt()`

```python
# 修复前
r = cover_agent.run_sync(prompt)
result = r.data.strip()

# 修复后
r = cover_agent.run_sync(prompt)
result = r.output.strip()
```

## 踩坑记录

1. **字段名不一致**：`pydantic-ai` 的 `Agent.run_sync()` 返回 `AgentRunResult`，结果字段在不同版本/不同文档中可能被描述为 `.data` 或 `.output`。实际以当前安装的版本为准，运行时直接 `print(dir(result))` 最可靠。
2. **代码分散容易遗漏**：`agent_core.py` 已经用了 `.output`，但 `web_ui.py` 的新增功能没同步。以后新增调用 `run_sync()` 的地方，必须统一检查字段名。
3. **README 已有记录**：README.md 第 188 行明确写了 "结果字段名变化：`result.data` → `result.output`"，但写新代码时没回头看文档。

## 验证方法

修复后，在 Web UI 中：
1. 先生成任意一篇小红书文案
2. 点击 **🎩 生成备选标题** — 应正常返回 3 个平台的备选标题
3. 点击 **🖼️ 生成小红书封面配图 Prompt** — 应正常返回画面描述 + Midjourney Prompt

## 下一步

- [x] 全项目扫描 `r.data` / `result.data` 残留 — 已完成，`web_ui.py` 是唯一运行时代码中的残留点
- [ ] 建立代码规范：任何调用 `Agent.run_sync()` 的地方，统一使用 `.output`
