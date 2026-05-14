# Content Agent —— AI 多平台内容改写助手

基于 **PydanticAI** 的轻量 Agent，输入你的技术学习笔记，一键生成 **小红书 / 微信公众号 / 抖音** 三平台文案。

> 本项目是作者学习 AI Agent 开发的第一个实战项目，从 0 到可运行仅用了一个晚上。

---

## 效果预览

输入一段技术学习笔记（如 PydanticAI 入门过程），Agent 自动输出：

| 平台 | 风格 | 字数 |
|------|------|------|
| 小红书 | emoji 要点化、轻松口语 | 300-600 |
| 公众号 | 深度长文、代码块、章节完整 | 1500-2500 |
| 抖音 | 口播脚本、开头钩子、画面提示 | 200-400 |

---

## 技术栈

- **Agent 框架**: [PydanticAI](https://github.com/pydantic/pydantic-ai) —— 类型安全、轻量、对后端开发者友好
- **LLM**: DeepSeek (via OpenAI 兼容 API)
- **语言**: Python 3.9+
- **输出**: Markdown 文件，带 YAML Frontmatter

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

编辑 `.env`，填入你的 DeepSeek API Key：

```
DEEPSEEK_API_KEY=sk-your-key-here
```

> 获取方式：注册 [DeepSeek 开放平台](https://platform.deepseek.com/)，创建 API Key。

### 4. 运行

```bash
python main.py
```

程序会在 `output/` 目录下生成三个 Markdown 文件：

```
output/
  20250514_143052_xiaohongshu.md
  20250514_143052_gongzhonghao.md
  20250514_143052_douyin.md
```

---

## 项目结构

```
.
├── main.py              # 主程序：定义 Agent、调用模型、保存文件
├── .env                 # API Key 配置文件（gitignore）
├── .env.example         # 配置模板
├── .gitignore
├── README.md
└── output/              # 生成的文案存放目录
```

---

## 自定义你的笔记

打开 `main.py`，找到 `raw_notes` 变量，替换为你自己的学习笔记：

```python
raw_notes = """
背景：下班后决定学 AI Agent 开发，想做副业。

今天学习核心步骤：
步骤1 ...
步骤2 ...
"""
```

保存后再次运行 `python main.py` 即可。

---

## 踩坑记录（真实）

1. **PydanticAI 0.8 API 变动大**：`OpenAIModel` 改名为 `OpenAIChatModel`，`base_url` 不能直传，需用 Provider 包装
2. **结果字段名变化**：`result.data` → `result.output`
3. **Kimi Code API 限制**：有 User-Agent 白名单，非官方客户端（如本脚本）无法调用，最终切换到 DeepSeek
4. **结构化输出参数名**：PydanticAI 使用 `output_type` 而非 `result_type`

---

## Roadmap

- [x] 小红书单平台输出
- [x] 三平台同时输出（小红书 / 公众号 / 抖音）
- [x] 自动保存为 Markdown
- [ ] 从文件读取笔记（支持 `.md` / `.txt`）
- [ ] 接入 MCP 工具协议，自动搜索补充资料
- [ ] Web UI 或 CLI 交互界面
- [ ] 支持更多模型（OpenAI、Claude、本地 Ollama）

---

## 为什么做这个项目

作者是一名后端工程师（Rust / AI Gateway 方向），想在下班后探索 AI Agent 开发作为副业方向。本项目既是学习笔记，也是第一个落地的 Agent 应用。

如果你也在学 Agent 开发，欢迎交流。

---

## License

MIT
