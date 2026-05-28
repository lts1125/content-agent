"""内容发布工具
"""

from .base import BaseTool, ToolResult


class PublishTool(BaseTool):
    """发布工具 - 发布内容"""

    def __init__(self):
        super().__init__(
            name="publish",
            description="发布内容到平台。参数: queue_id(队列项ID)"
        )

    def execute(self, queue_id: str) -> ToolResult:
        """执行发布"""
        try:
            from automation.executor import PublishExecutor
            executor = PublishExecutor()
            result = executor.execute_one(queue_id)
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))
