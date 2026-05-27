# 风格画像应用到 WriterAgent

> 让 FeedbackAgent 分析结果实际影响内容生成
> 时间：2026-05-25

---

## 1. 目标

- WriterAgent 生成内容时，读取风格画像
- 根据画像调整 system prompt
- 优先使用高表现模式，避免低表现模式

## 2. 实现方案

### 2.1 读取风格画像

```python
from automation.feedback_agent import FeedbackAgent

profile = FeedbackAgent().get_profile("gongzhonghao")
if profile:
    tone = profile.preferred_tone
    patterns = profile.high_performing_patterns
```

### 2.2 修改 WriterAgent system prompt

在原有 prompt 基础上，追加风格画像要求：

```
【风格画像参考】
- 语气特征：{preferred_tone}
- 高表现模式：{patterns}
- 平均互动分：{avg_score}

请优先采用上述高表现模式，生成符合平台偏好的内容。
```

### 2.3 集成位置

在 `WriterAgent._build_prompt()` 中，追加风格画像信息。

## 3. 降级策略

| 情况 | 处理 |
|------|------|
| 无画像 | 使用默认 prompt |
| 画像过期（>30天） | 提示用户更新 |
| 样本不足 | 使用默认 prompt |

## 4. 验证方式

1. 生成内容时检查 prompt 是否包含画像信息
2. 对比有/无画像的生成差异
