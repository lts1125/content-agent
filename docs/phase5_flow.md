# 从读笔记到生成三平台内容的完整流程

## 主流程（笔记驱动）

```
[用户] 提供笔记文件/目录
    |
    v
[main.py] 解析参数，确定输入
    |
    v
[Orchestrator.run()] 制定执行计划
    |
    +--> [ResearchAgent] 搜索增强（可选）
    |       - 提取关键词
    |       - DuckDuckGo/Tavily 搜索
    |       - 补充背景资料
    |
    +--> [WriterAgent] 生成内容
    |       - 读取笔记 + 研究资料
    |       - 调用 LLM 生成三平台文案
    |       - 返回 WriterOutput
    |           - xiaohongshu: 小红书文案
    |           - gongzhonghao: 公众号文案
    |           - douyin: 抖音文案
    |           - recommended_tags: 推荐标签
    |
    +--> [EditorAgent] 质量检查
    |       - 规则检查（字数、敏感词）
    |       - LLM 评分（1-10分）
    |       - 不通过则返回修改建议
    |       - 最多 3 轮循环
    |
    v
[Eval] 自动化评估（新增）
    - LLM Judge 多维度打分
    - 规则检查（字数、emoji、标签）
    - 保存到 eval_results 表
    |
    v
[保存文件] 输出到 output/日期/笔记名/
    - {timestamp}_xiaohongshu.md
    - {timestamp}_gongzhonghao.md
    - {timestamp}_douyin.md
    - xiaohongshu_cards.html（配图）
    |
    v
[PublishQueue] 入队（可选）
    - 状态: pending
    - 等待人工审核
    |
    v
[审核门] 人工确认
    - approve: 状态变为 approved
    - reject: 状态变为 rejected
    |
    v
[PublishExecutor] 发布
    - 微信公众号草稿箱（kuaifa）
    - 小红书/抖音需手动复制
```

## 热点驱动流程（P0）

```
[TrendScheduler] 定时检查热点
    - 拉取微博/掘金/知乎热榜
    - 关键词匹配
    - LLM 评估热点价值
    |
    v
[TopicPicker] 生成选题建议
    - 结合热点 + Vault 笔记
    - 保存到 topic_suggestions
    |
    v
[人工/自动] 接受选题
    - --trend-auto: 自动接受
    - 默认: pending 等待确认
    |
    v
[TopicExecutor] 自动生成内容
    - 读取对应笔记
    - RAG 检索相关笔记（可选）
    - 调用 Orchestrator 生成
    - 入队 PublishQueue
```

## 数据流

```
Vault 笔记 (.md)
    |
    v
Orchestrator
    +--> ResearchAgent --> 搜索资料
    +--> WriterAgent ----> 三平台文案
    +--> EditorAgent ----> 质量评分
    |
    v
Eval 评估 --> eval_results 表
    |
    v
文件输出 + PublishQueue 入队
```

## 关键模块

| 模块 | 文件 | 职责 |
|------|------|------|
| Orchestrator | agents/orchestrator.py | 调度中心 |
| ResearchAgent | agents/research_agent.py | 搜索增强 |
| WriterAgent | agents/writer_agent.py | 内容生成 |
| EditorAgent | agents/editor_agent.py | 质量检查 |
| Eval | automation/eval/ | 自动化评估 |
| PublishQueue | automation/executor.py | 发布队列 |
| TrendScheduler | automation/trend_scheduler.py | 热点监控 |
| TopicPicker | automation/topic_picker.py | 自动选题 |
| TopicExecutor | automation/topic_executor.py | 选题执行 |
| RAG | content_agent/rag/ | 向量检索 |
