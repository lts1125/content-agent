#!/usr/bin/env python3
"""
Content Agent - Web UI

基于 Gradio 的简洁 Web 界面，支持：
- 粘贴/上传笔记
- 选择平台（多选）
- 搜索增强开关
- 一键生成三平台文案
- 文案复制

安装: pip install gradio
运行: python web_ui.py
"""

import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    import gradio as gr
except ImportError:
    print("❌ 请先安装 Gradio: pip install gradio")
    sys.exit(1)

from content_agent.agent_core import ContentAgent
from content_agent.quality_checker import QualityChecker
from content_agent.research import research_notes, extract_keywords_with_llm


# 缓存 Agent 实例（避免每次都重新初始化）
_agent = None
_checker = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = ContentAgent()
    return _agent


def _get_checker():
    global _checker
    if _checker is None:
        _checker = QualityChecker(_get_agent().model)
    return _checker


def generate_content(note_text, note_file, platforms, enable_research, search_engine, progress=gr.Progress()):
    """
    Gradio 处理函数

    Returns:
        (xiaohongshu, gongzhonghao, douyin, status_msg)
    """
    # 优先使用上传的文件
    if note_file is not None:
        try:
            # note_file 是 tempfile 路径
            with open(note_file, "r", encoding="utf-8") as f:
                note_text = f.read()
        except Exception as e:
            return "", "", "", f"❌ 读取文件失败: {e}"

    note_text = note_text.strip() if note_text else ""
    if not note_text:
        return "", "", "", "⚠️ 请输入或上传笔记"

    # 解析平台
    platform_map = {
        "小红书": "xiaohongshu",
        "公众号": "gongzhonghao",
        "抖音": "douyin",
    }
    enabled = {platform_map[p] for p in platforms if p in platform_map}

    if not enabled:
        return "", "", "", "⚠️ 请至少选择一个平台"

    progress(0.1, desc="初始化 Agent...")
    agent = _get_agent()
    checker = _get_checker()

    current_notes = note_text

    # 搜索增强
    if enable_research:
        progress(0.2, desc="搜索增强中...")
        try:
            from pydantic_ai import Agent
            keyword_agent = Agent(
                agent.model,
                system_prompt="你是一个关键词提取助手，从技术笔记中提取精准的搜索关键词。"
            )
            keywords = extract_keywords_with_llm(note_text, keyword_agent)
            current_notes = research_notes(
                note_text,
                search_engine=search_engine,
                max_results=3,
                verbose=False,
                keywords=keywords,
            )
        except Exception as e:
            print(f"搜索增强失败: {e}")

    # 生成 + 质检
    progress(0.3, desc="生成中...")
    generation_result = None

    for attempt in range(1, 4):
        try:
            generation_result = agent.run(current_notes)
        except Exception as e:
            return "", "", "", f"❌ Agent 调用失败: {e}"

        progress(0.3 + attempt * 0.15, desc=f"质量检查第 {attempt} 次...")

        check = checker.check(
            generation_result.xiaohongshu,
            generation_result.gongzhonghao,
            generation_result.douyin,
            attempt=attempt,
        )

        if check.passed:
            break

        if attempt < 3:
            current_notes = (
                f"【请根据以下改进要求重新输出三平台文案】\n"
                f"{check.retry_suggestion}\n\n"
                f"--- 原始笔记 ---\n{note_text}"
            )

    progress(0.9, desc="整理结果...")

    xiaohongshu_text = generation_result.xiaohongshu if "xiaohongshu" in enabled else "（未选择此平台）"
    gongzhonghao_text = generation_result.gongzhonghao if "gongzhonghao" in enabled else "（未选择此平台）"
    douyin_text = generation_result.douyin if "douyin" in enabled else "（未选择此平台）"

    status = f"✅ 生成完成！平台: {', '.join(platforms)} | 笔记: {len(note_text)} 字"

    progress(1.0, desc="完成")
    return xiaohongshu_text, gongzhonghao_text, douyin_text, status


