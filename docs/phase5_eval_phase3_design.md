# Eval Phase 3 设计文档

> 回归测试 + 对比报告

---

## 1. 目标

- 固定测试集：10 个典型用例
- 改 prompt 前跑一遍，生成对比报告
- 追踪质量趋势

## 2. 回归测试集

```python
REGRESSION_CASES = [
    {
        "name": "MCP 协议热点",
        "note_file": "20260515_mcp_search_enhancement.md",
        "topic": "MCP 协议成为 AI 工具互联标准",
        "platforms": ["gongzhonghao", "xiaohongshu"],
        "trending_hint": "MCP 协议",
    },
    {
        "name": "CLI 工具改造",
        "note_file": "CLI工具化改造笔记.md",
        "topic": "从脚本到 CLI 工具",
        "platforms": ["gongzhonghao"],
        "trending_hint": "",
    },
    {
        "name": "三平台输出",
        "note_file": "20260518_three_platform_output.md",
        "topic": "多平台内容输出",
        "platforms": ["xiaohongshu", "douyin"],
        "trending_hint": "",
    },
    # ... 更多用例
]
```

## 3. 回归流程

```
1. 加载固定测试集
2. 对每个用例：
   a. 读取笔记
   b. 生成内容（每个平台）
   c. Eval 评估
   d. 保存结果
3. 生成对比报告（与基线对比）
4. 输出：哪些指标上升/下降
```

## 4. 对比报告格式

```
回归测试报告
==============
测试时间: 2026-05-24 10:00:00
基线版本: commit_abc123
当前版本: commit_def456

总体变化:
  综合评分: 7.5 -> 8.2 (+0.7)

各维度变化:
  相关性: 8.0 -> 8.5 (+0.5)
  可读性: 7.5 -> 8.0 (+0.5)
  原创性: 7.0 -> 7.5 (+0.5)
  实用性: 8.0 -> 8.5 (+0.5)

各用例详情:
  [通过] MCP 协议热点: 7.8 -> 8.3 (+0.5)
  [通过] CLI 工具改造: 7.2 -> 8.0 (+0.8)
  [下降] 三平台输出: 7.5 -> 7.0 (-0.5) ⚠️

结论: 整体质量提升，但"三平台输出"用例下降，需检查
```

## 5. CLI 命令

```bash
# 跑回归测试
python main.py --eval-regression

# 指定基线对比
python main.py --eval-regression --baseline commit_abc123

# 只看报告（不重新跑）
python main.py --eval-report
```

## 6. 数据存储

新增 `eval_baselines` 表：

```sql
CREATE TABLE eval_baselines (
    id TEXT PRIMARY KEY,
    commit_hash TEXT,
    case_name TEXT,
    platform TEXT,
    overall_score REAL,
    scores TEXT,  -- JSON
    created_at TEXT
);
```
