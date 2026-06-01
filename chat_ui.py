#!/usr/bin/env python3
"""
Content Agent - 聊天式 Web UI

基于 Gradio 的聊天界面，支持：
- 自然语言对话
- Agent 自动分析用户需求
- 自动选择平台、策略
- 生成内容并展示

运行: python chat_ui.py
"""

import os
import sys
import json
import logging
import queue
import re
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

# 调试日志
_LOG_PATH = os.getenv(
    "CHAT_UI_LOG_PATH",
    os.path.join(os.path.expanduser("~"), ".content_agent", "chat_ui.log"),
)
try:
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
except OSError:
    _LOG_PATH = os.path.join(Path(__file__).resolve().parent, "data", "logs", "chat_ui.log")
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
try:
    logging.basicConfig(
        filename=_LOG_PATH,
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
except OSError:
    _LOG_PATH = os.path.join(Path(__file__).resolve().parent, "data", "logs", "chat_ui.log")
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    logging.basicConfig(
        filename=_LOG_PATH,
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
logger = logging.getLogger("chat_ui")

logger.info("=== chat_ui 初始化开始 ===")

from dotenv import load_dotenv
load_dotenv()

try:
    import gradio as gr
except ImportError as e:
    print(f"❌ Gradio 导入失败: {e}")
    print("提示: pip install gradio")
    sys.exit(1)


def _patch_gradio_api_info_for_compatibility():
    if getattr(gr.Blocks, "_content_agent_api_info_patched", False):
        return

    original_get_api_info = gr.Blocks.get_api_info

    def safe_get_api_info(self, *args, **kwargs):
        try:
            return original_get_api_info(self, *args, **kwargs)
        except Exception as exc:
            # Log the real error so we can diagnose version mismatches in Docker.
            logger.warning(
                "Gradio get_api_info() failed (%s: %s). "
                "Falling back to empty endpoints so the UI can still submit events.",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return {"named_endpoints": {}, "unnamed_endpoints": {}}

    gr.Blocks.get_api_info = safe_get_api_info
    gr.Blocks._content_agent_api_info_patched = True


_patch_gradio_api_info_for_compatibility()

# Patch starlette TemplateResponse to bridge Gradio 4's old-style calls with newer starlette.
def _patch_starlette_template_response():
    try:
        from starlette.templating import Jinja2Templates
    except ImportError:
        return

    if getattr(Jinja2Templates, "_content_agent_template_patched", False):
        return

    _orig = Jinja2Templates.TemplateResponse

    def _patched(self, *args, **kwargs):
        # Gradio 4.44.x passes old-style positional args: TemplateResponse(name, context)
        # Newer starlette expects: TemplateResponse(request, name, context)
        if args and isinstance(args[0], str):
            name = args[0]
            context = args[1] if len(args) > 1 else kwargs.get("context", {})
            status_code = args[2] if len(args) > 2 else kwargs.get("status_code", 200)
            headers = args[3] if len(args) > 3 else kwargs.get("headers")
            media_type = args[4] if len(args) > 4 else kwargs.get("media_type")
            background = args[5] if len(args) > 5 else kwargs.get("background")

            if "request" not in context:
                raise ValueError('context must include a "request" key')
            request = context["request"]

            return _orig(
                self,
                request,
                name,
                context=context,
                status_code=status_code,
                headers=headers,
                media_type=media_type,
                background=background,
            )
        return _orig(self, *args, **kwargs)

    Jinja2Templates.TemplateResponse = _patched
    Jinja2Templates._content_agent_template_patched = True


_patch_starlette_template_response()

# 导入 Agent 组件
from agents.tools import execute_tool
from agents.planning import StrategySelector, AutonomousPlanner
from agents.schemas import WriterOutput
from agents.memory import MemoryManager
from agents.store import init_db
from content_agent.html_renderer import XiaohongshuRenderer


# ==================== 聊天核心逻辑 ====================

PLATFORM_LABELS = {
    "gongzhonghao": "公众号",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
}

PROGRESS_ICONS = {
    "done": "✅",
    "running": "🔄",
    "warning": "⚠️",
    "pending": "○",
}

REVISION_TASK_RE = re.compile(r"(chat_\d{8}_\d{6})")
REVISION_KEYWORDS = [
    "刚才那篇",
    "上一版",
    "上一次",
    "前面那篇",
    "这篇文章",
    "上面这篇",
    "刚才生成",
    "刚生成",
    "继续改",
    "继续修改",
    "继续优化",
]


def _format_progress_message(events: list) -> str:
    """把执行事件渲染成聊天里的进度消息。"""
    if not events:
        return "🔄 **正在处理...**"

    lines = ["🔄 **正在生成内容...**", ""]
    for event in events:
        icon = PROGRESS_ICONS.get(event.get("status", "pending"), "○")
        title = event.get("title") or event.get("step", "执行步骤")
        step_index = event.get("step_index")
        total_steps = event.get("total_steps")
        prefix = f"Step {step_index}/{total_steps} · " if step_index and total_steps else ""
        detail = event.get("detail", "")
        lines.append(f"{icon} {prefix}{title}")
        if detail:
            lines.append(f"   {detail}")
    return "\n".join(lines)


def _merge_progress_event(events: list, event: dict) -> list:
    """同一个 step 更新状态，不同 step 追加到末尾。"""
    step = event.get("step")
    merged = list(events)
    for idx, item in enumerate(merged):
        if item.get("step") == step:
            merged[idx] = {**item, **event}
            return merged
    merged.append(event)
    return merged


def _extract_revision_task_id(message: str) -> Optional[str]:
    match = REVISION_TASK_RE.search(message or "")
    return match.group(1) if match else None


def _is_revision_request(message: str) -> bool:
    msg = message or ""
    return bool(_extract_revision_task_id(msg)) or any(keyword in msg for keyword in REVISION_KEYWORDS)


def _select_gongzhonghao_file(files: list) -> Optional[str]:
    if not files:
        return None
    return next((f for f in files if "gongzhonghao" in f and str(f).endswith(".md")), None)


def _build_revision_notes_from_history(memory, message: str) -> tuple[Optional[str], Optional[dict]]:
    """根据用户修改指令，从历史任务中读取待修改公众号文章。"""
    if not _is_revision_request(message):
        return None, None

    target_task_id = _extract_revision_task_id(message)
    history = memory.list_generated_history(limit=50)

    selected = None
    selected_file = None
    for item in history:
        if target_task_id and item.get("task_id") != target_task_id:
            continue
        files = _safe_json_load(item.get("files"), [])
        gzh_file = _select_gongzhonghao_file(files)
        if gzh_file:
            selected = item
            selected_file = gzh_file
            break

    if not selected or not selected_file:
        if target_task_id:
            raise ValueError(f"没有找到 task {target_task_id} 对应的公众号文章文件")
        raise ValueError("没有找到可继续修改的历史公众号文章")

    article_path = Path(selected_file)
    if not article_path.exists():
        raise ValueError(f"历史文章文件不存在: {selected_file}")

    article = article_path.read_text(encoding="utf-8")
    task_id = selected.get("task_id") or ""
    notes = (
        f"【上一版公众号文章】\n{article}\n\n"
        f"【修改要求】\n{message.strip()}\n\n"
        "【输出要求】\n"
        "- 基于上一版文章进行修改，不要凭空换主题\n"
        "- 输出修改后的微信公众号文章\n"
    )
    return notes, {
        "task_id": task_id,
        "file": selected_file,
        "session_id": selected.get("session_id", ""),
    }


def _save_generated_markdown_files(content, platforms: list, output_dir: Path) -> list[str]:
    """保存各平台 Markdown，小红书同步生成 HTML 配图，并打包成 zip 供一键下载，返回可下载的文件列表。"""
    files = []

    for platform in platforms:
        text = getattr(content, platform, "")
        if not text:
            continue

        file_path = output_dir / f"{platform}.md"
        file_path.write_text(text, encoding="utf-8")
        files.append(str(file_path))

        # 小红书同步生成 HTML 配图
        if platform == "xiaohongshu":
            try:
                renderer = XiaohongshuRenderer()
                html_path = Path(renderer.render(text, output_dir))
                target_html = output_dir / "xiaohongshu.html"
                html_path.rename(target_html)
                files.append(str(target_html))
            except Exception as e:
                logger.warning(f"小红书 HTML 配图生成失败: {e}")

    # 小红书：将 md + html 打包成 zip，方便一键下载
    xhs_md = output_dir / "xiaohongshu.md"
    xhs_html = output_dir / "xiaohongshu.html"
    if xhs_md.exists() and xhs_html.exists():
        import zipfile
        zip_path = output_dir / "xiaohongshu.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(xhs_md, xhs_md.name)
            zf.write(xhs_html, xhs_html.name)
        files.append(str(zip_path))

    return files


def _download_button_updates(files):
    files = files or []
    by_platform = {Path(file).stem: file for file in files}
    return (
        gr.update(value=by_platform.get("gongzhonghao"), visible=bool(by_platform.get("gongzhonghao"))),
        gr.update(value=by_platform.get("xiaohongshu"), visible=bool(by_platform.get("xiaohongshu"))),
        gr.update(value=by_platform.get("douyin"), visible=bool(by_platform.get("douyin"))),
    )


def _safe_json_load(value, default=None):
    if value is None:
        return default if default is not None else []
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default if default is not None else []
    return default if default is not None else []


def _format_memory_refs(memory_refs: list[dict]) -> str:
    """把本次 RAG 引用来源渲染为给用户看的 Markdown。"""
    if not memory_refs:
        return "\n\n📚 **本次参考资料：** 未使用历史笔记，仅基于当前输入生成。"

    lines = ["", "", f"📚 **本次参考了 {len(memory_refs)} 条历史笔记：**"]
    for idx, ref in enumerate(memory_refs, start=1):
        title = ref.get("title") or "未命名笔记"
        source = ref.get("source") or "未知来源"
        heading = ref.get("heading") or ""
        snippet = (ref.get("snippet") or "").replace("\n", " ").strip()
        heading_part = f" / {heading}" if heading else ""
        lines.append(f"{idx}. **{title}**{heading_part}（{source}）")
        if snippet:
            lines.append(f"   - {snippet[:120]}...")
    return "\n".join(lines)


def _format_generated_history(items: list[dict], limit: int = 8) -> str:
    """把生成历史渲染为 Markdown，供页面面板和系统命令复用。"""
    if not items:
        return "📚 暂无生成历史。生成公众号文章后，这里会显示最近记录。"

    lines = [
        "📚 **近期生成历史**",
        "",
        "可在输入框里说：`修改 task chat_YYYYMMDD_HHMMSS，把开头写得更抓人`。",
        "",
    ]
    for item in items[:limit]:
        sid = item["session_id"][:8]
        task_id = item.get("task_id") or "-"
        platforms = _safe_json_load(item.get("platforms"), [])
        files = _safe_json_load(item.get("files"), [])
        labels = "、".join(PLATFORM_LABELS.get(p, p) for p in platforms) or "未知平台"
        main_file = next((f for f in files if "gongzhonghao" in f and f.endswith(".md")), None)
        if main_file is None and files:
            main_file = files[0]
        lines.append(f"- **{labels}** — {item['created_at']} — 会话 `{sid}...`")
        lines.append(f"  - task: `{task_id}`")
        if main_file:
            lines.append(f"  - 文件: `{main_file}`")
    return "\n".join(lines)


def _result_to_response(result: dict) -> tuple[str, str, list[str], bool]:
    """把 Agent 结果转换为聊天文本、公众号文件路径、下载文件列表和是否显示审核按钮。"""
    gzh_path = ""
    download_files = []
    show_review = False
    if result["type"] == "content":
        response = result["content"]
        download_files = result.get("files", [])
        if result.get("files"):
            response += "\n\n📁 **生成文件：**\n"
            for f in result["files"]:
                response += f"- {f}\n"
            for f in result["files"]:
                if "gongzhonghao" in f:
                    gzh_path = f
                    break
        if download_files:
            response += "\n📥 可以在下方按文件下载 Markdown。"
    elif result["type"] == "review":
        response = result["content"]
        show_review = True
    else:
        response = result["content"]
    return response, gzh_path, download_files, show_review


def _scale_html(html: str, scale: float = 0.48) -> str:
    def replace_px(match):
        val = int(match.group(1))
        if val <= 3:
            return match.group(0)
        scaled = max(1, int(val * scale))
        return f"{scaled}px"
    return re.sub(r'(\d+)px', replace_px, html)


def _render_xiaohongshu_preview(text: str) -> str:
    if not text or text.startswith("❌") or text == "（未选择此平台）":
        return ""
    try:
        renderer = XiaohongshuRenderer()
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = renderer.render(text, Path(tmpdir))
            html_content = Path(html_path).read_text(encoding="utf-8")
            return _scale_html(html_content, scale=0.48)
    except Exception as e:
        logger.warning(f"小红书 HTML 预览生成失败: {e}")
        return ""


def _copy_chat_history(chat_history: list) -> list:
    return [dict(item) for item in chat_history]


def _detect_requested_platforms(message: str) -> list:
    """优先从末尾生成指令判断平台，避免正文里的平台词误触发。"""
    message_lower = message.lower()
    non_empty_lines = [line.strip().lower() for line in message.splitlines() if line.strip()]
    last_line = non_empty_lines[-1] if non_empty_lines else message_lower
    if any(kw in last_line for kw in ["写", "生成", "创作", "改写", "整理"]):
        instruction_text = last_line
    else:
        instruction_text = message_lower[-120:]

    explicit_platforms = []
    explicit_patterns = [
        ("gongzhonghao", [r"(微信)?公众号(文章|长文|推文)?", r"wechat"]),
        ("xiaohongshu", [r"小红书(笔记|文案|帖子)?"]),
        ("douyin", [r"抖音(文案|脚本|口播|视频文案)?"]),
    ]

    for platform, patterns in explicit_patterns:
        if any(re.search(pattern, instruction_text) for pattern in patterns):
            explicit_platforms.append(platform)

    if explicit_platforms:
        return explicit_platforms

    platforms = []
    if "公众号" in message_lower or "微信" in message_lower:
        platforms.append("gongzhonghao")
    if "小红书" in message_lower:
        platforms.append("xiaohongshu")
    if "抖音" in message_lower:
        platforms.append("douyin")

    return platforms or ["gongzhonghao"]


def _extract_topic_or_source(message: str) -> tuple:
    """从请求中提取素材或短主题，保留正文里的原始措辞。"""
    original = message.strip()
    source = re.sub(
        r"\n*\s*根据(以上|上述|这些)?内容\s*(帮我|请|麻烦)?(写|生成|创作|改写|整理).*$",
        "",
        original,
        flags=re.S,
    ).strip()

    if source != original and len(source) >= 50:
        return source, True

    topic = original
    topic = re.sub(r"^\s*(帮我|请|麻烦|想要)?\s*(写|生成|创作|来)\s*(一篇|一个)?\s*", "", topic)
    topic = re.sub(r"\s*(的)?\s*(微信)?公众号(文章|长文|推文)?\s*$", "", topic)
    topic = re.sub(r"\s*小红书(笔记|文案|帖子)?\s*$", "", topic)
    topic = re.sub(r"\s*抖音(文案|脚本|口播|视频文案)?\s*$", "", topic)
    topic = topic.strip(" ，。:：\n\t")

    return topic or original, False


def _extract_writing_requirements(message: str) -> dict:
    """提取用户自然语言里的写作要求，用于稳定控制生成风格。"""
    requirements = {
        "audience": "",
        "tone": "",
        "style_reference": "",
        "avoid": [],
        "gongzhonghao_mode": "",
    }

    audience_match = re.search(r"给(.{1,12}?)(介绍|讲|写|科普)", message)
    if not audience_match:
        audience_match = re.search(r"面向(.{1,12}?)(读者|用户|人群|，|,|。|$)", message)
    if audience_match:
        requirements["audience"] = audience_match.group(1).strip(" 的，,。")

    tone_keywords = [
        "通俗易懂",
        "大白话",
        "口语化",
        "专业一点",
        "专业严谨",
        "轻松一点",
        "有故事感",
        "犀利一点",
        "克制一点",
        "接地气",
    ]
    matched_tones = [kw for kw in tone_keywords if kw in message]
    if matched_tones:
        requirements["tone"] = "、".join(matched_tones)

    popular_audience_keywords = ["普通人", "小白", "零基础", "非技术", "大众", "新手", "外行"]
    popular_style_keywords = ["通俗易懂", "大白话", "科普", "接地气", "少用术语", "不要太技术", "别太技术"]
    if (
        any(kw in requirements.get("audience", "") for kw in popular_audience_keywords)
        or any(kw in message for kw in popular_audience_keywords + popular_style_keywords)
    ):
        requirements["gongzhonghao_mode"] = "popular_science"

    style_match = re.search(r"像(.{2,30}?)(一样|那样|的风格|风格|类似|，|,|。|$)", message)
    if style_match:
        requirements["style_reference"] = style_match.group(1).strip(" ，,。")

    avoid_patterns = [
        r"少用[^，,。；;]{1,12}",
        r"不要[^，,。；;]{1,16}",
        r"别[^，,。；;]{1,16}",
        r"避免[^，,。；;]{1,16}",
    ]
    avoid_items = []
    for pattern in avoid_patterns:
        for match in re.findall(pattern, message):
            item = match.strip(" ，,。")
            if item and item not in avoid_items:
                avoid_items.append(item)
    requirements["avoid"] = avoid_items

    return requirements


def _strip_writing_requirements_from_topic(topic: str) -> str:
    """从短主题中移除附加风格指令，避免主题变得啰嗦。"""
    cleaned = topic
    split_patterns = [
        r"[，,。]\s*讲得.*$",
        r"[，,。]\s*讲的.*$",
        r"[，,。]\s*用.*风格.*$",
        r"[，,。]\s*像.*$",
        r"[，,。]\s*少用.*$",
        r"[，,。]\s*不要.*$",
        r"[，,。]\s*别.*$",
        r"[，,。]\s*避免.*$",
    ]
    for pattern in split_patterns:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = re.sub(r"\s*(的)?\s*(微信)?公众号(文章|长文|推文)?\s*$", "", cleaned)
    cleaned = re.sub(r"\s*小红书(笔记|文案|帖子)?\s*$", "", cleaned)
    cleaned = re.sub(r"\s*抖音(文案|脚本|口播|视频文案)?\s*$", "", cleaned)
    return cleaned.strip(" ，,。") or topic


def _format_writing_requirements(requirements: dict) -> str:
    lines = []
    if requirements.get("audience"):
        lines.append(f"- 目标读者：{requirements['audience']}")
    if requirements.get("tone"):
        lines.append(f"- 表达语气：{requirements['tone']}")
    if requirements.get("gongzhonghao_mode") == "popular_science":
        lines.append("- 公众号模式：通俗科普")
    if requirements.get("style_reference"):
        lines.append(
            "- 风格参考："
            f"{requirements['style_reference']}（提炼其抽象表达特征，不直接仿写具体个人措辞）"
        )
    if requirements.get("avoid"):
        lines.append(f"- 避免事项：{'；'.join(requirements['avoid'])}")
    if not lines:
        return ""
    return "## 写作要求\n\n" + "\n".join(lines)


def _build_generation_notes(topic: str, research_report: str, intent: dict) -> str:
    requirements_text = _format_writing_requirements(intent.get("writing_requirements", {}))

    if intent.get("has_source_material"):
        parts = [topic]
    else:
        parts = [f"# {topic}"]
        if research_report:
            parts.extend(["## 搜索资料", research_report])
        parts.extend(["## 主题", topic])

    if requirements_text:
        parts.append(requirements_text)

    return "\n\n".join(part for part in parts if part)


def _uploaded_file_path(uploaded_file) -> Path:
    """兼容 Gradio filepath / file dict / tempfile object。"""
    if uploaded_file is None:
        return None
    if isinstance(uploaded_file, (str, Path)):
        return Path(uploaded_file)
    if isinstance(uploaded_file, dict) and uploaded_file.get("path"):
        return Path(uploaded_file["path"])
    name = getattr(uploaded_file, "name", "")
    if name:
        return Path(name)
    return None


def _read_uploaded_note_file(uploaded_file) -> str:
    """读取上传的 Markdown 或纯文本笔记。"""
    path = _uploaded_file_path(uploaded_file)
    if path is None:
        return ""
    suffix = path.suffix.lower()
    if suffix not in (".md", ".txt"):
        raise ValueError("仅支持上传 .md 或 .txt 笔记文件")
    return path.read_text(encoding="utf-8")


def _merge_uploaded_note_with_message(message: str, uploaded_file) -> str:
    """把上传笔记作为素材，把输入框内容作为生成指令。"""
    note_text = _read_uploaded_note_file(uploaded_file).strip()
    instruction = (message or "").strip()
    if not instruction:
        instruction = "生成一篇公众号文章"
    return f"{note_text}\n\n根据以上内容，{instruction}"


class ChatAgent:
    """聊天 Agent，处理用户消息并执行内容生成"""
    
    def __init__(self):
        self.selector = StrategySelector()
        self.planner = AutonomousPlanner()
        self.history = []
        self.memory = MemoryManager()
        self.session_id = str(uuid.uuid4())
    
    def reset_session(self):
        """重置会话，保留旧会话历史"""
        self.session_id = str(uuid.uuid4())
        self.history = []
    
    def process_message(self, user_message: str) -> dict:
        """
        处理用户消息，分析意图并执行
        
        Returns:
            {
                "type": "text" | "content" | "error",
                "content": str,
                "platforms": list,
                "files": list,
            }
        """
        logger.info(f"用户消息: {user_message}")
        
        # 1. 分析用户意图
        intent = self._analyze_intent(user_message)
        logger.info(f"意图分析: {intent}")
        
        # 2. 根据意图执行
        if intent["type"] == "generate":
            return self._handle_generate(intent, user_message)
        elif intent["type"] == "help":
            return self._handle_help()
        elif intent["type"] == "status":
            return self._handle_status()
        else:
            return {
                "type": "text",
                "content": "我不太理解你的需求。你可以说：\n- '帮我写一篇关于XXX的公众号文章'\n- '生成小红书笔记：程序员健身指南'\n- '把这篇笔记改写成抖音文案'",
            }

    def process_message_stream(self, user_message: str):
        """处理用户消息，并产出可用于 UI 的进度事件。"""
        logger.info(f"用户消息: {user_message}")

        # 1. 保存用户消息到短期记忆
        self.memory.save_turn(self.session_id, "user", user_message)

        # 2. 处理系统命令
        sys_result = self._handle_system_command(user_message)
        if sys_result:
            self.memory.save_turn(self.session_id, "assistant", sys_result.get("content", ""))
            yield {"type": "result", "result": sys_result}
            return

        yield {
            "type": "progress",
            "event": {
                "step": "analyze-intent",
                "title": "分析需求",
                "status": "running",
                "detail": "正在识别主题、平台和写作要求",
            },
        }
        intent = self._analyze_intent(user_message)
        logger.info(f"意图分析: {intent}")

        if intent["type"] == "generate":
            labels = "、".join(PLATFORM_LABELS.get(p, p) for p in intent["platforms"])
            yield {
                "type": "progress",
                "event": {
                    "step": "analyze-intent",
                    "title": "分析需求",
                    "status": "done",
                    "detail": f"已识别目标平台：{labels}",
                },
            }
            yield from self._handle_generate_stream(intent, user_message)
            return

        if intent["type"] == "help":
            result = self._handle_help()
            self.memory.save_turn(self.session_id, "assistant", result.get("content", ""))
            yield {"type": "result", "result": result}
            return

        if intent["type"] == "status":
            result = self._handle_status()
            self.memory.save_turn(self.session_id, "assistant", result.get("content", ""))
            yield {"type": "result", "result": result}
            return

        fallback = {
            "type": "text",
            "content": "我不太理解你的需求。你可以说：\n- '帮我写一篇关于XXX的公众号文章'\n- '生成小红书笔记：程序员健身指南'\n- '把这篇笔记改写成抖音文案'",
        }
        self.memory.save_turn(self.session_id, "assistant", fallback["content"])
        yield {
            "type": "result",
            "result": fallback,
        }
    
    def _analyze_intent(self, message: str) -> dict:
        """分析用户意图"""
        message_lower = message.lower()
        
        # 检查是否是生成请求
        generate_keywords = ["写", "生成", "创作", "来一篇", "帮我", "想要"]
        is_generate = any(kw in message_lower for kw in generate_keywords) or _is_revision_request(message)
        
        if is_generate:
            platforms = _detect_requested_platforms(message)
            topic, has_source_material = _extract_topic_or_source(message)
            writing_requirements = _extract_writing_requirements(message)
            if not has_source_material:
                topic = _strip_writing_requirements_from_topic(topic)
            
            return {
                "type": "generate",
                "platforms": platforms,
                "topic": topic,
                "has_source_material": has_source_material,
                "writing_requirements": writing_requirements,
            }
        
        # 检查是否是帮助请求
        if "帮助" in message_lower or "help" in message_lower or "怎么用" in message_lower:
            return {"type": "help"}
        
        # 检查是否是状态请求
        if "状态" in message_lower or "进度" in message_lower:
            return {"type": "status"}
        
        return {"type": "unknown"}
    
    def _handle_generate(self, intent: dict, original_message: str) -> dict:
        """处理生成请求"""
        platforms = intent["platforms"]
        topic = intent["topic"]
        has_source_material = intent.get("has_source_material", False)
        
        # 如果没有提取到主题，使用原始消息
        if not topic or len(topic) < 5:
            topic = original_message
        
        try:
            # 1. 构建笔记。用户贴了完整素材时，优先忠实使用素材，避免搜索结果覆盖主题。
            if has_source_material:
                raw_notes = _build_generation_notes(topic, "", intent)
            else:
                search_result = execute_tool("search", query=topic[:200])
                research_report = search_result.data if search_result.success else ""
                raw_notes = _build_generation_notes(topic, research_report, intent)
            
            # 2. 选择策略
            strategy = self.selector.select(raw_notes)
            
            # 3. 执行生成
            result = self.planner.plan_and_execute(raw_notes, platforms, strategy)
            
            # 5. 构建响应
            content = result.get("content")
            if not content:
                return {
                    "type": "error",
                    "content": "生成失败，请重试",
                }
            
            # 构建输出文本
            output_text = f"✅ 已生成 {len(platforms)} 个平台的内容\n\n"
            output_text += f"📋 使用策略: {strategy.name}\n"
            output_text += f"📊 评分: {result.get('verdict', {}).overall if result.get('verdict') else 'N/A'}/100\n\n"
            
            for platform in platforms:
                text = getattr(content, platform, "")
                if text:
                    output_text += f"---\n\n### {PLATFORM_LABELS.get(platform, platform)}\n\n{text[:500]}...\n\n"

            output_dir = Path("output/chat") / datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir.mkdir(parents=True, exist_ok=True)
            files = _save_generated_markdown_files(content, platforms, output_dir)
            
            return {
                "type": "content",
                "content": output_text,
                "platforms": platforms,
                "files": files,
            }
            
        except Exception as e:
            logger.error(f"生成失败: {e}", exc_info=True)
            return {
                "type": "error",
                "content": f"生成失败: {str(e)}",
            }

    def _handle_generate_stream(self, intent: dict, original_message: str):
        """处理生成请求，并在关键阶段产出进度事件。"""
        platforms = intent["platforms"]
        topic = intent["topic"] or original_message
        has_source_material = intent.get("has_source_material", False)
        revision_meta = None
        if not topic or len(topic) < 5:
            topic = original_message

        try:
            revision_notes, revision_meta = _build_revision_notes_from_history(self.memory, original_message)
            if revision_notes:
                raw_notes = revision_notes
                topic = f"修改历史文章 {revision_meta.get('task_id') or ''}".strip()
                if "gongzhonghao" not in platforms:
                    platforms = ["gongzhonghao"]
                yield {
                    "type": "progress",
                    "event": {
                        "step": "prepare-notes",
                        "title": "读取历史文章",
                        "status": "done",
                        "detail": f"已读取历史任务：{revision_meta.get('task_id') or revision_meta.get('file')}",
                    },
                }
            elif has_source_material:
                raw_notes = _build_generation_notes(topic, "", intent)
                yield {
                    "type": "progress",
                    "event": {
                        "step": "prepare-notes",
                        "title": "整理输入素材",
                        "status": "done",
                        "detail": "已使用你提供的笔记内容，不额外搜索覆盖主题",
                    },
                }
            else:
                yield {
                    "type": "progress",
                    "event": {
                        "step": "search-topic",
                        "title": "搜索相关资料",
                        "status": "running",
                        "detail": "正在搜索背景资料",
                    },
                }
                search_result = execute_tool("search", query=topic[:200])
                research_report = search_result.data if search_result.success else ""
                yield {
                    "type": "progress",
                    "event": {
                        "step": "search-topic",
                        "title": "搜索相关资料",
                        "status": "done" if search_result.success else "warning",
                        "detail": f"搜索完成（{len(research_report)} 字）" if search_result.success else f"搜索失败，继续使用主题生成：{search_result.error}",
                    },
                }
                raw_notes = _build_generation_notes(topic, research_report, intent)

            yield {
                "type": "progress",
                "event": {
                    "step": "select-strategy",
                    "title": "选择生成策略",
                    "status": "running",
                    "detail": "正在判断需要哪些工具和步骤",
                },
            }
            strategy = self.selector.select(raw_notes)
            if revision_meta:
                strategy.steps = [step for step in strategy.steps if step not in ("search", "browse", "analyze", "read", "execute")]
                strategy.tools = [tool for tool in strategy.tools if tool not in ("search", "browse", "analyze", "read", "execute")]
            yield {
                "type": "progress",
                "event": {
                    "step": "select-strategy",
                    "title": "选择生成策略",
                    "status": "done",
                    "detail": f"使用策略：{strategy.name}",
                },
            }

            # 注入记忆上下文，并保留引用来源用于前台展示
            memory_context, memory_refs = self._build_memory_context_with_refs(topic)
            if memory_context:
                raw_notes = f"{raw_notes}\n\n{memory_context}"

            progress_queue = queue.Queue()
            result_holder = {}

            def _on_progress(event: dict):
                progress_queue.put(event)

            def _run_plan():
                try:
                    result_holder["result"] = self.planner.plan_and_execute(
                        raw_notes,
                        platforms,
                        strategy,
                        progress_callback=_on_progress,
                        enable_review_panel=True,
                    )
                except Exception as exc:
                    result_holder["error"] = exc

            thread = threading.Thread(target=_run_plan)
            thread.start()
            while thread.is_alive():
                try:
                    while True:
                        yield {"type": "progress", "event": progress_queue.get_nowait()}
                except queue.Empty:
                    pass
                time.sleep(0.1)
            thread.join()
            try:
                while True:
                    yield {"type": "progress", "event": progress_queue.get_nowait()}
            except queue.Empty:
                pass

            if result_holder.get("error"):
                raise result_holder["error"]

            result = result_holder.get("result", {})
            content = result.get("content")
            if not content:
                yield {"type": "result", "result": {"type": "error", "content": "生成失败，请重试"}}
                return

            # 检查是否进入审核面板
            review_panel = result.get("review")
            if review_panel:
                from agents.review import ReviewManager
                panel = review_panel
                panel.raw_content = content
                panel.platforms = platforms
                # 保存到数据库
                task_id = getattr(self, "_current_task_id", self.session_id)
                ReviewManager.save_panel(panel, task_id)

                review_md = panel.to_markdown() + _format_memory_refs(memory_refs)
                yield {
                    "type": "result",
                    "result": {
                        "type": "review",
                        "panel": panel,
                        "content": review_md,
                        "raw_content": content,
                        "platforms": platforms,
                        "memory_refs": memory_refs,
                    },
                }
                return

            yield {
                "type": "progress",
                "event": {
                    "step": "save-files",
                    "title": "保存生成文件",
                    "status": "running",
                    "detail": "正在保存 Markdown 文件",
                },
            }

            output_text = f"✅ 已生成 {len(platforms)} 个平台的内容\n\n"
            output_text += f"📋 使用策略: {strategy.name}\n"
            output_text += f"📊 评分: {result.get('verdict', {}).overall if result.get('verdict') else 'N/A'}/100\n\n"
            if revision_meta:
                output_text += f"🔁 基于历史任务修改：`{revision_meta.get('task_id') or revision_meta.get('file')}`\n\n"

            files = []
            output_dir = Path("output/chat") / datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir.mkdir(parents=True, exist_ok=True)
            for platform in platforms:
                text = getattr(content, platform, "")
                if text:
                    output_text += f"---\n\n### {PLATFORM_LABELS.get(platform, platform)}\n\n{text[:500]}...\n\n"
            files = _save_generated_markdown_files(content, platforms, output_dir)
            output_text += _format_memory_refs(memory_refs)

            yield {
                "type": "progress",
                "event": {
                    "step": "save-files",
                    "title": "保存生成文件",
                    "status": "done",
                    "detail": f"已保存 {len(files)} 个文件",
                },
            }

            # 保存 assistant 回复到短期记忆
            self.memory.save_turn(
                self.session_id, "assistant", output_text,
                platforms=platforms, files=files,
                task_id=f"chat_{output_dir.name}",
            )

            yield {
                "type": "result",
                "result": {
                    "type": "content",
                    "content": output_text,
                    "platforms": platforms,
                    "files": files,
                    "memory_refs": memory_refs,
                },
            }
        except Exception as e:
            logger.error(f"生成失败: {e}", exc_info=True)
            error_text = f"生成失败: {str(e)}"
            self.memory.save_turn(self.session_id, "assistant", error_text)
            yield {
                "type": "result",
                "result": {
                    "type": "error",
                    "content": error_text,
                },
            }
    
    def _handle_help(self) -> dict:
        """处理帮助请求"""
        return {
            "type": "text",
            "content": """🤖 **Content Agent 使用指南**

你可以用自然语言和我对话：

**生成内容：**
- "帮我写一篇关于 Python 的公众号文章"
- "生成小红书笔记：程序员健身指南"
- "把这篇笔记改写成抖音文案"

**支持的平台：**
- 公众号（长文）
- 小红书（短笔记）
- 抖音（口播脚本）

**其他命令：**
- "帮助" - 显示使用指南
- "状态" - 查看系统状态

**提示：**
- 描述越详细，生成内容越精准
- 可以指定多个平台，用"和"连接
""",
        }
    
    def _handle_status(self) -> dict:
        """处理状态请求"""
        return {
            "type": "text",
            "content": """📊 **系统状态**

✅ Agent 核心: 运行中
✅ 工具系统: 正常
✅ 策略选择器: 正常
✅ 生成引擎: 正常

**可用工具：**
- 搜索 (search)
- 浏览 (browse)
- 文件读取 (read)
- 数据分析 (analyze)
- 代码执行 (execute)

**支持平台：**
- 公众号 (gongzhonghao)
- 小红书 (xiaohongshu)
- 抖音 (douyin)
""",
        }

    def _handle_system_command(self, message: str) -> Optional[dict]:
        """处理系统命令，以 #! 开头。

        支持的命令：
        - #!index [path] — 手动索引 Vault 或单个文件
        - #!search <query> — 测试向量检索
        - #!prefs — 查看当前用户偏好
        - #!sessions — 列出近期会话
        - #!history — 列出近期生成历史
        - #!memory — 查看向量库状态
        """
        msg = message.strip()
        if not msg.startswith("#!"):
            return None

        parts = msg[2:].strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "index":
            path = arg or os.getenv("VAULT_PATH", str(Path.home() / ".content_agent" / "vault"))
            count = self.memory.index_note(path)
            return {
                "type": "text",
                "content": f"📚 索引完成：共索引了 {count} 个 chunk\n路径: {path}",
            }

        if cmd == "search":
            if not arg:
                return {"type": "text", "content": "❌ 请提供检索词，例如: #!search MCP 协议"}
            results = self.memory.search_notes(arg, top_k=5)
            if not results:
                return {"type": "text", "content": f"🔍 未找到与“{arg}”相关的笔记"}
            lines = [f"🔍 检索结果：{arg}", ""]
            for r in results:
                lines.append(f"**{r.title}** ({r.source})")
                lines.append(f"{r.text[:200]}...")
                lines.append("")
            return {"type": "text", "content": "\n".join(lines)}

        if cmd == "prefs":
            prefs = self.memory.get_preferences()
            if not prefs:
                return {"type": "text", "content": "📝 当前没有设置偏好"}
            lines = ["📝 用户偏好", ""]
            for k, v in prefs.items():
                lines.append(f"- **{k}**: {v}")
            return {"type": "text", "content": "\n".join(lines)}

        if cmd == "sessions":
            sessions = self.memory.list_sessions(limit=10)
            if not sessions:
                return {"type": "text", "content": "📅 暂无会话记录"}
            lines = ["📅 近期会话", ""]
            for s in sessions:
                sid = s["session_id"][:8]
                lines.append(f"- `{sid}...` — {s['turn_count']} 轮 — {s['last_active']}")
            return {"type": "text", "content": "\n".join(lines)}

        if cmd == "history":
            items = self.memory.list_generated_history(limit=10)
            return {"type": "text", "content": _format_generated_history(items, limit=10)}

        if cmd == "memory":
            stats = self.memory.get_index_stats()
            return {
                "type": "text",
                "content": f"🧠 记忆状态\n- 向量库: {stats['status']} (共 {stats['count']} 条)",
            }

        if cmd == "help" or cmd == "":
            return {
                "type": "text",
                "content": """**系统命令**

- `#!index [path]` — 索引 Vault 目录或单个文件
- `#!search <query>` — 向量检索笔记
- `#!prefs` — 查看用户偏好
- `#!sessions` — 列出近期会话
- `#!history` — 列出近期生成历史
- `#!memory` — 查看向量库状态
""",
            }

        return None

    def _build_memory_context(self, topic: str) -> str:
        return self._build_memory_context_with_refs(topic)[0]

    def _build_memory_context_with_refs(self, topic: str) -> tuple[str, list[dict]]:
        """构建记忆上下文：包含用户偏好和相关笔记检索结果。

        返回 (上下文文本, 引用来源列表)。
        """
        parts = []
        memory_refs = []

        # 1. 用户偏好
        prefs = self.memory.get_preferences()
        if prefs:
            pref_lines = []
            tone = prefs.get("preferred_tone")
            if tone:
                pref_lines.append(f"风格: {tone}")
            platforms = prefs.get("favorite_platforms")
            if platforms:
                pref_lines.append(f"常用平台: {', '.join(platforms)}")
            length = prefs.get("preferred_length")
            if length:
                pref_lines.append(f"长度偏好: {length}")
            custom = prefs.get("custom_prompt")
            if custom:
                pref_lines.append(f"自定义要求: {custom}")
            if pref_lines:
                parts.append("## 用户偏好\n" + "\n".join(f"- {l}" for l in pref_lines))

        # 2. 向量检索相关笔记
        try:
            notes = self.memory.search_notes(topic, top_k=3, min_score=0.4)
            if notes:
                note_lines = []
                for n in notes:
                    note_lines.append(f"- **{n.title}** ({n.source}): {n.text[:150]}...")
                    memory_refs.append({
                        "id": n.id,
                        "title": n.title,
                        "source": n.source,
                        "heading": n.heading,
                        "distance": n.distance,
                        "snippet": n.text[:200],
                    })
                parts.append("## 相关笔记参考\n" + "\n".join(note_lines))
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")

        return "\n\n".join(parts), memory_refs


# ==================== Gradio 界面 ====================

def _respond_stream(agent, message, chat_history, note_file=None):
    """Gradio 流式响应：先显示进度，再替换为最终结果。"""
    display_message = message
    if note_file:
        note_path = _uploaded_file_path(note_file)
        if note_path:
            display_message = f"{message}\n\n📎 已上传笔记：{note_path.name}"

    chat_history = list(chat_history)
    chat_history.append({"role": "user", "content": display_message})

    try:
        # 检查原始消息是否是系统命令，上传笔记时不应干扰命令执行
        is_system_cmd = message.strip().startswith("#!")
        if note_file and not is_system_cmd:
            process_message = _merge_uploaded_note_with_message(message, note_file)
            # 用户上传笔记后自动索引到向量库
            try:
                note_path = _uploaded_file_path(note_file)
                if note_path:
                    indexed = agent.memory.index_note(str(note_path))
                    if indexed > 0:
                        logger.info(f"自动索引上传笔记: {note_path}, {indexed} chunks")
            except Exception as e:
                logger.warning(f"上传笔记自动索引失败: {e}")
        else:
            process_message = message
    except Exception as e:
        chat_history.append({"role": "assistant", "content": f"❌ 读取上传笔记失败: {e}"})
        yield "", _copy_chat_history(chat_history), "", *_download_button_updates([]), gr.update(value="", visible=False), gr.update(visible=False), None
        return

    progress_events = []
    progress_index = None
    gzh_path = ""
    download_files = []

    for payload in agent.process_message_stream(process_message):
        if payload.get("type") == "progress":
            progress_events = _merge_progress_event(progress_events, payload["event"])
            progress_content = _format_progress_message(progress_events)
            if progress_index is None:
                chat_history.append({"role": "assistant", "content": progress_content})
                progress_index = len(chat_history) - 1
            else:
                chat_history[progress_index]["content"] = progress_content
            yield "", _copy_chat_history(chat_history), gzh_path, *_download_button_updates(download_files), gr.update(value="", visible=False), gr.update(visible=False), None
            continue

        if payload.get("type") == "result":
            response, gzh_path, download_files, show_review = _result_to_response(payload["result"])
            if progress_index is None:
                chat_history.append({"role": "assistant", "content": response})
            else:
                chat_history[progress_index]["content"] = response
            xiaohongshu_html = ""
            for f in download_files:
                if Path(f).stem == "xiaohongshu" and f.endswith(".md"):
                    try:
                        text = Path(f).read_text(encoding="utf-8")
                        xiaohongshu_html = _render_xiaohongshu_preview(text)
                    except Exception as e:
                        logger.warning(f"小红书 HTML 预览生成失败: {e}")
                    break
            # 如果是 review 类型，保存 panel 到状态
            review_panel_data = None
            if payload["result"].get("type") == "review":
                review_panel_data = payload["result"].get("panel")
            yield (
                "",
                _copy_chat_history(chat_history),
                gzh_path,
                *_download_button_updates(download_files),
                gr.update(value=xiaohongshu_html, visible=bool(xiaohongshu_html) and not show_review),
                gr.update(visible=show_review),
                review_panel_data,
            )
            return

    if progress_index is not None:
        chat_history[progress_index]["content"] = "⚠️ 生成流程没有返回结果，请重试。"
    else:
        chat_history.append({"role": "assistant", "content": "⚠️ 生成流程没有返回结果，请重试。"})
    yield "", _copy_chat_history(chat_history), gzh_path, *_download_button_updates(download_files), gr.update(value="", visible=False), gr.update(visible=False), None


def create_chat_ui():
    """创建聊天界面"""
    init_db()  # 确保数据库表已创建
    agent = ChatAgent()

    def respond(message, chat_history, note_file=None):
        """处理用户消息"""
        yield from _respond_stream(agent, message, chat_history, note_file)
    
    def clear_history():
        """清空历史"""
        agent.reset_session()
        return [], "", *_download_button_updates([]), gr.update(value="", visible=False), gr.update(visible=False), None
    
    def publish_gzh(cover_image, gzh_file_path):
        """发布到微信公众号草稿箱"""
        if not gzh_file_path:
            return "❌ 请先生成公众号内容"
        if not cover_image:
            return "❌ 请上传封面图片"
        
        try:
            from content_agent.publisher import publish_wechat_draft
            # 读取文件内容提取标题（第一行 # 标题）
            content = Path(gzh_file_path).read_text(encoding="utf-8")
            title = content.splitlines()[0].lstrip("# ").strip() if content else "Generated Article"
            if not title:
                title = "Generated Article"
            
            result = publish_wechat_draft(
                markdown_path=gzh_file_path,
                title=title,
                cover_path=cover_image,
            )
            if result.get("success"):
                return f"✅ {result.get('message', '发布成功')}"
            else:
                return f"❌ {result.get('message', '发布失败')}\n详情: {result.get('details', '')}"
        except Exception as e:
            return f"❌ 发布异常: {str(e)}"

    def refresh_generated_history():
        """刷新历史任务面板"""
        items = agent.memory.list_generated_history(limit=8)
        return _format_generated_history(items, limit=8)
    
    # 构建界面 - 使用系统字体避免加载 Google Fonts（国内网络阻塞问题）
    theme = gr.themes.Soft(
        font=["system-ui", "SF Pro Display", "Segoe UI", "PingFang SC", "Microsoft YaHei", "sans-serif"],
        font_mono=["SF Mono", "SFMono-Regular", "Consolas", "Liberation Mono", "Menlo", "monospace"],
    )
    
    with gr.Blocks(
        title="Content Agent - 公众号内容生产工作台",
        theme=theme,
        css="""
        :root {
            --ca-bg: #f6f8fb;
            --ca-panel: #ffffff;
            --ca-border: #e5e7eb;
            --ca-muted: #64748b;
            --ca-text: #0f172a;
            --ca-blue: #4f63f6;
            --ca-blue-soft: #eef2ff;
            --ca-green: #10b981;
            --ca-green-soft: #ecfdf5;
            --ca-amber: #f59e0b;
            --ca-shadow: 0 14px 40px rgba(15, 23, 42, 0.06);
        }
        .gradio-container {
            background: var(--ca-bg) !important;
        }
        .workbench-shell {
            max-width: 1480px;
            margin: 0 auto;
        }
        .workbench-header {
            padding: 14px 22px 14px;
            border: 1px solid var(--ca-border);
            border-radius: 8px;
            background: var(--ca-panel);
            box-shadow: var(--ca-shadow);
            margin-bottom: 14px;
        }
        .header-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }
        .brand-line {
            display: flex;
            align-items: center;
            gap: 12px;
            color: var(--ca-text);
            font-weight: 700;
            font-size: 18px;
        }
        .brand-mark {
            width: 28px;
            height: 28px;
            border-radius: 8px;
            background: linear-gradient(135deg, #4f63f6, #10b981);
            box-shadow: 0 8px 20px rgba(79, 99, 246, 0.22);
        }
        .task-title {
            margin-top: 10px;
            font-size: 26px;
            line-height: 1.2;
            font-weight: 800;
            color: var(--ca-text);
            letter-spacing: 0;
        }
        .task-subtitle {
            margin-top: 6px;
            color: var(--ca-muted);
            font-size: 14px;
        }
        .status-strip {
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-end;
            gap: 8px;
        }
        .status-pill {
            border: 1px solid var(--ca-border);
            border-radius: 999px;
            padding: 6px 10px;
            color: var(--ca-muted);
            background: #fff;
            font-size: 13px;
            font-weight: 600;
        }
        .status-pill.active {
            color: #3730a3;
            background: var(--ca-blue-soft);
            border-color: #c7d2fe;
        }
        .workflow-steps {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-top: 14px;
        }
        .workflow-step {
            min-height: 38px;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--ca-border);
            border-radius: 8px;
            background: #f8fafc;
            color: #475569;
            font-weight: 650;
            font-size: 14px;
        }
        .workflow-step.done {
            background: var(--ca-green-soft);
            border-color: #bbf7d0;
            color: #047857;
        }
        .workflow-step.active {
            background: var(--ca-blue-soft);
            border-color: #c7d2fe;
            color: #3730a3;
        }
        .main-workbench {
            align-items: stretch;
        }
        .input-panel,
        .result-panel,
        .delivery-bar {
            border: 1px solid var(--ca-border);
            border-radius: 8px;
            background: var(--ca-panel);
            box-shadow: var(--ca-shadow);
            padding: 18px !important;
        }
        .input-panel {
            min-width: 320px;
        }
        .panel-title h3 {
            margin: 0 0 4px;
            color: var(--ca-text);
            font-size: 18px;
        }
        .panel-title p {
            margin: 0 0 14px;
            color: var(--ca-muted);
            font-size: 13px;
        }
        .preference-summary {
            border: 1px solid var(--ca-border);
            border-radius: 8px;
            padding: 12px;
            background: #f8fafc;
            color: #334155;
            font-size: 13px;
            line-height: 1.7;
            margin: 10px 0 12px;
        }
        .preference-summary strong {
            color: var(--ca-text);
        }
        .primary-action-row button {
            min-height: 44px;
        }
        .input-panel button.boundedheight {
            min-height: 150px !important;
            height: 150px !important;
        }
        .input-panel textarea {
            min-height: 120px !important;
        }
        .secondary-actions button {
            min-height: 36px;
        }
        .result-panel .wrap {
            gap: 12px;
        }
        .chatbot {
            border-radius: 8px !important;
            border: 1px solid var(--ca-border) !important;
        }
        .support-panels {
            margin-top: 12px;
        }
        .history-scroll {
            max-height: 360px;
            overflow-y: auto;
            border: 1px solid var(--ca-border);
            border-radius: 8px;
            background: #ffffff;
            padding: 12px 14px;
            margin-top: 10px;
        }
        .history-scroll .prose {
            max-width: none !important;
        }
        .history-scroll ul,
        .history-scroll ol {
            margin-bottom: 0;
        }
        .hint-list {
            margin: 0;
            padding-left: 18px;
            color: #475569;
            line-height: 1.7;
            font-size: 13px;
        }
        .delivery-bar {
            position: sticky;
            bottom: 8px;
            z-index: 20;
            margin-top: 14px;
            align-items: center;
            gap: 12px;
        }
        .delivery-bar button {
            min-height: 40px;
        }
        .delivery-title {
            color: var(--ca-text);
            font-size: 15px;
            font-weight: 750;
            margin-bottom: 4px;
        }
        .delivery-desc {
            color: var(--ca-muted);
            font-size: 13px;
            line-height: 1.6;
            margin-bottom: 10px;
        }
        .delivery-downloads {
            gap: 8px;
        }
        .delivery-status textarea {
            min-height: 42px !important;
        }
        .cover-upload-btn button {
            min-height: 42px !important;
            width: 100%;
        }
        @media (max-width: 900px) {
            .workflow-steps {
                grid-template-columns: repeat(2, 1fr);
            }
            .task-title {
                font-size: 24px;
            }
            .delivery-bar {
                position: static;
            }
        }
        """
    ) as demo:
        # 存储最后一次生成的公众号文件路径。State 必须创建在 Blocks 内，
        # 否则事件输出会引用未注册组件，导致 Gradio 前端/API 报错。
        last_gzh_file = gr.State("")

        with gr.Column(elem_classes=["workbench-shell"]):
            gr.HTML("""
            <section class="workbench-header">
              <div class="header-top">
                <div>
                  <div class="brand-line"><span class="brand-mark"></span><span>Content Agent</span></div>
                  <div class="task-title">公众号文章生成</div>
                  <div class="task-subtitle">把技术笔记整理成可审核、可下载、可保存到公众号草稿箱的文章。</div>
                </div>
                <div class="status-strip" aria-label="任务状态">
                  <span class="status-pill">待输入</span>
                  <span class="status-pill">生成中</span>
                  <span class="status-pill active">待审核</span>
                  <span class="status-pill">可发布</span>
                </div>
              </div>
              <div class="workflow-steps" aria-label="生成流程">
                <div class="workflow-step done">输入素材</div>
                <div class="workflow-step done">生成文章</div>
                <div class="workflow-step active">质量审核</div>
                <div class="workflow-step">保存草稿</div>
              </div>
            </section>
            """)

            with gr.Row(elem_classes=["main-workbench"]):
                with gr.Column(scale=4, elem_classes=["input-panel"]):
                    gr.Markdown(
                        "### 输入与偏好\n把笔记、主题和写作要求放在这里，默认优先生成公众号文章。",
                        elem_classes=["panel-title"],
                    )
                    note_upload = gr.File(
                        label="上传笔记（.md / .txt，可选）",
                        file_types=[".md", ".txt"],
                        type="filepath",
                    )
                    msg_input = gr.Textbox(
                        label="写作要求",
                        placeholder="例如：根据这篇笔记生成公众号文章，写给普通技术人，通俗易懂，少用术语，多举真实例子。",
                        lines=5,
                        max_lines=9,
                        show_label=True,
                    )
                    with gr.Row(elem_classes=["primary-action-row"]):
                        send_btn = gr.Button("发送", scale=2, variant="primary")
                        clear_btn = gr.Button("清空对话", scale=1, variant="secondary")
                    gr.HTML("""
                    <div class="preference-summary">
                      <strong>当前默认</strong><br>
                      平台：微信公众号<br>
                      风格：通俗科普 / 技术深度可通过输入要求控制<br>
                      历史记忆：开启，生成时会自动检索相关笔记
                    </div>
                    """)
                    with gr.Row(elem_classes=["secondary-actions"]):
                        btn_gzh = gr.Button("公众号文章", size="sm", variant="secondary")
                        btn_xhs = gr.Button("小红书笔记", size="sm")
                        btn_dy = gr.Button("抖音文案", size="sm")
                    with gr.Accordion("记忆与历史入口", open=False):
                        gr.Markdown(
                            "- `#!sessions` 查看近期会话\n"
                            "- `#!history` 查看近期生成历史\n"
                            "- `#!memory` 查看向量库状态\n"
                            "- `#!search 关键词` 测试历史笔记检索\n"
                            "- `#!index 路径` 手动索引笔记目录"
                        )

                with gr.Column(scale=8, elem_classes=["result-panel"]):
                    gr.Markdown(
                        "### 结果与过程\n生成进度、审核建议和文章结果会集中显示在这里。",
                        elem_classes=["panel-title"],
                    )
                    chatbot = gr.Chatbot(
                        label="生成过程与结果",
                        height=420,
                        type="messages",
                        elem_classes=["chatbot"],
                    )
                    # 审核面板按钮（默认隐藏）
                    with gr.Row(visible=False) as review_row:
                        btn_revise = gr.Button("按建议修改", variant="primary", size="sm")
                        btn_ignore = gr.Button("忽略建议", size="sm")
                        btn_force = gr.Button("强行通过", variant="stop", size="sm")
                    review_state = gr.State(None)

                    # 小红书 HTML 预览
                    xhs_preview = gr.HTML(visible=False)

                    with gr.Accordion("引用来源与历史任务", open=False, elem_classes=["support-panels"]):
                        gr.HTML("""
                        <ul class="hint-list">
                          <li>生成完成后，后续会在这里展示本次参考的历史笔记。</li>
                          <li>历史任务中心会优先列出公众号文章、评分、文件和发布状态。</li>
                          <li>当前版本可先通过系统命令查看 session 和 memory 状态。</li>
                        </ul>
                        """)
                        refresh_history_btn = gr.Button("刷新生成历史", size="sm", variant="secondary")
                        history_panel = gr.Markdown(
                            _format_generated_history(agent.memory.list_generated_history(limit=8), limit=8),
                            elem_classes=["history-scroll"],
                        )

            with gr.Row(elem_classes=["delivery-bar"]):
                with gr.Column(scale=4):
                    gr.HTML("""
                    <div class="delivery-title">交付操作</div>
                    <div class="delivery-desc">生成公众号文章后，先下载核对 Markdown，再上传封面并保存到公众号草稿箱。</div>
                    """)
                    with gr.Row(elem_classes=["delivery-downloads"]):
                        download_gzh = gr.DownloadButton("下载公众号", visible=False, size="sm")
                        download_xhs = gr.DownloadButton("下载小红书", visible=False, size="sm")
                        download_dy = gr.DownloadButton("下载抖音", visible=False, size="sm")
                with gr.Column(scale=3):
                    cover_upload = gr.UploadButton(
                        "上传公众号封面",
                        file_types=["image"],
                        type="filepath",
                        elem_classes=["cover-upload-btn"],
                    )
                    gr.Markdown("支持 JPG / PNG。上传后可直接保存到公众号草稿箱。")
                with gr.Column(scale=5):
                    pub_status = gr.Textbox(
                        label="发布状态",
                        value="等待生成公众号内容...",
                        interactive=False,
                        show_label=True,
                        elem_classes=["delivery-status"],
                    )
                    publish_btn = gr.Button("保存到公众号草稿箱", variant="primary", size="sm")
        
        # 事件绑定
        send_btn.click(
            respond,
            inputs=[msg_input, chatbot, note_upload],
            outputs=[msg_input, chatbot, last_gzh_file, download_gzh, download_xhs, download_dy, xhs_preview, review_row, review_state]
        )
        
        msg_input.submit(
            respond,
            inputs=[msg_input, chatbot, note_upload],
            outputs=[msg_input, chatbot, last_gzh_file, download_gzh, download_xhs, download_dy, xhs_preview, review_row, review_state]
        )
        
        clear_btn.click(
            clear_history,
            outputs=[chatbot, last_gzh_file, download_gzh, download_xhs, download_dy, xhs_preview, review_row, review_state]
        )
        
        # 快捷按钮事件
        def quick_gzh():
            yield from _respond_stream(agent, "帮我写一篇技术文章的公众号版本", [], None)
        
        def quick_xhs():
            yield from _respond_stream(agent, "生成小红书笔记", [], None)
        
        def quick_dy():
            yield from _respond_stream(agent, "生成抖音口播脚本", [], None)
        
        btn_gzh.click(
            quick_gzh,
            outputs=[msg_input, chatbot, last_gzh_file, download_gzh, download_xhs, download_dy, xhs_preview, review_row, review_state]
        )
        btn_xhs.click(
            quick_xhs,
            outputs=[msg_input, chatbot, last_gzh_file, download_gzh, download_xhs, download_dy, xhs_preview, review_row, review_state]
        )
        btn_dy.click(
            quick_dy,
            outputs=[msg_input, chatbot, last_gzh_file, download_gzh, download_xhs, download_dy, xhs_preview, review_row, review_state]
        )
        
        # 发布按钮事件
        publish_btn.click(
            publish_gzh,
            inputs=[cover_upload, last_gzh_file],
            outputs=[pub_status]
        )

        refresh_history_btn.click(
            refresh_generated_history,
            outputs=[history_panel],
        )

        # 审核按钮事件
        def on_review_decision(decision, panel_data, chat_history):
            from agents.review import ReviewManager
            chat_history = list(chat_history)
            if panel_data is None:
                chat_history.append({"role": "assistant", "content": "⚠️ 审核面板数据已失效，请重新生成。"})
                return (
                    _copy_chat_history(chat_history),
                    gr.update(visible=False),
                    None,
                    "",
                    *_download_button_updates([]),
                    gr.update(value="", visible=False),
                )

            panel = panel_data
            decision_result = ReviewManager.apply_user_decision(panel, decision)
            action = decision_result["action"]

            if action == "publish":
                content = panel.raw_content
                platforms = panel.platforms
                output_dir = Path("output/chat") / datetime.now().strftime("%Y%m%d_%H%M%S")
                output_dir.mkdir(parents=True, exist_ok=True)
                files = _save_generated_markdown_files(content, platforms, output_dir)
                output_text = f"✅ 已生成 {len(platforms)} 个平台的内容\n\n"
                if panel.ignored_count > 0:
                    output_text += f"📊 评分: {panel.effective_score}/100 (忽略后)\n\n"
                else:
                    output_text += f"📊 评分: {panel.overall}/100\n\n"
                gzh_path = ""
                for platform in platforms:
                    text = getattr(content, platform, "")
                    if text:
                        output_text += f"---\n\n### {PLATFORM_LABELS.get(platform, platform)}\n\n{text[:500]}...\n\n"
                    for f in files:
                        if platform in f and f.endswith(".md") and platform == "gongzhonghao":
                            gzh_path = f
                chat_history.append({"role": "assistant", "content": output_text})
                xiaohongshu_html = ""
                for f in files:
                    if Path(f).stem == "xiaohongshu" and f.endswith(".md"):
                        try:
                            text = Path(f).read_text(encoding="utf-8")
                            xiaohongshu_html = _render_xiaohongshu_preview(text)
                        except Exception as e:
                            logger.warning(f"小红书 HTML 预览生成失败: {e}")
                        break
                return (
                    _copy_chat_history(chat_history),
                    gr.update(visible=False),
                    None,
                    gzh_path,
                    *_download_button_updates(files),
                    gr.update(value=xiaohongshu_html, visible=bool(xiaohongshu_html)),
                )

            if action == "revise":
                chat_history.append({"role": "assistant", "content": f"🔄 已采纳修改意见。\n\n**修改指令**：\n{panel.get_revision_prompt()}\n\n请重新输入相同需求以应用修改后重新生成。"})
                return (
                    _copy_chat_history(chat_history),
                    gr.update(visible=False),
                    None,
                    "",
                    *_download_button_updates([]),
                    gr.update(value="", visible=False),
                )

            if action == "retry":
                chat_history.append({"role": "assistant", "content": f"⚠️ 忽略未通过项后评分仍为 {panel.effective_score}/100，未达标。\n\n**建议**：{panel.get_revision_prompt()}\n\n请重新输入相同需求以应用修改后重新生成。"})
                return (
                    _copy_chat_history(chat_history),
                    gr.update(visible=False),
                    None,
                    "",
                    *_download_button_updates([]),
                    gr.update(value="", visible=False),
                )

            chat_history.append({"role": "assistant", "content": "未知的审核决策。"})
            return (
                _copy_chat_history(chat_history),
                gr.update(visible=False),
                None,
                "",
                *_download_button_updates([]),
                gr.update(value="", visible=False),
            )

        def on_revise_generate(panel_data, chat_history):
            chat_history = list(chat_history)
            if panel_data is None:
                chat_history.append({"role": "assistant", "content": "⚠️ 审核面板数据已失效，请重新生成。"})
                yield (
                    "",
                    _copy_chat_history(chat_history),
                    "",
                    *_download_button_updates([]),
                    gr.update(value="", visible=False),
                    gr.update(visible=False),
                    None,
                )
                return

            panel = panel_data
            from agents.review import MAX_REVISION_ATTEMPTS

            # 检查是否还能采纳修改
            if not panel.can_revise():
                chat_history.append({"role": "assistant", "content": f"⚠️ 已达最大修改次数限制（{MAX_REVISION_ATTEMPTS} 次）。\n\n请选择【忽略未通过项】或【强行发布】。"})
                yield (
                    "",
                    _copy_chat_history(chat_history),
                    "",
                    *_download_button_updates([]),
                    gr.update(value="", visible=False),
                    gr.update(visible=False),
                    panel,
                )
                return

            panel.revision_count += 1
            revision_prompt = panel.get_revision_prompt()

            # 从聊天记录中提取用户原始需求
            original_message = ""
            for msg in reversed(chat_history):
                if msg.get("role") == "user":
                    original_message = msg.get("content", "")
                    break

            revised_message = f"{original_message}\n\n【系统：根据以下修改意见重新生成，第 {panel.revision_count}/{MAX_REVISION_ATTEMPTS} 次修改】\n{revision_prompt}"

            # 先隐藏审核面板
            yield (
                "",
                _copy_chat_history(chat_history),
                "",
                *_download_button_updates([]),
                gr.update(value="", visible=False),
                gr.update(visible=False),
                panel,
            )

            # 自动携带修改意见重新生成
            yield from _respond_stream(agent, revised_message, chat_history, None)

        btn_revise.click(
            on_revise_generate,
            inputs=[review_state, chatbot],
            outputs=[msg_input, chatbot, last_gzh_file, download_gzh, download_xhs, download_dy, xhs_preview, review_row, review_state]
        )
        btn_ignore.click(
            lambda panel, hist: on_review_decision("ignore", panel, hist),
            inputs=[review_state, chatbot],
            outputs=[chatbot, review_row, review_state, last_gzh_file, download_gzh, download_xhs, download_dy, xhs_preview]
        )
        btn_force.click(
            lambda panel, hist: on_review_decision("force_publish", panel, hist),
            inputs=[review_state, chatbot],
            outputs=[chatbot, review_row, review_state, last_gzh_file, download_gzh, download_xhs, download_dy, xhs_preview]
        )

        # 使用说明
        with gr.Accordion("📖 使用说明", open=False):
            gr.Markdown("""
            ### 如何使用
            
            1. **直接输入需求**：用自然语言描述你想创作的内容
            2. **指定平台**：可以指定公众号、小红书、抖音中的一个或多个
            3. **等待生成**：Agent 会自动搜索资料、选择策略、生成内容
            4. **发布公众号**：生成公众号文章后，上传封面图片，点击发布按钮
            
            ### 支持的指令
            
            - **生成内容**："帮我写一篇关于XXX的文章"
            - **指定平台**："生成小红书笔记：XXX"
            - **多平台**："生成公众号和小红书的内容：XXX"
            - **查看状态**："状态"
            - **帮助**："帮助"
            
            ### 提示
            
            - 描述越详细，生成内容越精准
            - 可以要求特定风格或格式
            - 生成后可以要求修改或调整
            - 发布到公众号需要：
              - 先生成公众号内容
              - 上传封面图片（必填）
              - 安装 kuaifa CLI (`npm install -g kuaifa`)
            """)
    
    return demo


# ==================== 启动 ====================

if __name__ == "__main__":
    server_name = os.getenv("GRADIO_SERVER_NAME", "127.0.0.1")
    server_port = int(os.getenv("GRADIO_SERVER_PORT", "7861"))

    print("🚀 启动 Content Agent 聊天界面...")
    print(f"🌐 访问地址：http://{server_name}:{server_port}")
    print("📖 使用说明：")
    print("   - 输入需求，Agent 会自动生成内容")
    print("   - 支持平台：公众号、小红书、抖音")
    print("   - 输入'帮助'查看详细指南")
    print()
    
    demo = create_chat_ui()
    demo.launch(
        server_name=server_name,
        server_port=server_port,
        share=False,
        show_error=True,
        quiet=True,
    )