# ==================== Gradio 界面 ====================

with gr.Blocks(
    title="Content Agent",
    theme=gr.themes.Soft(),
    css="""
    .tab-content { min-height: 400px; }
    .copy-btn { margin-top: 8px; }
    """
) as demo:
    gr.Markdown("""
    # 📘 Content Agent - AI 多平台内容改写

    输入你的技术学习笔记，一键生成 **小红书 / 公众号 / 抖音** 三平台文案。
    """)

    with gr.Row():
        # 左侧：输入区
        with gr.Column(scale=1):
            gr.Markdown("### 📝 输入")

            note_input = gr.Textbox(
                label="笔记内容（支持 Markdown）",
                placeholder="粘贴你的技术学习笔记...\n\n示例：\n背景：今天学了 xxx\n核心步骤：...",
                lines=12,
                show_copy_button=False,
            )

            file_input = gr.File(
                label="或上传文件 (.md / .txt)",
                file_types=[".md", ".txt"],
            )

            with gr.Group():
                gr.Markdown("### ⚙️ 配置")

                platform_check = gr.CheckboxGroup(
                    label="选择平台",
                    choices=["小红书", "公众号", "抖音"],
                    value=["小红书", "公众号", "抖音"],
                )

                enable_research = gr.Checkbox(
                    label="🔍 启用搜索增强（自动补充背景资料）",
                    value=False,
                )

                search_engine = gr.Dropdown(
                    label="搜索引擎",
                    choices=[
                        ("DuckDuckGo (免费)", "duckduckgo"),
                        ("Tavily (需 API Key)", "tavily"),
                    ],
                    value="duckduckgo",
                )

            generate_btn = gr.Button("🚀 生成三平台文案", variant="primary", size="lg")

            status_text = gr.Textbox(
                label="状态",
                value="等待生成...",
                interactive=False,
            )

        # 右侧：输出区
        with gr.Column(scale=1):
            gr.Markdown("### 📋 输出")

            with gr.Tabs():
                with gr.TabItem("📱 小红书"):
                    xiaohongshu_output = gr.Textbox(
                        label="小红书文案",
                        lines=18,
                        show_copy_button=True,
                    )

                with gr.TabItem("💬 公众号"):
                    gongzhonghao_output = gr.Textbox(
                        label="公众号文案",
                        lines=18,
                        show_copy_button=True,
                    )

                with gr.TabItem("🎵 抖音"):
                    douyin_output = gr.Textbox(
                        label="抖音文案",
                        lines=18,
                        show_copy_button=True,
                    )

    # 事件绑定
    generate_btn.click(
        fn=generate_content,
        inputs=[
            note_input,
            file_input,
            platform_check,
            enable_research,
            search_engine,
        ],
        outputs=[
            xiaohongshu_output,
            gongzhonghao_output,
            douyin_output,
            status_text,
        ],
    )

    gr.Markdown("""
    ---
    📖 [GitHub](https://github.com/lts1125/content-agent) | 本地工具版: `python main.py -i notes.md`
    """)


if __name__ == "__main__":
    # 检查 API Key
    provider = os.getenv("MODEL_PROVIDER", "deepseek")
    key_map = {
        "deepseek": "DEEPSEEK_API_KEY",
        "kimi": "KIMI_API_KEY",
        "minimax": "MINIMAX_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    key_var = key_map.get(provider, "MODEL_API_KEY")
    if not os.getenv(key_var):
        print(f"⚠️ 警告: 未检测到 {key_var} 环境变量，请先配置 .env 文件")
        sys.exit(1)

    print("🚀 启动 Content Agent Web UI...")
    print("📎 打开浏览器访问: http://127.0.0.1:7860")
    print("📡 按 Ctrl+C 停止服务\n")

    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        show_error=True,
    )
