"""
内容发布 — 调用外部工具将文案发布到各平台

当前支持：
- 微信公众号草稿箱（通过 kuaifa CLI）
"""

import shutil
import subprocess
import tempfile
from pathlib import Path


class PublisherError(Exception):
    """发布相关错误"""
    pass


def check_kuaifa() -> tuple[bool, str]:
    """检查 kuaifa CLI 是否可用，返回 (是否可用, 版本信息)"""
    kuaifa_path = shutil.which("kuaifa")
    if not kuaifa_path:
        return False, "kuaifa CLI 未安装或未在 PATH 中"
    try:
        result = subprocess.run(
            ["kuaifa", "--version"],
            capture_output=True,
            text=True,
            check=True,
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

    cmd = [
        "kuaifa",
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
    ok, _ = check_kuaifa()
    if not ok:
        return []
    try:
        result = subprocess.run(
            ["kuaifa", "template", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
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
