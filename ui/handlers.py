"""
web_ui.py 的业务处理函数集合

包含：模板管理、配置读写、Vault 扫描、生成核心、导出、发布等
不依赖 Gradio 组件定义，只返回原始数据或 gr.update/gr.Progress
"""

import os
import re
import sys
import json
import tempfile
from datetime import datetime
from pathlib import Path

try:
    import gradio as gr
except ImportError as e:
    print(f"❌ Gradio 导入失败: {e}")
    sys.exit(1)

from dotenv import load_dotenv

load_dotenv()

from content_agent.agent_core import ContentAgent
from content_agent.quality_checker import QualityChecker
from content_agent.research import research_notes, extract_keywords_with_llm
from content_agent.html_renderer import XiaohongshuRenderer

from agents.schemas import TaskInput
from agents.orchestrator import Orchestrator

from content_agent.template_presets import list_templates, get_template, save_user_template, delete_user_template

# ==================== 常量 ====================

_IS_FROZEN = getattr(sys, "frozen", False)

if _IS_FROZEN:
    _APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "ContentAgent"
    _APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    ENV_PATH = _APP_SUPPORT_DIR / ".env"
else:
    ENV_PATH = Path(__file__).parent.parent / ".env"

PROVIDER_KEY_MAP = {
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "KIMI_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "openai": "OPENAI_API_KEY",
    "custom": "MODEL_API_KEY",
}

# ==================== 缓存 ====================

_agent = None
_checker = None
_orchestrator = None


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


def _get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


# ==================== 配置管理 ====================

def _read_env_file() -> dict:
    env = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def _ensure_default_env():
    if not ENV_PATH.exists():
        default_content = """# Content Agent - 环境变量配置
# 此文件由 Web UI 自动生成

MODEL_PROVIDER=deepseek

# 请在上方模型配置中填写你的 API Key（通过 Web UI 页面配置也可以）
DEEPSEEK_API_KEY=

# Tavily 搜索增强（可选）
# TAVILY_API_KEY=
"""
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(default_content)


def _write_env_file(env: dict):
    _ensure_default_env()
    lines = []

    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = ["# Content Agent - 环境变量配置\n", "# 此文件由 Web UI 自动生成\n\n"]

    written_keys = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in env:
                lines[i] = f"{k}={env[k]}\n"
                written_keys.add(k)

    for k, v in env.items():
        if k not in written_keys:
            lines.append(f"{k}={v}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

    for k, v in env.items():
        os.environ[k] = v


def get_config_status():
    provider = os.getenv("MODEL_PROVIDER", "deepseek")
    key_var = PROVIDER_KEY_MAP.get(provider, "MODEL_API_KEY")
    api_key = os.getenv(key_var, "")

    if not api_key or len(api_key) < 10:
        return False, f"⚠️ 未配置 {key_var}，请先在页面顶部的「模型配置」中填写并保存"

    if provider == "custom":
        base_url = os.getenv("MODEL_BASE_URL", "")
        model_name = os.getenv("MODEL_NAME", "")
        if not base_url:
            return False, "⚠️ 自定义平台未配置 MODEL_BASE_URL"
        if not model_name:
            return False, "⚠️ 自定义平台未配置 MODEL_NAME"

    masked = api_key[:8] + "***" if len(api_key) > 8 else "***"
    return True, f"✅ 当前 Provider: {provider} | Key: {masked}"


def load_config_for_ui():
    env = _read_env_file()
    provider = env.get("MODEL_PROVIDER", os.getenv("MODEL_PROVIDER", "deepseek"))
    return {
        "provider": provider,
        "deepseek_key": env.get("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY", "")),
        "kimi_key": env.get("KIMI_API_KEY", os.getenv("KIMI_API_KEY", "")),
        "minimax_key": env.get("MINIMAX_API_KEY", os.getenv("MINIMAX_API_KEY", "")),
        "openai_key": env.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        "custom_key": env.get("MODEL_API_KEY", os.getenv("MODEL_API_KEY", "")),
        "custom_base_url": env.get("MODEL_BASE_URL", os.getenv("MODEL_BASE_URL", "")),
        "custom_model_name": env.get("MODEL_NAME", os.getenv("MODEL_NAME", "")),
        "tavily_key": env.get("TAVILY_API_KEY", os.getenv("TAVILY_API_KEY", "")),
    }


