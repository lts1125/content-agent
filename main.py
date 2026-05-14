import os
from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.deepseek import DeepSeekProvider
import datetime

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    raise ValueError("请先设置 DEEPSEEK_API_KEY 环境变量，或创建 .env 文件")

# 使用 DeepSeek 内置 Provider
model = OpenAIChatModel("deepseek-chat", provider=DeepSeekProvider(api_key=api_key))

# 结构化输出：三平台文案
class MultiPlatformContent(BaseModel):
    xiaohongshu: str
    """小红书笔记：emoji多、段落短、要点化、语气轻松，适合手机阅读"""
    
    gongzhonghao: str
    """公众号文章：深度长文、结构完整、有代码块和技术细节，适合桌面阅读"""
    
    douyin: str
    """抖音口播脚本：开头有钩子、短句、口语化、带画面提示，适合视频拍摄"""

system_prompt = """你是一位全平台内容专家，擅长把技术学习笔记同时改写成三种风格的文案。

输入是程序员的学习笔记，输出必须包含三个平台的文案，分别符合以下要求：

【小红书笔记】
- 标题吸睛，带emoji和数字
- 开头一句话点出动机（例如"程序员想做副业，AI Agent 是个好方向"）
- 正文分步骤，每步带emoji编号，每步简洁明了
- 保留核心概念和踩坑记录，但大白话解释
- 结尾金句总结 + 互动问句
- 添加3-5个话题标签（#xxx 格式）
- 全文300-600字

【公众号文章】
- 标题正式，可带副标题
- 开头用导言引入，讲背景和动机
- 正文分大章节，用## 标题分隔
- 每个步骤详细展开：有原理解释、代码示例、实际场景
- 包含具体的命令行代码块（```bash格式）
- 有"总结"和"下一步"部分
- 全文1500-2500字，信息密度高

【抖音口播脚本】
- 开头前3秒必须有强钩子（"停！"“十个程序员里九个都不知道"“别再花错钱学技术了"）
- 每句话不超过15个字，短句排比
- 口语化，用"我"“你"“大家"等称呼
- 带画面提示（【镜头切到代码】【切换到页面】【配个表情包】）
- 中间有转折或悬念，尾部有行动号召
- 全文控制在200-400字，适合2-3分钟口播

核心原则：三个平台都必须基于同一份学习笔记，不编造内容，不流于表面，读者看完能复现学习路径。"""

agent = Agent(model, system_prompt=system_prompt, output_type=MultiPlatformContent)

def save_to_markdown(platform: str, content: str, output_dir: str = "output") -> str:
    """将生成的文案保存为 markdown 文件"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{output_dir}/{timestamp}_{platform}.md"
    
    md_content = f"""---
title: {platform}文案
date: {datetime.datetime.now().isoformat()}
source: Agent学习笔记Day1
platform: {platform}
---

{content}
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(md_content)
    return filename

if __name__ == "__main__":
    # 今天的学习笔记：Agent 开发第一天 —— 从 0 到第一个跑通的 Agent
    raw_notes = """
背景：下班后决定学 AI Agent 开发，想做一个内容改写 Agent 做副业。

今天学习核心步骤：

步骤1 理解 Agent 本质
Agent 不是什么高深的东西，它就是 LLM + 工具调用 + 循环。比如我让 Agent 写小红书文案，它需要先"思考"原文重点，然后"执行"改写，如果结果不满意还得"反思"再改。这就是 ReAct 模式（Reasoning + Acting）。

步骤2 选框架
不要一上来就碰 LangChain，太重了。我对比了几个：
- LangChain：功能全但隱形成本高，适合复杂企业项目
- PydanticAI：类型安全、轻量、对 Rust/后端开发者友好
- OpenAI Agents SDK：简单但捆绑 OpenAI
最后选了 PydanticAI，因为我喜欢它用 Pydantic Model 定义 result_type 的方式，跟写 Rust struct 一样舒服。

步骤3 搭环境
- 新建项目目录，用 python3 -m venv .venv 创建虚拟环境
- pip install pydantic-ai 安装（注意：它的依赖很多，等了很久）
- 装 python-dotenv 管理 API Key
- 用 .env 文件存放 DEEPSEEK_API_KEY

步骤4 第一个 Agent 代码
核心就三行：
1. 定义 model（用 DeepSeekProvider + OpenAIChatModel）
2. 写 system_prompt（告诉 Agent 它是谁、要做什么）
3. agent.run_sync(用户输入) 得结果
重点：system_prompt 是 Agent 的"灵魂"，写得好坏直接决定输出质量。

步骤5 踩坑记录
- 坑1：PydanticAI 0.8 的 API 和文档不一致，OpenAIModel 改名为 OpenAIChatModel，且不支持直接传 base_url，需要用 Provider 包装
- 坑2：结果字段是 result.output 不是 result.data，看源码才发现
- 坑3：Kimi Code 的 API 有 User-Agent 白名单限制，非官方客户端调不了，最后切换到 DeepSeek 才跑通

步骤6 下一步计划
- 加多平台输出（公众号/抖音/小红书三版）
- 用 Pydantic Model 定义结构化输出
- 接入 MCP 工具协议，让 Agent 能自动搜索补充资料
"""

    print("=" * 50)
    print("原文笔记已输入，Agent 正在生成三平台文案...")
    print("=" * 50)

    result = agent.run_sync(raw_notes)
    content = result.output
    
    # 分别保存三个平台
    files = []
    files.append(save_to_markdown("xiaohongshu", content.xiaohongshu))
    files.append(save_to_markdown("gongzhonghao", content.gongzhonghao))
    files.append(save_to_markdown("douyin", content.douyin))
    
    print(f"\n✅ 全部保存成功！共生成 {len(files)} 个文件：")
    for f in files:
        print(f"   • {f}")
    
    print(f"\n--- 小红书预览 ---\n{content.xiaohongshu[:300]}...")
    print(f"\n--- 公众号预览 ---\n{content.gongzhonghao[:300]}...")
    print(f"\n--- 抖音预览 ---\n{content.douyin[:300]}...")
