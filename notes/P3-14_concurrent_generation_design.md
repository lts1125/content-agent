# P3-14: 并发生成设计

## 现状

WriterAgent.run() 调用一次 LLM，同时生成三平台文案。但实际上：
- LLM 内部输出三平台是串行的（先小红书→公众号→抖音）
- 如果用户只选了 1-2 个平台，仍然会生成全部三平台，浪费 Token
- batch_mode 下多篇笔记串行处理

## 目标

将三平台生成从"单次调用生成全部"改为"按平台并发调用"，提升 2-3x 速度。

## 方案 B：按需并发（推荐）

默认保持现有"单次调用生成三平台"不变，新增 UI 开关控制是否启用并发模式。

### 并发模式启用时

1. 新增 `PlatformWriterAgent`：每个实例只负责一个平台
   - 精简 system prompt，只包含该平台的要求
   - 输出结构简化为 `{platform}_content` + `tags`

2. `WriterAgent`改为持有三个 `PlatformWriterAgent`实例

3. `WriterAgent.run()` 根据 `platforms` 列表，用 `ThreadPoolExecutor(max_workers=3)` 并发调用
   - 只调用用户勾选的平台
   - 返回 `WriterOutput`（合并结果）

4. `WriterAgent.refine()` 同理：只重生成需要修改的平台，单线程即可

### 非并发模式（默认）

保持现有逻辑不变：单次 LLM 调用生成三平台。

### Batch Mode 并发

无论并发模式是否开启，batch_mode 下多篇笔记的 for 循环改为 `ThreadPoolExecutor(max_workers=3)` 并发执行。

### UI 开关

在配置区域新增：
```python
concurrent_mode = gr.Checkbox(
    label="⚡ 并发生成（每平台独立调用 API，更快但耗费更多 Token）",
    value=False,
)
```

### Token 消耗对比

| 平台数 | 非并发 | 并发 | 增减 |
|---|---|---|---|
| 1 | ~4500 | ~1700 | -62% ⬇️ |
| 2 | ~4500 | ~4400 | -2% ⬇️ |
| 3 | ~4500 | ~6600 | +47% ⮆ |

单平台时并发更省，两平台基本持平，三平台增加约 50%。

### 关键代码路径

- `agents/writer_agent.py` — 增加 PlatformWriterAgent + 并发逻辑 + concurrent 参数
- `agents/orchestrator.py` — 将 concurrent 参数传递给 WriterAgent
- `ui/handlers.py` — generate_content 接收 concurrent_mode 参数，batch_mode 并发执行
- `web_ui.py` — 添加 concurrent_mode UI 组件 + 事件绑定

### 利弊

| 维度 | 利 | 弊 |
|---|---|---|
| 速度 | 开启后三平台并发，时间约等于最慢平台的生成时间 | — |
| 成本 | 默认不开，零增加；开启后按平台数可能增加 0-50% | — |
| 一致性 | 默认模式保持现有一致性 | 并发模式分开生成，风格可能略有差异 |
| 灵活性 | 用户自己决定是否付出额外成本换取速度 | — |
