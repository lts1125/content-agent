# Content Agent CLI 工具化改造笔记

## 背景

前面已经跑通了核心 Agent，能够输出结构化的三平台文案。但那个版本是一个硬编码的脚本，笔记写在代码里面，每次改内容都要改代码，不能用。

本次改造目标：把它从“脚本”变成“CLI 工具”，支持从文件读取、命令行参数、自动生成配图。

---

## 需求分析

理想的使用流程是：

```bash
# 写完学习笔记
vim notes/Agent-Day2.md

# 一行命令，生成全套发布素材
python main.py -i notes/Agent-Day2.md -o ./posts/2025-05-15/

# 去 output 目录拿文案 + 截图配图，直接发
```

需要支持的功能：
1. 从 `.md` 或 `.txt` 文件读取笔记
2. 支持 `--output` 指定输出目录
3. 支持 `--platforms` 选择平台（默认全部）
4. 自动生成小红书 HTML 配图卡片
5. 保存为标准的 markdown 文件
6. 错误处理：文件不存在、API 失败、格式解析失败

---

## 代码结构重构

之前所有代码都在 `main.py` 里，现在拆分成模块化结构：

```
content-agent/
├── main.py                  # CLI 入口，参数解析、调度
├── content_agent/           # 核心包
│   ├── __init__.py
│   ├── agent_core.py          # Agent 调用封装
│   └── html_renderer.py       # 小红书配图生成
├── notes/                   # 输入笔记
│   └── ai_invades_daily.md
└── output/                  # 输出目录
    ├── *.md                   # 三平台文案
    └── 配图/
        └── xiaohongshu_cards.html
```

---

## 步骤1：拆分 Agent 核心逻辑（agent_core.py）

把之前 `main.py` 里的 Agent 初始化、system prompt、结构化输出类定义抽出来：

```python
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.deepseek import DeepSeekProvider

class MultiPlatformContent(BaseModel):
    xiaohongshu: str
    gongzhonghao: str
    douyin: str

class ContentAgent:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = OpenAIChatModel(
            "deepseek-chat",
            provider=DeepSeekProvider(api_key=self.api_key),
        )
        self.agent = Agent(
            self.model,
            system_prompt=SYSTEM_PROMPT,
            output_type=MultiPlatformContent,
        )

    def run(self, raw_notes: str) -> MultiPlatformContent:
        result = self.agent.run_sync(raw_notes)
        return result.output
```

**关键点：**
- `SYSTEM_PROMPT` 保持之前调试好的版本，没改
- `MultiPlatformContent` 用 Pydantic Model 约束输出结构，确保三个字段都有值
- `ContentAgent` 类封装了所有与 LLM 交互的细节

---

## 步骤2：实现配图生成（html_renderer.py）

这是本次改造的亮点。之前配图是手动写 HTML，现在集成到代码里，自动根据文案内容生成卡片。

### 设计思路

小红书图文笔记通常需要 5-7 张卡片：
1. 封面：大标题 + 引人注目的视觉
2. 内容卡片 1-2 张：要点列表
3. 金句卡片：黑底白字，适合收藏
4. 互动卡片：引导评论区留言

每张卡片是 900x1200 像素（3:4 比例），用 CSS 模拟手机屏幕风格。

### 核心代码结构

```python
class XiaohongshuRenderer:
    def render(self, content: str, output_dir: Path) -> str:
        # 1. 从文案中提取标题
        title = _extract_title(content)
        
        # 2. 从文案中提取要点
        points = _extract_key_points(content, max_points=6)
        
        # 3. 生成各种卡片
        cards = []
        cards.append(_build_cover_card(title))
        cards.append(_build_content_card(1, "核心要点", points[:3]))
        cards.append(_build_content_card(2, "详细内容", points[3:]))
        cards.append(_build_quote_card("..."))
        cards.append(_build_cta_card())
        
        # 4. 组装成 HTML 文件
        html = XIAOHONGSHU_TEMPLATE.replace("{CARDS}", "\n".join(cards))
        
        # 5. 保存
        with open(output_dir / "xiaohongshu_cards.html", "w") as f:
            f.write(html)
```

### 内容提取逻辑

从文案中自动提取要点的关键是识别列表项：

```python
def _extract_key_points(text: str, max_points: int = 4) -> List[str]:
    lines = text.strip().split("\n")
    points = []
    for line in lines:
        line = line.strip()
        # 匹配各种列表符号
        if line.startswith(("-", "*", "•", "1.", "①", "②")):
            clean = line.lstrip("- *•1.①②").strip()
            if clean and len(clean) > 5:
                points.append(clean)
        if len(points) >= max_points:
            break
    return points
```

