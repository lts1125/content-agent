"""
ui/tabs/topics_tab.py — 🤖 智能选题 Tab

Phase 2 实现：
- 今日推荐选题列表
- 一键开始生成
- 笔记库扫描 + 热点匹配结果展示
"""

import gradio as gr


def create_tab():
    with gr.Tab("🤖 智能选题") as tab:
        gr.Markdown("### 智能选题（Phase 2 实现）")
    return tab
