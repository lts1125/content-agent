# 质量检查功能实现笔记

## 背景/需求

Roadmap P0 核心功能：LLM 生成的文案质量不稳定，有时会流于表面、缺少实质内容、不符合平台风格。需要一套自动化质量检查机制，确保输出可用。

## 设计思路

采用**混合模式**：先用规则快速过滤，再用 LLM 精细评分，分数低于阈值时带建议重试。

1. **规则校验** — 零 API 成本，快速检查字数、emoji、标签、代码块等硬性指标
2. **LLM 评分** — 用另一个 Agent 对三平台文案分别打分（0-100）
3. **重试机制** — 综合分数 < 70 时，将 LLM 的改进建议注入重试 prompt，最多重试3次

## 核心实现

### 1. 规则校验器（RuleChecker）

```python
class RuleChecker:
    @staticmethod
    def check_xiaohongshu(text: str) -> dict:
        checks = {
            "字数达标(200-800)": 200 <= len(text) <= 800,
            "含有emoji": bool(re.search(r'[\U0001F600-\U0001F9FF\u2600-\u26FF]', text)),
            "含有标签(#)": bool(re.search(r'#\S+', text)),
            "含有互动问句": bool(re.search(r'[?？]', text)),
            "分段清晰(≥3段)": text.count("\n\n") >= 2,
            "有数字或步骤": bool(re.search(r'\d[...]', text)),
            "标题吸睛": bool(re.search(r'\d|[...]', title)),
        }
        score = sum(checks.values()) / len(checks) * 100
        return {"score": round(score, 1), "checks": checks}
```

三个平台分别有独立的规则：
- 小红书：字数、emoji、标签、互动、分段、步骤、标题
- 公众号：字数、标题层级、代码块、总结、行动号召、段落、实例
- 抖音：字数、钩子、画面提示、短句、口语化、行动号召、节奏

### 2. LLM 评分（ScoreResult）

```python
class ScoreResult(BaseModel):
    xiaohongshu: int = Field(..., ge=0, le=100)
    gongzhonghao: int = Field(..., ge=0, le=100)
    douyin: int = Field(..., ge=0, le=100)
    overall: int = Field(..., ge=0, le=100)
    weakest: str = Field(..., description="最弱的平台名称")
    suggestion: str = Field(..., description="具体改进建议，用于重试 prompt")
```

评分 Agent 的 system prompt 要求根据各平台的样式要求打分，并给出最弱平台的改进建议。

### 3. 综合检查流程（QualityChecker.check）

```
生成文案
  → 规则校验（快速）
    → 规则通过 → LLM 评分
      → overall_score >= 70 → ✓ 返回
      → overall_score < 70 → 带 suggestion 重试（attempt++，最多3次）
    → 规则未通过 → 直接返回（标记规则失败）
```

### 4. 与 Agent 核心集成（agent_core.py）

```python
from content_agent.quality_checker import QualityChecker

checker = QualityChecker(model_config)
result = checker.check(content, original_note)

if not result.passed:
    # 重试逻辑...
```

## 踩坑记录

1. **规则和 LLM 的分数偏差可能很大** — 规则通过了但 LLM 可能打很低分，反之亦然。最终采用“规则必须通过 + LLM 评分作为参考”的策略。

2. **重试时的 token 消耗** — 每次重试都是一次完整的 API 调用，成本较高。设置最多3次重试上限，避免无限循环。

3. **敏感词检查与质量检查的边界** — 敏感词检查是单独模块（sensitive_checker.py），在生成前运行；质量检查是生成后运行。两者不冲突，但需要明确分工。

4. **评分 Agent 的模型选择** — 评分不需要太大的模型，用同一个模型即可。但需要确保模型支持结构化输出（output_type=ScoreResult）。

## 使用方法

内部自动调用，无需用户手动操作。生成文案时自动检查，如果需要重试会在终端/Web UI 状态栏显示。

## 下一步

- P0-3 性能测试优化（规则和 LLM 评分的时间开销）
- 考虑添加缓存机制（相同笔记不重复检查）
