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
from typing import List

from content_agent.agent_core import ContentAgent
from content_agent.html_renderer import XiaohongshuRenderer
from content_agent.quality_checker import QualityChecker
from content_agent.research import research_notes, extract_keywords_with_llm


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


def _collect_notes(input_path: Path) -> List[Path]:
    """
    收集笔记文件。
    如果是文件，直接返回。
    如果是目录，遍历所有 .md 和 .txt 文件。
    """
    if input_path.is_file():
        return [input_path]

    notes = []
    for ext in ("*.md", "*.txt"):
        notes.extend(input_path.glob(ext))
        notes.extend(input_path.rglob(ext))  # 递归子目录

    # 去重并排序
    seen = set()
    unique = []
    for p in sorted(notes):
        if str(p) not in seen:
            seen.add(str(p))
            unique.append(p)
    return unique


def process_single_note(
    note_path: Path,
    raw_notes: str,
    agent: ContentAgent,
    checker: QualityChecker,
    enabled_platforms: set,
    args,
    note_output_dir: Path,
) -> dict:
    """
    处理单个笔记，返回处理结果

    Returns:
        {"success": bool, "saved_files": list, "error": str|None}
    """
    note_name = note_path.stem
    result = {"success": False, "saved_files": [], "error": None}

    print(f"\n{'=' * 60}")
    print(f"📄 处理: {note_name} ({len(raw_notes)} 字)")
    print(f"{'=' * 60}")

    current_notes = raw_notes

    # 搜索增强（可选）
    if args.research:
        try:
            from pydantic_ai import Agent
            keyword_agent = Agent(
                agent.model,
                system_prompt="你是一个关键词提取助手，从技术笔记中提取精准的搜索关键词。"
            )
            keywords = extract_keywords_with_llm(raw_notes, keyword_agent)
            print(f"   💡 LLM 提取关键词: {keywords}")
        except Exception as e:
            print(f"   ⚠️ LLM 提取失败，使用启发式: {e}")
            keywords = None

        current_notes = research_notes(
            current_notes,
            search_engine=args.search_engine,
            max_results=3,
            verbose=True,
            keywords=keywords,
        )

    # 敏感词预检
    try:
        from content_agent.sensitive_checker import SensitiveChecker
        sc = SensitiveChecker()
        check_res = sc.check(raw_notes)
        if check_res["has_sensitive"]:
            hits = [h["word"] for h in check_res["hits"][:5]]
            print(f"   ⚠️ 敏感词预检: 检测到 {check_res['local_count']} 个敏感/违规词: {', '.join(hits)}")
            if len(check_res["hits"]) > 5:
                print(f"      等共 {len(check_res['hits'])} 个")
    except Exception:
        pass

    # 生成内容 + 质量检查 + 重试
    generation_result = None
    for attempt in range(1, 4):
        print(f"\n   🤖 第 {attempt} 次生成三平台文案...")

        try:
            generation_result = agent.run(current_notes)
        except Exception as e:
            result["error"] = f"Agent 调用失败: {e}"
            print(f"   ❌ {result['error']}")
            return result

        check = checker.check(
            generation_result.xiaohongshu,
            generation_result.gongzhonghao,
            generation_result.douyin,
            attempt=attempt,
        )

        print(f"   📊 质量检查: 综合 {check.overall_score}/100")

        if check.passed:
            print(f"   ✅ 通过，共 {attempt} 次")
            break

        if attempt < 3:
            print(f"   🔄 即将第 {attempt + 1} 次重试...")
            current_notes = (
                f"\u3010请根据以下改进要求重新输出三平台文案】\n"
                f"{check.retry_suggestion}\n\n"
                f"--- 原始笔记 ---\n{raw_notes}"
            )
        else:
            print(f"   ⚠️ 重试 3 次未达标，使用最后结果")

    if generation_result is None:
        result["error"] = "生成结果为空"
        return result

    # 保存文案
    saved = []
    if "xiaohongshu" in enabled_platforms:
        f = save_markdown("xiaohongshu", generation_result.xiaohongshu, note_output_dir)
        saved.append(f)
    if "gongzhonghao" in enabled_platforms:
        f = save_markdown("gongzhonghao", generation_result.gongzhonghao, note_output_dir)
        saved.append(f)
    if "douyin" in enabled_platforms:
        f = save_markdown("douyin", generation_result.douyin, note_output_dir)
        saved.append(f)

    print(f"   ✅ 已保存 {len(saved)} 个文件")

    # 打印推荐标签
    if generation_result and generation_result.recommended_tags:
        print(f"\n   🏷️ 推荐标签/\u8bdd\u9898:")
        for line in generation_result.recommended_tags.strip().split("\n"):
            if line.strip():
                print(f"      {line.strip()}")

    # 生成小红书配图
    if "xiaohongshu" in enabled_platforms:
        try:
            renderer = XiaohongshuRenderer()
            html_path = renderer.render(generation_result.xiaohongshu, note_output_dir / "配图")
            html_name = Path(html_path).name
            print(f"   🎨 配图已生成: {html_name}")
        except Exception as e:
            print(f"   ⚠️ 配图生成失败: {e}")

    result["success"] = True
    result["saved_files"] = saved
    return result



