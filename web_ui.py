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


# ==================== 配置管理 ====================

# 检测是否在 PyInstaller 打包环境中运行
_IS_FROZEN = getattr(sys, "frozen", False)

if _IS_FROZEN:
    # 打包后：配置文件放在用户家目录下，确保可写
    _APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "ContentAgent"
    _APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    ENV_PATH = _APP_SUPPORT_DIR / ".env"
else:
    # 开发时：放在项目根目录
    ENV_PATH = Path(__file__).parent / ".env"

PROVIDER_KEY_MAP = {
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "KIMI_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "openai": "OPENAI_API_KEY",
    "custom": "MODEL_API_KEY",
}


def _read_env_file() -> dict:
    """读取 .env 文件内容，返回 key->value 字典"""
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
    """打包后首次启动，如果 .env 不存在则创建默认模板"""
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
    """将配置字典写回 .env 文件（保留注释和格式）"""
    _ensure_default_env()
    lines = []

    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = ["# Content Agent - 环境变量配置\n", "# 此文件由 Web UI 自动生成\n\n"]

    # 更新已有行
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

    # 追加新 key
    for k, v in env.items():
        if k not in written_keys:
            lines.append(f"{k}={v}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # 同时更新当前进程环境变量，立即生效
    for k, v in env.items():
        os.environ[k] = v


def get_config_status():
    """检查当前配置是否可用，返回 (是否可用, 提示信息)"""
    provider = os.getenv("MODEL_PROVIDER", "deepseek")
    key_var = PROVIDER_KEY_MAP.get(provider, "MODEL_API_KEY")
    api_key = os.getenv(key_var, "")

    if not api_key or len(api_key) < 10:
        return False, f"⚠️ 未配置 {key_var}，请先在页面顶部的「模型配置」中填写并保存"

    # 自定义平台额外检查
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
    """加载当前配置，用于填充 UI 表单"""
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
    """保存配置到 .env 文件"""
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

    # 清除 Agent 缓存，下次调用会使用新配置
    global _agent, _checker
    _agent = None
    _checker = None

    ok, msg = get_config_status()
    return msg


# ==================== 本地笔记库（Obsidian / Markdown 目录）====================

def _get_vault_path() -> str:
    """读取保存的笔记库路径"""
    env = _read_env_file()
    path = env.get("VAULT_PATH", os.getenv("VAULT_PATH", ""))
    return path.strip()


def _save_vault_path(path: str) -> str:
    """保存笔记库路径到 .env"""
    p = path.strip()
    if not p:
        return "❌ 路径不能为空"
    if not Path(p).exists():
        return f"❌ 路径不存在: {p}"
    _write_env_file({"VAULT_PATH": p})
    return f"✅ 笔记库路径已保存: {p}"


def scan_vault_files(vault_path: str) -> list[str]:
    """扫描笔记库目录下所有 .md 文件，返回相对路径列表"""
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
    """读取笔记库中指定文件的内容"""
    if not vault_path or not rel_path:
        return ""
    fpath = Path(vault_path) / rel_path
    try:
        return fpath.read_text(encoding="utf-8")
    except Exception as e:
        return f"❌ 读取失败: {e}"


def on_vault_save(vault_path: str):
    """保存笔记库路径并刷新文件列表"""
    msg = _save_vault_path(vault_path)
    choices = scan_vault_files(vault_path.strip())
    return msg, gr.Dropdown(choices=choices)


def on_vault_refresh(vault_path: str):
    """刷新笔记库文件列表"""
    choices = scan_vault_files(vault_path.strip())
    return gr.Dropdown(choices=choices)


def on_vault_select(vault_path: str, rel_path: str) -> str:
    """选择笔记库文件后读取内容"""
    return read_vault_file(vault_path.strip(), rel_path)


# ==================== kuaifa 发布配置 ====================

_KUAIFA_CONFIG_DIR = Path.home() / ".kuaifa"
_KUAIFA_CONFIG_FILE = _KUAIFA_CONFIG_DIR / "config.json"


def load_kuaifa_config() -> dict:
    """加载 kuaifa 配置"""
    if _KUAIFA_CONFIG_FILE.exists():
        try:
            with open(_KUAIFA_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_kuaifa_config(appid: str, appsecret: str, api_key: str, default_author: str) -> str:
    """保存 kuaifa 配置到 ~/.kuaifa/config.json"""
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
    """验证微信配置是否正确"""
    import subprocess
    import shutil
    from pathlib import Path

    # 先检查是否已保存微信配置
    config_path = Path.home() / ".kuaifa" / "config.json"
    if not config_path.exists():
        return "❌ 请先填写并保存微信 AppID 和 AppSecret"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        if not config.get("appid") or not config.get("appsecret"):
            return "❌ 请先填写并保存微信 AppID 和 AppSecret"
    except Exception:
        # 配置文件为空或损坏，等同于未保存
        return "❌ 请先填写并保存微信 AppID 和 AppSecret"

    # 查找 kuaifa 实际路径
    kf_path = _find_kuaifa()
    if not kf_path:
        return "❌ kuaifa CLI 未安装，请先安装: npm install -g kuaifa"

    # 查找 node（kuaifa 的 shebang 依赖 env node）
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
    """查找 kuaifa 可执行文件（与 publisher.py 保持一致）"""
    import shutil
    from pathlib import Path
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
    """检测 kuaifa 安装及配置状态，返回状态提示"""
    import subprocess
    from pathlib import Path

    # 1. 检查 kuaifa CLI 是否安装
    kf_path = _find_kuaifa()
    if not kf_path:
        return (
            "❌ kuaifa 未安装\n"
            "请先在终端运行：\n"
            "  npm install -g kuaifa\n"
            "完成后再填写发布配置。"
        )

    # 2. 检查是否已配置
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


def _scale_html(html: str, scale: float = 0.48) -> str:
    """将 HTML 中所有 px 值按比例缩放，用于预览适配容器宽度"""
    def replace_px(match):
        val = int(match.group(1))
        # 极小的值不缩放（避免 border-radius 等变得太小）
        if val <= 3:
            return match.group(0)
        scaled = max(1, int(val * scale))
        return f"{scaled}px"
    return re.sub(r'(\d+)px', replace_px, html)


# 缓存 Agent 实例（避免每次都重新初始化）
_agent = None
_checker = None
_scheduler = None


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


def generate_content(note_text, note_file, platforms, enable_research, search_engine, style, batch_mode, history, progress=gr.Progress()):
    """
    Gradio 处理函数

    Returns:
        (xiaohongshu, gongzhonghao, douyin, xiaohongshu_html, tags, status, history, history_dropdown)
    """
    # 检查配置
    ok, config_msg = get_config_status()
    if not ok:
        yield "", "", "", "", "", config_msg, history, gr.Dropdown()
        return

    # 如果选了 Tavily，检查 Tavily Key
    if search_engine == "tavily" and not os.getenv("TAVILY_API_KEY", "").strip():
        yield (
            "", "", "", "", "",
            "⚠️ 使用 Tavily 搜索需要配置 TAVILY_API_KEY\n"
            "请在页面顶部「⭐ 模型配置」中填写 Tavily API Key，或切换为 DuckDuckGo (免费无需 Key)",
            history, gr.Dropdown()
        )
        return

    # 优先使用上传的文件
    if note_file is not None:
        try:
            with open(note_file, "r", encoding="utf-8") as f:
                note_text = f.read()
        except Exception as e:
            yield "", "", "", "", "", f"❌ 读取文件失败: {e}", history, gr.Dropdown()
            return

    note_text = note_text.strip() if note_text else ""
    if not note_text:
        yield "", "", "", "", "", "⚠️ 请输入或上传笔记", history, gr.Dropdown()
        return

    # 敏感词预检
    sensitive_check = None
    try:
        from content_agent.sensitive_checker import SensitiveChecker
        checker = SensitiveChecker()
        sensitive_check = checker.check(note_text)
    except Exception:
        pass

    # 解析平台
    platform_map = {
        "小红书": "xiaohongshu",
        "公众号": "gongzhonghao",
        "抖音": "douyin",
    }
    enabled = {platform_map[p] for p in platforms if p in platform_map}

    if not enabled:
        yield "", "", "", "", "", "⚠️ 请至少选择一个平台", history, gr.Dropdown()
        return

    # 拆分多篇笔记
    if batch_mode:
        notes_list = [n.strip() for n in re.split(r'\n\s*---\s*\n', note_text) if n.strip()]
    else:
        notes_list = [note_text]

    if not notes_list:
        yield "", "", "", "", "", "⚠️ 未能解析出有效笔记", history, gr.Dropdown()
        return

    # 风格指令
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

    # 立即反馈：让用户知道已经开始处理
    yield "", "", "", "", "", "⏳ 正在初始化 Agent，请稍候...", history, gr.Dropdown()

    all_xiaohongshu = []
    all_gongzhonghao = []
    all_douyin = []
    all_tags = []

    for idx, single_note in enumerate(notes_list, 1):
        base_progress = (idx - 1) / len(notes_list)
        progress(base_progress, desc=f"处理第 {idx}/{len(notes_list)} 篇...")

        current_notes = single_note

        # 搜索增强
        if enable_research:
            progress(base_progress + 0.05, desc=f"笔记 {idx}: 搜索增强...")
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

        styled_notes = current_notes + style_note if style_note else current_notes

        # 生成 + 质检
        progress(base_progress + 0.1, desc=f"笔记 {idx}: 生成中...")
        generation_result = None

        for attempt in range(1, 4):
            try:
                generation_result = agent.run(styled_notes)
            except Exception as e:
                generation_result = None
                print(f"笔记 {idx} Agent 调用失败: {e}")
                break

            progress(base_progress + 0.1 + attempt * 0.05, desc=f"笔记 {idx}: 质检第 {attempt} 次...")

            check = checker.check(
                generation_result.xiaohongshu,
                generation_result.gongzhonghao,
                generation_result.douyin,
                attempt=attempt,
            )

            if check.passed:
                break

            if attempt < 3:
                styled_notes = (
                    f"【请根据以下改进要求重新输出三平台文案】\n"
                    f"{check.retry_suggestion}\n\n"
                    f"--- 原始笔记 ---\n{single_note}"
                )

        if generation_result is None:
            xs = gh = dy = "❌ 生成失败"
            tag = ""
        else:
            xs = generation_result.xiaohongshu if "xiaohongshu" in enabled else "（未选择此平台）"
            gh = generation_result.gongzhonghao if "gongzhonghao" in enabled else "（未选择此平台）"
            dy = generation_result.douyin if "douyin" in enabled else "（未选择此平台）"
            tag = generation_result.recommended_tags or ""

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

    # 合并结果
    sep = "\n\n---\n\n" if len(notes_list) > 1 else "\n"
    xiaohongshu_text = sep.join(all_xiaohongshu)
    gongzhonghao_text = sep.join(all_gongzhonghao)
    douyin_text = sep.join(all_douyin)

    # 推荐标签只取第一篇的
    tags_text = all_tags[0] if all_tags else ""

    # HTML 预览只用第一篇
    xiaohongshu_html = ""
    first_xs = all_xiaohongshu[0]
    if "xiaohongshu" in enabled and first_xs and not first_xs.startswith("❌"):
        # 提取第一篇的纯文案部分（去掉 ## 标题）
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

    # 追加到历史记录
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "note_preview": f"批量 {len(notes_list)} 篇" if len(notes_list) > 1 else note_text[:30] + "...",
        "xiaohongshu": xiaohongshu_text,
        "gongzhonghao": gongzhonghao_text,
        "douyin": douyin_text,
        "recommended_tags": tags_text,
    }
    history = [entry] + (history if history else [])[:9]

    choices = [(f"{e['time']} | {e['note_preview']}", str(i)) for i, e in enumerate(history)]
    history_dropdown = gr.Dropdown(choices=choices, value=None)

    status = f"✅ 完成！共 {len(notes_list)} 篇 | 平台: {', '.join(platforms)} | 耗时请参考页面状态栏"
    if sensitive_check and sensitive_check["has_sensitive"]:
        hits = [h["word"] for h in sensitive_check["hits"][:5]]
        warn = f"⚠️ 检测到{sensitive_check['local_count']}个敏感/违规词: {', '.join(hits)}"
        if len(sensitive_check["hits"]) > 5:
            warn += f" 等共{len(sensitive_check['hits'])}个"
        status += f"\n{warn}"
    progress(1.0, desc="完成")
    yield xiaohongshu_text, gongzhonghao_text, douyin_text, xiaohongshu_html, tags_text, status, history, history_dropdown


def refine_content(xiaohongshu, gongzhonghao, douyin, instruction, note_text, style, history, progress=gr.Progress()):
    """根据修改指令，在当前文案基础上重新生成"""
    instruction = instruction.strip() if instruction else ""
    if not instruction:
        return xiaohongshu, gongzhonghao, douyin, "", "", "⚠️ 请输入修改指令", history, gr.Dropdown()

    progress(0.2, desc="准备优化...")
    agent = _get_agent()

    # 风格指令
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
        return xiaohongshu, gongzhonghao, douyin, "", "", f"❌ 优化失败: {e}", history, gr.Dropdown()

    progress(0.8, desc="整理结果...")

    # 生成小红书 HTML 卡片预览
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

    # 追加到历史记录
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "note_preview": f"优化: {instruction[:20]}...",
        "xiaohongshu": result.xiaohongshu,
        "gongzhonghao": result.gongzhonghao,
        "douyin": result.douyin,
        "recommended_tags": result.recommended_tags or "",
    }
    history = [entry] + (history if history else [])[:9]

    choices = [(f"{e['time']} | {e['note_preview']}", str(i)) for i, e in enumerate(history)]
    history_dropdown = gr.Dropdown(choices=choices, value=None)

    status = f"✅ 优化完成！指令: {instruction[:20]}..."
    progress(1.0, desc="完成")
    return result.xiaohongshu, result.gongzhonghao, result.douyin, xiaohongshu_html, result.recommended_tags or "", status, history, history_dropdown


