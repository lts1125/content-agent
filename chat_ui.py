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
        is_generate = any(kw in message_lower for kw in generate_keywords)
        
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
        if not topic or len(topic) < 5:
            topic = original_message

        try:
            if has_source_material:
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
            yield {
                "type": "progress",
                "event": {
                    "step": "select-strategy",
                    "title": "选择生成策略",
                    "status": "done",
                    "detail": f"使用策略：{strategy.name}",
                },
            }

            # 注入记忆上下文
            memory_context = self._build_memory_context(topic)
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

                review_md = panel.to_markdown()
                yield {
                    "type": "result",
                    "result": {
                        "type": "review",
                        "panel": panel,
                        "content": review_md,
                        "raw_content": content,
                        "platforms": platforms,
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

            files = []
            output_dir = Path("output/chat") / datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir.mkdir(parents=True, exist_ok=True)
            for platform in platforms:
                text = getattr(content, platform, "")
                if text:
                    output_text += f"---\n\n### {PLATFORM_LABELS.get(platform, platform)}\n\n{text[:500]}...\n\n"
            files = _save_generated_markdown_files(content, platforms, output_dir)

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
            )

            yield {
                "type": "result",
                "result": {
                    "type": "content",
                    "content": output_text,
                    "platforms": platforms,
                    "files": files,
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
- `#!memory` — 查看向量库状态
""",
            }

        return None

    def _build_memory_context(self, topic: str) -> str:
        """构建记忆上下文：包含用户偏好和相关笔记检索结果。

        返回空字符串表示没有可用的记忆上下文。
        """
        parts = []

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
                parts.append("## 相关笔记参考\n" + "\n".join(note_lines))
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")

        return "\n\n".join(parts)


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
    
    # 构建界面 - 使用系统字体避免加载 Google Fonts（国内网络阻塞问题）
    theme = gr.themes.Soft(
        font=["system-ui", "SF Pro Display", "Segoe UI", "PingFang SC", "Microsoft YaHei", "sans-serif"],
        font_mono=["SF Mono", "SFMono-Regular", "Consolas", "Liberation Mono", "Menlo", "monospace"],
    )
    
    with gr.Blocks(
        title="Content Agent - 聊天模式",
        theme=theme,
        css="""
        .app-intro h1 { margin-bottom: 8px; }
        .app-intro p { margin: 4px 0; }
        .app-intro ul { margin: 6px 0 10px 20px; }
        .input-box { margin-top: 8px; }
        .publish-box { margin-top: 16px; padding: 16px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fafafa; }
        """
    ) as demo:
        # 存储最后一次生成的公众号文件路径。State 必须创建在 Blocks 内，
        # 否则事件输出会引用未注册组件，导致 Gradio 前端/API 报错。
        last_gzh_file = gr.State("")

        gr.Markdown("""
        # 🤖 Content Agent - AI 内容创作助手
        
        用自然语言告诉我你想创作什么内容，我会自动分析、搜索资料、生成文案。示例："帮我写一篇关于 MCP 协议的公众号文章" / "生成小红书笔记：程序员颈椎拯救计划"
        """, elem_classes=["app-intro"])
        
        # 聊天区域
        chatbot = gr.Chatbot(
            label="对话",
            height=360,
            type="messages",
        )
        
        # 输入区域
        with gr.Row():
            msg_input = gr.Textbox(
                label="输入消息",
                placeholder="告诉我你想创作什么内容...",
                scale=8,
                show_label=False,
            )
            send_btn = gr.Button("发送", scale=1, variant="primary")

        with gr.Row():
            note_upload = gr.File(
                label="上传笔记（.md / .txt，可选）",
                file_types=[".md", ".txt"],
                type="filepath",
                scale=1,
            )
            with gr.Column(scale=1):
                with gr.Row():
                    download_gzh = gr.DownloadButton("⬇️ 公众号", visible=False, size="sm")
                    download_xhs = gr.DownloadButton("⬇️ 小红书", visible=False, size="sm")
                    download_dy = gr.DownloadButton("⬇️ 抖音", visible=False, size="sm")
        
        # 快捷按钮
        with gr.Row():
            btn_gzh = gr.Button("📱 公众号文章", size="sm")
            btn_xhs = gr.Button("📕 小红书笔记", size="sm")
            btn_dy = gr.Button("🎵 抖音文案", size="sm")
            clear_btn = gr.Button("🗑️ 清空对话", size="sm", variant="secondary")
        
        # 小红书 HTML 预览
        xhs_preview = gr.HTML(visible=False)

        # 审核面板按钮（默认隐藏）
        with gr.Row(visible=False) as review_row:
            btn_revise = gr.Button("采纳修改", variant="primary", size="sm")
            btn_ignore = gr.Button("忽略未通过项", size="sm")
            btn_force = gr.Button("强行发布", variant="stop", size="sm")
        review_state = gr.State(None)
        
        # 公众号发布区域
        with gr.Accordion("📤 发布到公众号草稿箱", open=False):
            with gr.Row(variant="panel"):
                with gr.Column(scale=1):
                    cover_upload = gr.Image(
                        label="📷 公众号封面",
                        type="filepath",
                        height=120,
                        show_label=True,
                    )
                with gr.Column(scale=2):
                    pub_status = gr.Textbox(
                        label="发布状态",
                        value="等待生成内容...",
                        interactive=False,
                        show_label=True,
                    )
                    publish_btn = gr.Button("📤 发布到公众号草稿箱", variant="primary", size="sm")
        
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
