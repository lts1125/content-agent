"""
内容生成工具
"""

from .base import BaseTool, ToolResult


class GenerateTool(BaseTool):
    """生成工具 - 生成内容"""

    def __init__(self, writer_agent=None):
        super().__init__(
            name="generate",
            description="生成内容。参数: raw_notes(原始笔记), platforms(平台列表), style(风格)"
        )
        self.writer_agent = writer_agent

    def execute(self, **kwargs) -> ToolResult:
        """执行生成"""
        try:
            if self.writer_agent is None:
                from agents.writer_agent import WriterAgent
                self.writer_agent = WriterAgent()

            raw_notes = kwargs.get("raw_notes", "")
            platforms = kwargs.get("platforms", ["gongzhonghao"])
            style = kwargs.get("style", "default")

            result = self.writer_agent.run(raw_notes, platforms, style=style)
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))
