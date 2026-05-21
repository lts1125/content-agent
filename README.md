# Content Agent —— AI 多平台内容改写助手

基于 **PydanticAI** 的轻量 Agent，输入你的技术学习笔记，一键生成 **小红书 / 微信公众号 / 抖音** 三平台文案，并自动生成小红书风格配图。

> 本项目是作者学习 AI Agent 开发的实战项目，从单文件脚本逐步重构为模块化 CLI 工具。

---

## 效果预览

输入一段技术学习笔记，Agent 自动输出：

| 平台 | 风格 | 字数 | 配图 | 标签 |
|------|------|------|------|------|
| 小红书 | emoji 要点化、轻松口语 | 300-600 | ✅ HTML 卡片预览 | ✅ 自动推荐 |
| 公众号 | 深度长文、代码块、章节完整 | 1500-2500 | ❌ | ✅ |
| 抖音 | 口播脚本、开头钩子、画面提示 | 200-400 | ❌ | ✅ |

|附带：标题 A/B 测试、配图 Prompt 生成、敏感词预检、一键导出 Markdown/Word、定时任务、内容日历、公众号一键发布。

---

## 技术栈

- **Agent 框架**: [PydanticAI](https://github.com/pydantic/pydantic-ai) — 类型安全、轻量、对后端开发者友好
- **LLM**: 多 Provider 支持（DeepSeek / Kimi / MiniMax / OpenAI / 自定义）
- **Web UI**: Gradio — 简洁的可视化界面
- **输出**: Markdown + Word(.docx) + HTML 配图卡片
- **打包**: PyInstaller — macOS 单文件桌面端应用
- **语言**: Python 3.9+

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/YOUR_NAME/content-agent.git
cd content-agent
```

### 2. 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pydantic-ai python-dotenv python-docx

# 如果需要 Web UI，额外安装：
pip install gradio
```

### 3. 配置 API Key

复制示例配置文件：

```bash
cp .env.example .env
```

编辑 `.env`，选择你想用的 Provider。默认推荐 **DeepSeek**（性价比最高）：

```
MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx
```

也支持其他 Provider，详见 `.env.example` 中的注释：
- **Kimi** (`platform.moonshot.cn`) —— 注意：Kimi Code (coding plan) 有白名单限制，第三方工具无法接入，需另外注册开放平台 API
- **MiniMax** (`platform.minimaxi.com`)
- **OpenAI**
- **自定义** —— 硅基流动、通义千问、智谱、本地 Ollama 等任何 OpenAI-compatible 服务

### 4. 运行

**使用默认笔记（演示）：**

```bash
python main.py
```

**从文件读取笔记：**

```bash
python main.py -i notes/my_note.md
```

**只生成小红书，指定输出目录：**

```bash
python main.py -i notes/my_note.md -p xiaohongshu -o ./dist
```

**启用搜索增强（自动补充背景资料）：**

```bash
# 使用 DuckDuckGo（免费，无需 API key）
python main.py -i notes/my_note.md -r

# 使用 Tavily（效果更好，需注册 API key）
python main.py -i notes/my_note.md -r --search-engine tavily
```

**Agent Mode（自动化工作流）：**

```bash
# 启动 Vault 监听，自动处理新放入的笔记
python main.py --watch

# 批量处理 inbox 下已有文件（处理完即退出）
python main.py --process-inbox

# 查看待发队列
python main.py --queue
python main.py --queue --status approved

# 审核通过 / 拒绝
python main.py --approve queue_xxx
python main.py --reject queue_xxx

# 手动发布下一个已审核项
python main.py --publish-next
```

> Agent Mode 依赖环境变量 `VAULT_PATH`（默认 `~/.content_agent/vault`），
> 监听 `$VAULT_PATH/inbox/` 目录下的 `.md`/`.txt` 文件，处理完后自动归档到 `processed/` 或 `failed/`。

> 更多参数见 `python main.py --help`。

输出按日期分目录存放：

```
output/
  20260515/
    20260515_095151_xiaohongshu.md
    20260515_095151_gongzhonghao.md
    20260515_095151_douyin.md
    配图/
      xiaohongshu_card.html
```

> 配图是 HTML 文件，用浏览器打开后逐张截图即可直接发小红书。

---

## Web UI （可视化界面）

除了 CLI，还提供了基于 Gradio 的 Web 界面，适合不喜欢命令行的用户。

**启动 Web UI：**

```bash
pip install gradio  # 首次使用需安装
python web_ui.py
```

然后打开浏览器访问 `http://127.0.0.1:7860`。

**界面功能概览：**
- **生成**：粘贴/上传笔记、多平台选择、风格切换、搜索增强、实时预览
- **辅助**：标题 A/B 测试、配图 Prompt 生成、敏感词预检、历史恢复
- **工作流**：定时任务（Cron 调度）、内容日历（发布计划跟踪）、公众号一键发布（通过 [kuaifa](https://github.com/shirenchuang/kuaifa) CLI）
- **导出**：一键复制、Markdown / Word 导出

---

## 项目结构

```
.
├── main.py                      # CLI 入口
├── web_ui.py                    # Web UI 入口（Gradio）
├── content_agent/
│   ├── __init__.py
│   ├── agent_core.py            # Agent 核心（多 Provider 配置、三平台输出、标签推荐）
│   ├── html_renderer.py         # 小红书 HTML 配图卡片
│   ├── quality_checker.py       # 混合质量检查（规则 + LLM 评分 + 重试）
│   ├── research.py              # 搜索增强（DuckDuckGo / Tavily）
│   ├── docx_exporter.py         # Word 文档导出（字体、排版、列表）
│   ├── sensitive_checker.py     # 敏感词预检（本地词表 + 可选百度API）
│   ├── calendar.py              # 内容日历管理（发布计划、状态跟踪）
│   └── publisher.py             # 多平台发布（当前支持微信公众号草稿箱）
├── automation/                  # P0: Agent 化自动运行层
│   ├── vault_watcher.py         # Vault 目录监听（watchdog）
│   ├── agent_controller.py      # 自动触发 Orchestrator
│   ├── publish_queue.py         # 待发队列（pending → approved → published）
│   └── style_profile.py         # 风格画像样本收集
├── agents/                      # Multi-Agent 架构
│   ├── orchestrator.py          # 任务调度器
│   ├── writer_agent.py          # 文案生成
│   ├── editor_agent.py          # 质量审稿
│   ├── research_agent.py        # 搜索增强
│   ├── publisher_agent.py       # 发布执行
│   └── schemas.py               # 数据模型
├── scripts/
│   ├── build_app.py             # PyInstaller 打包脚本（macOS 桌面端）
│   ├── test_app.py              # 打包后验证脚本
│   └── test_app_v2.py           # 打包验证脚本 v2
├── notes/                       # 开发笔记
├── .env                         # API Key 配置（gitignore）
├── .env.example                 # 配置模板
├── .gitignore
├── README.md
└── output/                      # 生成的文案（按日期子目录）
```

---

## 打包为桌面端应用（可选）

如果想分发给不会用命令行的朋友，可以用 PyInstaller 打包成单文件 `.app`：

```bash
pip install pyinstaller
python scripts/build_app.py
```

|打包完成后在 `dist/ContentAgent.app` 找到应用，双击即可运行，无需终端。

> **注意：公众号发布功能依赖外部 kuaifa CLI**
> 
>打包后的 `.app` 不包含 kuaifa，因为它是 Node.js/npm 工具。如需使用公众号发布功能，需要在目标机器上单独安装 [kuaifa](https://github.com/shirenchuang/kuaifa)：
> ```bash
> npm install -g kuaifa
> ```
> 然后在 Web UI 的「发布配置」面板中填写微信 AppID、AppSecret 和 kuaifa API Key。

> 当前只在 macOS 上测试过，Windows/Linux 需要小调配置。

---

## 自定义你的笔记

将学习笔记保存为 `.md` 或 `.txt` 文件，放入 `notes/` 目录，然后运行：

```bash
python main.py -i notes/你的笔记.md
```

笔记格式没有严格要求，纯文本即可，Agent 会自动提取重点并改写。

---

## Roadmap

### P1 — 核心功能（已完成）
- [x] 小红书单平台输出
- [x] 三平台同时输出（小红书 / 公众号 / 抖音）
- [x] 自动保存为 Markdown
- [x] 从文件读取笔记（支持 `.md` / `.txt`）
- [x] 支持多模型 Provider（DeepSeek / Kimi / MiniMax / OpenAI / 自定义）
- [x] CLI 参数交互（选择平台、指定输入输出）
- [x] 自动生成小红书 HTML 配图卡片
- [x] 混合质量检查（规则 + LLM 评分 + 重试）
- [x] 搜索增强（DuckDuckGo / Tavily）
- [x] 批量处理多篇笔记
- [x] Web UI（Gradio）
- [x] 风格切换（专业 / 轻松 / 情绪 / 悬忶）
- [x] 标签/话题推荐
- [x] 敏感词预检
- [x] 标题 A/B 测试
- [x] 配图 Prompt 生成
- [x] 一键导出 Word
- [x] PyInstaller 打包桌面端

### P2 — 工作流整合（已完成）
- [x] 定时任务 / Cron 调度
- [x] 内容日历管理
- [x] 微信公众号一键发布到草稿箱（通过 [kuaifa](https://github.com/shirenchuang/kuaifa) CLI）

### P3 — Agent 化（已完成）
- [x] Vault 监听自动触发（watchdog）
- [x] 待发队列管理（pending → approved → published）
- [x] 风格画像样本收集

---

## 为什么做这个项目

作者是一名后端工程师（Rust / AI Gateway 方向），想在下班后探索 AI Agent 开发作为副业方向。本项目既是学习笔记，也是第一个落地的 Agent 应用。

如果你也在学 Agent 开发，欢迎交流。

---

## License

MIT
