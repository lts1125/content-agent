"""
代码执行工具
"""

from .base import BaseTool, ToolResult


class CodeExecutionTool(BaseTool):
    """代码执行工具 - 安全执行 Python 代码"""

    def __init__(self):
        super().__init__(
            name="execute",
            description="执行 Python 代码并返回结果。参数: code(代码字符串)"
        )

    def execute(self, code: str) -> ToolResult:
        """安全执行代码"""
        try:
            # 安全检查：禁止危险操作
            dangerous_keywords = [
                'import os', 'import sys', 'open(', 'eval(', 'exec(',
                '__import__', 'subprocess', 'shell', 'rm -rf',
                'import socket', 'import urllib',
            ]

            code_lower = code.lower()
            for keyword in dangerous_keywords:
                if keyword in code_lower:
                    return ToolResult(
                        success=False,
                        data="",
                        error=f"代码包含危险操作: {keyword}"
                    )

            # 在受限环境中执行
            import io
            import contextlib

            # 捕获输出
            output_buffer = io.StringIO()

            # 创建受限的全局命名空间
            safe_globals = {
                '__builtins__': {
                    'print': print,
                    'len': len,
                    'range': range,
                    'enumerate': enumerate,
                    'zip': zip,
                    'map': map,
                    'filter': filter,
                    'sum': sum,
                    'min': min,
                    'max': max,
                    'abs': abs,
                    'round': round,
                    'str': str,
                    'int': int,
                    'float': float,
                    'list': list,
                    'dict': dict,
                    'tuple': tuple,
                    'set': set,
                    'sorted': sorted,
                    'reversed': reversed,
                }
            }

            safe_locals = {}

            with contextlib.redirect_stdout(output_buffer):
                exec(code, safe_globals, safe_locals)

            output = output_buffer.getvalue()

            return ToolResult(success=True, data=output or "代码执行成功，无输出")

        except Exception as e:
            return ToolResult(success=False, data="", error=f"代码执行错误: {e}")
