"""
ui/tabs/generate_tab.py — 📝 工作台（生成 Tab）

Phase 0：占位模块。
当前生成界面的全部逻辑仍在 web_ui.py 中（约 line 1017-1200+）。
后续迁移计划：
1. 将 generate_content()、refine_content() 等业务函数保留在 web_ui.py 或迁移到 agents/ 调用层
2. 将 Gradio 组件定义（note_input、platform_check、输出 Textbox 等）迁移至此
3. 事件绑定（generate_btn.click(...)）一并迁移
"""

import gradio as gr


def create_tab():
    """
    返回 gr.Tab 容器。当前为占位实现。
    完整实现需从 web_ui.py 中逐段提取组件和事件处理器。
    """
    with gr.Tab("📝 生成") as tab:
        gr.Markdown("### 工作台（迁移中，当前由 web_ui.py 提供服务）")
    return tab
