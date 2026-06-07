# Content Agent —— AI 多平台内容创作助手

基于 **PydanticAI** 的中文内容 Agent。你可以输入一个主题，或者上传/粘贴一篇技术学习笔记，自动生成适配 **微信公众号 / 小红书 / 抖音** 的内容，并支持把公众号文章保存到微信公众号草稿箱。

当前最稳定的核心场景是：

> **技术笔记 / 选题 → 生成微信公众号文章 → 审核修改 → 上传封面 → 发布前核对 → 保存到公众号草稿箱 → 历史归档最终稿**

> 本项目是作者学习 AI Agent 开发的实战项目，从单文件脚本逐步重构为聊天式 Web UI、CLI、多 Agent 工作流、RAG 检索、自动发布和反馈优化系统。

---

## 效果预览

输入一个主题或一段技术学习笔记，Agent 自动输出：

| 平台 | 风格 | 字数 | 配图 | 标签 |
|------|------|------|------|------|
| 小红书 | emoji 要点化、轻松口语 | 300-600 | ✅ HTML 卡片 | ✅ 自动推荐 |
| 公众号 | 技术深度 / 通俗科普 | 1200-2500 | ❌ | ✅ |
| 抖音 | 口播脚本、热点资讯 | 200-400 | ✅ HTML 卡片 | ✅ |

对于微信公众号，聊天式 UI 还支持：

- 上传 `.md` / `.txt` 笔记作为生成素材
- 自动检索历史笔记作为参考资料
- 根据输入要求切换“技术深度版 / 通俗科普版”
- 展示生成过程、质量检查和审核修改建议
- 下载生成的 Markdown
- 上传封面并保存到微信公众号草稿箱
- 发布前核对标题、字数、task、文件和封面
- 发布成功后在历史任务中标记为“最终稿”

---

## 技术栈

