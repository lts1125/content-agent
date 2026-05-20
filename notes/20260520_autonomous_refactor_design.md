# content-agent Autonomous 重构设计文档

## 1. 背景与现状

当前 content-agent 是一个**硬编码 LLM Pipeline**：

```
笔记输入 → 搜索增强(可选) → Agent生成 → 质量检查 → 输出
```

质量检查不合格时，通过外部循环重试（最多 3 次）。整个流程由 `main.py` / `web_ui.py` 编排，agent 本身不参与决策。

**现有问题：**
- 生成、检查、搜索之间没有智能协调，全靠 if/else 硬编码
- 没有模块边界，所有逻辑堆在 `agent_core.py` 和几个工具模块里
- 不能自主决定"要不要搜索"、"重写时换风格还是补细节"
- 没有记忆积累，每次生成从零开始

## 2. 目标架构

从 **Pipeline** 演进为 **Modular Multi-Agent with Lightweight ReAct**。

核心原则：**不追求全自主，追求"有判断力的助手"**。

```
┌─────────────────────────────────────────────────────────┐
│                   Orchestrator (调度器)                  │
│              负责任务分发、循环控制、状态聚合               │
└─────────────────────────────────────────────────────────┘
    │         │           │           │           │
    ▼         ▼           ▼           ▼           ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Research│ │ Writer │ │ Editor │ │Publish │ │Feedback│
│ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │
│(找热点)│ │(写文案) │ │(审质量) │ │(发平台) │ │(记反馈) │
└────────┘ └────────┘ └────────┘ └────────┘ └────────┘
```

## 3. 模块分层边界（关键约定）

| 目录 | 定位 | 内容 |
|------|------|------|
| `agents/` | **唯一对外暴露的业务层** | Orchestrator、ResearchAgent、WriterAgent、EditorAgent、PublisherAgent、FeedbackAgent、TopicPicker |
| `content_agent/` | **底层工具函数库** | 搜索、HTML 渲染、DOCX 导出、敏感词检测、日历、定时任务等。**不再持有 Agent 实例** |
| `ui/` | **前端界面模块** | 按 Tab 拆分的 Gradio 组件，每个 Tab 独立文件 |
| `data/` | **本地数据库** | SQLite 数据库 + 风格画像 JSON |

`main.py` 和 `web_ui.py` 最终只调用 `agents/` 和 `ui/`，不直接触碰 `content_agent/` 。

## 4. Agent 定义与接口

每个 Agent 是一个独立的 PydanticAI Agent 实例，有专属 System Prompt 和结构化输出。

### 4.1 Orchestrator（纯 Python 类，非 LLM）

**推回原设计：不用 PydanticAI Agent 包装**。当前流程分支极少，用 LLM 决策是过度设计，增加 1-2 秒延迟和 token 成本。

实现：一个普通 Python 类，用 if/else 做调度。`ExecutionPlan` 作为内部数据结构，不通过 LLM 生成。

```python
class Orchestrator:
    def run(self, task_input: TaskInput) -> TaskState:
        # 1. 制定计划（纯代码）
        plan = self._make_plan(task_input)
        # 2. 执行
        state = TaskState(task_id=gen_id(), status="planned")
        if plan.needs_search:
            state = self.research_agent.run(state)
        state = self.writer_agent.run(state)
        state = self._edit_loop(state)
        return state

    def _make_plan(self, inp: TaskInput) -> ExecutionPlan:
        # 纯规则：用户勾选了搜索 → needs_search=True
        # 纯规则：用户选的平台 → target_platforms
        return ExecutionPlan(
            needs_search=inp.enable_research,
            target_platforms=inp.platforms,
            steps=["research" if inp.enable_research else None, "write", "edit"],
        )
```

### 4.2 ResearchAgent（由 research.py 升级）

职责：
- 提取搜索关键词（已有 LLM 提取）
- 执行搜索（DuckDuckGo / Tavily）
- 摘要搜索结果，输出"资料包"

输出：
```python
class ResearchResult(BaseModel):
    keywords: List[str]
    sources: List[dict]       # title, href, summary
    key_insights: str         # 对写作有价值的要点摘要
    confidence: int           # 0-100，资料充足度
```

