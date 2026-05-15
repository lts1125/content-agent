#!/usr/bin/env python3
"""
Content Agent - AI 内容改写工具

一键将技术学习笔记改写为小红书/公众号/抖音三平台文案，
并自动生成小红书配图。

用法:
    python main.py                              # 使用默认笔记演示
    python main.py -i notes.md                  # 从文件读取笔记
    python main.py -i notes.md -o ./dist        # 指定输出目录
    python main.py -i notes.md -p xiaohongshu   # 只生成小红书
"""

import argparse
import datetime
import os
import sys
from pathlib import Path

from content_agent.agent_core import ContentAgent
from content_agent.html_renderer import XiaohongshuRenderer


DEFAULT_NOTES = """背景：下班后决定学 AI Agent 开发，想做一个内容改写 Agent 做副业。

今天学习核心步骤：

步骤1 理解 Agent 本质
Agent 不是什么高深的东西，它就是 LLM + 工具调用 + 循环。
比如我让 Agent 写小红书文案，它需要先"思考"原文重点，然后"执行"改写，如果结果不满意还得"反思"再改。这就是 ReAct 模式（Reasoning + Acting）。

步骤2 选框架
不要一上来就碰 LangChain，太重了。我对比了几个：
- LangChain：功能全但隐性成本高，适合复杂企业项目
- PydanticAI：类型安全、轻量、对 Rust/后端开发者友好
- OpenAI Agents SDK：简单但捆绑 OpenAI
最后选了 PydanticAI，因为我喜欢它用 Pydantic Model 定义 result_type 的方式。

步骤3 搭环境
- 新建项目目录，用 python3 -m venv .venv 创建虚拟环境
- pip install pydantic-ai 安装
- 装 python-dotenv 管理 API Key
- 用 .env 文件存放 DEEPSEEK_API_KEY

步骤4 第一个 Agent 代码
核心就三行：
1. 定义 model（用 DeepSeekProvider + OpenAIChatModel）
2. 写 system_prompt
3. agent.run_sync(用户输入) 得结果
重点：system_prompt 是 Agent 的"灵魂"。

步骤5 踩坑记录
- 坑1：PydanticAI 0.8 API 和文档不一致，OpenAIModel 改名为 OpenAIChatModel
- 坑2：结果字段是 result.output 不是 result.data
- 坑3：Kimi Code API 有 User-Agent 白名单限制，最后切换到 DeepSeek

步骤6 下一步计划
- 加多平台输出
- 用 Pydantic Model 定义结构化输出
- 接入 MCP 工具协议
"""


def save_markdown(platform: str, content: str, output_dir: Path) -> str:
    """保存文案为 markdown 文件"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = output_dir / f"{timestamp}_{platform}.md"

    md_content = f"""---
title: {platform}文案
date: {datetime.datetime.now().isoformat()}
source: 学习笔记
platform: {platform}
---

{content}
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(md_content)
    return str(filename)


def _get_date_subdir(base_dir: Path) -> Path:
    """生成日期子目录，格式: output/YYYYMMDD/"""
    today = datetime.datetime.now().strftime("%Y%m%d")
    date_dir = base_dir / today
    date_dir.mkdir(parents=True, exist_ok=True)
    return date_dir


