"""
LLM Judge - 用 LLM 给内容打分
"""

import json
import os
from typing import Optional


class LLMJudge:
    """LLM 内容评分器"""

    SYSTEM_PROMPT = """你是一位资深内容编辑，擅长评估中文技术文案的质量。

请对以下文案进行评分（1-10分，10分为最佳）。

评分维度：
1. 相关性：内容与主题的相关程度
2. 可读性：语言是否流畅，结构是否清晰
3. 原创性：是否有独特见解，而非泛泛而谈
4. 实用性：读者能否从中获得实际价值

请严格按以下 JSON 格式输出，不要添加其他内容：
{
  "relevance": 8,
  "readability": 7,
  "originality": 6,
  "practicality": 9,
  "overall": 7.5,
  "strengths": ["优点1", "优点2"],
  "weaknesses": ["不足1", "不足2"]
}"""

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.getenv("MODEL_PROVIDER", "deepseek")

    def evaluate(self, content: str, topic: str = "") -> dict:
        """
        评估内容质量

        Args:
            content: 文案内容
            topic: 主题/标题（可选）

        Returns:
            {
                "relevance": int,
                "readability": int,
                "originality": int,
                "practicality": int,
                "overall": float,
                "strengths": list,
                "weaknesses": list,
            }
        """
        from pydantic_ai import Agent
        from content_agent.agent_core import ModelConfig

        # 获取模型配置
        model_config = ModelConfig.from_env()
        model = model_config[0] if isinstance(model_config, tuple) else model_config

        agent = Agent(
            model,
            system_prompt=self.SYSTEM_PROMPT,
        )

        prompt = f"主题：{topic}\n\n文案：\n{content[:3000]}"  # 限制长度，控制 token

        try:
            result = agent.run_sync(prompt)
            # 解析 JSON
            text = result.output.strip()
            # 提取 JSON 部分
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            scores = json.loads(text)
            return {
                "relevance": scores.get("relevance", 0),
                "readability": scores.get("readability", 0),
                "originality": scores.get("originality", 0),
                "practicality": scores.get("practicality", 0),
                "overall": scores.get("overall", 0.0),
                "strengths": scores.get("strengths", []),
                "weaknesses": scores.get("weaknesses", []),
            }
        except Exception as e:
            print(f"[LLMJudge] 评分失败: {e}")
            return {
                "relevance": 0,
                "readability": 0,
                "originality": 0,
                "practicality": 0,
                "overall": 0.0,
                "strengths": [],
                "weaknesses": [f"评分失败: {e}"],
            }


def demo():
    """测试评分"""
    judge = LLMJudge()

    content = """
# 从脚本到 CLI 工具：AI Content Agent 改造实践

前几周我搭建了一个 Content Agent，能把技术笔记改写成多平台文案。
但有个问题：笔记是写死在代码里的。

于是我进行了工程化改造...
"""

    result = judge.evaluate(content, "AI Agent CLI 改造")
    print("评分结果:")
    print(f"  相关性: {result['relevance']}/10")
    print(f"  可读性: {result['readability']}/10")
    print(f"  原创性: {result['originality']}/10")
    print(f"  实用性: {result['practicality']}/10")
    print(f"  综合: {result['overall']}/10")
    print(f"  优点: {result['strengths']}")
    print(f"  不足: {result['weaknesses']}")


if __name__ == "__main__":
    demo()