### 4.3 WriterAgent（由 agent_core.py 拆分）

职责：
- 接收原始笔记 + 研究资料（可选）+ 风格指令 + 风格画像
- 生成三平台文案
- 支持"增量修改"：接收 Editor 建议，**只改最弱平台**

**双模式 Prompt 策略：**
- **初稿模式**：传入完整 SYSTEM_PROMPT（现有的三平台写作指南）
- **修改模式**：传入精简的"编辑助手" prompt，只包含该平台的规范 + 修改指令，不重新传全文规范

输出：保持现有 `MultiPlatformContent` 结构，增加 `revision_notes` 字段记录本轮改了什么。

```python
class WriterOutput(BaseModel):
    xiaohongshu: str
    gongzhonghao: str
    douyin: str
    recommended_tags: str
    revision_notes: str       # 本轮修改了哪些地方
```

**Refine 策略详细设计：**
1. Editor 返回 `weakest: str` 指出最弱平台
2. Writer 只重生成该平台的文案，其他两平台保持不变
3. 如果 `overall < 60`（全面不合格），才重写三平台
4. 每次 refine 必须输出 `revision_notes`，说明"按照 Editor 建议X，修改了Y"

### 4.4 EditorAgent（由 quality_checker.py 升级）

职责：
- 对三平台文案分别评分（已有 LLM 评分）
- 给出**具体、结构化的修改建议**
- 判断"是否值得重试"，返回 verdict

**强制 suggestions 格式：**
```
[平台名称] 第X段: 具体问题描述 → 期望修改效果
```

示例：
```
[公众号] 第2段: 缺少具体的命令行示例 → 补充一个可复制的代码块
[小红书] 结尾: 没有互动问句 → 加一句"你们觉得哪个方法更好？评论区告诉我"
[抖音] 开头: 钩子不够强 → 前3秒直接抛出数字或反问句
```

输出：
```python
class EditVerdict(BaseModel):
    scores: dict              # {platform: int}
    overall: int
    passed: bool
    verdict: Literal["pass", "retry", "human_review"]
    weakest: str              # 最弱平台名称，供 Writer refine 使用
    suggestions: List[str]    # 必须按上述格式输出
    priority: Literal["high", "medium", "low"]
```

### 4.5 PublisherAgent（由 publisher.py 升级）

职责：
- 调用 kuaifa 发布到公众号草稿箱（已有）
- 记录发布元数据（时间、平台、状态）
- 返回发布结果

### 4.6 FeedbackAgent（新增，受限版）

职责：
- 读取用户手动导入的后台数据（CSV / JSON / 表单）
- 做简单统计：哪种风格点击率更高、哪种标题互动更多
- 生成"风格偏好画像"，供 WriterAgent 参考

**推回原设计：不做 OCR**。截图 OCR 会引入沉重的原生依赖（paddleocr/easyocr），PyInstaller 打包体积和兼容性都会受影响。只做 CSV/JSON 文件上传 + 手动表单输入。

输出：
```python
class StyleProfile(BaseModel):
    preferred_tone: str               # "专业干货" / "轻松口语" 等
    high_performing_patterns: List[str]  # 高互动标题模式
    last_updated: str
```

## 5. ReAct 循环设计

不是完全开放的"想干嘛干嘛"，而是**受控的生成-编辑循环**。

```
用户输入 ──▶ Orchestrator 制定计划（纯代码）
                 │
                 ▼
         ┌──────────────┐
         │  Research?   │──是──▶ ResearchAgent ──▶ 资料包
         │  (可选)      │        (1次，不循环)
         └──────────────┘
                 │
                 ▼
         ┌──────────────┐
         │  WriterAgent │◄──────┐
         │   生成初稿   │       │
         └──────────────┘       │
                 │              │
                 ▼              │
         ┌──────────────┐      │
         │  EditorAgent │      │
         │   审阅评分   │      │
         └──────────────┘      │
                 │              │
         ┌───────┴───────┐     │
         ▼               ▼     │
       pass           retry    │
         │               │     │
         ▼               └─────┘
    输出结果        (最多2次循环)
                      │
                 3次仍不过
                      │
                      ▼
               human_review
               (推给用户决定)
```