def restore_history(selected_index, history):
    """从历史记录恢复文案到输出区"""
    if not selected_index or not history:
        return "", "", "", "", "", "⚠️ 请先选择历史记录"

    try:
        idx = int(selected_index)
        entry = history[idx]
    except (ValueError, IndexError):
        return "", "", "", "", "", "❌ 无效的历史记录"

    # 生成小红书 HTML 预览
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
    """为当前三平台文案各生成 3 个备选标题"""
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


def generate_cover_prompt(xiaohongshu, progress=gr.Progress()):
    """根据小红书文案生成 AI 绘画 Prompt"""
    if not xiaohongshu or xiaohongshu == "（未选择此平台）":
        return "⚠️ 请先生成小红书文案", ""

    progress(0.3, desc="准备配图 prompt...")
    agent = _get_agent()

    from pydantic_ai import Agent as PydanticAgent

    cover_agent = PydanticAgent(
        agent.model,
        system_prompt="你是一位专业的 AI 绘画提示词工程师，擅长根据文案内容生成高质量的小红书封面图绘画 prompt。",
    )

    prompt = f"""请根据以下小红书文案，生成一个适合作为小红书封面图的 AI 绘画 prompt。

要求：
- 画面风格：清新、现代、适合科技/学习类内容，色彩明快
- 构图：适合 3:4 竖版比例（小红书封面）
- 不要包含文字或字符，纯图像
- 提供中文画面描述和英文 Midjourney 风格 prompt
- Midjourney prompt 需包含风格参数（如 --ar 3:4）

文案内容：
{xiaohongshu[:1200]}

请严格按以下格式输出：
【画面描述】
（用一段话描述画面内容、色彩、氛围、构图）

【Midjourney Prompt】
（英文关键词组成的 prompt，结尾带 --ar 3:4 等参数）
"""

    try:
        r = cover_agent.run_sync(prompt)
        result = r.output.strip()
    except Exception as e:
        return f"生成失败: {e}", ""

    progress(1.0, desc="完成")
    return result, "✅ 配图 prompt 生成完成，可复制到 Midjourney/通义万相/即梦 等工具"


