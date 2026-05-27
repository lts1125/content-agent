# Feedback Loop 与风格画像设计

> 将平台数据导入、FeedbackAgent 分析、决策逻辑和 WriterAgent 风格画像应用合并为一套闭环。

整合来源（以下文件已合并到本文档）：

- ~~`phase5_feedback_agent_design.md`~~
- ~~`phase5_feedback_decision_logic.md`~~
- ~~`phase5_style_profile_integration.md`~~

## 目标

- 支持手动导入公众号、小红书等平台数据。
- 从真实表现数据中提取高表现内容特征。
- 更新平台风格画像，影响后续 WriterAgent 生成。
- 避免每次都靠主观感觉调 prompt。

## 数据输入

### 微信公众号 CSV

```csv
title,read_count,like_count,share_count,comment_count,pub_time
"文章标题1",1000,50,30,10,"2026-05-20 09:00"
"文章标题2",2000,100,60,20,"2026-05-21 12:00"
```

### 小红书 CSV

```csv
title,like_count,collect_count,comment_count,share_count,pub_time
"笔记标题1",500,100,50,20,"2026-05-20 11:00"
"笔记标题2",1000,200,100,40,"2026-05-21 14:00"
```

## 分析维度

| 维度 | 说明 |
| --- | --- |
| 高表现内容 | 阅读、点赞、收藏、分享前 20% |
| 最佳发布时间 | 高表现内容的发布时间分布 |
| 标题特征 | 标题关键词、长度、结构 |
| 内容长度 | 高表现内容的字数分布 |
| 互动率 | 点赞/阅读、评论/阅读、收藏/阅读 |
| 内容模式 | 教程、复盘、清单、观点、案例等 |

## 风格画像

```python
@dataclass
class StyleProfile:
    platform: str
    preferred_tone: str
    high_performing_patterns: list[str]
    avg_length: int
    best_time_slots: list[int]
    top_keywords: list[str]
    avg_score: float
    updated_at: str
```

示例：

```text
【gongzhonghao 风格画像】
- 语气特征：专业严谨但不失亲切
- 高表现模式：详细代码示例、原理+实践结合、结构化章节
- 平均互动分：150
```

## 决策逻辑

### 自动触发条件

| 条件 | 阈值 | 说明 |
| --- | --- | --- |
| 样本数量 | >= 5 条 | 足够做基础统计 |
| 新数据占比 | >= 30% | 上次分析后新增数据足够多 |
| 时间间隔 | >= 7 天 | 定期刷新 |
| 表现差异 | > 20% | 新数据和旧画像明显不同 |

### 手动触发

```bash
python main.py --analyze-feedback --platform gongzhonghao
```

### 决策流程

```text
导入平台数据
  -> 样本数量是否足够
  -> 计算新数据综合分
  -> 与现有画像对比
  -> 差异是否显著
  -> 触发 LLM 分析
  -> 更新风格画像
  -> 输出优化建议
```

如果样本不足或变化不明显，则跳过更新，继续积累数据。

## WriterAgent 集成

读取风格画像：

```python
from automation.feedback_agent import FeedbackAgent

profile = FeedbackAgent().get_profile("gongzhonghao")
if profile:
    tone = profile.preferred_tone
    patterns = profile.high_performing_patterns
```

追加到 WriterAgent prompt：

```text
【风格画像参考】
根据历史数据分析，该平台高表现内容的特征如下：
- 语气特征：{preferred_tone}
- 高表现模式：{patterns}
- 平均互动分：{avg_score}

请优先采用上述高表现模式，生成符合平台偏好的内容。
```

集成位置：

```text
WriterAgent._build_prompt()
```

## 降级策略

| 情况 | 处理 |
| --- | --- |
| 无画像 | 使用默认 prompt |
| 样本不足 | 使用默认 prompt |
| 画像过期 | 提示用户导入新数据 |
| 数据异常 | 保留旧画像，不自动覆盖 |
| 平台无数据 | 只使用平台默认规则 |

## CLI 命令

```bash
# 导入数据
python main.py --import-metrics data/wechat_202605.csv --platform gongzhonghao

# 查看风格画像
python main.py --show-profile --platform gongzhonghao

# 分析反馈
python main.py --analyze-feedback --platform gongzhonghao
```

## 输出示例

```text
[FeedbackAgent] 检测到内容表现变化：
- 平均互动率从 5% 上升到 8%
- 高表现内容特征：实用教程类、带代码示例
- 建议：增加技术深度，减少纯概念内容
```

## 验证方式

1. 导入一组平台数据。
2. 运行反馈分析。
3. 检查 `style_profiles` 是否更新。
4. 生成内容时检查 prompt 是否包含画像信息。
5. 对比有画像和无画像时的生成差异。

## 注意事项

- 风格画像只能作为偏好，不应覆盖用户明确主题。
- 高表现模式要和当前内容主题兼容，不能机械套用。
- 数据量不足时不要过度拟合。
- 建议保留画像更新历史，方便回滚。