def main():
    parser = argparse.ArgumentParser(
        description="Content Agent - AI 内容改写工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                              使用默认笔记演示
  python main.py -i notes.md                  从文件读取笔记
  python main.py -i notes.md -o ./dist        指定输出目录
  python main.py -i notes.md -p xiaohongshu   只生成小红书
        """,
    )
    parser.add_argument(
        "--input", "-i",
        help="输入的笔记文件路径 (.md 或 .txt)"
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="输出目录 (默认: output)"
    )
    parser.add_argument(
        "--platforms", "-p",
        default="all",
        help="平台选择，用逗号分隔，默认 all (选项: xiaohongshu,gongzhonghao,douyin)"
    )
    parser.add_argument(
        "--clean", "-c",
        action="store_true",
        help="清理同一天的旧文件后再生成（默认保留历史文件）"
    )

    args = parser.parse_args()

    # 1. 读取输入
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"❌ 错误: 输入文件不存在: {args.input}")
            sys.exit(1)
        with open(input_path, "r", encoding="utf-8") as f:
            raw_notes = f.read()
        print(f"📄 已读取输入: {args.input} ({len(raw_notes)} 字)")
    else:
        raw_notes = DEFAULT_NOTES
        print("📄 未指定输入文件，使用默认笔记")

    # 2. 解析平台选项
    platform_arg = args.platforms.lower().strip()
    if platform_arg == "all":
        enabled_platforms = {"xiaohongshu", "gongzhonghao", "douyin"}
    else:
        enabled_platforms = {p.strip() for p in platform_arg.split(",")}
        valid = {"xiaohongshu", "gongzhonghao", "douyin"}
        invalid = enabled_platforms - valid
        if invalid:
            print(f"❌ 错误: 无效平台: {', '.join(invalid)}")
            print(f"   有效选项: {', '.join(valid)}")
            sys.exit(1)

    # 3. 初始化 Agent
    try:
        agent = ContentAgent()
    except ValueError as e:
        print(f"❌ 配置错误: {e}")
        sys.exit(1)

    # 4. 生成内容
    print("\n" + "=" * 50)
    print("🤖 Agent 正在生成三平台文案...")
    print("=" * 50)

    try:
        result = agent.run(raw_notes)
    except Exception as e:
        print(f"❌ Agent 调用失败: {e}")
        sys.exit(1)

    # 5. 保存文案（按日期子目录）
    base_output_dir = Path(args.output)
    output_dir = _get_date_subdir(base_output_dir)

    # 如果传了 --clean，清理同一天的旧文件
    if args.clean and output_dir.exists():
        import shutil
        cleaned = 0
        for item in output_dir.iterdir():
            if item.is_file():
                item.unlink()
                cleaned += 1
            elif item.is_dir() and item.name == "配图":
                shutil.rmtree(item)
                cleaned += 1
        if cleaned > 0:
            print(f"\n🚿 已清理 {cleaned} 个旧文件/目录")

    saved_files = []
    if "xiaohongshu" in enabled_platforms:
        f = save_markdown("xiaohongshu", result.xiaohongshu, output_dir)
        saved_files.append(f)
    if "gongzhonghao" in enabled_platforms:
        f = save_markdown("gongzhonghao", result.gongzhonghao, output_dir)
        saved_files.append(f)
    if "douyin" in enabled_platforms:
        f = save_markdown("douyin", result.douyin, output_dir)
        saved_files.append(f)

    print(f"\n✅ 文案保存成功！共 {len(saved_files)} 个文件:")
    for f in saved_files:
        print(f"   • {f}")

    # 6. 生成小红书配图（保存到日期子目录下的配图文件夹）
    if "xiaohongshu" in enabled_platforms:
        print("\n🎨 正在生成小红书配图...")
        try:
            renderer = XiaohongshuRenderer()
            html_path = renderer.render(result.xiaohongshu, output_dir / "配图")
            print(f"   ✅ 配图已生成: {html_path}")
            print(f"   💡 提示: 用浏览器打开该 HTML 文件，逐张截图即可发小红书")
        except Exception as e:
            print(f"   ⚠️ 配图生成失败: {e}")

    # 7. 预览
    print("\n" + "-" * 50)
    if "xiaohongshu" in enabled_platforms:
        print(f"\n📱 小红书预览:")
        print(result.xiaohongshu[:300] + "...")
    if "gongzhonghao" in enabled_platforms:
        print(f"\n💬 公众号预览:")
        print(result.gongzhonghao[:300] + "...")
    if "douyin" in enabled_platforms:
        print(f"\n🎵 抖音预览:")
        print(result.douyin[:300] + "...")

    print(f"\n🎉 全部完成！输出目录: {output_dir.absolute()}")


if __name__ == "__main__":
    main()
