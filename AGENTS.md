# AGENTS.md

本文件为 Codex (Codex.ai/code) 提供在操作本仓库代码时的指导。

## 项目概览

Content Agent 是一个基于 PydanticAI 的中文 AI 内容改写助手。输入技术学习笔记，一键生成适配小红书、微信公众号、抖音三个平台的文案，并自动生成小红书风格的 HTML 配图卡片。

## 开发命令

本项目使用 pip 直接管理依赖（未提交 `requirements.txt`，按 README 手动安装）。

- **运行 CLI**: `python main.py -i notes/my_note.md`
- **运行 Web UI**: `python web_ui.py`（打开 http://127.0.0.1:7860）
- **打包桌面端**: `python scripts/build_app.py`（输出 `dist/ContentAgent.app`，仅 macOS）
- **测试打包结果**: `python scripts/test_app.py`

本项目没有正式的测试框架。`scripts/test_app.py` 和 `scripts/test_app_v2.py` 是针对 PyInstaller 打包结果的临时冒烟测试。

## 架构

### 入口文件

- `main.py` — CLI 入口。负责参数解析、批量目录遍历、按笔记创建子目录，并编排生成流水线：搜索增强 → 敏感词预检 → 生成文案 → 质量检查 → 保存文件 → 渲染 HTML 配图。
- `web_ui.py` — Gradio Web 界面（约 2000 行）。使用全局 `_agent` / `_checker` 缓存模式（通过 `_get_agent()` / `_get_checker()` 获取）。界面按 Tab 组织：📝 生成、⚙️ 配置、📚 历史，其中配置页内嵌定时任务和内容日历的子 Tab。

### 核心模块 (`content_agent/`)

- **`agent_core.py`** — PydanticAI Agent 配置与多 Provider LLM 管理。
  - `ModelConfig.from_env()` 读取 `.env`，返回 `(OpenAIChatModel, provider_name)`。
  - 支持的 Provider：`deepseek`、`kimi`、`minimax`、`openai`、`custom`（任意 OpenAI-compatible 接口）。
  - `ContentAgent.run()` 调用 `agent.run_sync(raw_notes)`，返回 `MultiPlatformContent`。
  - 注意：PydanticAI 0.8+ 使用 `output_type`（非 `result_type`），结果字段为 `result.output`（非 `result.data`）。

- **`quality_checker.py`** — 混合质量检查器。
  - `RuleChecker` 做零成本的正则/长度硬性校验。
  - `LLMScorer` 复用同一模型，换评分 prompt 做精细打分。
  - `QualityChecker.check()` 先跑规则，规则通过后再跑 LLM 评分。综合分 < 70 则附带改进建议重试（最多 3 次）。

- **`research.py`** — 搜索增强模块，在生成前补充背景资料。
  - `duckduckgo_search()` 通过 `ddgs` 实现（免费，无需 key）。
  - `tavily_search()` 通过 HTTP API 调用（需 `TAVILY_API_KEY`）。
  - `extract_keywords_with_llm()` 提取 2-3 个搜索关键词，失败时回退到 `heuristic_extract_keywords()`。

- **`html_renderer.py`** — 将生成的小红书文案解析为多卡片 HTML（`xiaohongshu_cards.html`），适配手机截图。使用基于正则的智能解析（`_smart_parse`）提取标题、小节、要点和金句。

- **`docx_exporter.py`** — Markdown 转 Word，带中文字体回退（`w:eastAsia`）。支持标题、列表、表格代码块、行内加粗/斜体/代码/链接、分隔线等。

- **`sensitive_checker.py`** — 本地敏感词表（政治、黄赌毒、广告法极限词、低俗）+ 可选百度 AI 内容审核 API（`BAIDU_CENSOR_API_KEY`）。

- **`scheduler.py`** — 基于 `schedule` 库的定时任务调度器。
  - 任务持久化到 `~/.content_agent/schedule.json`。
  - 在后台线程中通过子进程调用 `main.py` 执行任务。
  - 需要 `pip install schedule`。

- **`calendar.py`** — 内容日历（发布计划跟踪）。
  - 数据持久化到 `~/.content_agent/calendar.json`。
  - 状态流转：草稿 → 已排期 → 已生成 → 已发布。

- **`publisher.py`** — 微信公众号草稿箱发布，依赖外部 `kuaifa` CLI。
  - `kuaifa` 是 Node.js/npm 工具，**不会被 PyInstaller 打包进去**。
  - `_find_kuaifa()` 和 `_find_node()` 会搜索 PATH 及常见安装路径（包括 `~/.hermes/node/bin`）。
  - 实际调用：`node <kuaifa> publish <markdown> --draft --title ...`。

### 配置与持久化

- **开发环境**: `.env` 放在项目根目录。
- **PyInstaller 打包后**: `.env` 放在 `~/Library/Application Support/ContentAgent/.env`。
- **定时任务/日历数据**: `~/.content_agent/schedule.json` 和 `calendar.json`。

### 打包注意事项

- `ContentAgent.spec` 是 PyInstaller 的 spec 文件（生成时硬编码了 `/Users/lee/content-agent/`）。建议优先使用 `scripts/build_app.py`，它在脚本内拼接 PyInstaller 命令。
- macOS 桌面端使用 `--windowed` + `--onedir`。
- `web_ui.py` 中多处检查 `sys.frozen` 以区分打包环境，处理配置路径、stdout/stderr 重定向、`urllib` 代理绕过等。

## 重要约束

- **Kimi Code 与 Kimi API 的区别**：本项目**不能**使用 Kimi Code 订阅 key（有 User-Agent 白名单限制）。必须使用 Moonshot 开放平台的 API key，通过 `KIMI_API_KEY` 配置。
- **kuaifa 外部依赖**：微信公众号发布功能要求目标机器单独安装 `npm install -g kuaifa`，它不在 Python 依赖内。
- **无测试框架**：没有 pytest/unittest。修改后通过直接运行 `main.py` 或 `web_ui.py` 验证。
- **Python 版本要求**: 3.9+。