**关键约束：**
- Writer → Editor 循环最多 3 次（含初稿）
- 每次 retry 必须基于 Editor 的具体 suggestions
- 第 3 次仍不过，输出当前最佳稿 + 问题说明，不无限循环
- Token 预算：单次任务不超过 5 轮 LLM 调用（Orchestrator 不占用 LLM 调用次数）

## 6. 状态管理与记忆

### 6.1 任务状态（TaskState）
```python
@dataclass
class TaskState:
    task_id: str
    status: Literal["planned", "researching", "writing", "editing", "done", "failed"]
    note_source: str                      # 笔记来源（文件路径/文本/笔记库）
    research_data: Optional[ResearchResult]
    drafts: List[WriterOutput]            # 每次生成的版本，包含 revision_notes
    edit_history: List[EditVerdict]       # 每次审稿记录
    final_output: Optional[WriterOutput]
    metadata: dict                        # 耗时、token 数、模型等
```

### 6.2 持久化存储

**推回原设计：不用 JSONL，用 SQLite**。

理由：`sqlite3` 是 Python 标准库，零依赖。相比 JSONL 的追加写简单但查询累赞，SQLite 的按状态/日期筛选、事务保证都更可靠。个人工具每天几条数据，SQLite 完全过剩。

存储规划：
- `data/content_agent.db` — SQLite 数据库，存储任务记录、审稿历史、发布记录
- `data/style_profile.json` — 风格画像，JSON 文件（结构简单，不需 SQL）

### 6.3 Agent 间通信
不引入消息队列，使用显式函数调用：
```python
orchestrator.run(task_input)
    -> research_agent.run(state)
    -> writer_agent.run(state)
    -> editor_agent.run(state)
    -> if retry: writer_agent.refine(state, verdict)
```

## 7. 自主选题（TopicPicker）

**定位：半自主**。agent 提议，人拍板。

实现：
1. **扫描器**：每天定时扫描笔记库，找出新增/修改文件
2. **热点获取**：ResearchAgent 搜索当日技术热点
3. **匹配器**：LLM 判断"笔记A + 热点B = 值得写的话题"，输出选题建议
4. **推送**：Web UI 首页显示"今日推荐选题"

```python
class TopicSuggestion(BaseModel):
    title: str
    note_file: str            # 关联的笔记
    trending_topic: str       # 蹭的热点
    platforms: List[str]      # 建议发哪些平台
    reason: str               # 为什么值得写
    priority: int             # 1-5
```

## 8. 反馈闭环（受限版）

**直接读取平台数据不可行**，采用替代方案：

### 8.1 人工导入反馈
- Web UI 增加"导入数据"入口：上传 CSV/JSON 文件或粘贴表单
- FeedbackAgent 解析提取关键指标（阅读、点赞、收藏、评论）

### 8.2 内部 A/B 评分
- 同一笔记生成多风格版本时，用户手动打分
- 记录到 `data/style_profile.json`，长期积累个人偏好

### 8.3 搜索反馈（轻量）
- 发布后 24h，搜索看内容是否被平台收录，间接评估
- 价值有限，作为辅助信号

## 9. Web UI 调整

**推回原设计：Phase 0 就拆分 web_ui.py**。

当前 `web_ui.py` 已经 2000+ 行，再增加 Tab 会变成维护噩梦。拆分为 `ui/tabs/` 下的独立模块，每个模块暴露 `create_tab(gr.Blocks)` 函数。

```
ui/
├── __init__.py
├── app.py                 # Gradio Blocks 主容器，组装各 Tab
└── tabs/
    ├── generate_tab.py      # 📝 工作台：输入、生成、输出
    ├── topics_tab.py        # 🤖 智能选题
    ├── data_tab.py          # 📊 数据中心：历史、风格画像、反馈导入
    ├── config_tab.py        # ⚙️ 设置：模型、发布、笔记库
    └── components.py        # 共用组件（状态栏、导出按钮等）
```

| Tab | 内容 |
|-----|------|
| 📝 工作台 | 输入笔记、生成文案、查看输出（当前主功能） |
| 🤖 智能选题 | 今日推荐选题、一键开始生成 |
| 📊 数据中心 | 历史任务列表、风格画像、反馈数据导入 |
| ⚙️ 设置 | 模型配置、发布配置、笔记库路径 |

