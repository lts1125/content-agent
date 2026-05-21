# Content Agent — 重构演进历史

本文档记录 content-agent 从单文件脚本到多 Agent 架构的完整演进过程，包含每次重大变更的背景、问题、方案和结果。

---

## 标记法

- 【功能】— 新增用户可感知的功能
- 【重构】— 代码结构调整，功能可能不变但可维护性提升
- 【修复】— bug 修复或兼容性处理
- 【设计】— 架构设计文档，尚未完全落地

---

## 总览

```
v0.1 单平台输出 (2026-05-13 前)
  ↓
v0.2 三平台输出 + 模块化重构 (2026-05-14)
  ↓
v0.3 质量检查 + 搜索增强 + 批量处理 (2026-05-15)
  ↓
v0.4 Web UI + 体验优化 (2026-05-16)
  ↓
v0.5 P1 完整功能集 + PyInstaller 打包 (2026-05-17)
  ↓
v0.6 工作流整合—定时任务 + 内容日历 + 微信发布 (2026-05-18)
  ↓
v0.7 笔记库联动 + UI Tab 拆分 (2026-05-19)
  ↓
v0.8 自主 Agent 架构 (2026-05-20) ← 当前
```

---

## 详细记录

### Phase 0: 起点 — 单文件脚本 (2026-05-13 前)

- **状态**：单个 `main.py`，硬编码 DeepSeek API 调用，只能输出小红书单平台
- **问题**：无法切换模型、无法批量处理、无配置文件管理
- **笔记**: 无（起步阶段）

---

### 【功能】v0.2 — 三平台同时输出 (2026-05-14)

**Commit**: `eea4683`

**Background**
用户需要把同一份技术笔记同时改写成小红书、公众号、抖音三种风格，而不是只生成一种。

**方案**
- 在 System Prompt 中明确定义三个平台的写作规范
- 输出结构由单字段改为 `MultiPlatformContent` dataclass（后来升级为 Pydantic `WriterOutput`）
- 每个平台有独立的字数、格式、风格要求

**结果**
- `main.py -p all` 可以一次生成三份文案
- 输出按日期分目录存放

**笔记**: `notes/20260518_three_platform_output.md`

---

### 【重构】v0.3 — 模块化 + 多 Provider 支持 (2026-05-14)

**Commit**: `b6670a1`

**Background**
原始代码硬编码 DeepSeek，想用 Kimi 或 OpenAI 时需要手动改代码。单文件 `main.py` 超过 300 行，难以维护。

**问题**
- 模型配置写死在代码里
- 无法通过 `.env` 切换 Provider
- 无 CLI 参数支持

**方案**
- 拆分 `content_agent/agent_core.py`：模型配置、Agent 初始化、三平台生成
- 引入 `python-dotenv`，从 `.env` 读取 `MODEL_PROVIDER` 和对应 API Key
- 支持 4 种 Provider：DeepSeek / Kimi / MiniMax / OpenAI + 自定义
- 新增 `main.py` CLI 参数：`-i` 输入、`-o` 输出、`-p` 平台、`-c` 清理

**兼容性**
- `存在于 PydanticAI 0.8 API 变动：`OpenAIModel` → `OpenAIChatModel`，`base_url` 需用 Provider 包装

**结果**
- 通过环境变量切换模型，无需改代码
- CLI 支持完整的参数交互

**笔记**: `notes/多Provider支持与质量检查实现笔记.md`

---

### 【功能】混合质量检查 (2026-05-14)

**Commit**: `c4ab87d`

**Background**
大模型生成的三平台文案质量参差不齐，有时候公众号缺少代码块，抖音口语化不足。需要自动检测并触发重试。

**方案**
- **层级 1**：`RuleChecker` — 基于规则的零成本检查
  - 检测公众号是否有代码块、小红书是否有 emoji、抖音是否有画面提示
- **层级 2**：`LLMScorer` — 大模型对三平台分别打分（0-100）
  - 公众号：结构完整性、技术深度、代码清晰度、逻辑连贯
  - 小红书：标题吸引力、信息密度、互动钩子、可读性
  - 抖音：开头钩子、短句比例、画面提示、行动号召
- **重试机制**：overall < 70 时，把 `retry_suggestion` 拼入 prompt 重新生成，最多 3 次

**笔记**: `notes/20260518_quality_checker.md`

---

### 【功能】搜索增强 (2026-05-15)

**Commits**: `9baf9fb`, `049c58c`

**Background**
笔记可能缺少背景信息（如新技术的发展现状、行业实践），导致文案浅薄。

**方案**
- `research.py`：封装 DuckDuckGo 和 Tavily 搜索
- `extract_keywords_with_llm`：用 LLM 从笔记中提取搜索关键词（避免搜索整篇笔记）
- 搜索结果摘要后拼入 prompt，作为背景资料

**笔记**: `notes/20260515_mcp_search_enhancement.md`

---

### 【功能】批量处理 (2026-05-16)

**Commit**: `1844ea3`

**Background**用户一次有多篇笔记要处理，需要能用 `---` 分隔笔记一次性生成。

**方案**
- `用 `re.split(r'\n\s*---\s*\n', note_text)` 拆分多篇笔记
- 循环生成，结果用 `\n\n---\n\n` 拼接
- 每篇独立质检，互不影响

