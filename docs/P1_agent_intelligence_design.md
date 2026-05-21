# P1 Agent 智能优化设计文档

> 目标：数据回流分析 + 自动选题 + A/B 测试框架
> 分支：`agent-autonomy`
> 依赖：P0 已完成（Vault 监听 / Publish Queue / Style Samples）

---

## 1. 新增模块结构

```
automation/
  feedback_agent.py      # 数据回流分析 + 风格画像更新
  topic_picker.py        # 自动选题（Vault 挖掘 + 热点结合）
  ab_test_framework.py   # A/B 测试变体生成 + 结果记录

agents/store.py          # 扩展：content_metrics / style_profiles / topic_suggestions / ab_test_variants 表
main.py                  # 扩展：--import-metrics / --analyze-feedback / --pick-topics / --generate-ab
```

---

## 2. FeedbackAgent (automation/feedback_agent.py)

### 职责
- 接收用户手动导入的平台数据
- 关联到已发布的队列项
- 调用 LLM 分析高表现 vs 低表现文案的差异特征
- 更新 `style_profiles` 表（从 P0 的原始样本升级为分析后的画像）

### 数据模型

```python
@dataclass
class ContentMetrics:
    id: str
    queue_item_id: str          # 关联 publish_queue.id
    platform: str
    reads: int = 0
    likes: int = 0
    shares: int = 0
    comments: int = 0
    collects: int = 0
    import_date: str
    publish_date: str

@dataclass
class StyleProfileRecord:
    id: str
    platform: str
    preferred_tone: str
    high_performing_patterns: List[str]   # 高表现模式列表
    avg_score: int                          # 平均分（reads + likes*2 + shares*3 + comments*2 + collects*2）
    sample_count: int
    created_at: str
    updated_at: str
```

### 数据库表

```sql
-- 内容数据指标（用户手动导入）
CREATE TABLE IF NOT EXISTS content_metrics (
    id TEXT PRIMARY KEY,
    queue_item_id TEXT,
    platform TEXT NOT NULL,
    reads INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    collects INTEGER DEFAULT 0,
    import_date TEXT,
    publish_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_metrics_queue ON content_metrics(queue_item_id);
CREATE INDEX IF NOT EXISTS idx_metrics_platform ON content_metrics(platform);

-- 风格画像（LLM 分析后的结果，替代 P0 的原始样本）
CREATE TABLE IF NOT EXISTS style_profiles (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    preferred_tone TEXT,
    high_performing_patterns TEXT,  -- JSON list
    avg_score INTEGER,
    sample_count INTEGER,
    created_at TEXT,
    updated_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_style_platform ON style_profiles(platform);
```

### 核心流程

```
用户导入 CSV/JSON → 解析为 ContentMetrics → 存入 DB
↓
调用 FeedbackAgent.analyze(platform)
  1. 拉取该平台所有已发布项的 metrics + content
  2. 按综合分排序，取前 30% 高表现 + 后 30% 低表现
  3. 构建 prompt 让 LLM 分析差异
  4. 提取 preferred_tone + high_performing_patterns
  5. 更新/insert style_profiles 表
```

### 综合分计算
```python
def _composite_score(m: ContentMetrics) -> int:
    return m.reads + m.likes * 2 + m.shares * 3 + m.comments * 2 + m.collects * 2
```

### LLM Prompt 示例
```
你是一位内容分析专家。请分析以下高表现和低表现文案的差异，输出风格画像。

【高表现文案】（综合分 > X）
...

【低表现文案】（综合分 < Y）
...

请输出：
1. preferred_tone: 该平台高表现文案的共同语气特征
2. high_performing_patterns: 列表，每项一个高表现模式
```

### 接口
```python
class FeedbackAgent:
    def __init__(self, model=None)
    def import_metrics(self, file_path: Path) -> dict   # 导入 CSV/JSON，返回统计
    def analyze(self, platform: str | None = None) -> StyleProfileRecord   # 分析并更新画像
    def get_profile(self, platform: str) -> StyleProfileRecord | None
```

### 导入文件格式

**CSV** (支持多平台后台导出的通用格式):
```csv
queue_item_id,platform,reads,likes,shares,comments,collects,publish_date
queue_abc123,xiaohongshu,1200,45,12,8,20,2026-05-15
```

**JSON**:
```json
[
  {"queue_item_id": "queue_abc123", "platform": "xiaohongshu", "reads": 1200, ...}
]
```

---

