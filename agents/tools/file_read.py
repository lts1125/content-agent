"""
文件读取工具
"""

from pathlib import Path

from .base import BaseTool, ToolResult


class FileReadTool(BaseTool):
    """文件读取工具 - 读取本地文件"""

    def __init__(self):
        super().__init__(
            name="read",
            description="读取本地文件内容。参数: path(文件路径)"
        )

    def execute(self, path: str) -> ToolResult:
        """执行文件读取"""
        try:
            # 安全检查：限制文件路径在项目目录下
            project_root = Path(__file__).resolve().parent.parent.parent
            resolved_path = Path(path).expanduser().resolve()

            # 检查是否在项目目录或用户笔记目录下
            allowed_roots = [
                project_root,
                Path.home() / "notes",
                Path.home() / "wechat_doc",
            ]

            # 检查是否在允许的路径下
            allowed = any(
                resolved_path == root or resolved_path.is_relative_to(root)
                for root in allowed_roots
            )
            if not allowed:
                return ToolResult(
                    success=False,
                    data="",
                    error=f"文件路径不在允许范围内: {path}"
                )

            # 读取文件
            with open(resolved_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 截断过长的内容
            if len(content) > 5000:
                content = content[:5000] + "..."

            return ToolResult(success=True, data=content)
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))
