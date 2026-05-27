# Content Agent —— AI 多平台内容改写助手

基于 **PydanticAI** 的轻量 Agent，输入你的技术学习笔记，一键生成 **小红书 / 微信公众号 / 抖音** 三平台文案，并自动生成配图。

> 本项目是作者学习 AI Agent 开发的实战项目，从单文件脚本逐步重构为模块化 CLI 工具。

---

## 效果预览

输入一段技术学习笔记，Agent 自动输出：

| 平台 | 风格 | 字数 | 配图 | 标签 |
|------|------|------|------|------|
| 小红书 | emoji 要点化、轻松口语 | 300-600 | ✅ HTML 卡片 | ✅ 自动推荐 |
| 公众号 | 深度长文、代码块、章节完整 | 1500-2500 | ❌ | ✅ |
| 抖音 | 口播脚本、热点资讯 | 200-400 | ✅ HTML 卡片 | ✅ |

---

## 技术栈

- **Agent 框架**: [PydanticAI](https://github.com/pydantic/pydantic-ai)
- **LLM**: 多 Provider 支持（DeepSeek / Kimi / MiniMax / OpenAI）
- **Web UI**: Gradio
- **输出**: Markdown + HTML 配图卡片
- **语言**: Python 3.9+

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/YOUR_NAME/content-agent.git
cd content-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

### 3. 配置公众号发布（可选）

如需使用公众号草稿箱发布功能，需安装 kuaifa CLI：

```bash
# 安装 kuaifa（需 Node.js 环境）
npm install -g kuaifa

# 配置 kuaifa（按提示输入微信公众号 AppID、AppSecret、API Key）
kuaifa config
```

安装完成后，在 Web UI 的「配置」Tab 中验证 kuaifa 状态。

### 4. 运行

```bash
# 默认演示
python main.py

# 从文件生成三平台内容
python main.py -i notes/my_note.md

# ReAct Agent 模式
python main.py --react --note-file ~/notes/mcp.md --platforms gongzhonghao,xiaohongshu,douyin
```

---

## 详细文档

- [CLI 使用手册](docs/cli_usage.md) — 完整命令参考
- [ReAct Agent 使用说明](docs/react_cli_usage.md) — ReAct 模式详解
- [架构设计](docs/architecture_decisions.md) — 技术架构决策
- [实现笔记](notes/) — 开发过程记录

---

## 核心功能

| 功能 | 状态 |
|------|------|
| 三平台内容生成 | ✅ |
| 小红书/抖音配图 | ✅ |
| 热点监控 & 自动选题 | ✅ |
| 公众号自动发布 | ✅（需安装 kuaifa CLI）|
| ReAct Agent | ✅ |
| 智能排期 | ✅ |
| 数据回流 & 风格画像 | ✅ |

---

## License

MIT
