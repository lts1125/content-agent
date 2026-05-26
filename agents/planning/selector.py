"""
策略选择器

根据内容自动选择策略
"""

from typing import Optional

from pydantic_ai import Agent

from agents.planning.strategy import ContentType, Strategy, STRATEGIES
from agents.writer_agent import _ModelConfig


class StrategySelector:
    """策略选择器"""

    def __init__(self):
        self.model, _ = _ModelConfig.from_env()
        self._agent = Agent(
            self.model,
            system_prompt="""你是一位内容分类专家，擅长识别文本的内容类型。

任务：根据提供的文本内容，判断其属于哪种类型。

可选类型：
- 深度长文：技术教程、源码分析、架构设计等深入技术内容
- 热点快讯：行业动态、产品发布、新闻资讯等时效性内容
- 实战教程：手把手教学、代码示例、操作指南等实践内容
- 评测对比：产品评测、方案对比、性能测试等比较内容
- 观点评论：个人见解、趋势判断、经验分享等主观内容

输出要求：
- 只输出类型名称，不要解释
- 如果不确定，输出"未知类型"
""",
        )

    def select(self, raw_notes: str, topic: str = "") -> Strategy:
        """
        根据内容自动选择策略

        Args:
            raw_notes: 原始笔记内容
            topic: 主题（可选）

        Returns:
            选择的策略
        """
        # 使用 LLM 判断内容类型
        prompt = f"""请判断以下内容属于哪种类型：

{raw_notes[:1000]}

类型："""

        try:
            result = self._agent.run_sync(prompt)
            content_type = self._parse_type(result.output)
            return STRATEGIES.get(content_type, STRATEGIES[ContentType.UNKNOWN])
        except Exception:
            return STRATEGIES[ContentType.UNKNOWN]

    def _parse_type(self, text: str) -> ContentType:
        """解析类型文本"""
        text = text.strip().lower()

        if "深度" in text or "教程" in text or "源码" in text or "架构" in text:
            return ContentType.DEEP_DIVE
        elif "热点" in text or "新闻" in text or "快讯" in text or "动态" in text:
            return ContentType.HOT_NEWS
        elif "实战" in text or "教学" in text or "指南" in text or "步骤" in text:
            return ContentType.TUTORIAL
        elif "评测" in text or "对比" in text or "测试" in text or "比较" in text:
            return ContentType.REVIEW
        elif "观点" in text or "评论" in text or "见解" in text or "经验" in text:
            return ContentType.OPINION
        else:
            return ContentType.UNKNOWN