# ==================== 导出功能 ====================

def export_markdown(platform: str, content: str):
    """导出指定平台文案为 Markdown 文件"""
    if not content or content.startswith("（未选择此平台）") or content.startswith("❌"):
        return gr.update(value=None, visible=False), f"⚠️ {platform} 无内容可导出"

    fd, path = tempfile.mkstemp(suffix=f"_{platform}.md", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {platform}文案\ndate: {datetime.now().isoformat()}\nplatform: {platform}\n---\n\n")
        f.write(content)
    return gr.update(value=path, visible=True), f"✅ {platform} Markdown 已就绪，点击下载"


def export_word(platform: str, content: str):
    """导出指定平台文案为精美排版的 Word 文件"""
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
    """发布公众号文案到微信草稿箱"""
    from content_agent.publisher import publish_wechat_draft, save_content_as_markdown

    if not gongzhonghao_text or gongzhonghao_text.startswith("（未选择此平台）"):
        return "❌ 公众号文案为空，请先生成文案"

    # 确定封面路径
    cover_path = ""
    if cover_file:
        # Gradio File 组件返回临时文件路径
        if isinstance(cover_file, str):
            cover_path = cover_file
        elif hasattr(cover_file, "name"):
            cover_path = cover_file.name
    if not cover_path and cover_url and cover_url.strip():
        cover_path = cover_url.strip()

    if not cover_path:
        return "❌ 微信草稿要求必须有封面图片，请上传封面或填入图片 URL"

    # 保存 Markdown
    article_title = title.strip() or "未命名文章"
    md_path = save_content_as_markdown(article_title, gongzhonghao_text)

    # 调用 kuaifa
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

    with gr.Row():
        # 左侧：输入区
        with gr.Column(scale=1):
            # ── 模型配置 ──
            with gr.Accordion("⚙️ 模型配置（第一次使用请先填写）", open=False) as config_accordion:
                config_status = gr.Textbox(
                    label="状态",
                    value=get_config_status()[1],
                    interactive=False,
                )

                provider_select = gr.Dropdown(
                    label="选择 Provider",
                    choices=[
                        ("DeepSeek (推荐，性价比最高)", "deepseek"),
                        ("Kimi (月之暗面)", "kimi"),
                        ("MiniMax", "minimax"),
                        ("OpenAI / Azure", "openai"),
                        ("自定义 OpenAI-compatible", "custom"),
                    ],
                    value=load_config_for_ui()["provider"],
                )

                # 各 Provider 的 Key 输入（password 隐藏）
                deepseek_key_input = gr.Textbox(
                    label="DeepSeek API Key",
                    placeholder="sk-...",
                    type="password",
                    value=load_config_for_ui()["deepseek_key"],
                    visible=load_config_for_ui()["provider"] == "deepseek",
                )
                kimi_key_input = gr.Textbox(
                    label="Kimi API Key",
                    placeholder="sk-...",
                    type="password",
                    value=load_config_for_ui()["kimi_key"],
                    visible=load_config_for_ui()["provider"] == "kimi",
                )
                minimax_key_input = gr.Textbox(
                    label="MiniMax API Key",
                    placeholder="your-minimax-api-key",
                    type="password",
                    value=load_config_for_ui()["minimax_key"],
                    visible=load_config_for_ui()["provider"] == "minimax",
                )
                openai_key_input = gr.Textbox(
                    label="OpenAI API Key",
                    placeholder="sk-...",
                    type="password",
                    value=load_config_for_ui()["openai_key"],
                    visible=load_config_for_ui()["provider"] == "openai",
                )

                # 自定义平台扩展字段
                with gr.Column(visible=load_config_for_ui()["provider"] == "custom") as custom_fields:
                    custom_key_input = gr.Textbox(
                        label="API Key",
                        placeholder="sk-...",
                        type="password",
                        value=load_config_for_ui()["custom_key"],
                    )
                    custom_base_url_input = gr.Textbox(
                        label="Base URL",
                        placeholder="https://api.example.com/v1",
                        value=load_config_for_ui()["custom_base_url"],
                    )
                    custom_model_name_input = gr.Textbox(
                        label="Model Name",
                        placeholder="deepseek-ai/DeepSeek-V3",
                        value=load_config_for_ui()["custom_model_name"],
                    )
                    gr.Markdown("""
                    常见平台参考：
                    - 硅基流动: `https://api.siliconflow.cn/v1` + `deepseek-ai/DeepSeek-V3`
                    - 通义千问: `https://dashscope.aliyuncs.com/compatible-mode/v1` + `qwen-plus`
                    - 智谱: `https://open.bigmodel.cn/api/paas/v4` + `glm-4-flash`
                    - Ollama: `http://localhost:11434/v1` + `qwen2.5:7b`
                    """)

                # ── Tavily 搜索引擎 Key ──
                gr.Markdown("---")
                tavily_key_input = gr.Textbox(
                    label="Tavily API Key（搜索增强用，可选）",
                    placeholder="tvly-... （选填，用 Tavily 搜索时需要）",
                    type="password",
                    value=load_config_for_ui()["tavily_key"],
                )
                gr.Markdown("注册: [https://app.tavily.com/home](https://app.tavily.com/home) 免费 1000 credits/月")

                save_config_btn = gr.Button("💾 保存配置", variant="primary", size="sm")

            # ── Provider 切换时显示/隐藏对应的 Key 输入框 ──
            def _toggle_provider_inputs(provider):
                return {
                    deepseek_key_input: gr.update(visible=provider == "deepseek"),
                    kimi_key_input: gr.update(visible=provider == "kimi"),
                    minimax_key_input: gr.update(visible=provider == "minimax"),
                    openai_key_input: gr.update(visible=provider == "openai"),
                    custom_fields: gr.update(visible=provider == "custom"),
                }

            provider_select.change(
                fn=_toggle_provider_inputs,
                inputs=[provider_select],
                outputs=[deepseek_key_input, kimi_key_input, minimax_key_input, openai_key_input, custom_fields],
            )

            save_config_btn.click(
                fn=save_config,
                inputs=[
                    provider_select,
                    deepseek_key_input,
                    kimi_key_input,
                    minimax_key_input,
                    openai_key_input,
                    custom_key_input,
                    custom_base_url_input,
                    custom_model_name_input,
                    tavily_key_input,
                ],
                outputs=[config_status],
            )

            # —— kuaifa 发布配置 ——
            with gr.Accordion("🔧 发布配置（kuaifa 微信公众号）", open=False):
                kf_cfg = load_kuaifa_config()
                kuaifa_status = gr.Textbox(
                    label="状态",
                    value=get_kuaifa_setup_status(),
                    interactive=False,
                )
                kuaifa_appid = gr.Textbox(
                    label="微信 AppID",
                    placeholder="wx...",
                    value=kf_cfg.get("appid", ""),
                )
                kuaifa_appsecret = gr.Textbox(
                    label="微信 AppSecret",
                    placeholder="微信公众号的 AppSecret",
                    type="password",
                    value=kf_cfg.get("appsecret", ""),
                )
                kuaifa_api_key = gr.Textbox(
                    label="kuaifa API Key",
                    placeholder="kuaifa_...",
                    type="password",
                    value=kf_cfg.get("api-key", ""),
                )
                kuaifa_author = gr.Textbox(
                    label="默认作者名",
                    placeholder="如：小爪",
                    value=kf_cfg.get("default-author", ""),
                )
                with gr.Row():
                    save_kuaifa_btn = gr.Button("💾 保存发布配置", variant="primary", size="sm")
                    verify_kuaifa_btn = gr.Button("🔐 验证微信配置", size="sm")

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

            with gr.Group():
                gr.Markdown("### 📜 生成历史")
                history_dropdown = gr.Dropdown(
                    label="选择历史记录",
                    choices=[],
                    value=None,
                )
                restore_btn = gr.Button("🔄 恢复到输出区", variant="secondary", size="sm")

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

                with gr.TabItem("⏰ 定时任务"):
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

                with gr.TabItem("📅 内容日历"):
                    gr.Markdown("### 📅 内容发布计划")
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

            with gr.Group():
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

            with gr.Group():
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

            with gr.Group():
                gr.Markdown("### 🎨 配图 Prompt 生成")
                cover_prompt_btn = gr.Button("🖼️ 生成小红书封面配图 Prompt", variant="secondary")
                cover_prompt_output = gr.Textbox(
                    label="绘画 Prompt（可复制到 Midjourney/通义万相/即梦）",
                    lines=10,
                    show_copy_button=True,
                )

    # ==================== 定时任务处理函数 ====================

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
    # —— kuaifa 发布配置绑定 ——
    save_kuaifa_btn.click(
        fn=save_kuaifa_config,
        inputs=[kuaifa_appid, kuaifa_appsecret, kuaifa_api_key, kuaifa_author],
        outputs=[kuaifa_status],
    )
    verify_kuaifa_btn.click(
        fn=verify_kuaifa_config,
        inputs=[],
        outputs=[kuaifa_status],
    )

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
            history_dropdown,
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
            history_dropdown,
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

    restore_btn.click(
        fn=restore_history,
        inputs=[history_dropdown, history_state],
        outputs=[
            xiaohongshu_output,
            gongzhonghao_output,
            douyin_output,
            xiaohongshu_preview,
            tags_output,
            status_text,
        ],
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