**笔记**: `notes/20260516_batch_processing.md`

---

### 【功能】Web UI 基于 Gradio (2026-05-16)

**Commits**: `992c993`, `0fb208a`

**Background**
非技术用户不会用 CLI，需要可视化界面。

**方案**
- `引入 Gradio，单个页面实现所有功能
- `左侧输入区（笔记、平台选择、配置）+ 右侧输出区（三平台文案、HTML 预览）
- `监听本地 `127.0.0.1:7860`

**兼容性**
- `打包后 windowed 模式下无 stdout，增加保护逻辑避免 gradio 报错

**笔记**: `notes/20260516_web_ui.md`

---

### 【修复】AgentRunResult 字段名 bug (2026-05-16)

**Commit**: 无单独 commit（修复合并到 web_ui 相关 commit）

**Background**
PydanticAI 0.8 升级后，`AgentRunResult.data` 改名为 `AgentRunResult.output`。项目里混用了旧字段名，导致标题 A/B 测试和配图 Prompt 生成功能报错。

**影响范围**
- `web_ui.py` 中的 `generate_titles()` 和 `generate_cover_prompt()`
- `content_agent/agent_core.py` 中的 `agent.run()`

**笔记**: `notes/20260516_agentrunresult_data_bugfix.md`

---

### 【功能】P1 完整功能集 (2026-05-17)

**Commit**: `cd79197`

**包含功能**
- `标签/话题推荐`：基于内容生成平台标签
- `敏感词预检`：本地词表 + 可选百度 API
- `Word 导出`：`python-docx` 生成 .docx，支持标题、列表、排版
- `PyInstaller 打包`：单文件 `.app` 桌面端

**笔记**
- `notes/20260518_tags_recommendation.md`
- `notes/20260518_sensitive_word_check.md`
- `notes/20260518_export_feature.md`
- `notes/20260517_pyinstaller_desktop_app.md`

---

### 【功能】工作流整合 (2026-05-18)

**Commits**: `03f079b`, `d56e2a1`, `3185eaa`, `c900b98`

**定时任务**
- `定时任务 / Cron 调度` (P2-1)
- `使用 `schedule` 库实现每日/工作日生成
- `Web UI 内可增删查看定时任务

**内容日历**
- `内容日历管理` (P2-2)
- `发布计划跟踪：草稿 → 已排期 → 已生成 → 已发布
- `SQLite 存储入口

**微信发布**
- `微信公众号草稿箱自动发布` (P2-3)
- `通过 [kuaifa](https://github.com/shirenchuang/kuaifa) CLI 调用微信公众号 API
- `Web UI 内集成 kuaifa 配置面板（AppID / AppSecret / API Key）
- `支持封面图片上传和摘要填写

**笔记**
- `notes/20260518_content_calendar.md`
- `notes/20260518_wechat_publisher.md`

---

### 【功能】笔记库联动 (2026-05-19)

**Commit**: `f793fc5`

**Background**
用户使用 Obsidian 管理笔记，希望能直接从 Obsidian vault 选择笔记文件，而不是手动粘贴。

**方案**
- `新增 vault 路径配置（保存在 .env 的 VAULT_PATH）
- `自动扫描 vault 下所有 .md 文件
- `Dropdown 选择文件后自动读取内容到输入框

