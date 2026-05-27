# RAG + Eval 体系落地方案

> 在当前 content-agent 项目中引入 RAG 检索增强和自动化评估体系

---

## 一、RAG 方案

### 1.1 当前痛点

Vault 笔记查找目前有两种方式：
- **精确匹配**：按文件名/标题匹配（`P0_automation_implementation.md`）
- **模糊匹配**：按关键词在标题中搜索

**问题**：无法语义检索。比如笔记标题是"MCP 协议详解"，用户热点是"AI 工具互联标准"，关键词匹配会失败，但语义上是相关的。

### 1.2 方案选型

| 方案 | 向量数据库 | 嵌入模型 | 优点 | 缺点 |
|------|-----------|---------|------|------|
| A | Chroma | OpenAI text-embedding-3-small | 效果最佳，实现简单 | 有 API 成本 |
| B | Chroma | BGE-small-zh（本地） | 免费，离线可用 | 需要下载模型（~100MB） |
| C | 无（BM25） | 无 | 最简单，零成本 | 无语义能力，效果差 |

**推荐：方案 B（Chroma + BGE 本地嵌入）**

理由：
1. 项目已是单机应用，加本地模型不增加外部依赖
2. BGE-small-zh 对中文效果好，足够本项目使用
3. 零运行成本，不依赖外部 API 稳定性

### 1.3 架构设计

```
content_agent/
└── rag/
    ├── __init__.py
    ├── embedder.py       # BGE 嵌入模型封装
    ├── vector_store.py   # Chroma 向量数据库操作
    └── indexer.py        # 笔记索引（切分 + 入库）
```

**数据流**

```
Vault 笔记 → 切分 chunk → BGE 生成向量 → Chroma 存储
                                    ↓
热点/选题 → 关键词向量化 → 语义检索 → 返回 top-k 相关笔记
                                    ↓
                            作为上下文传给 LLM 生成
```

### 1.4 切分策略

**方案**：按 Markdown 标题层级切分

```python
# 示例：一篇笔记切分为多个 chunk
chunk_1: "# MCP 协议介绍\n\nMCP 是 Model Context Protocol..."
chunk_2: "## 核心概念\n\nMCP 定义了三个核心概念..."
chunk_3: "## 与 Function Calling 的区别\n\nFunction Calling 是..."
```

**理由**：
- 保持语义完整性（一个标题下的内容是一个主题）
- 比固定长度切分更合理
- 比段落切分更粗粒度，减少 chunk 数量

**备选**：固定长度 500 token + 100 token 重叠（实现更简单）

### 1.5 接入点

| 模块 | 当前逻辑 | 接入 RAG 后 |
|------|---------|------------|
| TopicPicker | 扫描 Vault 文件名 | 热点向量化 → 检索相关笔记 → 按相关度排序推荐 |
| TopicExecutor | 读单篇笔记生成 | 检索 top-3 相关笔记 → 合并为上下文 → 生成 |
| TrendScheduler | 无笔记关联 | 热点评估时，检索是否有相关笔记可结合 |

### 1.6 实现步骤

1. **安装依赖**：`pip install chromadb sentence-transformers`
2. **实现 embedder**：封装 BGE 模型，提供 `embed(text) -> vector`
3. **实现 vector_store**：Chroma 的增删查接口
4. **实现 indexer**：遍历 Vault，切分 chunk，生成向量，入库
5. **修改 TopicPicker**：选题时先做向量检索，再生成建议
6. **修改 TopicExecutor**：生成时检索相关笔记作为上下文

### 1.7 成本估算

- **存储**：100 篇笔记 × 10 chunk × 384 维 × 4 字节 ≈ 1.5MB
- **内存**：BGE-small 模型约 100MB
- **时间**：索引 100 篇笔记约 10 秒（一次性）
- **查询**：单次检索 < 100ms

---

## 二、Eval 体系方案

### 2.1 当前痛点

- 无自动化评估，靠人工看效果
- 改 prompt 后不知道生成质量是升是降
- 无法量化不同模型的效果差异

### 2.2 评估维度设计

| 维度 | 指标 | 评估方式 | 触发时机 |
|------|------|---------|---------|
| 内容质量 | 相关性、可读性、原创性 | LLM 打分 1-10 | 每次生成后 |
| 热点匹配 | 内容与热点的相关度 | LLM 判断 + 关键词匹配 | 热点驱动生成后 |
| 平台适配 | 是否符合平台风格 | LLM 打分 + 规则检查 | 每次生成后 |
| 一致性 | 同一任务多次生成的稳定性 | 相似度计算 | 回归测试时 |
| 成本效率 | token 使用量、耗时 | 直接统计 | 每次生成后 |

### 2.3 方案选型

| 方案 | 方式 | 优点 | 缺点 |
|------|------|------|------|
| A | LLM 打分 | 灵活，可评估语义质量 | 增加 token 成本 |
| B | 规则评分 | 零成本，可解释 | 无法评估语义 |
| C | 人工标注 + 离线训练 | 最准确 | 太重，不适合 |

**推荐：方案 A（LLM 打分）为主 + 方案 B（规则检查）为辅**