## 3. TopicPicker (automation/topic_picker.py)

### 职责
- 扫描 Vault 中的所有笔记，提取每篇笔记的主题/关键词
- 结合当前热点（通过 ResearchAgent 搜索）
- 生成选题建议：哪些笔记适合当前热点，还缺什么内容
- 保存到 `topic_suggestions` 表

### 数据模型

已在 `agents/schemas.py` 中定义 `TopicSuggestion`：
```python
class TopicSuggestion(BaseModel):
    title: str
    note_file: str
    trending_topic: str
    platforms: List[str]
    reason: str
    priority: int = 3        # 1-5
```

### 数据库表

```sql
CREATE TABLE IF NOT EXISTS topic_suggestions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    note_file TEXT,
    trending_topic TEXT,
    platforms TEXT,           -- JSON list
    reason TEXT,
    priority INTEGER DEFAULT 3,
    status TEXT DEFAULT 'pending',  -- pending | accepted | rejected | generated
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_topics_status ON topic_suggestions(status);
```

### 核心流程

```
用户调用 --pick-topics
  ↓
1. 扫描 Vault 下所有 .md 文件
   - 读取前 1000 字作为预览
   - 提取文件名 + 标题
  ↓
2. 调用 ResearchAgent 搜索当前热点（技术领域）
   - 关键词可配置：AGENT_TOPIC_KEYWORDS="AI Agent,LLM,大模型"
  ↓
3. LLM 分析
   - 输入：笔记列表 + 热点列表
   - 输出：TopicSuggestion 列表
   - 判断：这篇笔记是否适合某个热点？还缺什么？优先级如何？
  ↓
4. 保存到 topic_suggestions 表
```

### 接口
```python
class TopicPicker:
    def __init__(self, research_agent=None, model=None)
    def scan_vault(self, vault_path: str) -> List[dict]   # 返回笔记列表
    def pick_topics(self, vault_path: str, keywords: str | None = None, limit: int = 5) -> List[TopicSuggestion]
    def accept(self, suggestion_id: str) -> bool           # 接受建议，状态变为 accepted
    def reject(self, suggestion_id: str) -> bool
    def list_suggestions(self, status: str | None = None) -> List[TopicSuggestion]
```

### LLM Prompt 示例
```
你是一位内容策划专家。根据以下笔记和热点，生成选题建议。

【笔记列表】
1. MCP协议介绍.md - 介绍 MCP 协议的核心概念
2. Agent框架对比.md - 对比 LangChain / PydanticAI

【当前热点】
- OpenAI 发布 GPT-5
- MCP 协议成为行业标准

请输出 JSON 数组，每项包含：
- title: 文章标题
- note_file: 关联的笔记文件
- trending_topic: 关联热点
- platforms: [平台列表]
- reason: 为什么这个笔记适合这个热点
- priority: 1-5 整数
```

---

## 4. A/B Test 框架 (automation/ab_test_framework.py)

### 职责
- 为同一笔记/文案生成多个变体（标题、开头钩子、风格）
- 记录各变体的发布表现
- 分析结果，推荐最优版本

### 数据模型

```python
@dataclass
class ABTestVariant:
    id: str
    task_id: str
    platform: str
    variant_type: Literal["title", "hook", "style"]   # 变体类型
    variant_content: str                                # 变体内容
    status: Literal["pending", "published", "result_imported"]
    metrics_id: str | None                              # 关联 content_metrics
    created_at: str
```

### 数据库表

```sql
CREATE TABLE IF NOT EXISTS ab_test_variants (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    variant_type TEXT NOT NULL,
    variant_content TEXT,
    status TEXT DEFAULT 'pending',
    metrics_id TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ab_task ON ab_test_variants(task_id);
```

### 核心流程

```
用户调用 --generate-ab title,hook
  ↓
1. 取最近的一个 pending/approved 队列项
  ↓
2. 对每个指定类型生成 2-3 个变体
   - title: 为同一篇文案生成 3 个不同标题
   - hook: 为同一篇文案生成 3 个不同开头钩子
  ↓
3. 保存到 ab_test_variants 表
  ↓
4. 用户发布后导入 metrics，关联到 variant
  ↓
5. 分析结果：哪个 variant 综合分最高
```

### 变体生成示例

**Title 变体** (对同一篇公众号文章):
```
变体 A: "MCP 协议入门：让 AI 工具互联的标准化方案"
变体 B: "什么是 MCP？为什么这个协议能改变 AI 开发的游戏规则"
变体 C: "花了 3 天理解 MCP 协议，我的总结是..."
```

