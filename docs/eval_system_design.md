# Eval 体系设计文档

> 自动化评估生成内容质量，支持回归测试
> 时间：2026-05-24

---

## 1. 目标

- 每次生成后自动打分，量化内容质量
- 改 prompt 前跑回归测试，有据可依
- 长期积累数据，追踪质量趋势

## 2. 评估维度

| 维度 | 指标 | 评估方式 | 触发时机 |
|------|------|---------|---------|
| 内容质量 | 相关性、可读性、原创性、实用性 | LLM 打分 1-10 | 每次生成后 |
| 热点匹配 | 内容与热点的相关度 | LLM 判断 + 关键词匹配 | 热点驱动生成后 |
| 平台适配 | 是否符合平台风格 | LLM 打分 + 规则检查 | 每次生成后 |
| 一致性 | 同一任务多次生成的稳定性 | 相似度计算 | 回归测试时 |
| 成本效率 | token 使用量、耗时 | 直接统计 | 每次生成后 |

## 3. 架构

```
automation/eval/
  ├── __init__.py
  ├── evaluator.py      # 主评估器
  ├── llm_judge.py      # LLM 打分实现
  ├── metrics.py        # 指标定义
  └── regression.py     # 回归测试
```

## 4. 数据库表

```sql
CREATE TABLE IF NOT EXISTS eval_results (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    platform TEXT,
    content_hash TEXT,
    
    -- LLM 打分 (1-10)
    relevance_score INTEGER,
    readability_score INTEGER,
    originality_score INTEGER,
    practicality_score INTEGER,
    overall_score REAL,
    
    -- 规则检查
    word_count INTEGER,
    has_sensitive_words BOOLEAN,
    has_link BOOLEAN,
    
    -- 成本
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER,
    
    -- 元数据
    model TEXT,
    eval_model TEXT,
    created_at TEXT
);
```

## 5. LLM Judge Prompt

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

## 6. 回归测试

固定测试集：10 个典型热点/笔记组合

流程：
1. 加载固定测试集
2. 对每个用例生成内容
3. LLM Judge 打分
4. 与基线分数对比
5. 生成回归报告

## 7. 接入点

| 模块 | 接入方式 |
|------|---------|
| Orchestrator | 生成完成后调用 Evaluator 打分 |
| TopicExecutor | 热点驱动生成后评估热点匹配度 |
| main.py | 新增 `--eval-regression` 参数 |

## 8. 成本

- 单次评估：~500 token
- 回归测试：10 用例 × 3 平台 × 500 = 15K token
- 生产环境可抽样（10%）

## 9. 实施计划

| Phase | 内容 | 时间 |
|-------|------|------|
| 1 | LLM Judge 单指标 + 自动打分 | 1 天 |
| 2 | 多维度打分 + 规则检查 + 成本统计 | 1 天 |
| 3 | 回归测试 + 对比报告 | 1 天 |

---

*文档生成时间：2026-05-24*