**踩坑：**
- 小红书文案里有很多 emoji 和换行，提取时需要清理掉格式符号
- 标题通常在文案第一行，但可能带有 `#` 或 emoji，需要过滤

---

## 步骤3：实现 CLI 入口（main.py）

用 `argparse` 实现命令行参数：

```python
import argparse

def main():
    parser = argparse.ArgumentParser(description="Content Agent - AI 内容改写工具")
    parser.add_argument("--input", "-i", help="输入的笔记文件路径 (.md 或 .txt)")
    parser.add_argument("--output", "-o", default="output", help="输出目录")
    parser.add_argument("--platforms", "-p", default="all", 
                       help="平台选择，用逗号分隔（默认: all）")
    args = parser.parse_args()
```

### 关键逻辑流程

1. **读取输入**
   - 如果传了 `-i`，读取文件内容
   - 如果没传，使用内置的 `DEFAULT_NOTES` 作为演示

2. **解析平台选项**
   - `all` → 生成三个平台
   - `xiaohongshu,gongzhonghao` → 只生成指定平台
   - 无效平台 → 报错退出

3. **调用 Agent**
   - 初始化 `ContentAgent`
   - 如果 API Key 不存在，提前报错

4. **保存输出**
   - 文案保存为 `YYYYmmdd_HHMMSS_{platform}.md`
   - 配图保存到 `output/配图/xiaohongshu_cards.html`

5. **预览**
   - 终端打印每个平台的前 300 字预览

### 错误处理

覆盖了以下场景：

```python
try:
    agent = ContentAgent()
except ValueError as e:
    print(f"❌ 配置错误: {e}")
    sys.exit(1)

try:
    result = agent.run(raw_notes)
except Exception as e:
    print(f"❌ Agent 调用失败: {e}")
    sys.exit(1)
```

---

## 踩坑记录

### 坑1：虚拟环境激活状态下检查全局 pip

本机检查时发现，激活了 content-agent 的 venv 后，`pip3 list` 和 `python3 -m pip list` 都指向了虚拟环境，而不是系统级的 pip。

**解决**：需要用 `deactivate` 退出 venv 后再检查全局环境，或者直接检查 venv 里的就够了。

### 坑2：HTML 配图的中文字体

生成的 HTML 卡片用的是系统字体栈（`PingFang SC` 等），在不同机器上打开可能样式不一致。

**解决**：使用标准的系统字体栈，不强制依赖某个特定字体：
```css
font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", 
             "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
```

### 坑3：内容提取的鲁棒性

当前的 `_extract_key_points` 只是简单的正则匹配，如果文案格式不规范（比如没有列表符号），提取出来的要点会很少。

**待优化**：后续可以用 LLM 再做一次摘要，或者用正则匹配更多种格式。

---

## 使用方法

### 基本用法

```bash
# 进入项目目录
cd ~/content-agent
source .venv/bin/activate

# 使用默认笔记演示
python main.py

# 从文件读取
python main.py -i notes/ai_invades_daily.md

# 指定输出目录
python main.py -i notes/ai_invades_daily.md -o ./posts/2025-05-15/

# 只生成小红书
python main.py -i notes/ai_invades_daily.md -p xiaohongshu
```

### 输出结果

```
output/
├── 20260515_085706_xiaohongshu.md      # 小红书文案
├── 20260515_085706_gongzhonghao.md     # 公众号文案
├── 20260515_085706_douyin.md           # 抖音脚本
└── 配图/
    └── xiaohongshu_cards.html             # 配图卡片，浏览器打开截图
```

---

## 下一步计划

1. **支持 URL 输入**
   - `python main.py -u https://example.com/article`
   - 自动抓取网页内容再改写

2. **更多配图模板**
   - 支持公众号配图（横幅海报风格）
   - 支持知乎配图

3. **接入 MCP 协议**
   - 让 Agent 在改写时自动搜索补充资料
   - 丰富内容深度

4. **批量处理**
   - `python main.py -i notes/*.md` 批量处理多篇笔记

---

## 总结

这次改造的核心是**模块化 + 自动化**。

把之前一个大脚本拆分成了三个模块：
- `agent_core.py` 负责与 LLM 交互
- `html_renderer.py` 负责视觉输出
- `main.py` 负责用户交互

最后用 CLI 封装起来，让整个流程变成一行命令。
