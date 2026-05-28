"""
数据分析工具
"""

from pydantic_ai import Agent

from content_agent.config.model_config import ModelConfig

from .base import BaseTool, ToolResult


class DataAnalysisTool(BaseTool):
    """数据分析工具 - 分析数据并生成洞察"""

    def __init__(self):
        super().__init__(
            name="analyze",
            description="分析数据并生成洞察。参数: data(数据内容), analysis_type(分析类型: summary/trend/comparison)"
        )
        self.model, _ = ModelConfig.from_env()
        self._agent = Agent(
            self.model,
            system_prompt="""你是一位数据分析师，擅长从数据中提取洞察。

任务：
1. 分析提供的数据
2. 提取关键趋势和模式
3. 生成结构化分析报告

输出格式：
## 数据概览
[总体描述]

## 关键发现
- [发现1]
- [发现2]

## 趋势分析
[趋势描述]

## 建议
[基于数据的建议]
""",
        )

    def execute(self, data: str, analysis_type: str = "summary") -> ToolResult:
        """执行数据分析"""
        try:
            prompt = f"""请对以下数据进行{analysis_type}分析：

数据：
{data[:3000]}

请输出结构化分析报告。"""

            result = self._agent.run_sync(prompt)
            return ToolResult(success=True, data=result.output)
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))
