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
import re
import sys
import json
import tempfile
import logging
from datetime import datetime
from pathlib import Path

# 调试日志：打包后 windowed 模式下 stdout 可能被重定向，日志写文件确保可调试
_LOG_PATH = os.path.join(tempfile.gettempdir(), "ca_launch.log")
logging.basicConfig(
    filename=_LOG_PATH,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ca")
logger.info("=== web_ui 初始化开始 ===")

# 保护：打包后 windowed 模式下可能没有 stdout/stderr，重定向到 devnull 避免库报错
if sys.platform == "darwin" and getattr(sys, "frozen", False):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    logger.info("windowed stdout/stderr 保护已触发")

# 确保 urllib 访问 localhost 时不走代理（Gradio 启动检查需要）
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

from dotenv import load_dotenv

load_dotenv()

try:
    import gradio as gr
except ImportError as e:
    print(f"❌ Gradio 导入失败: {e}")
    print("提示: 请确保已激活虚拟环境，然后运行: pip install gradio")
    print("示例: source .venv/bin/activate && pip install gradio")
    sys.exit(1)

from content_agent.agent_core import ContentAgent
from content_agent.quality_checker import QualityChecker
from content_agent.research import research_notes, extract_keywords_with_llm
from content_agent.html_renderer import XiaohongshuRenderer

from agents.schemas import TaskInput
from agents.orchestrator import Orchestrator

from ui.tabs import config_tab

# ==================== 配置管理 ====================

# ==================== 从 handlers 导入业务逻辑 ====================

from ui.handlers import (
    _build_template_choices,
    on_template_select,
    on_template_save,
    on_template_delete,
    get_config_status,
    load_config_for_ui,
    save_config,
    _get_vault_path,
    _save_vault_path,
    scan_vault_files,
    read_vault_file,
    on_vault_save,
    on_vault_refresh,
    on_vault_select,
    on_file_upload,
    load_kuaifa_config,
    save_kuaifa_config,
    verify_kuaifa_config,
    get_kuaifa_setup_status,
    _find_kuaifa,
    generate_content,
    refine_content,
    restore_history,
    generate_titles,
    generate_cover_prompt,
    export_markdown,
    export_word,
    publish_to_wechat,
)
# ==================== Gradio 界面 ====================

with gr.Blocks(
    title="Content Agent",
    theme=gr.themes.Soft(),
    css="""
    .tab-content { min-height: 400px; }
    .copy-btn { margin-top: 8px; }
    """
) as demo:
    # 会话级历史记录状态
    history_state = gr.State([])

    gr.Markdown("""
    # 📘 Content Agent - AI 多平台内容改写

    输入你的技术学习笔记，一键生成 **小红书 / 公众号 / 抖音** 三平台文案。
    """)

    with gr.Tabs() as main_tabs:
        with gr.Tab("📝 生成"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 📝 输入")

                    note_input = gr.Textbox(
                        label="笔记内容（支持 Markdown，多篇用 --- 分隔）",
                        placeholder="粘贴你的技术学习笔记...\n\n示例：\n背景：今天学了 xxx\n核心步骤：...\n\n---\n\n第二篇笔记...",
                        lines=12,
                        show_copy_button=False,
                    )

                    file_input = gr.File(
                        label="或上传文件 (.md / .txt)",
                        file_types=[".md", ".txt"],
                    )

                    with gr.Group():
                        gr.Markdown("#### 📁 或从本地笔记库选择（Obsidian / Markdown 目录）")
                        vault_path_input = gr.Textbox(
                            label="笔记库路径",
                            placeholder="/Users/lee/Documents/ObsidianVault",
                            value=_get_vault_path(),
                        )
                        with gr.Row():
                            vault_save_btn = gr.Button("💾 保存路径", size="sm")
                            vault_refresh_btn = gr.Button("🔄 刷新文件列表", size="sm")
                        vault_file_select = gr.Dropdown(
                            label="选择笔记文件",
                            choices=scan_vault_files(_get_vault_path()),
                            value=None,
                            interactive=True,
                        )
                        vault_status = gr.Textbox(
                            label="状态",
                            interactive=False,
                            visible=True,
                        )

                    with gr.Group():
                        gr.Markdown("### 🎯 配置模板")

                        template_dropdown = gr.Dropdown(
                            label="选择模板（快速加载配置套餐）",
                            choices=_build_template_choices(),
                            value=None,
                            allow_custom_value=False,
                        )

                        with gr.Row():
                            template_save_name = gr.Textbox(
                                label="新模板名称",
                                placeholder="保存当前配置为新模板...",
                                scale=2,
                            )
                            template_save_btn = gr.Button("✅ 保存", scale=1)

                        template_delete_btn = gr.Button("❌ 删除当前模板", visible=False, interactive=False)

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

                        style_radio = gr.Radio(
                            label="🎨 文案风格",
                            choices=["专业干货", "轻松口语", "情绪共鸣", "悬念钩子"],
                            value="专业干货",
                        )

                        batch_mode = gr.Checkbox(
                            label="📤 批量模式（多篇笔记用 --- 分隔）",
                            value=False,
                        )

                    generate_btn = gr.Button("🚀 生成三平台文案", variant="primary", size="lg")

                    status_text = gr.Textbox(
                        label="状态",
                        value="等待生成...",
                        interactive=False,
                    )

                with gr.Column(scale=1):
                    gr.Markdown("### 📋 输出")

                    with gr.Tabs():
                        with gr.TabItem("📱 小红书"):
                            xiaohongshu_output = gr.Textbox(
                                label="小红书文案",
                                lines=18,
                                show_copy_button=True,
                            )
                            xiaohongshu_preview = gr.HTML()
                            with gr.Row():
                                export_md_xhs_btn = gr.Button("📥 导出 Markdown", size="sm")
                                export_docx_xhs_btn = gr.Button("📄 导出 Word", size="sm")
                            xiaohongshu_download = gr.File(label="下载文件", visible=False)

                        with gr.TabItem("💬 公众号"):
                            gongzhonghao_output = gr.Textbox(
                                label="公众号文案",
                                lines=18,
                                show_copy_button=True,
                            )
                            with gr.Row():
                                export_md_gzh_btn = gr.Button("📥 导出 Markdown", size="sm")
                                export_docx_gzh_btn = gr.Button("📄 导出 Word", size="sm")
                            gongzhonghao_download = gr.File(label="下载文件", visible=False)

                            # 发布到微信公众号草稿箱
                            with gr.Accordion("📤 发布到公众号草稿箱（需安装 kuaifa CLI）", open=False):
                                publish_title = gr.Textbox(
                                    label="文章标题",
                                    placeholder="留空则使用默认标题",
                                    lines=1,
                                )
                                publish_author = gr.Textbox(
                                    label="作者名（可选）",
                                    placeholder="作者名",
                                    lines=1,
                                )
                                publish_digest = gr.Textbox(
                                    label="文章摘要（可选）",
                                    placeholder="摘要会显示在公众号列表中",
                                    lines=2,
                                )
                                gr.Markdown("**封面图片**（必填：微信草稿要求必须有封面）")
                                cover_upload = gr.File(
                                    label="上传封面图片",
                                    file_types=["image"],
                                    type="filepath",
                                )
                                cover_url = gr.Textbox(
                                    label="或填入图片 URL",
                                    placeholder="https://example.com/cover.jpg",
                                    lines=1,
                                )
                                publish_wechat_btn = gr.Button(
                                    "📤 一键发布到草稿箱",
                                    variant="primary",
                                )
                                publish_result = gr.Textbox(
                                    label="发布结果",
                                    lines=4,
                                    interactive=False,
                                )

                        with gr.TabItem("🎥 抖音"):
                            douyin_output = gr.Textbox(
                                label="抖音文案",
                                lines=18,
                                show_copy_button=True,
                            )
                            with gr.Row():
                                export_md_dy_btn = gr.Button("📥 导出 Markdown", size="sm")
                                export_docx_dy_btn = gr.Button("📄 导出 Word", size="sm")
                            douyin_download = gr.File(label="下载文件", visible=False)

                        gr.Markdown("### 🏷️ 推荐标签/话题")
                        tags_output = gr.Textbox(
                            label="生成的各平台推荐标签，可直接复制使用",
                            lines=8,
                            show_copy_button=True,
                        )

                    with gr.Group():
                        gr.Markdown("### ✏️ 不满意？再改一版")
                        refine_input = gr.Textbox(
                            label="修改指令",
                            placeholder="例如：更口语化 / 加个钩子 / 缩短一点 / 多加点 emoji / 语气更在地气",
                            lines=2,
                        )
                        refine_btn = gr.Button("🔄 再改一版", variant="secondary")

                        gr.Markdown("### 🎲 标题 A/B 测试")
                        title_btn = gr.Button("🎩 生成备选标题", variant="secondary")
                        with gr.Row():
                            with gr.Column():
                                gr.Markdown("📱 小红书")
                                xiaohongshu_titles = gr.Markdown("点击上方按钮生成")
                            with gr.Column():
                                gr.Markdown("💬 公众号")
                                gongzhonghao_titles = gr.Markdown("点击上方按钮生成")
                            with gr.Column():
                                gr.Markdown("🎥 抖音")
                                douyin_titles = gr.Markdown("点击上方按钮生成")

                        gr.Markdown("### 🎨 配图 Prompt 生成")
                        cover_prompt_btn = gr.Button("🖼️ 生成小红书封面配图 Prompt", variant="secondary")
                        cover_prompt_output = gr.Textbox(
                            label="绘画 Prompt（可复制到 Midjourney/通义万相/即梦）",
                            lines=10,
                            show_copy_button=True,
                        )

        with gr.Tab("⚙️ 配置"):
            config_tab.create_tab(save_config_fn=save_config)

            gr.Markdown("### ⏰ 定时任务管理")
            gr.Markdown("每个任务绑定一个具体笔记文件（如 `notes/daily.md`），到点后自动生成文案。也可以填写目录，会处理目录下所有笔记。")

            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("#### 添加任务")
                    task_name_input = gr.Textbox(label="任务名称", placeholder="例如：每日早报", value="每日生成")
                    task_input_dir = gr.Textbox(label="输入文件路径", placeholder="notes/daily.md 或目录 notes/", value="notes/daily.md")
                    task_output_dir = gr.Textbox(label="输出目录", placeholder="output/", value="output")
                    with gr.Row():
                        task_hour = gr.Dropdown(
                            label="小时",
                            choices=[f"{h:02d}" for h in range(24)],
                            value="09",
                        )
                        task_minute = gr.Dropdown(
                            label="分钟",
                            choices=[f"{m:02d}" for m in range(0, 60, 5)],
                            value="00",
                        )
                    task_weekdays = gr.CheckboxGroup(
                        label="执行日期（不选=每天）",
                        choices=["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
                    )
                    add_task_btn = gr.Button("➕ 添加任务", variant="primary")
                    task_status = gr.Textbox(label="状态", value="等待操作...", interactive=False)

                with gr.Column(scale=1):
                    gr.Markdown("#### 任务列表")
                    task_dropdown = gr.Dropdown(label="选择任务", choices=[], value=None)
                    task_detail = gr.Markdown("点击刷新查看任务列表")
                    with gr.Row():
                        refresh_tasks_btn = gr.Button("🔄 刷新")
                        run_now_btn = gr.Button("▶️ 立即执行", variant="secondary")
                        toggle_btn = gr.Button("⏸️ 启用/暂停")
                        delete_task_btn = gr.Button("🗑️ 删除", variant="stop")

            gr.Markdown("管理内容发布排期，跟踪状态。")

            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("#### 添加/编辑计划")
                    cal_id_hidden = gr.Textbox(visible=False, value="")
                    cal_title = gr.Textbox(label="标题", placeholder="例如：MCP协议介绍", value="")
                    cal_topic = gr.Textbox(label="主题/关键词", placeholder="例如：MCP, AI工具", value="")
                    cal_platforms = gr.CheckboxGroup(
                        label="平台",
                        choices=["小红书", "公众号", "抖音"],
                        value=["小红书"],
                    )
                    cal_date = gr.Textbox(
                        label="排期日期",
                        placeholder="2026-05-20",
                        value=datetime.now().strftime("%Y-%m-%d"),
                    )
                    cal_note_file = gr.Textbox(label="关联笔记文件", placeholder="notes/mcp_intro.md", value="")
                    cal_status = gr.Dropdown(
                        label="状态",
                        choices=["草稿", "已排期", "已生成", "已发布"],
                        value="草稿",
                    )
                    with gr.Row():
                        cal_add_btn = gr.Button("➕ 添加", variant="primary")
                        cal_update_btn = gr.Button("💾 更新", variant="secondary")
                        cal_clear_btn = gr.Button("🔄 清空", variant="secondary")
                    cal_status_msg = gr.Textbox(label="状态", value="等待操作...", interactive=False)

                with gr.Column(scale=1):
                    gr.Markdown("#### 计划列表")
                    cal_filter = gr.Dropdown(
                        label="筛选",
                        choices=["全部", "本周", "本月", "草稿", "已排期", "已生成", "已发布"],
                        value="全部",
                    )
                    cal_dropdown = gr.Dropdown(label="选择计划", choices=[], value=None)
                    cal_detail = gr.Markdown("点击刷新查看计划列表")
                    with gr.Row():
                        cal_refresh_btn = gr.Button("🔄 刷新")
                        cal_delete_btn = gr.Button("🗑️ 删除", variant="stop")

        with gr.Tab("📚 历史"):
            gr.Markdown("### 📚 历史记录管理")
            with gr.Row():
                with gr.Column(scale=1):
                    history_dropdown_big = gr.Dropdown(
                        label="选择历史记录",
                        choices=[],
                        value=None,
                    )
                    with gr.Row():
                        restore_big_btn = gr.Button("🔄 加载到工作台", variant="primary")
                        clear_history_big_btn = gr.Button("🗑️ 清空全部历史", variant="stop")
                with gr.Column(scale=1):
                    history_detail = gr.Markdown("**历史记录详情**\n\n切换到此页面时会自动加载历史列表。\n选择一条记录可查看详情。")

    def _get_scheduler():
        """获取调度器单例（延迟初始化，避免导入失败）"""
        global _scheduler
        if _scheduler is None:
            try:
                from content_agent.scheduler import TaskScheduler
                _scheduler = TaskScheduler()
                _scheduler.start()
            except ImportError as e:
                print(f"[定时任务] 初始化失败: {e}")
                return None
        return _scheduler

    def _format_task_list(tasks: list[dict]) -> str:
        if not tasks:
            return "**暂无定时任务**"
        lines = [
            "| 名称 | 时间 | 输入 | 输出 | 状态 | 上次运行 |",
            "|---|---|---|---|---|---|",
        ]
        for t in tasks:
            if t.get("weekdays"):
                names = ["一", "二", "三", "四", "五", "六", "日"]
                wd_str = "周" + "、".join(names[wd] for wd in t["weekdays"])
            else:
                wd_str = "每天"
            time_str = f"{t['hour']:02d}:{t['minute']:02d}"
            status = "🟢 启用" if t["enabled"] else "🔴 暂停"
            last = t.get("last_run", "从未")[:16] if t.get("last_run") else "从未"
            last_status = t.get("last_status", "")
            if last_status and last_status != "success":
                last += f" ({last_status})"
            lines.append(
                f"| {t['name']} | {wd_str} {time_str} | {t['input_dir']} | {t['output_dir']} | {status} | {last} |"
            )
        return "\n".join(lines)

    def refresh_scheduled_tasks():
        scheduler = _get_scheduler()
        if scheduler is None:
            return gr.Dropdown(), "**定时任务功能未启用**（缺少 schedule 库，请运行 `pip install schedule`）"
        tasks = scheduler.list_tasks()
        choices = [(f"{t['name']} ({t['hour']:02d}:{t['minute']:02d})", t["id"]) for t in tasks]
        return gr.Dropdown(choices=choices, value=None), _format_task_list(tasks)

    def add_scheduled_task(name, input_dir, output_dir, hour, minute, weekdays):
        scheduler = _get_scheduler()
        if scheduler is None:
            return "❌ 定时任务功能未启用（缺少 schedule 库）", gr.Dropdown(), ""

        wd_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
        weekdays_int = [wd_map[w] for w in (weekdays or [])]

        try:
            task_id = scheduler.add_task(
                name or "未命名任务",
                input_dir or "notes",
                output_dir or "output",
                int(hour) if hour else 9,
                int(minute) if minute else 0,
                weekdays_int,
            )
            tasks = scheduler.list_tasks()
            choices = [(f"{t['name']} ({t['hour']:02d}:{t['minute']:02d})", t["id"]) for t in tasks]
            return (
                f"✅ 任务已添加: {name}",
                gr.Dropdown(choices=choices, value=task_id),
                _format_task_list(tasks),
            )
        except Exception as e:
            return f"❌ 添加失败: {e}", gr.Dropdown(), ""

    def delete_scheduled_task(task_id):
        scheduler = _get_scheduler()
        if scheduler is None:
            return "❌ 定时任务功能未启用", gr.Dropdown(), ""
        if not task_id:
            return "⚠️ 请先选择任务", gr.Dropdown(), ""
        if scheduler.remove_task(task_id):
            tasks = scheduler.list_tasks()
            choices = [(f"{t['name']} ({t['hour']:02d}:{t['minute']:02d})", t["id"]) for t in tasks]
            return "✅ 任务已删除", gr.Dropdown(choices=choices, value=None), _format_task_list(tasks)
        return "❌ 删除失败", gr.Dropdown(), ""

    def toggle_scheduled_task(task_id):
        scheduler = _get_scheduler()
        if scheduler is None:
            return "❌ 定时任务功能未启用", ""
        if not task_id:
            return "⚠️ 请先选择任务", ""
        result = scheduler.toggle_task(task_id)
        if result is not None:
            tasks = scheduler.list_tasks()
            choices = [(f"{t['name']} ({t['hour']:02d}:{t['minute']:02d})", t["id"]) for t in tasks]
            status = "启用" if result else "暂停"
            return f"✅ 任务已{status}", _format_task_list(tasks)
        return "❌ 操作失败", ""

    def run_scheduled_task_now(task_id):
        scheduler = _get_scheduler()
        if scheduler is None:
            return "❌ 定时任务功能未启用"
        if not task_id:
            return "⚠️ 请先选择任务"
        if scheduler.run_now(task_id):
            return "🚀 任务已在后台执行，请刷新查看状态"
        return "❌ 执行失败"

    # ==================== 内容日历处理函数 ====================

    def _get_calendar():
        """获取日历单例"""
        try:
            from content_agent.calendar import ContentCalendar
            return ContentCalendar()
        except Exception as e:
            print(f"[内容日历] 初始化失败: {e}")
            return None

    def _format_calendar_list(entries: list[dict]) -> str:
        if not entries:
            return "**暂无发布计划**"
        lines = [
            "| 日期 | 标题 | 平台 | 状态 | 笔记 | 创建时间 |",
            "|---|---|---|---|---|---|",
        ]
        for e in entries:
            platforms = "、".join(e.get("platforms", []))
            status = e.get("status_display", e.get("status", ""))
            note = e.get("note_file", "") or "无"
            created = e.get("created_at", "")[:10]
            lines.append(
                f"| {e['scheduled_date']} | {e['title']} | {platforms} | {status} | {note} | {created} |"
            )
        return "\n".join(lines)

    def refresh_calendar_entries(filter_type):
        cal = _get_calendar()
        if cal is None:
            return gr.Dropdown(), "**内容日历初始化失败**"

        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")

        if filter_type == "全部":
            entries = cal.list_entries()
        elif filter_type == "本周":
            start = datetime.now().strftime("%Y-%m-%d")
            end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            entries = cal.list_entries(filter_date_from=start, filter_date_to=end)
        elif filter_type == "本月":
            start = datetime.now().strftime("%Y-%m-01")
            end = (datetime.now().replace(day=28) + timedelta(days=4)).strftime("%Y-%m-01")
            entries = cal.list_entries(filter_date_from=start, filter_date_to=end)
        else:
            entries = cal.list_entries(filter_status=filter_type)

        choices = [(f"{e['scheduled_date']} | {e['title']}", e["id"]) for e in entries]
        return gr.Dropdown(choices=choices, value=None), _format_calendar_list(entries)

    def add_calendar_entry(title, topic, platforms, scheduled_date, note_file, status):
        cal = _get_calendar()
        if cal is None:
            return "❌ 日历初始化失败", gr.Dropdown(), "", ""
        try:
            entry_id = cal.add(title, topic, platforms, scheduled_date, note_file, status)
            entries = cal.list_entries()
            choices = [(f"{e['scheduled_date']} | {e['title']}", e["id"]) for e in entries]
            return (
                f"✅ 计划已添加: {title}",
                gr.Dropdown(choices=choices, value=entry_id),
                _format_calendar_list(entries),
                "",
            )
        except Exception as e:
            return f"❌ 添加失败: {e}", gr.Dropdown(), "", ""

    def delete_calendar_entry(entry_id):
        cal = _get_calendar()
        if cal is None:
            return "❌ 日历初始化失败", gr.Dropdown(), ""
        if not entry_id:
            return "⚠️ 请先选择计划", gr.Dropdown(), ""
        if cal.delete(entry_id):
            entries = cal.list_entries()
            choices = [(f"{e['scheduled_date']} | {e['title']}", e["id"]) for e in entries]
            return "✅ 计划已删除", gr.Dropdown(choices=choices, value=None), _format_calendar_list(entries)
        return "❌ 删除失败", gr.Dropdown(), ""

    def load_calendar_entry_for_edit(entry_id):
        cal = _get_calendar()
        if cal is None or not entry_id:
            return "", "", "", [], "", "", "草稿"
        e = cal.get_entry(entry_id)
        if not e:
            return "", "", "", [], "", "", "草稿"
        return (
            e["id"],
            e["title"],
            e["topic"],
            e.get("platforms", []),
            e["scheduled_date"],
            e["note_file"],
            e.get("status_display", "草稿"),
        )

    def update_calendar_entry(entry_id, title, topic, platforms, scheduled_date, note_file, status):
        cal = _get_calendar()
        if cal is None:
            return "❌ 日历初始化失败", ""
        if not entry_id:
            return "⚠️ 请先选择计划或加载", ""
        try:
            cal.update(
                entry_id,
                title=title,
                topic=topic,
                platforms=platforms,
                scheduled_date=scheduled_date,
                note_file=note_file,
                status=status,
            )
            entries = cal.list_entries()
            choices = [(f"{e['scheduled_date']} | {e['title']}", e["id"]) for e in entries]
            return (
                f"✅ 计划已更新: {title}",
                _format_calendar_list(entries),
            )
        except Exception as e:
            return f"❌ 更新失败: {e}", ""

    def clear_calendar_form():
        return "", "", "", [], datetime.now().strftime("%Y-%m-%d"), "", "草稿", "表单已清空"

    # 事件绑定
    # 笔记库事件绑定
    vault_save_btn.click(
        fn=on_vault_save,
        inputs=[vault_path_input],
        outputs=[vault_status, vault_file_select],
    )
    vault_refresh_btn.click(
        fn=on_vault_refresh,
        inputs=[vault_path_input],
        outputs=[vault_file_select],
    )
    vault_file_select.change(
        fn=on_vault_select,
        inputs=[vault_path_input, vault_file_select],
        outputs=[note_input],
    )
    file_input.change(
        fn=on_file_upload,
        inputs=[file_input],
        outputs=[note_input],
    )

    generate_btn.click(
        fn=generate_content,
        inputs=[
            note_input,
            file_input,
            platform_check,
            enable_research,
            search_engine,
            style_radio,
            batch_mode,
            history_state,
        ],
        outputs=[
            xiaohongshu_output,
            gongzhonghao_output,
            douyin_output,
            xiaohongshu_preview,
            tags_output,
            status_text,
            history_state,
        ],
    )

    refine_btn.click(
        fn=refine_content,
        inputs=[
            xiaohongshu_output,
            gongzhonghao_output,
            douyin_output,
            refine_input,
            note_input,
            style_radio,
            history_state,
        ],
        outputs=[
            xiaohongshu_output,
            gongzhonghao_output,
            douyin_output,
            xiaohongshu_preview,
            tags_output,
            status_text,
            history_state,
        ],
    )

    title_btn.click(
        fn=generate_titles,
        inputs=[
            xiaohongshu_output,
            gongzhonghao_output,
            douyin_output,
            note_input,
            style_radio,
        ],
        outputs=[
            xiaohongshu_titles,
            gongzhonghao_titles,
            douyin_titles,
            status_text,
        ],
    )

    cover_prompt_btn.click(
        fn=generate_cover_prompt,
        inputs=[xiaohongshu_output],
        outputs=[cover_prompt_output, status_text],
    )

    # —— 导出事件绑定 ——
    export_md_xhs_btn.click(
        fn=lambda text: export_markdown("小红书", text),
        inputs=[xiaohongshu_output],
        outputs=[xiaohongshu_download, status_text],
    )
    export_docx_xhs_btn.click(
        fn=lambda text: export_word("小红书", text),
        inputs=[xiaohongshu_output],
        outputs=[xiaohongshu_download, status_text],
    )

    export_md_gzh_btn.click(
        fn=lambda text: export_markdown("公众号", text),
        inputs=[gongzhonghao_output],
        outputs=[gongzhonghao_download, status_text],
    )
    export_docx_gzh_btn.click(
        fn=lambda text: export_word("公众号", text),
        inputs=[gongzhonghao_output],
        outputs=[gongzhonghao_download, status_text],
    )

    # —— 公众号发布绑定 ——
    publish_wechat_btn.click(
        fn=publish_to_wechat,
        inputs=[
            gongzhonghao_output,
            publish_title,
            publish_author,
            publish_digest,
            cover_upload,
            cover_url,
        ],
        outputs=[publish_result],
    )

    export_md_dy_btn.click(
        fn=lambda text: export_markdown("抖音", text),
        inputs=[douyin_output],
        outputs=[douyin_download, status_text],
    )
    export_docx_dy_btn.click(
        fn=lambda text: export_word("抖音", text),
        inputs=[douyin_output],
        outputs=[douyin_download, status_text],
    )

    # —— 定时任务事件绑定 ——
    add_task_btn.click(
        fn=add_scheduled_task,
        inputs=[task_name_input, task_input_dir, task_output_dir, task_hour, task_minute, task_weekdays],
        outputs=[task_status, task_dropdown, task_detail],
    )
    refresh_tasks_btn.click(
        fn=refresh_scheduled_tasks,
        inputs=[],
        outputs=[task_dropdown, task_detail],
    )
    delete_task_btn.click(
        fn=delete_scheduled_task,
        inputs=[task_dropdown],
        outputs=[task_status, task_dropdown, task_detail],
    )
    toggle_btn.click(
        fn=toggle_scheduled_task,
        inputs=[task_dropdown],
        outputs=[task_status, task_detail],
    )
    run_now_btn.click(
        fn=run_scheduled_task_now,
        inputs=[task_dropdown],
        outputs=[task_status],
    )

    # —— 内容日历事件绑定 ——
    cal_add_btn.click(
        fn=add_calendar_entry,
        inputs=[cal_title, cal_topic, cal_platforms, cal_date, cal_note_file, cal_status],
        outputs=[cal_status_msg, cal_dropdown, cal_detail, cal_id_hidden],
    )
    cal_refresh_btn.click(
        fn=refresh_calendar_entries,
        inputs=[cal_filter],
        outputs=[cal_dropdown, cal_detail],
    )
    cal_delete_btn.click(
        fn=delete_calendar_entry,
        inputs=[cal_dropdown],
        outputs=[cal_status_msg, cal_dropdown, cal_detail],
    )
    cal_dropdown.change(
        fn=load_calendar_entry_for_edit,
        inputs=[cal_dropdown],
        outputs=[cal_id_hidden, cal_title, cal_topic, cal_platforms, cal_date, cal_note_file, cal_status],
    )
    cal_update_btn.click(
        fn=update_calendar_entry,
        inputs=[cal_id_hidden, cal_title, cal_topic, cal_platforms, cal_date, cal_note_file, cal_status],
        outputs=[cal_status_msg, cal_detail],
    )
    cal_clear_btn.click(
        fn=clear_calendar_form,
        inputs=[],
        outputs=[cal_id_hidden, cal_title, cal_topic, cal_platforms, cal_date, cal_note_file, cal_status, cal_status_msg],
    )

    # 历史页事件绑定
    def refresh_history_list(history):
        if not history:
            return gr.Dropdown(choices=[]), "暂无历史记录"
        choices = [(f"{i+1}. {h.get('note_preview', h.get('note', '无标题'))[:40]}...", i) for i, h in enumerate(history)]
        return gr.Dropdown(choices=choices), f"✅ 已加载 {len(history)} 条历史记录"

    def show_history_detail(idx, history):
        if idx is None or idx < 0 or idx >= len(history):
            return "请选择一条历史记录"
        h = history[idx]
        ts = h.get("time", h.get("timestamp", "未知"))
        note_src = h.get('note_preview', h.get('note', '无标题'))
        return f"""**笔记来源**: {note_src[:80]}...

**生成时间**: {ts}

**小红书**:
{h.get('xiaohongshu', '')[:300]}...

**公众号**:
{h.get('gongzhonghao', '')[:300]}...

**抖音**:
{h.get('douyin', '')[:300]}...
"""

    def clear_all_history():
        return [], gr.Dropdown(choices=[]), "✅ 历史记录已清空"

    # 页面切换时自动刷新历史列表
    main_tabs.select(
        fn=refresh_history_list,
        inputs=[history_state],
        outputs=[history_dropdown_big, history_detail],
    )

    history_dropdown_big.change(
        fn=show_history_detail,
        inputs=[history_dropdown_big, history_state],
        outputs=[history_detail],
    )

    restore_big_btn.click(
        fn=restore_history,
        inputs=[history_dropdown_big, history_state],
        outputs=[
            xiaohongshu_output,
            gongzhonghao_output,
            douyin_output,
            xiaohongshu_preview,
            tags_output,
            status_text,
        ],
    )

    clear_history_big_btn.click(
        fn=clear_all_history,
        inputs=[],
        outputs=[history_state, history_dropdown_big, history_detail],
    )

    # ========== 配置模板事件绑定 ==========
    template_dropdown.change(
        fn=on_template_select,
        inputs=[template_dropdown],
        outputs=[
            platform_check,
            enable_research,
            search_engine,
            style_radio,
            batch_mode,
            template_delete_btn,
            status_text,
        ],
    )

    def _save_template_and_refresh(name, platforms, enable_research, search_engine, style, batch_mode):
        msg, _ = on_template_save(name, platforms, enable_research, search_engine, style, batch_mode)
        return msg, gr.update(choices=_build_template_choices()), ""

    template_save_btn.click(
        fn=_save_template_and_refresh,
        inputs=[template_save_name, platform_check, enable_research, search_engine, style_radio, batch_mode],
        outputs=[status_text, template_dropdown, template_save_name],
    )

    def _delete_template_and_refresh(template_id):
        msg, _ = on_template_delete(template_id)
        return msg, gr.update(choices=_build_template_choices(), value=None), gr.update(visible=False, interactive=False)

    template_delete_btn.click(
        fn=_delete_template_and_refresh,
        inputs=[template_dropdown],
        outputs=[status_text, template_dropdown, template_delete_btn],
    )

    gr.Markdown("""
    ---
    📖 [GitHub](https://github.com/lts1125/content-agent) | 本地工具版: `python main.py -i notes.md`
    """)


if __name__ == "__main__":
    logger.info("=== __main__ 开始执行 ===")
    # 检查 API Key，未配置时提示但不退出（用户可在 Web UI 中配置）
    ok, msg = get_config_status()
    logger.info(f"API Key 检查: ok={ok}, msg={msg}")
    if not ok:
        print(f"⚠️ {msg}")
        print("💡 提示: 启动后请在页面顶部的「模型配置」中填写 API Key\n")
    else:
        print(f"✅ {msg}\n")

    # 自己找一个可用端口，避免 Gradio 内部用端口 0 导致验证失败
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        free_port = s.getsockname()[1]
    logger.info(f"预分配端口: {free_port}")

    print("🚀 启动 Content Agent Web UI...")
    print(f"📎 打开浏览器访问: http://127.0.0.1:{free_port}")
    print("📡 按 Ctrl+C 停止服务\n")

    # 启动定时任务调度器
    try:
        _get_scheduler()
        logger.info("定时任务调度器已启动")
    except Exception as e:
        logger.warning(f"定时任务调度器启动失败: {e}")
        print(f"[定时任务] 后台调度器启动失败: {e}")
        print("[定时任务] 提示: 运行 `pip install schedule` 可启用定时任务功能\n")

    logger.info(f"即将调用 demo.launch(port={free_port})")
    demo.launch(
        server_name="0.0.0.0",
        server_port=free_port,
        show_error=True,
        share=False,
        inbrowser=True,
    )
    logger.info("demo.launch 已返回（不应该走到这里）")