def save_config(provider, deepseek_key, kimi_key, minimax_key, openai_key,
                custom_key, custom_base_url, custom_model_name, tavily_key=""):
    env = {"MODEL_PROVIDER": provider}

    if provider == "deepseek" and deepseek_key.strip():
        env["DEEPSEEK_API_KEY"] = deepseek_key.strip()
    elif provider == "kimi" and kimi_key.strip():
        env["KIMI_API_KEY"] = kimi_key.strip()
    elif provider == "minimax" and minimax_key.strip():
        env["MINIMAX_API_KEY"] = minimax_key.strip()
    elif provider == "openai" and openai_key.strip():
        env["OPENAI_API_KEY"] = openai_key.strip()
    elif provider == "custom":
        if custom_key.strip():
            env["MODEL_API_KEY"] = custom_key.strip()
        if custom_base_url.strip():
            env["MODEL_BASE_URL"] = custom_base_url.strip()
        if custom_model_name.strip():
            env["MODEL_NAME"] = custom_model_name.strip()

    if tavily_key.strip():
        env["TAVILY_API_KEY"] = tavily_key.strip()

    _write_env_file(env)

    global _agent, _checker, _orchestrator
    _agent = None
    _checker = None
    _orchestrator = None

    ok, msg = get_config_status()
    return msg


# ==================== 本地笔记库 ====================

def _get_vault_path() -> str:
    env = _read_env_file()
    path = env.get("VAULT_PATH", os.getenv("VAULT_PATH", ""))
    return path.strip()


def _save_vault_path(path: str) -> str:
    p = path.strip()
    if not p:
        return "❌ 路径不能为空"
    if not Path(p).exists():
        return f"❌ 路径不存在: {p}"
    _write_env_file({"VAULT_PATH": p})
    return f"✅ 笔记库路径已保存: {p}"


def scan_vault_files(vault_path: str) -> list[str]:
    if not vault_path or not Path(vault_path).exists():
        return []
    vault = Path(vault_path)
    files = []
    for f in vault.rglob("*.md"):
        try:
            rel = f.relative_to(vault)
            files.append(str(rel))
        except ValueError:
            continue
    return sorted(files)


def read_vault_file(vault_path: str, rel_path: str) -> str:
    if not vault_path or not rel_path:
        return ""
    fpath = Path(vault_path) / rel_path
    try:
        return fpath.read_text(encoding="utf-8")
    except Exception as e:
        return f"❌ 读取失败: {e}"


def on_vault_save(vault_path: str):
    msg = _save_vault_path(vault_path)
    choices = scan_vault_files(vault_path.strip())
    return msg, gr.Dropdown(choices=choices)


def on_vault_refresh(vault_path: str):
    choices = scan_vault_files(vault_path.strip())
    return gr.Dropdown(choices=choices)


def on_vault_select(vault_path: str, rel_path: str) -> str:
    return read_vault_file(vault_path.strip(), rel_path)


# ==================== 文件上传 ====================

def on_file_upload(file_path):
    if file_path is None:
        return ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"❌ 读取文件失败: {e}"


# ==================== kuaifa 发布配置 ====================

_KUAIFA_CONFIG_DIR = Path.home() / ".kuaifa"
_KUAIFA_CONFIG_FILE = _KUAIFA_CONFIG_DIR / "config.json"


