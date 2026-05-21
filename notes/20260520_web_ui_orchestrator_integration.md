# Web UI 接入 Orchestrator

## 背景/需求

原先 `web_ui.py` 的 `generate_content()` 直接调用 `ContentAgent.run()` 生成文案，然后手动调用 `QualityChecker.check()` 做质检，最多重试 3 次。这个逻辑与 CLI 版 `main.py` 中的硬编码循环重复，且缺乏结构化信息（用户看不到编辑过程）。

随着 `agents/` 目录下 `Orchestrator` → `WriterAgent` → `EditorAgent` 的流水线成型，Web UI 需要接入这套新架构，获得：
- Writer → Editor 循环（最多 3 次含初稿）
- 结构化编辑建议展示
- 熔断机制（3 次不过则标记 human_review）
- 统一的 LLM 调用计数和耗时统计

## 设计思路

**方案对比：**

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| A. web_ui 内保留旧循环 | 改动最小 | 与 Orchestrator 重复，维护两份逻辑 | ❌ |
| B. 封装 `process_request()` 同步接口 | 清晰封装，web_ui 零感知异步细节 | 需额外函数层 | 考虑过，最终未采用 |
| C. **直接调用 `orchestrator.run()`** | 最简单，Orchestrator 本身是同步接口 | web_ui 直接依赖 Orchestrator 内部结构 | ✅ 采用 |

最终选择方案 C，原因是 `Orchestrator.run()` 已经是同步方法，返回 `TaskState`，web_ui 直接构建 `TaskInput` 传入即可，无需额外封装。

**搜索增强的处理：** 保留在 Orchestrator 外部。因为 web_ui 已有自己的搜索增强逻辑（LLM 关键词提取 + DuckDuckGo/Tavily），Orchestrator 的 `enable_research` 是独立开关。为避免重复搜索，传入 `enable_research=False`，让 Orchestrator 跳过 ResearchAgent。

## 核心实现

### 1. 导入与懒加载

```python
from agents.schemas import TaskInput
from agents.orchestrator import Orchestrator

_orchestrator = None

def _get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
```

`_get_orchestrator()` 与 `_get_agent()`、`_get_checker()` 保持一致，避免每次点击生成都重新初始化。

### 2. `generate_content()` 中的调用替换

**旧逻辑（保留在代码注释中已删除）：**
```python
# 旧：直接 agent.run + checker.check 循环
for attempt in range(1, 4):
    generation_result = agent.run(styled_notes)
    check = checker.check(...)
    if check.passed: break
```

**新逻辑：**
```python
# 新：通过 Orchestrator 统一调度
task_input = TaskInput(
    note_text=styled_notes,
    note_source=note_file or "clipboard",
    platforms=list(enabled),
    enable_research=False,  # 搜索增强已在外层处理
    search_engine=search_engine,
    style=style,
    batch_mode=False,
)
orchestrator = _get_orchestrator()
state = orchestrator.run(task_input)
generation_result = state.final_output
orchestrator_states.append(state)
```

### 3. 状态栏展示 Orchestrator 元数据

收集 `orchestrator_states`（批量模式下每篇一个），在状态栏展示：

```python
total_llm_calls = sum((st.metadata.get("llm_calls", 0) for st in orchestrator_states if st), 0)
total_duration = sum((st.metadata.get("duration_sec", 0) for st in orchestrator_states if st), 0)
human_review_count = sum((1 for st in orchestrator_states if st and st.metadata.get("human_review_needed")), 0)
token_exceeded_count = sum((1 for st in orchestrator_states if st and st.metadata.get("token_budget_exceeded")), 0)
```

状态栏输出示例：
```
✅ 完成！共 1 篇 | 平台: 小红书, 公众号, 抖音 | LLM调用:3次 | 耗时:8.5s
```

当编辑未达标时：
```
⚠️ 1篇3次编辑未达标，取最佳稿
编辑建议:
  • 小红书缺少 emoji，建议每段加 1-2 个
  • 公众号开头可以更抓人
```

### 4. 批量模式适配

批量模式下每篇笔记独立构建 `TaskInput`，独立调用 `orchestrator.run()`，各自产生 `TaskState`，最后合并到 `orchestrator_states` 列表中统一统计。

## 踩坑记录

1. **`TaskInput.enable_research=False` 避免重复搜索** — Orchestrator 内部也有 ResearchAgent，如果 web_ui 外层已做搜索增强，必须传 `False`，否则同一篇笔记会被搜两次，浪费 Token 且可能引入无关信息。

2. **`state.final_output` 可能为 `None`** — 当 Orchestrator 内部发生异常（如 LLM 调用失败）时，`final_output` 可能为 `None`。需兜底处理：
   ```python
   if generation_result is None:
       xs = gh = dy = "❌ 生成失败"
   ```

3. **编辑建议的展示长度控制** — `edit_history` 可能很长，状态栏只展示最后一轮的 `suggestions[:3]`，避免 Gradio 文本框溢出。

4. **Orchestrator 的同步接口** — 最初考虑过 `asyncio.run()` 包装异步 Orchestrator，但发现 `Orchestrator.run()` 已是同步方法，无需 async 转换。

## 使用方法

直接运行 Web UI，使用方式无变化：

```bash
python web_ui.py
```

用户无感知架构切换，但状态栏会显示更丰富的生成过程信息（LLM 调用次数、耗时、编辑建议）。

## 下一步

- [ ] `refine_content()`（"再改一版"）也接入 Orchestrator，当前仍直接调用 `agent.run()`
- [ ] 考虑给 Orchestrator 加一个 `asyncio.Lock()`，防止用户快速双击生成按钮导致并发问题
- [ ] 当 `human_review_needed` 时，在 UI 上高亮提示，而不是仅在状态栏文字提示