def main():
    parser = argparse.ArgumentParser(
        description="Content Agent - AI 内容改写工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                              使用默认笔记演示
  python main.py -i notes.md                  从文件读取笔记
  python main.py -i notes/                    批量处理目录下所有笔记
  python main.py -i notes.md -o ./dist        指定输出目录
  python main.py -i notes.md -p xiaohongshu   只生成小红书
  python main.py -i notes.md -r               启用搜索增强
  python main.py -i notes/ -r --search-engine tavily  批量+搜索增强
        """,
    )
    parser.add_argument(
        "--input", "-i",
        help="输入的笔记文件或目录 (.md / .txt)"
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="输出目录 (默认: output)"
    )
    parser.add_argument(
        "--platforms", "-p",
        default="all",
        help="平台选择，逗号分隔，默认 all (选项: xiaohongshu,gongzhonghao,douyin)"
    )
    parser.add_argument(
        "--clean", "-c",
        action="store_true",
        help="清理同一天的旧文件后再生成（默认保留历史文件）"
    )
    parser.add_argument(
        "--research", "-r",
        action="store_true",
        help="启用搜索增强，在生成前自动搜索相关背景资料"
    )
    parser.add_argument(
        "--search-engine",
        default="duckduckgo",
        choices=["duckduckgo", "tavily"],
        help="搜索引擎选择（默认: duckduckgo，无需 API key）"
    )

    args = parser.parse_args()

    # 1. 确定输入
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"❌ 错误: 输入路径不存在: {args.input}")
            sys.exit(1)
        note_files = _collect_notes(input_path)
        if not note_files:
            print(f"⚠️ 未找到任何 .md 或 .txt 笔记文件")
            sys.exit(0)
        is_batch = input_path.is_dir()
    else:
        # 默认模式：使用内置笔记
        note_files = [None]
        is_batch = False

    print(f"📁 共发现 {len(note_files)} 个笔记文件" if is_batch else "📄 单文件模式")

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

    # 3. 初始化共享的 Agent 和 Checker
    try:
        agent = ContentAgent()
    except ValueError as e:
        print(f"❌ 配置错误: {e}")
        sys.exit(1)

    checker = QualityChecker(agent.model)

    # 4. 处理笔记
    base_output_dir = Path(args.output)
    date_dir = _get_date_subdir(base_output_dir)

    # 如果是单文件模式且传了 --clean，清理日期目录
    if not is_batch and args.clean and date_dir.exists():
        import shutil
        cleaned = 0
        for item in date_dir.iterdir():
            if item.is_file():
                item.unlink()
                cleaned += 1
            elif item.is_dir():
                shutil.rmtree(item)
                cleaned += 1
        if cleaned > 0:
            print(f"🚿 已清理 {cleaned} 个旧文件/目录")

    results = []
    for idx, note_path in enumerate(note_files, 1):
        if note_path is None:
            # 默认笔记模式
            raw_notes = DEFAULT_NOTES
            note_name = "default"
            note_output_dir = date_dir
        else:
            with open(note_path, "r", encoding="utf-8") as f:
                raw_notes = f.read()
            note_name = note_path.stem
            if is_batch:
                # 批量模式：每个笔记单独子目录
                note_output_dir = date_dir / note_name
                note_output_dir.mkdir(parents=True, exist_ok=True)
            else:
                # 单文件模式：也创建笔记名子目录，保持结构统一
                note_output_dir = date_dir / note_name
                note_output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n📊 进度: {idx}/{len(note_files)}")

        result = process_single_note(
            note_path=note_path or Path("default"),
            raw_notes=raw_notes,
            agent=agent,
            checker=checker,
            enabled_platforms=enabled_platforms,
            args=args,
            note_output_dir=note_output_dir,
        )
        results.append(result)

    # 5. 总结
    success_count = sum(1 for r in results if r["success"])
    total_files = sum(len(r["saved_files"]) for r in results)

    print(f"\n{'=' * 60}")
    print(f"🎉 全部完成！{success_count}/{len(note_files)} 个笔记处理成功")
    print(f"📁 共生成 {total_files} 个文件")
    print(f"📂 输出目录: {date_dir.absolute()}")
    print(f"{'=' * 60}")

    # 失败的笔记打印错误
    failed = [(note_files[i].name if note_files[i] else "default", r["error"])
              for i, r in enumerate(results) if not r["success"]]
    if failed:
        print(f"\n❌ 失败的笔记:")
        for name, err in failed:
            print(f"   • {name}: {err}")


if __name__ == "__main__":
    main()
