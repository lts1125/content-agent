"""
ui/components.py — Gradio 共用组件

Phase 0：提取可在各 Tab 复用的 UI 元素。
"""

import gradio as gr


def status_bar(initial_text: str = "等待操作...") -> gr.Textbox:
    """统一状态栏组件"""
    return gr.Textbox(
        label="状态",
        value=initial_text,
        interactive=False,
    )


def platform_checkbox(default: list = None) -> gr.CheckboxGroup:
    """平台选择组件"""
    if default is None:
        default = ["小红书", "公众号", "抖音"]
    return gr.CheckboxGroup(
        label="选择平台",
        choices=["小红书", "公众号", "抖音"],
        value=default,
    )


def export_buttons(prefix: str = ""):
    """导出 Markdown / Word 按钮组，返回 (md_btn, docx_btn, download_file)"""
    with gr.Row():
        md_btn = gr.Button("📥 导出 Markdown", size="sm")
        docx_btn = gr.Button("📄 导出 Word", size="sm")
    download = gr.File(label="下载文件", visible=False)
    return md_btn, docx_btn, download