def load_kuaifa_config() -> dict:
    if _KUAIFA_CONFIG_FILE.exists():
        try:
            with open(_KUAIFA_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_kuaifa_config(appid: str, appsecret: str, api_key: str, default_author: str) -> str:
    try:
        _KUAIFA_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config = load_kuaifa_config()
        if appid.strip():
            config["appid"] = appid.strip()
        if appsecret.strip():
            config["appsecret"] = appsecret.strip()
        if api_key.strip():
            config["api-key"] = api_key.strip()
        if default_author.strip():
            config["default-author"] = default_author.strip()
        with open(_KUAIFA_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return "✅ kuaifa 配置已保存"
    except Exception as e:
        return f"❌ 保存失败: {e}"


def verify_kuaifa_config() -> str:
    import subprocess
    import shutil

    config_path = Path.home() / ".kuaifa" / "config.json"
    if not config_path.exists():
        return "❌ 请先填写并保存微信 AppID 和 AppSecret"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        if not config.get("appid") or not config.get("appsecret"):
            return "❌ 请先填写并保存微信 AppID 和 AppSecret"
    except Exception:
        return "❌ 请先填写并保存微信 AppID 和 AppSecret"

    kf_path = _find_kuaifa()
    if not kf_path:
        return "❌ kuaifa CLI 未安装，请先安装: npm install -g kuaifa"

    node_path = shutil.which("node")
    if not node_path:
        for candidate in [
            Path.home() / ".hermes" / "node" / "bin" / "node",
            Path.home() / ".nvm" / "versions" / "node" / "current" / "bin" / "node",
            Path("/usr/local/bin/node"),
            Path("/opt/homebrew/bin/node"),
        ]:
            if candidate.exists():
                node_path = str(candidate.resolve())
                break
    if not node_path:
        return "❌ 未找到 Node.js，kuaifa 需要 Node 环境才能运行"

    try:
        env = os.environ.copy()
        extra_paths = [str(Path(kf_path).parent), str(Path(node_path).parent)]
        env["PATH"] = os.pathsep.join(extra_paths + [env.get("PATH", "")])
        result = subprocess.run(
            [node_path, kf_path, "config", "verify-wechat"],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        if result.returncode == 0:
            return "✅ 微信配置验证通过"
        else:
            return f"❌ 验证失败: {result.stderr or result.stdout}"
    except subprocess.TimeoutExpired:
        return "❌ 验证超时"
    except Exception as e:
        return f"❌ 验证异常: {e}"


def _find_kuaifa() -> "str | None":
    import shutil

    kf = shutil.which("kuaifa")
    if kf:
        return kf
    home = Path.home()
    candidates = [
        home / ".hermes" / "node" / "bin" / "kuaifa",
        home / ".nvm" / "versions" / "node" / "current" / "bin" / "kuaifa",
        home / ".local" / "bin" / "kuaifa",
        Path("/usr/local/bin/kuaifa"),
        Path("/opt/homebrew/bin/kuaifa"),
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return None


def get_kuaifa_setup_status() -> str:
    import subprocess

    kf_path = _find_kuaifa()
    if not kf_path:
        return (
            "❌ kuaifa 未安装\n"
            "请先在终端运行：\n"
            "  npm install -g kuaifa\n"
            "完成后再填写发布配置。"
        )

    cfg = load_kuaifa_config()
    missing = []
    if not cfg.get("appid"):
        missing.append("微信 AppID")
    if not cfg.get("appsecret"):
        missing.append("微信 AppSecret")
    if not cfg.get("api-key"):
        missing.append("kuaifa API Key")

    if missing:
        return f"⚠️ kuaifa 已安装，但缺少配置：{', '.join(missing)}"

    return "✅ kuaifa 已安装且配置完整，可以发布到公众号草稿箱"


# ==================== 工具 ====================

def _scale_html(html: str, scale: float = 0.48) -> str:
    def replace_px(match):
        val = int(match.group(1))
        if val <= 3:
            return match.group(0)
        scaled = max(1, int(val * scale))
        return f"{scaled}px"
    return re.sub(r'(\d+)px', replace_px, html)


# ==================== 配置模板管理 ====================

def _build_template_choices():
    templates = list_templates()
    return [(cfg["name"], tid) for tid, cfg in templates.items()]


def on_template_select(template_id):
    """模板下拉框变更时，批量更新配置组件"""
    cfg = get_template(template_id)
    if not cfg:
        return (
            gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(),
            gr.update(value="等待生成..."),
        )
    return (
        gr.update(value=cfg.get("platforms", ["小红书", "公众号", "抖音"])),
        gr.update(value=cfg.get("enable_research", False)),
        gr.update(value=cfg.get("search_engine", "duckduckgo")),
        gr.update(value=cfg.get("style", "专业干货")),
        gr.update(value=cfg.get("batch_mode", False)),
        gr.update(
            visible=template_id.startswith("user_"),
            interactive=template_id.startswith("user_"),
        ),
        gr.update(value=f"已加载模板: {cfg.get('name', template_id)}"),
    )


def on_template_save(name, platforms, enable_research, search_engine, style, batch_mode):
    """保存当前配置为用户自定义模板"""
    if not name or not name.strip():
        return "模板名称不能为空", ""
    name = name.strip()
    template_id = f"user_{name}"
    cfg = {
        "name": name,
        "platforms": platforms,
        "enable_research": enable_research,
        "search_engine": search_engine,
        "style": style,
        "batch_mode": batch_mode,
    }
    msg = save_user_template(template_id, cfg)
    return msg, ""


def on_template_delete(template_id):
    """删除用户自定义模板"""
    if not template_id:
        return "请先选择一个模板", ""
    msg = delete_user_template(template_id)
    return msg, ""


# ==================== 生成核心逻辑 ====================

def generate_content(note_text, note_file, platforms, enable_research, search_engine, style, batch_mode, concurrent_mode, skip_edit, history, progress=gr.Progress()):
    ok, config_msg = get_config_status()
    if not ok:
        yield "", "", "", "", "", config_msg, history
        return

    if search_engine == "tavily" and not os.getenv("TAVILY_API_KEY", "").strip():
        yield (
            "", "", "", "", "",
            "⚠️ 使用 Tavily 搜索需要配置 TAVILY_API_KEY\n"
            "请在页面顶部「⭐ 模型配置」中填写 Tavily API Key，或切换为 DuckDuckGo (免费无需 Key)",
            history
        )
        return

    if note_file is not None:
        try:
            with open(note_file, "r", encoding="utf-8") as f:
                note_text = f.read()
        except Exception as e:
            yield "", "", "", "", "", f"❌ 读取文件失败: {e}", history
            return

    note_text = note_text.strip() if note_text else ""
    if not note_text:
        yield "", "", "", "", "", "⚠️ 请输入或上传笔记", history
        return

    sensitive_check = None
    try:
        from content_agent.sensitive_checker import SensitiveChecker
        checker = SensitiveChecker()
        sensitive_check = checker.check(note_text)
    except Exception:
        pass

    platform_map = {
        "小红书": "xiaohongshu",
        "公众号": "gongzhonghao",
        "抖音": "douyin",
    }
    enabled = {platform_map[p] for p in platforms if p in platform_map}

    if not enabled:
        yield "", "", "", "", "", "⚠️ 请至少选择一个平台", history
        return

    if batch_mode:
        notes_list = [n.strip() for n in re.split(r'\n\s*---\s*\n', note_text) if n.strip()]
    else:
        notes_list = [note_text]

    if not notes_list:
        yield "", "", "", "", "", "⚠️ 未能解析出有效笔记", history
        return

    style_instructions = {
        "专业干货": "",
        "轻松口语": "\n【风格要求：语气像朋友聊天，轻松自然，多用生活化比喻，少讲大道理】",
        "情绪共鸣": "\n【风格要求：开头点出痛点让读者产生共鸣，语气有温度，适当表达焦虑和成就感】",
        "悬念钩子": "\n【风格要求：开头埋悬念钩子，正文逐步揭秘，结尾反转或出人意料】",
    }
    style_note = style_instructions.get(style, "")

    progress(0.05, desc="初始化 Agent...")
    agent = _get_agent()
    checker = _get_checker()

    yield "", "", "", "", "", "⏳ 正在初始化 Agent，请稍候...", history

    # ---- 单篇生成逻辑（可被并发调用）----
    def _process_single(idx: int, single_note: str) -> dict:
        state = None
        generation_result = None
        if enable_research:
            try:
                from pydantic_ai import Agent
                keyword_agent = Agent(
                    agent.model,
                    system_prompt="你是一个关键词提取助手，从技术笔记中提取精准的搜索关键词。"
                )
                keywords = extract_keywords_with_llm(single_note, keyword_agent)
                current_notes = research_notes(
                    single_note,
                    search_engine=search_engine,
                    max_results=3,
                    verbose=False,
                    keywords=keywords,
                )
            except Exception as e:
                print(f"笔记 {idx} 搜索增强失败: {e}")
                current_notes = single_note
        else:
            current_notes = single_note

        styled_notes = current_notes + style_note if style_note else current_notes

        try:
            task_input = TaskInput(
                note_text=styled_notes,
                note_source=note_file or "clipboard",
                platforms=list(enabled),
                enable_research=False,
                search_engine=search_engine,
                style=style,
                batch_mode=False,
                concurrent_mode=concurrent_mode,
                skip_edit=skip_edit,
            )
            orchestrator = _get_orchestrator()
            state = orchestrator.run(task_input)
            generation_result = state.final_output
        except Exception as e:
            generation_result = None
            print(f"笔记 {idx} Orchestrator 调用失败: {e}")
            import traceback
            traceback.print_exc()

        if generation_result is None:
            xs = gh = dy = "❌ 生成失败"
            tag = ""
        else:
            xs = generation_result.xiaohongshu if "xiaohongshu" in enabled else "（未选择此平台）"
            gh = generation_result.gongzhonghao if "gongzhonghao" in enabled else "（未选择此平台）"
            dy = generation_result.douyin if "douyin" in enabled else "（未选择此平台）"
            tag = generation_result.recommended_tags or ""

        return {
            "idx": idx,
            "note": single_note,
            "xs": xs,
            "gh": gh,
            "dy": dy,
            "tag": tag,
            "state": state,
        }

    # ---- 并行处理 ----
    if batch_mode and concurrent_mode and len(notes_list) > 1:
        progress(0.1, desc=f"并发处理 {len(notes_list)} 篇笔记...")
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(len(notes_list), 3)) as executor:
            futures = {
                executor.submit(_process_single, i + 1, n): i
                for i, n in enumerate(notes_list)
            }
            results = [None] * len(notes_list)
            for future in futures:
                res = future.result()
                results[res["idx"] - 1] = res
    else:
        results = []
        for idx, single_note in enumerate(notes_list, 1):
            base_progress = (idx - 1) / len(notes_list)
            progress(base_progress, desc=f"处理第 {idx}/{len(notes_list)} 篇...")
            res = _process_single(idx, single_note)
            results.append(res)

    # ---- 合并结果 ----
    all_xiaohongshu = []
    all_gongzhonghao = []
    all_douyin = []
    all_tags = []
    orchestrator_states = []

    for res in results:
        idx = res["idx"]
        single_note = res["note"]
        xs, gh, dy, tag = res["xs"], res["gh"], res["dy"], res["tag"]
        state = res.get("state")
        if state:
            orchestrator_states.append(state)

        all_tags.append(tag)

        if len(notes_list) > 1:
            preview = single_note[:30] + "..." if len(single_note) > 30 else single_note
            all_xiaohongshu.append(f"## 笔记 {idx}: {preview}\n\n{xs}")
            all_gongzhonghao.append(f"## 笔记 {idx}: {preview}\n\n{gh}")
            all_douyin.append(f"## 笔记 {idx}: {preview}\n\n{dy}")
        else:
            all_xiaohongshu.append(xs)
            all_gongzhonghao.append(gh)
            all_douyin.append(dy)

    sep = "\n\n---\n\n" if len(notes_list) > 1 else "\n"
    xiaohongshu_text = sep.join(all_xiaohongshu)
    gongzhonghao_text = sep.join(all_gongzhonghao)
    douyin_text = sep.join(all_douyin)

    tags_text = all_tags[0] if all_tags else ""

    xiaohongshu_html = ""
    first_xs = all_xiaohongshu[0]
    if "xiaohongshu" in enabled and first_xs and not first_xs.startswith("❌"):
        render_text = first_xs.split("\n\n", 1)[-1] if first_xs.startswith("## ") else first_xs
        try:
            renderer = XiaohongshuRenderer()
            with tempfile.TemporaryDirectory() as tmpdir:
                html_path = renderer.render(render_text, tmpdir)
                with open(html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                xiaohongshu_html = _scale_html(html_content, scale=0.48)
        except Exception as e:
            print(f"HTML 预览生成失败: {e}")

    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "note_preview": f"批量 {len(notes_list)} 篇" if len(notes_list) > 1 else note_text[:30] + "...",
        "xiaohongshu": xiaohongshu_text,
        "gongzhonghao": gongzhonghao_text,
        "douyin": douyin_text,
        "recommended_tags": tags_text,
    }
    history = [entry] + (history if history else [])[:9]

    status_parts = [f"✅ 完成！共 {len(notes_list)} 篇 | 平台: {', '.join(platforms)}"]

    total_llm_calls = sum((st.metadata.get("llm_calls", 0) for st in orchestrator_states if st), 0)
    total_duration = sum((st.metadata.get("duration_sec", 0) for st in orchestrator_states if st), 0)
    human_review_count = sum((1 for st in orchestrator_states if st and st.metadata.get("human_review_needed")), 0)
    token_exceeded_count = sum((1 for st in orchestrator_states if st and st.metadata.get("token_budget_exceeded")), 0)

    if total_llm_calls:
        status_parts.append(f"LLM调用:{total_llm_calls}次")
    if total_duration:
        status_parts.append(f"耗时:{total_duration:.1f}s")
    if human_review_count:
        status_parts.append(f"⚠️{human_review_count}篇3次编辑未达标，取最佳稿")
    if token_exceeded_count:
        status_parts.append(f"⚠️{token_exceeded_count}篇Token预算超出")

    edit_notes = ""
    if len(notes_list) == 1 and orchestrator_states and orchestrator_states[0]:
        st = orchestrator_states[0]
        if st.edit_history:
            last_v = st.edit_history[-1]
            if last_v.suggestions and not last_v.passed:
                edit_notes = chr(10) + "编辑建议:" + chr(10) + chr(10).join(f"  • {s}" for s in last_v.suggestions[:3])

    status = " | ".join(status_parts) + edit_notes
    if sensitive_check and sensitive_check["has_sensitive"]:
        hits = [h["word"] for h in sensitive_check["hits"][:5]]
        warn = f"⚠️ 检测到{sensitive_check['local_count']}个敏感/违规词: {', '.join(hits)}"
        if len(sensitive_check["hits"]) > 5:
            warn += f" 等共{len(sensitive_check['hits'])}个"
        status += f"\n{warn}"
    progress(1.0, desc="完成")
    yield xiaohongshu_text, gongzhonghao_text, douyin_text, xiaohongshu_html, tags_text, status, history


def refine_content(xiaohongshu, gongzhonghao, douyin, instruction, note_text, style, history, progress=gr.Progress()):
    instruction = instruction.strip() if instruction else ""
    if not instruction:
        return xiaohongshu, gongzhonghao, douyin, "", "", "⚠️ 请输入修改指令", history

    progress(0.2, desc="准备优化...")
    agent = _get_agent()

    style_instructions = {
        "专业干货": "",
        "轻松口语": "\n【风格要求：语气像朋友聊天，轻松自然，多用生活化比喻，少讲大道理】",
        "情绪共鸣": "\n【风格要求：开头点出痛点让读者产生共鸣，语气有温度，适当表达焦虑和成就感】",
        "悬念钩子": "\n【风格要求：开头埋悬念钩子，正文逐步揭秘，结尾反转或出人意料】",
    }
    style_note = style_instructions.get(style, "")

    refine_prompt = f"""【请根据以下改进要求重新输出三平台文案】
{instruction}

--- 当前文案 ---
小红书：
{xiaohongshu}

公众号：
{gongzhonghao}

抖音：
{douyin}

--- 原始笔记 ---
{note_text}{style_note}"""

    progress(0.5, desc="重新生成...")
    try:
        result = agent.run(refine_prompt)
    except Exception as e:
        return xiaohongshu, gongzhonghao, douyin, "", "", f"❌ 优化失败: {e}", history

    progress(0.8, desc="整理结果...")

    xiaohongshu_html = ""
    if result.xiaohongshu:
        try:
            renderer = XiaohongshuRenderer()
            with tempfile.TemporaryDirectory() as tmpdir:
                html_path = renderer.render(result.xiaohongshu, tmpdir)
                with open(html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                xiaohongshu_html = _scale_html(html_content, scale=0.48)
        except Exception as e:
            print(f"HTML 预览生成失败: {e}")

    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "note_preview": f"优化: {instruction[:20]}...",
        "xiaohongshu": result.xiaohongshu,
        "gongzhonghao": result.gongzhonghao,
        "douyin": result.douyin,
        "recommended_tags": result.recommended_tags or "",
    }
    history = [entry] + (history if history else [])[:9]

    status = f"✅ 优化完成！指令: {instruction[:20]}..."
    progress(1.0, desc="完成")
    return result.xiaohongshu, result.gongzhonghao, result.douyin, xiaohongshu_html, result.recommended_tags or "", status, history


def restore_history(selected_index, history):
    if not selected_index or not history:
        return "", "", "", "", "", "⚠️ 请先选择历史记录"

    try:
        idx = int(selected_index)
        entry = history[idx]
    except (ValueError, IndexError):
        return "", "", "", "", "", "❌ 无效的历史记录"

    xiaohongshu_html = ""
    if entry.get("xiaohongshu") and entry["xiaohongshu"] != "（未选择此平台）":
        try:
            renderer = XiaohongshuRenderer()
            with tempfile.TemporaryDirectory() as tmpdir:
                html_path = renderer.render(entry["xiaohongshu"], tmpdir)
                with open(html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                xiaohongshu_html = _scale_html(html_content, scale=0.48)
        except Exception as e:
            print(f"HTML 预览生成失败: {e}")

    status = f"✅ 已恢复 {entry['time']} 的文案"
    return (
        entry.get("xiaohongshu", ""),
        entry.get("gongzhonghao", ""),
        entry.get("douyin", ""),
        xiaohongshu_html,
        entry.get("recommended_tags", ""),
        status,
    )


def generate_titles(xiaohongshu, gongzhonghao, douyin, note_text, style, progress=gr.Progress()):
    progress(0.2, desc="准备标题生成...")
    agent = _get_agent()

    from pydantic_ai import Agent as PydanticAgent

    style_desc = {
        "专业干货": "专业、权威、有信息量",
        "轻松口语": "亲切、口语化、像朋友推荐",
        "情绪共鸣": "戳痛点、引发共鸣、有情感冲击",
        "悬念钩子": "制造悬念、引发好奇、想点击",
    }.get(style, "吸引人点击")

    title_agent = PydanticAgent(
        agent.model,
        system_prompt="你是一位爆款标题专家，擅长为不同平台的内容生成吸引人的标题。",
    )

    platform_map = {
        "小红书": xiaohongshu,
        "公众号": gongzhonghao,
        "抖音": douyin,
    }

    results = {}
    for idx, (platform, text) in enumerate(platform_map.items(), 1):
        if not text or text == "（未选择此平台）":
            results[platform] = "*未选择此平台*"
            continue

        progress(0.2 + idx * 0.2, desc=f"生成 {platform} 标题...")

        prompt = f"""请为以下{platform}文案生成 3 个备选标题。

要求：
- 风格：{style_desc}
- 吸引人点击，有信息量
- 每个标题不超过 20 字
- 标注每个标题的类型（如：数字型、疑问型、痛点型、悬念型、对比型）

原始笔记摘要：
{note_text[:500]}

文案内容：
{text[:800]}

请严格按以下格式输出：
1. 【标题】（类型：xxx）
2. 【标题】（类型：xxx）
3. 【标题】（类型：xxx）
"""
        try:
            r = title_agent.run_sync(prompt)
            results[platform] = r.output
        except Exception as e:
            results[platform] = f"生成失败: {e}"

    progress(1.0, desc="完成")
    return results["小红书"], results["公众号"], results["抖音"], "✅ 备选标题生成完成"


def generate_cover_prompt(content, platform="xiaohongshu", progress=gr.Progress()):
    if not content or content == "（未选择此平台）":
        platform_name = "小红书" if platform == "xiaohongshu" else "公众号"
        return f"⚠️ 请先生成{platform_name}文案", ""

    progress(0.3, desc="准备配图 prompt...")
    agent = _get_agent()

    from pydantic_ai import Agent as PydanticAgent

    if platform == "gongzhonghao":
        system = "你是一位专业的 AI 绘画提示词工程师，擅长根据文案内容生成高质量的公众号封面图绘画 prompt。"
        user_prompt = f"""请根据以下公众号文章，生成一个适合作为公众号封面图的 AI 绘画 prompt。

要求：
- 画面风格：专业、大气、适合科技/学习类公众号，色彩稳重有质感
- 构图：适合 16:9 横版比例（公众号封面），主体突出，留出标题位置
- 可以包含与主题相关的图像元素，但不要出现具体文字字符
- 提供中文画面描述和英文 Midjourney 风格 prompt
- Midjourney prompt 需包含风格参数（如 --ar 16:9）

文案内容：
{content[:1200]}

请严格按以下格式输出：
【画面描述】
（用一段话描述画面内容、色彩、氛围、构图，强调公众号封面的专业感）

【Midjourney Prompt】
（英文关键词组成的 prompt，结尾带 --ar 16:9 等参数）
"""
    else:
        system = "你是一位专业的 AI 绘画提示词工程师，擅长根据文案内容生成高质量的小红书封面图绘画 prompt。"
        user_prompt = f"""请根据以下小红书文案，生成一个适合作为小红书封面图的 AI 绘画 prompt。

要求：
- 画面风格：清新、现代、适合科技/学习类内容，色彩明快
- 构图：适合 3:4 竖版比例（小红书封面）
- 不要包含文字或字符，纯图像
- 提供中文画面描述和英文 Midjourney 风格 prompt
- Midjourney prompt 需包含风格参数（如 --ar 3:4）

文案内容：
{content[:1200]}

请严格按以下格式输出：
【画面描述】
（用一段话描述画面内容、色彩、氛围、构图）

【Midjourney Prompt】
（英文关键词组成的 prompt，结尾带 --ar 3:4 等参数）
"""

    cover_agent = PydanticAgent(
        agent.model,
        system_prompt=system,
    )

    try:
        r = cover_agent.run_sync(user_prompt)
        result = r.output.strip()
    except Exception as e:
        return f"生成失败: {e}", ""

    progress(1.0, desc="完成")
    platform_label = "公众号" if platform == "gongzhonghao" else "小红书"
    return result, f"✅ {platform_label}封面 prompt 生成完成，可复制到 Midjourney/通义万相/即梦 等工具"


# ==================== 导出功能 ====================

def export_markdown(platform: str, content: str):
    if not content or content.startswith("（未选择此平台）") or content.startswith("❌"):
        return gr.update(value=None, visible=False), f"⚠️ {platform} 无内容可导出"

    fd, path = tempfile.mkstemp(suffix=f"_{platform}.md", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {platform}文案\ndate: {datetime.now().isoformat()}\nplatform: {platform}\n---\n\n")
        f.write(content)
    return gr.update(value=path, visible=True), f"✅ {platform} Markdown 已就绪，点击下载"


def export_word(platform: str, content: str):
    if not content or content.startswith("（未选择此平台）") or content.startswith("❌"):
        return gr.update(value=None, visible=False), f"⚠️ {platform} 无内容可导出"

    try:
        from content_agent.docx_exporter import render_markdown_to_docx
    except ImportError as e:
        return (
            gr.update(value=None, visible=False),
            f"⚠️ 导出模块加载失败: {e}",
        )

    try:
        path = render_markdown_to_docx(content, title=f"{platform}文案")
    except ImportError:
        return (
            gr.update(value=None, visible=False),
            "⚠️ 未安装 python-docx，请运行: pip install python-docx",
        )
    except Exception as e:
        return (
            gr.update(value=None, visible=False),
            f"❌ Word 生成失败: {e}",
        )

    return gr.update(value=path, visible=True), f"✅ {platform} Word 已就绪，点击下载"


# ==================== 发布功能 ====================

def publish_to_wechat(
    gongzhonghao_text: str,
    title: str,
    author: str,
    digest: str,
    cover_file,
    cover_url: str,
):
    from content_agent.publisher import publish_wechat_draft, save_content_as_markdown

    if not gongzhonghao_text or gongzhonghao_text.startswith("（未选择此平台）"):
        return "❌ 公众号文案为空，请先生成文案"

    cover_path = ""
    if cover_file:
        if isinstance(cover_file, str):
            cover_path = cover_file
        elif hasattr(cover_file, "name"):
            cover_path = cover_file.name
    if not cover_path and cover_url and cover_url.strip():
        cover_path = cover_url.strip()

    if not cover_path:
        return "❌ 微信草稿要求必须有封面图片，请上传封面或填入图片 URL"

    article_title = title.strip() or "未命名文章"
    md_path = save_content_as_markdown(article_title, gongzhonghao_text)

    result = publish_wechat_draft(
        markdown_path=md_path,
        title=article_title,
        cover_path=cover_path,
        author=author.strip(),
        digest=digest.strip(),
    )

    msg = result["message"]
    if result["details"]:
        msg += f"\n\n详情:\n{result['details']}"
    return msg
