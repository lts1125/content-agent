"""
ui/state.py — Web UI 的状态管理与配置函数

所有与 Gradio 组件无关的纯逻辑函数放在这里，供 web_ui.py 和各 Tab 模块共用。
避免 web_ui.py 与 tabs 之间的循环导入。
"""

import json
import os
import sys
from pathlib import Path

import gradio as gr

# 检测是否在 PyInstaller 打包环境中运行
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

# ---------------------------------------------------------------------------
# .env 文件操作
# ---------------------------------------------------------------------------

def read_env_file() -> dict:
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


def ensure_default_env():
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


def write_env_file(env: dict):
    """将配置字典写回 .env 文件（保留注释和格式）"""
    ensure_default_env()
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


# ---------------------------------------------------------------------------
# 模型配置
# ---------------------------------------------------------------------------

def get_config_status():
    """检查当前配置是否可用，返回 (是否可用, 提示信息)"""
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
    """加载当前配置，用于填充 UI 表单"""
    env = read_env_file()
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

    write_env_file(env)
    ok, msg = get_config_status()
    return msg


# ---------------------------------------------------------------------------
# 笔记库
# ---------------------------------------------------------------------------

def get_vault_path() -> str:
    """读取保存的笔记库路径"""
    env = read_env_file()
    path = env.get("VAULT_PATH", os.getenv("VAULT_PATH", ""))
    return path.strip()


def save_vault_path(path: str) -> str:
    """保存笔记库路径到 .env"""
    p = path.strip()
    if not p:
        return "❌ 路径不能为空"
    if not Path(p).exists():
        return f"❌ 路径不存在: {p}"
    write_env_file({"VAULT_PATH": p})
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
    msg = save_vault_path(vault_path)
    choices = scan_vault_files(vault_path.strip())
    return msg, gr.Dropdown(choices=choices)


def on_vault_refresh(vault_path: str):
    """刷新笔记库文件列表"""
    choices = scan_vault_files(vault_path.strip())
    return gr.Dropdown(choices=choices)


def on_vault_select(vault_path: str, rel_path: str) -> str:
    """选择笔记库文件后读取内容"""
    return read_vault_file(vault_path.strip(), rel_path)


# ---------------------------------------------------------------------------
# kuaifa 发布配置
# ---------------------------------------------------------------------------

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


def _find_kuaifa() -> "str | None":
    """查找 kuaifa 可执行文件"""
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
    """检查 kuaifa 是否可用"""
    import shutil
    import subprocess

    kuaifa_path = _find_kuaifa()
    if not kuaifa_path:
        return "❌ kuaifa CLI 未安装"
    node_path = shutil.which("node")
    if not node_path:
        return "❌ 未找到 Node.js"
    try:
        env = os.environ.copy()
        extra_paths = [str(Path(kuaifa_path).parent), str(Path(node_path).parent)]
        env["PATH"] = os.pathsep.join(extra_paths + [env.get("PATH", "")])
        result = subprocess.run(
            [node_path, kuaifa_path, "--version"],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        return f"✅ kuaifa 已安装: {result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        return f"❌ kuaifa 检查失败: {e.stderr}"


def verify_kuaifa_config() -> str:
    """验证微信配置是否正确"""
    import shutil
    import subprocess

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
