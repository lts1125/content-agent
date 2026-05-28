"""
Researcher Agent — 资料搜集 Agent

负责：
1. 搜索相关资料
2. 浏览网页获取详细信息
3. 整理研究报告
"""

from pydantic_ai import Agent

from content_agent.config.model_config import ModelConfig


RESEARCH_SYSTEM_PROMPT = """你是一位专业的研究员，擅长搜集和整理技术资料。

任务：
1. 根据主题搜索相关资料
2. 整理关键信息
3. 输出结构化的研究报告

输出格式：
## 核心概念
[概念解释]

## 关键信息
- [要点1]
- [要点2]
- [要点3]

## 应用场景
[场景描述]

## 相关链接
[如果有]

注意：
- 信息要准确、简洁
- 优先使用中文
- 技术术语保留英文
"""


class ResearcherAgent:
    """资料搜集 Agent"""

    def __init__(self):
        self.model, _ = ModelConfig.from_env()
        self._agent = Agent(
            self.model,
            system_prompt=RESEARCH_SYSTEM_PROMPT,
        )

    def run(self, topic: str) -> str:
        """
        搜集资料并生成研究报告

        Args:
            topic: 研究主题

        Returns:
            研究报告文本
        """
        # 1. 搜索相关资料
        search_results = self._search(topic)

        # 2. 整理研究报告
        prompt = f"""请根据以下搜索结果，整理一份研究报告：

主题：{topic}

搜索结果：
{search_results[:2000]}

请输出结构化的研究报告。"""

        result = self._agent.run_sync(prompt)
        return result.output if isinstance(result.output, str) else str(result.output)

    def _search(self, query: str) -> str:
        """执行搜索"""
        try:
            from agents.tools import execute_tool
            result = execute_tool("search", query=query)
            if result.success:
                return result.data
            return f"搜索失败: {result.error}"
        except Exception as e:
            return f"搜索异常: {e}"
