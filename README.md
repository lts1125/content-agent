# Content Agent —— AI 多平台内容改写助手

基于 **PydanticAI** 的轻量 Agent，输入你的技术学习笔记，一键生成 **小红书 / 微信公众号 / 抖音** 三平台文案，并自动生成小红书风格配图。

> 本项目是作者学习 AI Agent 开发的实战项目，从单文件脚本逐步重构为模块化 CLI 工具。

---

## 效果预览

输入一段技术学习笔记，Agent 自动输出：

| 平台 | 风格 | 字数 | 配图 |
|------|------|------|------|
| 小红书 | emoji 要点化、轻松口语 | 300-600 | ✅ 自动生成 HTML 卡片 |
| 公众号 | 深度长文、代码块、章节完整 | 1500-2500 | ❌ |
| 抖音 | 口播脚本、开头钩子、画面提示 | 200-400 | ❌ |

---

## 技术栈

- **Agent 框架**: [PydanticAI](https://github.com/pydantic/pydantic-ai) —— 类型安全、轻量、对后端开发者友好
- **LLM**: 多 Provider 支持（DeepSeek / Kimi / MiniMax / OpenAI / 自定义）
- **语言**: Python 3.9+
- **输出**: Markdown + HTML 配图卡片

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
pip install pydantic-ai python-dotenv
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

**完整 CLI 参数：**

```
-i, --input     输入的笔记文件路径 (.md 或 .txt)
-o, --output    输出目录 (默认: output)
-p, --platforms 平台选择，逗号分隔 (默认: all，可选: xiaohongshu,gongzhonghao,douyin)
-c, --clean     清理同一天的旧文件后再生成
```

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

## 项目结构

```
.
├── main.py                      # CLI 入口：参数解析、调用 Agent、保存文件
├── content_agent/
│   ├── __init__.py
│   ├── agent_core.py            # Agent 核心：多 Provider 模型配置 + 系统提示词
│   └── html_renderer.py         # 小红书 HTML 配图卡片渲染
├── notes/                       # 存放输入笔记（示例）
├── .env                         # API Key 配置文件（gitignore）
├── .env.example                 # 多 Provider 配置模板
├── .gitignore
├── README.md
└── output/                      # 生成的文案存放目录（按日期子目录）
```

---

## 自定义你的笔记

将学习笔记保存为 `.md` 或 `.txt` 文件，放入 `notes/` 目录，然后运行：

```bash
python main.py -i notes/你的笔记.md
```

笔记格式没有严格要求，纯文本即可，Agent 会自动提取重点并改写。

---

## 踩坑记录（真实）

1. **PydanticAI 0.8 API 变动大**：`OpenAIModel` 改名为 `OpenAIChatModel`，`base_url` 不能直传，需用 Provider 包装
2. **结果字段名变化**：`result.data` → `result.output`
3. **Kimi Code API 限制**：有 User-Agent 白名单，非官方客户端（如本脚本）无法调用。Kimi Code key 只能用于 Kimi CLI、Claude Code 等特定工具。如需在本项目中使用 Kimi，需另外申请 Moonshot 开放平台的 API key
4. **结构化输出参数名**：PydanticAI 使用 `output_type` 而非 `result_type`

---

## Roadmap

- [x] 小红书单平台输出
- [x] 三平台同时输出（小红书 / 公众号 / 抖音）
- [x] 自动保存为 Markdown
- [x] 从文件读取笔记（支持 `.md` / `.txt`）
- [x] 支持多模型 Provider（DeepSeek / Kimi / MiniMax / OpenAI / 自定义）
- [x] CLI 参数交互（选择平台、指定输入输出）
- [x] 自动生成小红书 HTML 配图卡片
- [ ] 接入 MCP 工具协议，自动搜索补充资料
- [ ] Web UI

---

## 为什么做这个项目

作者是一名后端工程师（Rust / AI Gateway 方向），想在下班后探索 AI Agent 开发作为副业方向。本项目既是学习笔记，也是第一个落地的 Agent 应用。

如果你也在学 Agent 开发，欢迎交流。

---

## License

MIT
