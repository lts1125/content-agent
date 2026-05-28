# Content Agent 架构整理备忘

日期：2026-05-27

## 背景

`content-agent` 最初是一个内容生成脚本/工具，后续逐步加入多平台输出、质量检查、ReAct、Orchestrator、自动化队列、选题、发布等能力。现在它已经适合作为“从工具演进到 Agent”的实践原型，但代码结构开始出现旧链路与新链路并存、配置重复、工具实现漂移等问题。

当前阶段先暂停新增功能，优先做架构收口和可维护性整理。

## 当前定位

更准确的项目定位：

> 一个内容创作 Agent 原型：从笔记输入开始，经历研究、写作、审稿、修改、入队，逐步加入工具、记忆和自动化触发。

不建议对外称为“完全自主 Agent”。更适合表达为：从内容生成工具逐步演进到具备 Agent 特征的自动化内容系统。

## 主要问题

### 1. RAG 工具实现实际上失效 【已解决】

位置：`agents/tools.py`

`RAGTool` 当前导入：

```python
from content_agent.rag_pipeline import RAGPipeline
```

但项目中没有找到 `content_agent/rag_pipeline.py`。实际 RAG 目录是 `content_agent/rag/`，`TopicExecutor` 使用的是：

```python
from content_agent.rag.indexer import VaultIndexer
```

风险：

- ReAct 工具列表暴露了 `rag`，但实际调用可能失败。
- 教学展示时容易出现“工具存在但不可用”的问题。

建议：

- 统一 `RAGTool` 到 `content_agent.rag.indexer.VaultIndexer`。
- 给 `rag` 工具加最小单测，验证空索引、正常检索、异常降级。

### 2. ReAct 修改闭环还不完整 【已解决】

位置：`agents/react_agent.py`

当前逻辑里：

- `regenerate` 会重新调用 `generate`，但没有把评估建议稳定注入 prompt。
- `refine` 分支目前只是 `pass`。

风险：

- 代码名义上有“评估-反思-修改循环”，但实际修改能力不完整。
- 对外讲 ReAct 时，容易被真实代码行为拖后腿。

建议：

- 将 `refine` 接到 `WriterAgent.refine` 或平台级 `PlatformWriterAgent.refine`。
- 把 `eval_observation`、`suggestions`、`weakest` 明确传给修改 prompt。
- 记录每轮修改前后的差异，便于 UI 和文章展示。

### 3. 模型配置重复且已经漂移 【已解决】

位置：

- `content_agent/agent_core.py`
- `agents/writer_agent.py`
- `agents/tools.py`

问题：

- `content_agent.agent_core.ModelConfig` 和 `agents.writer_agent._ModelConfig` 重复。
- MiniMax base URL 不一致：
  - `agent_core.py`: `https://api.minimax.chat/v1`
  - `writer_agent.py`: `https://api.minimaxi.com/v1`
- `tools.py` 又从 `agents.writer_agent` 导入 `_ModelConfig`。

风险：

- 后续切换模型或修 Provider 时容易漏改。
- 测试和实际运行链路可能使用不同配置。

建议：

- 新建统一配置模块，例如 `content_agent/config/model_config.py` 或 `agents/model_config.py`。
- 所有 Agent、工具、旧核心都从统一入口读取模型。
- 将旧配置保留为兼容导入，逐步迁移。

### 4. 旧链路和新链路并存，主路径不清晰

位置：`main.py`

当前同时存在：

- 旧链路：`ContentAgent + QualityChecker`
- 新链路：`Orchestrator + TaskInput`

风险：

- 同类功能需要在两个地方维护。
- 后续视频/文章讲项目架构时，主线不够清楚。
- 新增功能容易不知道接到旧链路还是新链路。

建议：

- 明确主流程统一走 `agents/Orchestrator`。
- 旧链路移动或标记为 `legacy`，只作为历史演进材料保留。
- `main.py` 只保留清晰 CLI 分派，不再承载过多业务逻辑。

### 5. 数据库 schema version 设计不够稳

位置：`agents/store.py`

当前：

```python
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
)
```

读取：

```python
SELECT version FROM schema_version LIMIT 1
```

问题：

- 每次版本变化可能插入新行。
- `LIMIT 1` 没有排序，未来可能读到旧版本。

建议：

- 改为单行 schema 状态：

```sql
CREATE TABLE schema_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL
)
```

- 或使用 `PRAGMA user_version` 管理 schema 版本。

### 6. 工具层存在本机路径硬编码 【已解决】

位置：`agents/tools.py`

当前存在：

```python
sys.path.insert(0, '/Users/lee/content-agent')
```

风险：

- 项目迁移、开源、换机器、打包后都容易失效。
- 作为教程项目不够干净。

建议：

- 使用标准包导入。
- 在 CLI/应用入口统一处理项目根路径。
- 工具层不应该知道本机绝对路径。

### 7. `tools.py` 过重，工具注册和工具实现耦合

位置：`agents/tools.py`

当前一个文件同时承担：

- ToolResult/BaseTool 抽象
- 搜索/浏览/读文件/生成/评估/发布/RAG/分析/代码执行所有工具实现
- 工具注册表

风险：

- 文件继续变大后难以维护。
- 工具测试不够聚焦。
- 高风险工具（发布、代码执行）和低风险工具混在一起。

建议拆分：

```text
agents/tools/
  __init__.py
  base.py
  registry.py
  search.py
  browse.py
  file_read.py
  generate.py
  evaluate.py
  publish.py
  rag.py
  analysis.py
  code_execution.py
```

### 8. Agent 执行轨迹还不够产品化

当前已经有 `TaskState`、`drafts`、`edit_history`，但对“系列内容展示”还不够友好。

建议后续增加：

- `trace.json`：记录 plan、tool calls、drafts、editor verdict、final output。
- UI 展示 Thought / Action / Observation。
- 每个任务保留可视化 timeline，方便做公众号截图和抖音讲解。

## 推荐整理顺序

### 第一阶段：架构收口

1. 抽出统一 `ModelConfig`。
2. 修复 `RAGTool`。
3. 将 ReAct `refine` 分支接入真实修改逻辑。
4. 明确主链路统一走 `Orchestrator`。
5. 旧 `ContentAgent` 链路标记为 legacy。

### 第二阶段：工具层整理

1. 拆分 `agents/tools.py`。
2. 去掉本机绝对路径。
3. 给每个工具写最小单测。
4. 区分安全工具和高风险工具。

### 第三阶段：状态与可观察性

1. 修正 schema version。
2. 补充任务 trace。
3. UI 展示 Agent 运行过程。
4. 将执行轨迹作为文章/视频素材来源。

## 内容系列角度的表达

适合对外讲成：

1. 第一个版本只是内容生成脚本。
2. 后来抽出 Writer / Editor / Researcher。
3. 再加入 Orchestrator 管控流程。
4. 然后接入工具系统和 ReAct。
5. 最后逐步加入记忆、队列、自动触发和审核门。

这条线比“我直接做了一个 Agent”更真实，也更有说服力。