**笔记**: `notes/20260519_obsidian_vault_integration.md`

---

### 【重构】Web UI 重构为 Tab 布局 (2026-05-19)

**Commit**: `5cc1fdd`

**Background**
web_ui.py 超过 2000 行，所有功能堆在一个页面上，滚屏距离很长。

**问题**
- `配置、历史、生成均在同一页
- `代码可维护性差

**方案**
- `分 3 个 Tab：
  - `📝 生成` — 输入区 + 输出区 + 优化/标题/预览
  - `⚙️ 配置` — 模型配置 + 发布配置 + 定时任务
  - `📚 历史` — 历史记录管理
- `保留 Gradio 组件引用不变，只是按 Tab 分组

**后续清理**
- `生成 Tab 内红于的历史下拉框被移除，统一放到 📚 历史 Tab
- `删除残留的 kuaifa 事件绑定，消除 NameError 风险

---

### 【设计】自主 Agent 架构 (2026-05-20)

**Commit**: `a9c2c8b`

**Background**
原有架构是硬编码 Pipeline：`main.py` / `web_ui.py` 直接调用 `agent_core.py`，agent 本身不参与决策。想让系统能自主决定"要不要搜索"、"重写时只改最弱平台"。

**方案**
- `新增 `agents/` 目录，引入多 Agent 架构
- `层级边界：
  - `agents/` — 业务层（唯一对外暴露）
  - `content_agent/` — 底层工具库
  - `ui/` — 前端界面模块
- `Orchestrator (纯 Python 调度器)：不用 LLM、用 if/else 控制流程
  - `Writer → Editor → Writer 循环，最多 3 次
  - `熔断机制：3 次不过则取最佳稿 + 推给用户
  - `Token 预算：单次任务 ≤ 5 轮 LLM 调用
- `WriterAgent 双模式 prompt：
  - `初稿模式：完整三平台写作指南
  - `修改模式：精简 prompt，只改最弱平台（overall < 60 才重写三平台）
- `EditorAgent 结构化 suggestions：
  - `强制格式：`[平台] 第X段: 具体问题 → 期望效果`
  - `规则检查保底 + LLM 精细评分
- `ResearchAgent：从 research.py 升级，输出结构化 ResearchResult
- `Store：SQLite 任务记录 + JSON 风格画像

**Schema 设计**
- `TaskInput` — 用户输入
- `TaskState` — 贯穿任务生命周期的状态对象
- `WriterOutput` — 包装三平台文案 + revision_notes
- `EditVerdict` — 带结构化 suggestions 的审稿结果

**分阶段实施**
- `Phase 0` (当前)：新建 agents/ + ui/ 目录，代码结构清晰，功能与现有一致
- `Phase 1` (进行中)：web_ui.py 接入 Orchestrator，实现受控 write-edit 循环
- `Phase 2` (待定)：自主选题 TopicPicker
- `Phase 3` (待定)：反馈与风格画像
- `Phase 4` (待定)：多模型竞争

**兼容策略**
- `不删除 `content_agent/agent_core.py`，保留作为 fallback
- `WriterOutput.to_content_dict()` 方法，无缝传给原有工具函数

**笔记**: `notes/20260520_autonomous_refactor_design.md`

---

### 【重构】web_ui.py 接入 Orchestrator (2026-05-20)

**Commit**: 当前会话中实施

**Background**
Phase 0 新建了 agents/ 架构，但 web_ui.py 仍然直接调用 ContentAgent + QualityChecker 手动循环，未真正接入 Orchestrator 的自动调度能力。

**问题**
- `原来的质检循环是外层硬编码：生成 → 检查 → 失败则把 retry_suggestion 拼到 prompt 里重新生成全部三平台
- `EditorAgent 不能精准定位问题平台
- `WriterAgent 不能只修改最弱平台，每次重试都是全量重写

