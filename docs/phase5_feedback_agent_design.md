# FeedbackAgent 设计文档

> 手动导入平台数据，分析后更新风格画像
> 时间：2026-05-25

---

## 1. 目标

- 支持手动导入各平台数据（CSV/JSON）
- 分析数据，提取高表现内容特征
- 更新风格画像，指导后续生成

## 2. 数据格式

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

## 3. 分析维度

| 维度 | 说明 |
|------|------|
| 高表现内容 | 阅读量/点赞量前 20% |
| 最佳发布时间 | 高表现内容的发布时间分布 |
| 标题特征 | 高表现内容的标题关键词、长度 |
| 内容长度 | 高表现内容的字数分布 |
| 互动率 | 点赞/阅读、评论/阅读比率 |

## 4. 风格画像更新

```python
@dataclass
class StyleProfile:
    platform: str
    preferred_tone: str  # 语气偏好
    high_performing_patterns: List[str]  # 高分模式
    avg_length: int  # 平均长度
    best_time_slots: List[int]  # 最佳时段
    top_keywords: List[str]  # 高频关键词
```

## 5. CLI 命令

```bash
# 导入数据
python main.py --import-metrics data/wechat_202605.csv --platform gongzhonghao

# 查看风格画像
python main.py --show-profile --platform gongzhonghao

# 分析反馈
python main.py --analyze-feedback --platform gongzhonghao
```

## 6. 实现步骤

1. **数据导入** `automation/feedback_agent.py`
   - 解析 CSV/JSON
   - 存入 content_metrics 表

2. **数据分析**
   - 统计高表现内容特征
   - 计算最佳时段

3. **风格画像更新**
   - 更新 style_profiles 表
   - 生成优化建议
