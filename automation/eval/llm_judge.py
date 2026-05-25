"""
LLM Judge - 用 LLM 给内容打分（Phase 2：多维度独立评估）
"""

import json
import os
from typing import Optional


class LLMJudge:
    """LLM 内容评分器"""

    # 每个维度的独立评估 prompt
    DIMENSION_PROMPTS = {
        "relevance": """你是一位资深内容编辑。请评估以下文案与主题的相关程度（1-10分）。

主题：{topic}
文案：
{content}

请只输出一个 1-10 的整数分数，不要其他内容。""",
        "readability": """你是一位资深内容编辑。请评估以下文案的可读性（1-10分）。

评分标准：
- 语言是否流畅自然
- 结构是否清晰（标题、段落、列表）
- 是否易于理解

文案：
{content}

请只输出一个 1-10 的整数分数，不要其他内容。""",
        "originality": """你是一位资深内容编辑。请评估以下文案的原创性（1-10分）。

评分标准：
- 是否有独特见解
- 是否只是泛泛而谈
- 是否有个人经验或案例

文案：
{content}

请只输出一个 1-10 的整数分数，不要其他内容。""",
        "practicality": """你是一位资深内容编辑。请评估以下文案的实用性（1-10分）。

评分标准：
- 读者能否获得实际价值
- 是否有可操作的建议
- 是否能解决实际问题

文案：
{content}

请只输出一个 1-10 的整数分数，不要其他内容。""",
        "platform_fit": """你是一位资深内容编辑。请评估以下文案是否符合{platform}平台的风格（1-10分）。

{platform_desc}

文案：
{content}

请只输出一个 1-10 的整数分数，不要其他内容。""",
        "trend_match": """你是一位资深内容编辑。请评估以下文案与热点话题的匹配程度（1-10分）。

热点：{trend}
文案：
{content}

请只输出一个 1-10 的整数分数，不要其他内容。""",
    }

    PLATFORM_DESCRIPTIONS = {
        "xiaohongshu": "小红书：轻松活泼，多用emoji，短段落，口语化，个人经验分享为主",
        "gongzhonghao": "公众号：正式专业，结构完整，有深度，适合长文阅读",
        "douyin": "抖音：简短有力，抓人眼球，适合快速浏览",
    }

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.getenv("MODEL_PROVIDER", "deepseek")

    def _get_model(self):
        """获取模型实例"""
        from pydantic_ai import Agent
        from content_agent.agent_core import ModelConfig

        model_config = ModelConfig.from_env()
        model = model_config[0] if isinstance(model_config, tuple) else model_config
        return model

    def _evaluate_dimension(self, dimension: str, **kwargs) -> int:
        """评估单个维度"""
        from pydantic_ai import Agent

        prompt_template = self.DIMENSION_PROMPTS.get(dimension)
        if not prompt_template:
            return 0

        prompt = prompt_template.format(**kwargs)

        try:
            agent = Agent(self._get_model())
            result = agent.run_sync(prompt)
            # 提取数字
            text = result.output.strip()
            # 尝试解析 JSON 或直接数字
            try:
                score = int(text)
            except ValueError:
                # 尝试从文本中提取数字
                import re
                match = re.search(r'\b(\d+)\b', text)
                if match:
                    score = int(match.group(1))
                else:
                    score = 0

            return max(1, min(10, score))  # 限制在 1-10
        except Exception as e:
            print(f"[LLMJudge] {dimension} 评分失败: {e}")
            return 0

    def evaluate(
        self,
        content: str,
        topic: str = "",
        platform: str = "",
        trending_hint: str = "",
    ) -> dict:
        """
        多维度独立评估

        Returns:
            {
                "relevance": int,
                "readability": int,
                "originality": int,
                "practicality": int,
                "platform_fit": int,
                "trend_match": int,
                "overall": float,
            }
        """
        content = content[:2000]  # 限制长度，控制 token

        scores = {}

        # 基础维度（所有内容都评估）
        scores["relevance"] = self._evaluate_dimension(
            "relevance", content=content, topic=topic
        )
        scores["readability"] = self._evaluate_dimension(
            "readability", content=content
        )
        scores["originality"] = self._evaluate_dimension(
            "originality", content=content
        )
        scores["practicality"] = self._evaluate_dimension(
            "practicality", content=content
        )

        # 平台适配度（如果指定了平台）
        if platform:
            platform_desc = self.PLATFORM_DESCRIPTIONS.get(platform, "")
            scores["platform_fit"] = self._evaluate_dimension(
                "platform_fit", content=content, platform=platform, platform_desc=platform_desc
            )
        else:
            scores["platform_fit"] = 0

        # 热点匹配度（如果指定了热点）
        if trending_hint:
            scores["trend_match"] = self._evaluate_dimension(
                "trend_match", content=content, trend=trending_hint
            )
        else:
            scores["trend_match"] = 0

        # 计算综合分（有评分的维度取平均）
        valid_scores = [v for v in scores.values() if v > 0]
        scores["overall"] = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0.0

        return scores


def demo():
    """测试评分"""
    judge = LLMJudge()

    content = """
# 从脚本到 CLI 工具：AI Content Agent 改造实践

前几周我搭建了一个 Content Agent，能把技术笔记改写成多平台文案。
但有个问题：笔记是写死在代码里的。

于是我进行了工程化改造...
"""

    result = judge.evaluate(
        content=content,
        topic="AI Agent CLI 改造",
        platform="gongzhonghao",
        trending_hint="AI工具化",
    )

    print("评分结果:")
    print(f"  相关性: {result['relevance']}/10")
    print(f"  可读性: {result['readability']}/10")
    print(f"  原创性: {result['originality']}/10")
    print(f"  实用性: {result['practicality']}/10")
    print(f"  平台适配: {result['platform_fit']}/10")
    print(f"  热点匹配: {result['trend_match']}/10")
    print(f"  综合: {result['overall']}/10")


if __name__ == "__main__":
    demo()
