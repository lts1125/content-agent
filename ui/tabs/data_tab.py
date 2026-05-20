"""
ui/tabs/data_tab.py — 📊 数据中心（历史记录、风格画像、反馈导入）

Phase 0：占位模块。
当前历史记录逻辑在 web_ui.py 的 📚 历史 Tab 中。
后续将接入 agents/store.py 的 SQLite 数据源。
"""

import gradio as gr


def create_tab():
    with gr.Tab("📊 数据中心") as tab:
        gr.Markdown("### 数据中心（Phase 3 实现）")
    return tab