### 接口
```python
class ABTestFramework:
    def __init__(self, model=None)
    def generate_variants(self, queue_item_id: str, variant_types: List[str], count: int = 3) -> List[ABTestVariant]
    def list_variants(self, task_id: str) -> List[ABTestVariant]
    def record_result(self, variant_id: str, metrics_id: str) -> bool
    def analyze_results(self, task_id: str) -> dict   # 返回最优 variant 和统计
```

---

## 5. DB 扩展 (agents/store.py)

扩展 `init_db()` 增量 DDL：

```python
def init_content_metrics_table(): ...
def init_style_profiles_table(): ...
def init_topic_suggestions_table(): ...
def init_ab_test_variants_table(): ...
```

将 `_SCHEMA_VERSION` 从 2 升级到 3，在 `init_db()` 中调用新的 `init_*_table()` 函数。

---

## 6. CLI 扩展 (main.py)

新增参数：

```bash
# 导入平台数据
python main.py --import-metrics metrics.csv

# 分析反馈，更新风格画像
python main.py --analyze-feedback [--platform xiaohongshu]

# 查看风格画像
python main.py --show-profile [--platform xiaohongshu]

# 自动选题
python main.py --pick-topics [--vault /path/to/vault] [--keywords "AI,LLM"]

# 查看选题建议
python main.py --topics [--status pending]

# 接受/拒绝选题建议
python main.py --accept-topic <id>
python main.py --reject-topic <id>

# 生成 A/B 测试变体
python main.py --generate-ab title,hook [--count 3] [--queue-id queue_xxx]

# 查看 A/B 测试结果
python main.py --ab-results <task_id>
```

---

## 7. 与 P0 的衔接

| P0 组件 | P1 使用方式 |
|---------|-----------|
| `publish_queue` | FeedbackAgent 关联 metrics 到已发布项；ABTest 关联 variants 到队列项 |
| `style_samples` | FeedbackAgent 分析 samples 生成 style_profiles |
| `VaultWatcher` | TopicPicker 扫描 Vault 时复用相同逻辑 |
| `Orchestrator` | TopicPicker 生成文案时复用（accepted topic 变成 task 进入 Orchestrator） |

---

## 8. 执行时序图

### Feedback 回流
```
用户 → python main.py --import-metrics metrics.csv
              ↓
        FeedbackAgent.import_metrics()
              ↓
        存入 content_metrics 表
              ↓
用户 → python main.py --analyze-feedback
              ↓
        FeedbackAgent.analyze("xiaohongshu")
              ↓
        拉取该平台已发布项 + metrics
              ↓
        LLM 分析高/低表现差异
              ↓
        更新 style_profiles 表
```

### 自动选题
```
用户 → python main.py --pick-topics
              ↓
        TopicPicker.scan_vault()
        TopicPicker.pick_topics()
              ↓
        ResearchAgent 搜索热点
        LLM 分析笔记 + 热点
              ↓
        保存到 topic_suggestions
              ↓
用户 → python main.py --accept-topic <id>
              ↓
        调用 Orchestrator 生成文案
              ↓
        进入 Publish Queue
```

### A/B 测试
```
用户 → python main.py --generate-ab title,hook --queue-id queue_xxx
              ↓
        ABTestFramework.generate_variants()
              ↓
        对每个 type 生成 3 个变体
              ↓
        保存到 ab_test_variants
              ↓
用户发布后导入 metrics → 关联 variant
              ↓
用户 → python main.py --ab-results <task_id>
              ↓
        返回最优 variant
```

---

## 9. MVP Checklist

1. [ ] 实现 `FeedbackAgent`：导入 CSV + 分析 + 更新 style_profiles
2. [ ] 实现 `TopicPicker`：扫描 Vault + 生成建议 + 保存
3. [ ] 实现 `ABTestFramework`：生成变体 + 记录结果
4. [ ] 扩展 DB：4 张新表
5. [ ] 扩展 CLI：6 个新参数
6. [ ] 端到端测试：导入测试数据 → 分析 → 查看画像 → 选题 → A/B 变体

---

## 10. 与 P2 的衔接

- P1 的 `style_profiles` 在 P2 中被 WriterAgent 使用，影响生成策略
- P1 的 `topic_suggestions` 在 P2 中可以自动排期发布
- P1 的 `ab_test_variants` 在 P2 中实现自动分配发布
