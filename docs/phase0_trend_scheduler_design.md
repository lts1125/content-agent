# P0 Trend Scheduler 设计文档

## 目标

让 content-agent 能自动感知外部热点事件，评估是否值得跟进，自动选题并生成内容入队。

## 非目标

- 不碰发布环节（已有 `TaskScheduler.run_publish()`）
- 不做复杂的多源聚合（先支持单一热榜源）
- 不替代现有 vault 监听（并行运行）

---

## 现状分析

### 现有架构

```
触发层
  ├── CLI: python main.py --watch (VaultWatcher 文件监听)
  ├── CLI: python main.py --daemon (APScheduler 定时扫描+发布)
  └── Web UI: Gradio 手动触发

控制层: AgentController
  └── 读取笔记 → Orchestrator.run() → PublishQueue + StyleProfile

核心层: Orchestrator (纯 Python 调度)
  └── ResearchAgent → WriterAgent → EditorAgent (最多3轮)

输出层
  ├── PublishQueue (SQLite: 待发布内容)
  ├── StyleProfile (SQLite: 风格样本)
  └── TopicPicker (SQLite: 选题建议)
```

### 关键对接点

| 对接点 | 现有代码 | 怎么用 |
|--------|---------|--------|
| 定时扫描 | `automation/scheduler.py:TaskScheduler.run_scan()` | 已有 cron 触发，但只扫 vault inbox |
| 文件监听 | `automation/vault_watcher.py:VaultWatcher` | 基于 watchdog，只监听本地文件 |
| 任务执行 | `automation/agent_controller.py:AgentController.on_new_note()` | 统一的笔记处理入口 |
| 发布队列 | `automation/publish_queue.py:PublishQueue` | 生成后自动入队，支持状态流转 |
| 选题建议 | `automation/topic_picker.py:TopicPicker` | 已有热点搜索 + LLM 选题，但无自动触发 |
| 配置中心 | `automation/config.py:SchedulerConfig` | 环境变量 + YAML，可扩展 |

### 现状缺口

1. **无外部事件触发** — 只能文件监听和定时 cron，不能响应"微博热榜更新了"
2. **热点监控是手动的** — `TopicPicker.pick_topics()` 需要人工调用，不会自动跑
3. **触发后无决策逻辑** — 有热点 → 直接生成？还是先评估匹配度？缺少 agent 判断
4. **scheduler 和 topic_picker 没打通** — 定时任务只扫 vault，不扫热点

---

## 新增模块

```
content_agent/
└── trend_watcher/          # 新增：热点监控
    ├── __init__.py
    ├── base.py             # TrendSource 抽象基类
    ├── weibo_hot.py        # 微博热搜源
    └── zhihu_hot.py        # 知乎热榜源（预留）

automation/
└── trend_scheduler.py      # 新增：热点调度器
    # 定时拉热榜 → 匹配关键词 → 评估 → 触发 TopicPicker → 生成 → 入队
```

---

## 数据流

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐
│  APScheduler │────→│ TrendSource  │────→│ TrendFilter │────→│ TopicPicker │
│  (每30分钟)  │     │ (拉取热榜)    │     │ (匹配+评估)  │     │ (生成选题)   │
└─────────────┘     └──────────────┘     └─────────────┘     └──────┬──────┘
                                                                    │
                              ┌─────────────────────────────────────┘
                              ▼
                       ┌─────────────┐     ┌─────────────┐
                       │Orchestrator │────→│PublishQueue │
                       │ (生成内容)   │     │ (待审核)     │
                       └─────────────┘     └─────────────┘
```

---

## TrendFilter 评估逻辑

不是有热点就生成，要过两道过滤：

### 1. 关键词匹配

热榜标题是否命中用户配置的领域词（如 "AI Agent", "LLM", "大模型"）

### 2. LLM 评估（可选，V2 再做）

匹配的热点，让模型判断"这个热点适合我的账号调性吗？能产出技术视角的内容吗？"

评估 prompt：

```
你是一位技术内容创作者。判断以下热点是否值得跟进：

热点: {title}
你的领域: {user_keywords}
账号调性: {style_profile}

请输出：
- decision: follow / skip
- reason: 一句话说明
- angle: 如果跟进，建议从技术什么角度切入
```

---

## 配置扩展

`automation/config.py:SchedulerConfig` 新增：

```python
trend_check_cron: str = "*/30 * * * *"   # 每30分钟检查热点
trend_keywords: List[str] = field(default_factory=list)  # 监控关键词
trend_sources: List[str] = field(default_factory=lambda: ["weibo"])  # 热榜源
trend_auto_generate: bool = False  # 是否自动生成（false=只保存选题建议）
```

---

## 与现有代码对接

| 现有模块 | 对接方式 |
|---------|---------|
| `TaskScheduler` | `TrendScheduler` 作为独立 job 注册到同一 APScheduler 实例 |
| `TopicPicker` | 直接复用，`pick_topics()` 增加 `trending_hint` 参数传入热点 |
| `AgentController` | 选题被接受后，调用 `on_new_note()` 或新建 `on_topic_suggestion()` |
| `PublishQueue` | 生成后直接入队，走现有审核流程 |

---

## 最小可用 Demo 范围

1. 只实现微博热搜源（爬 `https://s.weibo.com/top/summary`）
2. 只匹配关键词，先不做 LLM 评估（简化）
3. 匹配到后调用 `TopicPicker.pick_topics()` 生成选题
4. 打印日志，不入队（让用户先观察效果）

---

## 后续迭代

- V1: 接入 LLM 评估，过滤低质量匹配
- V2: 支持多源（知乎、B站、Twitter）
- V3: 自动接受选题并触发生成流水线
- V4: 热点效果追踪，形成"热点→生成→发布→数据→优化"闭环
