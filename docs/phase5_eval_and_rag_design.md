# Eval + RAG 体系设计

> 将内容质量评估、回归测试和 RAG 检索增强收口到同一套质量体系中。

整合来源（以下文件已合并到本文档）：

- ~~`phase5_eval_system_design.md`~~
- ~~`phase5_eval_phase2_design.md`~~
- ~~`phase5_eval_phase3_design.md`~~
- ~~`phase5_rag_eval_proposal.md`~~

## 目标

- 每次生成后自动评估内容质量，减少纯人工判断。
- 改 prompt、模型、策略前后可以跑回归，有数据可对比。
- 用 RAG 从本地 Vault 笔记中检索相关上下文，提升内容相关性。
- 记录 token、耗时、模型等成本指标，支持后续优化。

## 总体架构

```text
Vault 笔记
  -> Markdown chunk 切分
  -> BGE-small-zh 向量化
  -> Chroma 持久化
  -> TopicPicker / TopicExecutor 检索 top-k 相关笔记
  -> WriterAgent 生成
  -> Evaluator / LLMJudge 打分
  -> Regression 对比报告
```

推荐模块结构：

```text
content_agent/rag/
  embedder.py       # BGE 嵌入模型封装
  vector_store.py   # Chroma 向量数据库
  indexer.py        # Vault 索引和检索

automation/eval/
  evaluator.py      # 主评估器
  llm_judge.py      # LLM 评分
  metrics.py        # 指标定义
  regression.py     # 回归测试
```

## RAG 方案

### 当前痛点

- 只能按文件名、标题或关键词匹配笔记。
- 热点和笔记语义相关但关键词不一致时容易漏召回。
- 生成内容时缺少历史实践笔记作为上下文。

### 选型

| 方案 | 向量数据库 | 嵌入模型 | 优点 | 缺点 |
| --- | --- | --- | --- | --- |
| A | Chroma | OpenAI text-embedding-3-small | 效果好，实现简单 | 有 API 成本 |
| B | Chroma | BGE-small-zh 本地模型 | 免费、离线、中文可用 | 首次需要下载模型 |
| C | BM25 | 无 | 最简单 | 无语义能力 |

推荐方案 B：`Chroma + BGE-small-zh`。

### 切分策略

优先按 Markdown 标题层级切分：

```text
# MCP 协议介绍
## 核心概念
## 与 Function Calling 的区别
```

理由：

- 保留语义完整性。
- 比固定长度 chunk 更适合技术笔记。
- chunk 数量可控，便于本地检索。

### 接入点

| 模块 | 接入方式 |
| --- | --- |
| TopicPicker | 热点向量化后检索相关笔记，辅助生成选题 |
| TopicExecutor | 生成前检索 top-k 笔记，合并为上下文 |
| TrendScheduler | 判断热点是否能和本地笔记结合 |
| RAGTool | 给 ReAct Agent 提供语义检索工具 |

## Eval 方案

### 评估维度

| 维度 | 指标 | 评估方式 | 触发时机 |
| --- | --- | --- | --- |
| 内容质量 | 相关性、可读性、原创性、实用性 | LLM 打分 | 每次生成后 |
| 热点匹配 | 内容与热点相关度 | LLM + 关键词检查 | 热点驱动生成后 |
| 平台适配 | 是否符合平台风格 | LLM + 规则检查 | 每次生成后 |
| 一致性 | 同任务多次生成稳定性 | 相似度 / 回归测试 | 回归时 |
| 成本效率 | token、耗时、模型 | 直接统计 | 每次生成后 |

### LLM Judge Prompt

```text
你是一位资深内容编辑。请对以下文案进行评分（1-10分）。

主题：
{topic}

平台：
{platform}

文案：
{content}

评分维度：
1. 相关性：内容与主题的相关程度
2. 可读性：语言是否流畅，结构是否清晰
3. 原创性：是否有独特见解，而非泛泛而谈
4. 实用性：读者能否获得实际价值
5. 平台适配：是否符合该平台阅读习惯

请输出 JSON：
{
  "relevance": 8,
  "readability": 7,
  "originality": 6,
  "practicality": 9,
  "platform_fit": 8,
  "overall": 7.6,
  "strengths": ["优点1", "优点2"],
  "weaknesses": ["不足1", "不足2"]
}
```

