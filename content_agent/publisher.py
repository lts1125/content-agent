"""
内容发布 — 调用外部工具将文案发布到各平台

当前支持：
- 微信公众号草稿箱（通过 kuaifa CLI）
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class PublisherError(Exception):
    """发布相关错误"""
    pass


def _find_kuaifa() -> "str | None":
    """查找 kuaifa 可执行文件，先用 shutil.which，再尝试常见安装路径"""
    # 1. 尝试系统 PATH
    kf = shutil.which("kuaifa")
    if kf:
        return kf

    # 2. 尝试常见路径（包括 Hermes 安装的 node 模块）
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


def _find_node() -> "str | None":
    """查找 node 可执行文件，kuaifa 的 shebang 依赖 env node"""
    node = shutil.which("node")
    if node:
        return node
    home = Path.home()
    candidates = [
        home / ".hermes" / "node" / "bin" / "node",
        home / ".nvm" / "versions" / "node" / "current" / "bin" / "node",
        Path("/usr/local/bin/node"),
        Path("/opt/homebrew/bin/node"),
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return None


def check_kuaifa() -> tuple[bool, str]:
    """检查 kuaifa CLI 是否可用，返回 (是否可用, 版本信息)"""
    kuaifa_path = _find_kuaifa()
    if not kuaifa_path:
        return False, "kuaifa CLI 未安装或未在 PATH 中"
    node_path = _find_node()
    if not node_path:
        return False, "未找到 Node.js，kuaifa 需要 Node 环境才能运行"
    try:
        # 确保调用时能找到 node 等依赖
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
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, f"kuaifa 检查失败: {e.stderr}"


def publish_wechat_draft(
    markdown_path: str,
    title: str,
    cover_path: str = "",
    author: str = "",
    digest: str = "",
    template_id: str = "",
) -> dict:
    """
    发布文章到微信公众号草稿箱

    Args:
        markdown_path: Markdown 文件路径
        title: 文章标题
        cover_path: 封面图片路径或 URL（微信草稿必须有封面）
        author: 作者名
        digest: 文章摘要
        template_id: 模板 ID

    Returns:
        {"success": bool, "message": str, "details": str}
    """
    ok, info = check_kuaifa()
    if not ok:
        return {"success": False, "message": "❌ kuaifa 未安装", "details": info}

    kuaifa_path = _find_kuaifa()
    node_path = _find_node()
    if not kuaifa_path or not node_path:
        return {"success": False, "message": "❌ 找不到 kuaifa 或 Node.js", "details": ""}

    # 确保调用时能找到 node 等依赖
    env = os.environ.copy()
    extra_paths = [str(Path(kuaifa_path).parent), str(Path(node_path).parent)]
    env["PATH"] = os.pathsep.join(extra_paths + [env.get("PATH", "")])

    cmd = [
        node_path,
        kuaifa_path,
        "publish",
        markdown_path,
        "--draft",
        "--title", title,
    ]
    if cover_path:
        cmd.extend(["--cover", cover_path])
    if author:
        cmd.extend(["--author", author])
    if digest:
        cmd.extend(["--digest", digest])
    if template_id:
        cmd.extend(["--template", template_id])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        if result.returncode == 0:
            return {
                "success": True,
                "message": "✅ 已成功保存到微信公众号草稿箱",
                "details": result.stdout,
            }
        else:
            return {
                "success": False,
                "message": "❌ 发布失败",
                "details": result.stderr or result.stdout,
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "❌ 发布超时（超过60秒）",
            "details": "",
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"❌ 发布异常: {e}",
            "details": str(e),
        }


def save_content_as_markdown(title: str, content: str, output_dir: str = "") -> str:
    """
    将文案保存为 Markdown 文件，返回文件路径
    """
    if not output_dir:
        output_dir = tempfile.gettempdir()
    out_path = Path(output_dir) / f"{title.replace(' ', '_').replace('/', '_')[:50]}.md"
    out_path.write_text(content, encoding="utf-8")
    return str(out_path)


def list_kuaifa_templates() -> list[dict]:
    """获取 kuaifa 可用模板列表"""
    kuaifa_path = _find_kuaifa()
    node_path = _find_node()
    if not kuaifa_path or not node_path:
        return []
    try:
        env = os.environ.copy()
        extra_paths = [str(Path(kuaifa_path).parent), str(Path(node_path).parent)]
        env["PATH"] = os.pathsep.join(extra_paths + [env.get("PATH", "")])
        result = subprocess.run(
            [node_path, kuaifa_path, "template", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
            env=env,
        )
        # 简单解析输出，每行一个模板
        templates = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("-"):
                continue
            parts = line.split(None, 1)
            if len(parts) >= 2:
                templates.append({"id": parts[0], "name": parts[1]})
            elif len(parts) == 1:
                templates.append({"id": parts[0], "name": parts[0]})
        return templates
    except Exception:
        return []
