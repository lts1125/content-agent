# Content Agent 项目笔记索引

> 按时间线整理从初始实现到当前迭代的关键笔记。
> 命名约定：`notes/YYYY-MM-DD_主题.md` （实现笔记） | `docs/phaseX_主题.md` （设计文档）

---

## 目录结构

- `notes/` — 实现笔记（按日期排序）
- `docs/` — 设计文档（按阶段分类）
- `archive/` — 归档杂项
- `TEMPLATE.md` — 笔记模板

---

## Phase 0: CLI 工具化基础（2026-05-15）

| 文件 | 内容 |
|------|------|
| `notes/2026-05-15_cli_tooling.md` | CLI 工具化改造：argparse 命令行、配置文件、日志系统 |
| `notes/2026-05-15_multi_provider_quality_check.md` | 多 Provider 支持（Moonshot/OpenAI）+质量检查器初版 |
| `notes/2026-05-15_mcp_search_enhancement.md` | MCP 搜索增强：搜索结果处理、内容提取优化 |

## Phase 1: Web UI 基础（2026-05-16）

| 文件 | 内容 |
|------|------|
| `notes/2026-05-16_web_ui.md` | Web UI 核心实现：FastAPI + Jinja2 模板 |
| `notes/2026-05-16_web_ui_preview.md` | 文章预览功能：标题/正文/标签分离展示 |
| `notes/2026-05-16_web_ui_style.md` | UI 样式设计：暗色主题、响应式布局 |
| `notes/2026-05-16_web_ui_roadmap.md` | Web UI 路线图与迭代计划 |
| `notes/2026-05-16_batch_processing.md` | 批量处理：多文章并行生成 |
| `notes/2026-05-16_agentrunresult_bugfix.md` | AgentRunResult data 字段匹配 bug 修复 |

## Phase 2: 功能扩展（2026-05-17 ~ 05-18）

| 文件 | 内容 |
|------|------|
| `notes/2026-05-17_pyinstaller_desktop.md` | PyInstaller 打包桌面端应用 |
| `notes/2026-05-18_export_feature.md` | 导出功能：Markdown / HTML / 图片 |
| `notes/2026-05-18_tags_recommendation.md` | 智能标签推荐：基于内容关键词提取 |
| `notes/2026-05-18_sensitive_word_check.md` | 敏感词检查：过滤与警告机制 |
| `notes/2026-05-18_quality_checker.md` | 质量检查器升级：多维度评分 |
| `notes/2026-05-18_research_enhancement.md` | 搜索增强：多源聚合、信息去重 |
| `notes/2026-05-18_html_renderer.md` | HTML 渲染器：微信公众号样式卡片 |
| `notes/2026-05-18_content_calendar.md` | 内容日历：发布计划与排期 |
| `notes/2026-05-18_wechat_publisher.md` | 微信公众号发布流程 |
| `notes/2026-05-18_three_platform_output.md` | 三平台输出：公众号/小红书/抖音 |

## Phase 3: 集成与打包（2026-05-19）

| 文件 | 内容 |
|------|------|
| `notes/2026-05-19_obsidian_integration.md` | Obsidian Vault 集成：双向同步 |
| `notes/2026-05-19_pyinstaller_kuaifa_fixes.md` | PyInstaller + kuaifa 打包 bug 修复 |

## Phase 4: Agent 架构重构（2026-05-20 ~ 05-21）

| 文件 | 内容 |
|------|------|
| `notes/2026-05-21_automation_implementation.md` | P0 自动化实现：TrendScheduler + PublishQueue |
| `notes/2026-05-21_concurrent_generation.md` | P3-14 并发生成设计：多文章并行 |
| `notes/2026-05-21_config_template.md` | P3 配置模板：多平台配置管理 |
| `notes/2026-05-21_web_ui_refactor.md` | Web UI 重构：与 Orchestrator 集成 |

## Phase 5: 当前迭代（2026-05-27）

| 文件 | 内容 |
|------|------|
| `notes/2026-05-27_architecture_cleanup.md` | 架构清理：移除过期代码、结构优化 |
| `notes/2026-05-27_series_plan.md` | Content Agent 系列计划 |
| `notes/2026-05-27_trend_scheduler_implementation.md` | TrendScheduler 实现进度 |

---

## 设计文档（docs/ 目录）

| 文件 | 阶段 | 内容 |
|------|------|------|
| `phase0_agent_implementation_design.md` | P0 | Agent 核心实现设计 |
| `phase0_trend_scheduler_design.md` | P0 | TrendScheduler 设计 |
| `phase1_agent_intelligence_design.md` | P1 | Agent 智能增强设计 |
| `phase2_auto_publish_design.md` | P2 | 自动发布设计 |
| `phase4_autonomous_planning_design.md` | P4 | 自主规划设计 |
| `phase4_autonomous_refactor_design.md` | P4 | 自主架构重构设计 |
| `phase4_multi_agent_collaboration_design.md` | P4 | 多 Agent 协作设计 |
| `phase4_react_cli_usage.md` | P4 | ReAct CLI 使用文档 |
| `phase4_react_refactor_design.md` | P4 | ReAct 重构设计 |
| `phase4_web_ui_orchestrator_integration.md` | P4 | Web UI + Orchestrator 集成 |
| `phase5_architecture_decisions.md` | 架构 | 架构决策记录 |
| `phase5_auto_screenshot_design.md` | 架构 | 自动截图设计 |
| `phase5_b1_self_trigger_design.md` | 架构 | B1 自触发设计 |
| `phase5_cli_usage.md` | 架构 | CLI 使用文档 |
| `phase5_enhanced_tools_design.md` | 架构 | 增强工具设计 |
| `phase5_eval_phase2_design.md` | 架构 | 评估系统 Phase2 |
| `phase5_eval_phase3_design.md` | 架构 | 评估系统 Phase3 |
| `phase5_eval_system_design.md` | 架构 | 评估系统设计 |
| `phase5_feedback_agent_design.md` | 架构 | Feedback Agent 设计 |
| `phase5_feedback_decision_logic.md` | 架构 | 反馈决策逻辑 |
| `phase5_flow.md` | 架构 | 业务流程图 |
| `phase5_rag_eval_proposal.md` | 架构 | RAG 评估方案 |
| `phase5_smart_schedule_design.md` | 架构 | 智能排期设计 |
| `phase5_style_profile_integration.md` | 架构 | 风格配置集成 |