**方案**
- `web_ui.py 导入 TaskInput 和 Orchestrator
- `修改 `generate_content()` 核心循环：
  - `原：`agent.run() + checker.check() 手动 3 次循环
  - `新：`orchestrator.run(task_input)`，内部自动处理 Writer → Editor → refine
- `搜索增强仍在外层处理，`TaskInput.enable_research=False` 避免重复
- `状态栏增强：
  - `显示 LLM 调用次数、耗时
  - `人工审核提示（human_review_needed）
  - `单篇笔记时显示 Editor 结构化建议
- `新增 `_get_orchestrator()` 缓存 + `save_config` 时清除缓存

**结果**
- `Orchestrator 自动控制最多 3 次 write-edit 循环
- `WriterAgent.refine() 只修改最弱平台，减少 token 消耗
- `EditorAgent 按格式输出具体段落定位的修改建议

---

## 已知遗留问题

1. **OpenAI SSE 解析器共用**：`ProtocolType::OpenAiSse` 和 `DifySse` 共用同一个 `SseChatMessageParser`，仍依赖 fallback 手动提取
2. **WriterAgent style 参数**：当前仍通过 `note_text` 拼接 `style_note` 传入，未真正利用 `WriterAgent.run()` 的 `style` 参数
3. **EditorAgent suggestions 质量**：结构化格式在 prompt 中强制，但 LLM 偶尔仍会偏离格式
4. **ResearchAgent 原始笔记传递**：已修复，`TaskState.metadata["_raw_note_text"]` 保存原始笔记供 ResearchAgent 读取

---

## 文件变更时间线

```
2026-05-13  前   单文件 main.py，硬编码 DeepSeek
2026-05-14       三平台输出 + 模块化 + 多 Provider
2026-05-14       质量检查
2026-05-15       搜索增强 v1/v2
2026-05-16       批量处理 + Web UI + 字段名 bugfix
2026-05-16       小红书 HTML 卡片预览
2026-05-16       风格模板库
2026-05-17       P1 完整功能集（标签/敏感词/Word导出/PyInstaller）
2026-05-18       定时任务 + 内容日历 + 微信发布
2026-05-19       笔记库联动 + Web UI Tab 拆分
2026-05-20       自主 Agent 架构 (agents/ + ui/) + web_ui.py 接入 Orchestrator
```

---

## 开发笔记索引

| 日期 | 笔记文件 | 内容 |
|------|-----------|------|
| 05-15 | `20260515_mcp_search_enhancement.md` | 搜索增强设计 |
| 05-16 | `20260516_agentrunresult_data_bugfix.md` | PydanticAI 0.8 字段名变更 bugfix |
| 05-16 | `20260516_batch_processing.md` | 批量处理实现 |
| 05-16 | `20260516_web_ui_preview.md` | HTML 卡片预览实现 |
| 05-16 | `20260516_web_ui_roadmap.md` | Web UI Roadmap |
| 05-16 | `20260516_web_ui_style.md` | 风格模板库 |
| 05-16 | `20260516_web_ui.md` | Web UI 初版实现 |
| 05-17 | `20260517_pyinstaller_desktop_app.md` | PyInstaller 打包桌面端 |
| 05-18 | `20260518_content_calendar.md` | 内容日历管理 |
| 05-18 | `20260518_export_feature.md` | Word 导出功能 |
| 05-18 | `20260518_html_renderer.md` | HTML 渲染器实现 |
| 05-18 | `20260518_quality_checker.md` | 质量检查实现 |
| 05-18 | `20260518_research_enhancement.md` | 搜索增强详细设计 |
| 05-18 | `20260518_sensitive_word_check.md` | 敏感词检测 |
| 05-18 | `20260518_tags_recommendation.md` | 标签推荐功能 |
| 05-18 | `20260518_three_platform_output.md` | 三平台输出设计 |
| 05-18 | `20260518_wechat_publisher.md` | 微信发布功能 |
| 05-19 | `20260519_obsidian_vault_integration.md` | Obsidian 笔记库联动 |
| 05-19 | `20260519_pyinstaller_kuaifa_bugfixes.md` | PyInstaller + kuaifa 兼容性修复 |
| 05-20 | `20260520_autonomous_refactor_design.md` | 自主 Agent 架构设计文档 |
| 05-15 | `CLI工具化改造笔记.md` | CLI 工具化总结 |
| 05-15 | `多Provider支持与质量检查实现笔记.md` | 多 Provider 和质检总结 |
