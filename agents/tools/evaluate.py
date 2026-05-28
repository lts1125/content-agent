"""内容评估工具
"""

from .base import BaseTool, ToolResult


class EvaluateTool(BaseTool):
    """评估工具 - 评估内容质量"""

    def __init__(self, editor_agent=None):
        super().__init__(
            name="evaluate",
            description="评估内容质量。参数: xiaohongshu(小红书内容), gongzhonghao(公众号内容), douyin(抖音内容)"
        )
        self.editor_agent = editor_agent

    def execute(self, **kwargs) -> ToolResult:
        """执行评估"""
        try:
            if self.editor_agent is None:
                from content_agent.config.model_config import ModelConfig
                from agents.editor_agent import EditorAgent
                model, _ = ModelConfig.from_env()
                self.editor_agent = EditorAgent(model)

            if len(kwargs) == 1:
                platform, content = list(kwargs.items())[0]
                result = self.editor_agent.run_single(platform, content)
                return ToolResult(success=True, data=result)

            # 多平台评估
            xiaohongshu = kwargs.get("xiaohongshu", "")
            gongzhonghao = kwargs.get("gongzhonghao", "")
            douyin = kwargs.get("douyin", "")

            result = self.editor_agent.run(xiaohongshu, gongzhonghao, douyin)
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))