## 10. 分阶段实施计划

### Phase 0：模块化拆分（3-4 天）
- 新建 `agents/` 目录，实现 Orchestrator、ResearchAgent、WriterAgent、EditorAgent、PublisherAgent 类
- Orchestrator 用纯代码调度，不用 LLM
- 新建 `ui/tabs/`，拆分 `web_ui.py`
- `content_agent/` 降级为工具库，保留原有功能
- 引入 SQLite 存储 `TaskState`
- **目标**：代码结构清晰，功能与现在完全一致

### Phase 1：ReAct 循环（4-5 天）
- Orchestrator 实现 Writer → Editor → Writer 循环
- 打磨 EditorAgent 的 suggestions 输出质量（结构化格式、具体段落定位）
- WriterAgent 实现双模式 prompt（初稿/修改）和单平台 refine
- 加入熔断和 token 预算
- **目标**：生成质量提升，agent 能自主决定重试

### Phase 2：自主选题（2-3 天，可选）
- 实现 TopicPicker：笔记库扫描 + 热点搜索 + 匹配
- Web UI 增加"智能选题" Tab
- 可配置定时任务每日推送
- **目标**：从"人找工具"变成"工具提醒人"

### Phase 3：反馈与画像（2-3 天，可选）
- 增加数据导入功能（CSV/JSON 上传 + 手动表单）
- 不做 OCR
- FeedbackAgent 统计高互动模式
- WriterAgent 参考 style_profile 调整输出
- **目标**：越用越懂用户偏好

### Phase 4：真·多 Agent 协作（可选，远期）
- Research 与 Write 并行（如果技术允许）
- 引入多模型竞争（DeepSeek 和 Kimi 各写一版，Editor 选优）
- 视前面效果决定

## 11. 文件变更规划

```
content-agent/
├── agents/                      # 新增：业务层
│   ├── __init__.py
│   ├── orchestrator.py          # 纯代码调度器
│   ├── research_agent.py        # ResearchAgent
│   ├── writer_agent.py          # WriterAgent（初稿 + refine 双模式）
│   ├── editor_agent.py          # EditorAgent（强制结构化 suggestions）
│   ├── publisher_agent.py       # PublisherAgent
│   ├── topic_picker.py          # 自主选题
│   └── feedback_agent.py        # 反馈分析
├── content_agent/               # 保留：底层工具库，不再持有 Agent
│   ├── agent_core.py            # 逐步迁移到 writer_agent.py 后删除
│   ├── research.py              # 保留底层搜索函数
│   ├── quality_checker.py       # 保留底层规则检查
│   ├── html_renderer.py
│   ├── docx_exporter.py
│   ├── publisher.py
│   ├── sensitive_checker.py
│   ├── calendar.py
│   └── scheduler.py
├── ui/                          # 新增：界面层
│   ├── __init__.py
│   ├── app.py                   # 主容器
│   ├── components.py            # 共用组件
│   └── tabs/
│       ├── generate_tab.py
│       ├── topics_tab.py
│       ├── data_tab.py
│       └── config_tab.py
├── data/                        # 新增（gitignore）
│   ├── content_agent.db         # SQLite
│   └── style_profile.json
├── main.py                      # 适配新架构
├── web_ui.py                    # 逐步迁移到 ui/app.py 后删除
└── ...
```

## 12. 已知限制与风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| ReAct 循环不稳定，反复重写 | Token 成本高、响应慢 | 硬限制循环次数（3次）+ token 预算 + 单平台 refine |
| EditorAgent suggestions 质量不稳定 | Writer 改不到点子上 | Phase 1 前3天专门调试 prompt，强制结构化格式 + 正例 |
| 自主选题质量差 | 推荐无关内容，用户不信任 | 增加 confidence 阈值，低分选题不展示 |
| 人工导入反馈繁琐 | 用户懒得用，数据积累慢 | 简化导入流程（CSV/JSON 批量上传） |
| 重构期间引入 bug | 现有功能损坏 | Phase 0 做全面回归测试，保留旧入口作为 fallback |
| web_ui.py 拆分引入事件绑定 bug | Tab 之间状态不同步 | 拆分时保持 Gradio 组件引用不变，逐步迁移 |