理由：
1. 已有 LLM 调用基础设施，增加一个打分调用成本低
2. 规则检查作为快速过滤（如字数、敏感词）
3. 人工标注可作为高价值样本，后续优化用

### 2.4 架构设计

```
automation/
└── eval/
    ├── __init__.py
    ├── evaluator.py      # 主评估器
    ├── metrics.py        # 指标定义
    ├── llm_judge.py      # LLM 打分实现
    └── regression.py     # 回归测试
```

**数据库表**

```sql
CREATE TABLE IF NOT EXISTS eval_results (
    id TEXT PRIMARY KEY,
    task_id TEXT,              -- 关联生成任务
    platform TEXT,             -- 平台
    content_hash TEXT,         -- 内容哈希（用于一致性检查）
    
    -- LLM 打分
    relevance_score INTEGER,   -- 相关性 1-10
    readability_score INTEGER, -- 可读性 1-10
    originality_score INTEGER, -- 原创性 1-10
    platform_fit_score INTEGER,-- 平台适配 1-10
    
    -- 规则检查
    word_count INTEGER,        -- 字数
    has_sensitive_words BOOLEAN,
    has_link BOOLEAN,          -- 是否包含链接
    
    -- 成本
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER,        -- 耗时
    
    -- 元数据
    model TEXT,                -- 使用的模型
    eval_model TEXT,           -- 评估用的模型
    created_at TEXT
);
```

### 2.5 LLM Judge Prompt 设计

**内容质量评估**

```
你是一位资深内容编辑。请对以下文案进行评分（1-10分）。

文案：
{content}

评分维度：
1. 相关性：内容与主题的相关程度
2. 可读性：语言是否流畅，结构是否清晰
3. 原创性：是否有独特见解，而非泛泛而谈
4. 实用性：读者能否从中获得实际价值

请输出 JSON：
{
  "relevance": 8,
  "readability": 7,
  "originality": 6,
  "practicality": 9,
  "overall": 7.5,
  "strengths": ["优点1", "优点2"],
  "weaknesses": ["不足1", "不足2"]
}
```

### 2.6 回归测试设计

**固定测试集**：10 个典型热点/笔记组合

```python
TEST_CASES = [
    {
        "name": "MCP 协议热点",
        "trending_hint": "MCP 协议成为 AI 工具互联标准",
        "note_file": "mcp_protocol.md",
        "expected_keywords": ["MCP", "Function Calling", "工具调用"]
    },
    # ... 更多用例
]
```

**回归流程**

```
1. 加载固定测试集
2. 对每个用例生成内容
3. LLM Judge 打分
4. 与基线分数对比
5. 生成回归报告（哪些指标上升/下降）
```

### 2.7 接入点

| 模块 | 接入方式 |
|------|---------|
| Orchestrator | 生成完成后，调用 Evaluator 打分，结果存入 DB |
| TopicExecutor | 热点驱动生成后，额外评估热点匹配度 |
| main.py | 新增 `--eval-regression` 参数，跑回归测试 |

### 2.8 成本估算

- **单次评估**：约 500 token（prompt + completion）
- **回归测试**：10 用例 × 3 平台 × 500 token = 15K token
- **频率**：开发时每次改 prompt 跑一次，生产环境抽样评估

---

## 三、推荐实施顺序

### Phase 1：RAG（1-2 天）

1. 安装 chromadb + sentence-transformers
2. 实现 embedder + vector_store
3. 实现 indexer（索引现有笔记）
4. 修改 TopicExecutor：生成时检索相关笔记
5. 验证：同一热点，有 RAG 和无 RAG 的生成质量对比

### Phase 2：Eval 基础（1 天）

1. 实现 llm_judge（单指标：overall_score）
2. 修改 Orchestrator：生成后自动打分
3. 实现 `--eval-regression` 跑固定测试集
4. 验证：改 prompt 后跑回归，看分数变化

### Phase 3：Eval 完善（1-2 天）

1. 增加多维度打分（相关性、可读性、原创性）
2. 增加规则检查（字数、敏感词）
3. 增加成本统计（token、耗时）
4. 实现 eval 报告生成（对比基线）

---

## 四、与招聘要求的对应

| 招聘要求 | RAG 对应 | Eval 对应 |
|---------|---------|----------|
| RAG / Knowledge pipeline | Chroma + BGE 向量检索 | - |
| 向量数据库（Milvus/Chroma） | Chroma | - |
| Agent Eval / 自动化测试 | - | LLM Judge + 回归测试 |
| 优化 latency、cost、token | - | 成本统计 + 模型降级策略 |
| 多 Agent 协作 | 检索 Agent + 生成 Agent | 评估 Agent |

---

## 五、风险与对策

| 风险 | 对策 |
|------|------|
| BGE 模型下载慢 | 首次运行时自动下载，后续缓存 |
| Chroma 占用内存 | 100MB 模型 + 1.5MB 数据，可接受 |
| Eval 增加 token 成本 | 开发时全量，生产时抽样（10%） |
| LLM Judge 主观性强 | 多模型投票（DeepSeek + Kimi 各评一次取平均） |

---

*文档生成时间：2026-05-24*