### 规则检查

| 平台 | 检查项 |
| --- | --- |
| 公众号 | 标题长度、章节结构、代码块、总结/下一步 |
| 小红书 | emoji 数量、标签数量、段落长度、标题吸引力 |
| 抖音 | 开头钩子、短句比例、画面提示、行动号召 |
| 通用 | 字数、敏感词、链接、空内容、重复内容 |

### 成本统计

| 指标 | 说明 |
| --- | --- |
| `prompt_tokens` | 输入 token 数 |
| `completion_tokens` | 输出 token 数 |
| `total_tokens` | 总 token 数 |
| `latency_ms` | 生成耗时 |
| `eval_latency_ms` | 评估耗时 |
| `model` | 生成模型 |
| `eval_model` | 评估模型 |

## 数据表

```sql
CREATE TABLE IF NOT EXISTS eval_results (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    platform TEXT,
    content_hash TEXT,
    relevance_score INTEGER,
    readability_score INTEGER,
    originality_score INTEGER,
    practicality_score INTEGER,
    platform_fit_score INTEGER,
    overall_score REAL,
    word_count INTEGER,
    has_sensitive_words BOOLEAN,
    has_link BOOLEAN,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER,
    model TEXT,
    eval_model TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS eval_baselines (
    id TEXT PRIMARY KEY,
    commit_hash TEXT,
    case_name TEXT,
    platform TEXT,
    overall_score REAL,
    scores TEXT,
    created_at TEXT
);
```

## 回归测试

固定测试集覆盖典型内容类型：

```python
REGRESSION_CASES = [
    {
        "name": "MCP 协议热点",
        "note_file": "2026-05-15_mcp_search_enhancement.md",
        "topic": "MCP 协议成为 AI 工具互联标准",
        "platforms": ["gongzhonghao", "xiaohongshu"],
        "trending_hint": "MCP 协议",
    },
    {
        "name": "CLI 工具改造",
        "note_file": "2026-05-15_cli_tooling.md",
        "topic": "从脚本到 CLI 工具",
        "platforms": ["gongzhonghao"],
        "trending_hint": "",
    },
]
```

流程：

```text
加载固定测试集
  -> 读取笔记
  -> 生成内容
  -> Eval 评分
  -> 保存结果
  -> 与基线对比
  -> 输出变化报告
```

CLI：

```bash
python main.py --eval-regression
python main.py --eval-regression --baseline commit_abc123
python main.py --eval-report
```

报告格式：

```text
回归测试报告
==============
基线版本: commit_abc123
当前版本: commit_def456

总体变化:
  综合评分: 7.5 -> 8.2 (+0.7)

各维度变化:
  相关性: 8.0 -> 8.5 (+0.5)
  可读性: 7.5 -> 8.0 (+0.5)

各用例详情:
  [通过] MCP 协议热点: 7.8 -> 8.3 (+0.5)
  [下降] 三平台输出: 7.5 -> 7.0 (-0.5)
```

## 实施顺序

1. RAG 基础：实现 embedder、vector_store、indexer。
2. RAG 接入：TopicExecutor 生成前检索相关笔记。
3. Eval 基础：LLMJudge 单指标 overall 打分。
4. Eval 完善：多维度评分、规则检查、成本统计。
5. Regression：固定测试集、基线、对比报告。
6. 生产策略：开发时全量评估，生产时抽样评估。

## 风险与对策

| 风险 | 对策 |
| --- | --- |
| BGE 模型下载慢 | 首次运行下载，后续缓存；支持配置本地路径 |
| Chroma 占用内存 | 当前笔记规模可接受，必要时懒加载 |
| Eval 增加成本 | 生产环境抽样，开发环境全量 |
| LLM Judge 主观性强 | 固定 prompt、固定测试集，必要时多模型投票 |
| RAG 引入噪声 | 限制 top-k，保留原始用户目标，RAG 只作为补充上下文 |