- **Agent 框架**: [PydanticAI](https://github.com/pydantic/pydantic-ai)
- **LLM**: 多 Provider 支持（DeepSeek / Kimi / MiniMax / OpenAI / OpenAI-compatible）
- **Web UI**: Gradio（聊天式 UI + 传统 Web UI）
- **RAG**: Chroma + BGE 中文向量模型
- **输出**: Markdown + Word + HTML 配图卡片 + 微信公众号草稿箱
- **语言**: Python 3.9+

---

## 从零开始

### 0. 环境要求

- Python 3.9+（推荐 3.10 或 3.11）
- 一个可用的 LLM API Key（默认推荐 DeepSeek）
- 如需发布到公众号草稿箱：Node.js + [kuaifa CLI](https://github.com/shirenchuang/kuaifa)
- 如需 RAG 检索：首次运行会加载/下载 BGE embedding 模型

### 1. 克隆项目并安装依赖

```bash
git clone https://github.com/YOUR_NAME/content-agent.git
cd content-agent

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

如果你在 macOS 上看到 `urllib3` 关于 LibreSSL 的 warning，一般不影响本项目运行。

### 2. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`，至少配置一个模型 Provider。默认是 DeepSeek：

```env
MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
```

也可以使用 Kimi、MiniMax、OpenAI 或任意 OpenAI-compatible 服务，详见 `.env.example`。

> 注意：Kimi Code 订阅不是 Moonshot 开放平台 API Key。本项目需要 `platform.moonshot.cn` 的 `KIMI_API_KEY`。

#### API Key、Token Plan 与 Coding Plan 的区别

本项目调用的是标准大模型 API，所以能接入的是“可被程序直接调用”的 API Key 或 Token 套餐。

| 类型 | 是否支持 | 配置方式 |
|------|----------|----------|
| 官方 API Key | ✅ 支持 | 使用对应 Provider，例如 `deepseek` / `kimi` / `openai` |
| OpenAI-compatible API / Token Plan | ✅ 支持 | 使用 `MODEL_PROVIDER=custom` |
| 本地模型服务 | ✅ 支持 | 使用 `custom`，例如 Ollama 的 `/v1` 兼容接口 |
| Coding Plan / IDE 订阅账号 | ⚠️ 通常不支持 | 只有官方提供开放 API、Base URL 和模型名时才支持 |

如果你的套餐提供了 `API Key + Base URL + Model Name`，可以这样配置：

```env
MODEL_PROVIDER=custom
MODEL_BASE_URL=https://your-provider.example.com/v1
MODEL_NAME=your-model-name
MODEL_API_KEY=your-api-key-or-token
```

如果只是 Cursor、Kimi Code、Claude Code、Windsurf 等 Coding 工具的登录态、订阅权益或客户端 token，通常不能直接填到本项目里使用。

### 3. 启动聊天式 Web UI（推荐）

```bash
python chat_ui.py
```

打开浏览器访问：

```text
http://127.0.0.1:7861
```

聊天页支持两种输入方式：

1. **只输入主题**

```text
帮我写一篇关于 MCP 协议的公众号文章
```

2. **上传笔记文件后输入生成要求**

先上传 `.md` 或 `.txt` 笔记，然后输入：

```text
根据这篇笔记生成一篇公众号文章，面向普通人，通俗易懂，不要太技术
```

或：

```text
根据这篇笔记生成一篇公众号文章，面向技术从业者，专业严谨，保留技术细节和代码示例
```

### 4. 推荐主流程：技术笔记到公众号草稿箱

当前推荐先把“技术笔记 → 微信公众号可发布草稿”这条链路用顺：

1. 启动 `chat_ui.py`，打开 `http://127.0.0.1:7861`。
2. 上传一篇 `.md` 或 `.txt` 笔记，也可以只输入一个主题。
3. 在输入框里写清楚目标读者和风格，例如“给非技术人员阅读，通俗易懂”。
4. 点击发送，等待生成过程完成。
5. 查看生成结果和质量检查报告；如需修改，可以直接输入“把开头写得更抓人”或“改得更通俗一点”。
6. 下载公众号 Markdown，人工核对内容。
7. 上传公众号封面图。
8. 在“发布前核对”区确认标题、字数、task、文件和封面。
9. 勾选“我已核对文章、封面和发布目标”。
10. 点击“保存到公众号草稿箱”。
11. 到微信公众号后台草稿箱做最后检查。

发布成功后，历史任务会记录发布状态，并标记该 task 为“最终稿”。后续可以在历史任务中复制类似命令继续修改：

```text
基于最终稿 task chat_YYYYMMDD_HHMMSS 继续改写
```

### 5. 控制公众号文章风格

公众号支持两种常用生成方向：

| 模式 | 适合场景 | 触发方式 |
|------|----------|----------|
| 技术深度版 | 技术教程、架构分析、开发经验 | 默认模式，或写“面向技术从业者 / 专业严谨 / 保留代码示例” |
| 通俗科普版 | 面向普通人、产品、运营、小白读者 | 写“普通人 / 小白 / 零基础 / 通俗易懂 / 大白话 / 科普 / 少用术语 / 不要太技术” |

示例：

```text
根据这篇笔记生成一篇公众号文章，写给普通人看，通俗易懂，少用术语
```

```text
根据这篇笔记生成一篇公众号文章，面向后端工程师，保留实现细节和代码示例
```

### 6. 记忆、历史任务与最终稿

聊天式 UI 会记录生成历史，用于后续复用和修改：

- 上传笔记后，系统会自动索引笔记片段，后续生成时可检索相关历史内容。
- 历史任务会显示 task、文件、评分、审核决策、引用来源和发布状态。
- 可以用 task 精确指定历史文章，例如：

```text
修改 task chat_20260601_150235，把开头写得更抓人
```

```text
基于 task chat_20260601_150235 改得更通俗一点
```

- 保存到公众号草稿箱成功后，历史任务会显示“最终稿”和封面文件名。

### 7. 保存到微信公众号草稿箱（可选）

如需使用公众号草稿箱保存功能，需安装开源工具 [kuaifa CLI](https://github.com/shirenchuang/kuaifa)：

```bash
# 安装 kuaifa（需 Node.js 环境）
npm install -g kuaifa

# 配置 kuaifa（按提示输入微信公众号 AppID、AppSecret、API Key）
kuaifa config
```

使用流程：

1. 在 `chat_ui.py` 中生成公众号文章。
2. 下载并核对 Markdown。
3. 上传公众号封面图。
4. 检查“发布前核对”区里的标题、字数、task、文件和封面。
5. 勾选“我已核对文章、封面和发布目标”。
6. 点击“保存到公众号草稿箱”。
7. 到微信公众号后台草稿箱检查文章。

> [kuaifa](https://github.com/shirenchuang/kuaifa) 是外部 Node.js 开源工具，不会被 PyInstaller 或 Python 依赖自动打包。目标机器需要单独安装。

### 8. Docker 部署聊天 UI（可选）

服务器上可以用 Docker 先跑 `chat_ui.py`：

```bash
cp .env.example .env
# 编辑 .env，填入模型 API Key

docker compose up -d --build
```

访问：

```text
http://服务器IP:7861
```

默认会持久化这些目录：

```text
./output          -> 生成内容
./data            -> 本地数据库/运行数据
./.content_agent  -> 日志、定时任务、内容日历等用户配置
```

注意：

- Docker 默认使用轻量依赖文件 `requirements-docker.txt`，用于内容生成和聊天 UI，不安装 `sentence-transformers` / `torch` / `chromadb` 等 RAG 重依赖。
- 如果确实要在容器内启用完整 RAG，可改用完整依赖构建：

```bash
REQUIREMENTS_FILE=requirements.txt docker compose up -d --build
```

- 国内服务器默认使用阿里云 apt / pip 源；如需切回官方源：

```bash
USE_CHINA_APT_MIRROR=false \
PIP_INDEX_URL=https://pypi.org/simple \
docker compose build --no-cache
```

- RAG 首次使用可能下载 embedding 模型，服务器需要能访问模型源，或提前挂载缓存。
- 公众号草稿箱发布依赖 Node.js 和 kuaifa CLI，当前 Dockerfile 未内置；如需在容器内发布公众号，可后续扩展镜像。

### 9. 传统 CLI 运行方式

```bash
# 默认演示
python main.py

# 从文件生成三平台内容
python main.py -i notes/my_note.md

# ReAct Agent 模式
python main.py --react --note-file ~/notes/mcp.md --platforms gongzhonghao,xiaohongshu,douyin
```

### 10. 传统 Web UI（可选）

项目仍保留较完整的 Gradio 管理界面：

```bash
python web_ui.py
```

打开：

```text
http://127.0.0.1:7860
```

`web_ui.py` 更偏配置、历史、任务、日历等管理能力；`chat_ui.py` 更适合日常“上传笔记/输入主题 -> 生成 -> 发草稿箱”的轻量工作流。

---

## 详细文档

- [CLI 使用手册](docs/phase5_cli_usage.md) — 完整命令参考
- [架构设计](docs/phase5_architecture_decisions.md) — 技术架构决策
- [系统流程](docs/phase5_flow.md) — Agent 流程和模块关系
- [Eval + RAG 设计](docs/phase5_eval_and_rag_design.md) — RAG 与质量评估方案
- [实现笔记](notes/) — 开发过程记录

---

## 核心功能

| 功能 | 状态 |
|------|------|
| 三平台内容生成 | ✅ |
| 小红书/抖音配图 | ✅ |
| 聊天式生成 UI | ✅ |
| 上传 `.md` / `.txt` 笔记生成 | ✅ |
| 公众号技术深度 / 通俗科普模式 | ✅ |
| 生成过程可视化 | ✅ |
| 审核面板与按建议修改 | ✅ |
| 历史任务 task 继续改写 | ✅ |
| 公众号发布前核对 | ✅ |
| 公众号最终稿归档 | ✅ |
| 热点监控 & 自动选题 | ✅ |
| 公众号自动发布 | ✅（需安装 kuaifa CLI）|
| ReAct Agent | ✅ |
| 智能排期 | ✅ |
| 数据回流 & 风格画像 | ✅ |
| RAG 本地笔记检索 | ✅ |

---

## 常见问题

### 1. 启动 `chat_ui.py` 后端口被占用怎么办？

默认端口是 `7861`。如果被占用，可以临时换端口：

```bash
GRADIO_SERVER_PORT=7862 python chat_ui.py
```

### 2. 生成内容时提示缺少 API Key？

检查 `.env` 是否存在，以及 `MODEL_PROVIDER` 对应的 API Key 是否已填写。例如：

```env
MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx
```

### 3. 上传笔记支持哪些格式？

当前聊天页支持 `.md` 和 `.txt`。PDF、Word 后续可以扩展，但目前建议先导出为 Markdown 或纯文本。

### 4. 公众号发布失败怎么办？

先确认：

- 已安装 Node.js
- 已安装 `kuaifa`: `npm install -g kuaifa`
- 已执行 `kuaifa config`
- 上传了公众号封面图
- 已勾选发布前核对确认
- `.env` 或 kuaifa 配置中的微信 AppID/AppSecret/API Key 正确

### 5. 如何让文章更通俗？

在输入里明确写：

```text
面向普通人，通俗易懂，少用术语，不要太技术
```

系统会自动切到“公众号通俗科普模式”。

### 6. 如何让文章更专业？

在输入里明确写：

```text
面向技术从业者，专业严谨，保留技术细节和代码示例
```

这会走默认公众号专业长文模式。

### 7. 如何基于之前生成的文章继续修改？

在历史任务中找到对应的 `task`，然后在输入框里写：

```text
修改 task chat_YYYYMMDD_HHMMSS，把开头写得更抓人
```

如果这篇文章已经保存到公众号草稿箱，历史任务会标记“最终稿”，也可以写：

```text
基于最终稿 task chat_YYYYMMDD_HHMMSS 继续改写
```

---

## License

MIT
