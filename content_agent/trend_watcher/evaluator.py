"""
热点评估器 — 用 LLM 判断热点是否值得跟进

用法:
    from content_agent.trend_watcher.evaluator import TrendEvaluator
    evaluator = TrendEvaluator()
    result = evaluator.evaluate(trend_item, user_profile)
    if result.should_follow:
        print(f"跟进: {result.angle}")
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

from pydantic import BaseModel
from pydantic_ai import Agent

from content_agent.trend_watcher.base import TrendItem
from content_agent.agent_core import ModelConfig


class EvaluationResult(BaseModel):
    """热点评估结果"""
    should_follow: bool = False
    reason: str = ""           # 一句话说明判断理由
    angle: str = ""            # 建议切入角度
    confidence: int = 0        # 0-100
    content_type: str = ""     # 建议内容形式：技术解读 / 教程 / 观点 / 资讯
    platforms: List[str] = []  # 建议发布平台


@dataclass
class UserProfile:
    """用户账号画像"""
    domain: str = ""           # 领域，如 "AI/大模型"
    tone: str = ""             # 调性，如 "技术干货"
    target_audience: str = ""  # 目标受众
    avoid_topics: List[str] = field(default_factory=list)  # 回避话题


class TrendEvaluator:
    """热点评估器"""

    SYSTEM_PROMPT = """你是一位资深内容策略顾问，帮助技术博主判断热点是否值得跟进。

判断标准：
1. 领域匹配度：热点是否和博主领域相关？能否从技术角度切入？
2. 时效性价值：这个热点是昙花一现还是有持续讨论价值？
3. 独特视角：博主能否提供不同于大众媒体的独特观点？
4. 受众兴趣：目标读者会关心这个话题吗？
5. 内容深度：能否写出有技术深度的内容，而非简单复述新闻？

输出要求：
- should_follow: true 只有当热点确实值得跟进时
- angle: 具体的技术切入角度，避免泛泛而谈
- content_type: 从 [技术解读, 实战教程, 观点评论, 行业资讯] 中选择
- confidence: 你的确定程度（0-100）
- platforms: 建议发布到哪些平台 [xiaohongshu, gongzhonghao, douyin]

重要：不要为了追热点而追热点。质量差的跟进会损害账号调性。"""

    def __init__(self, model=None):
        if model is None:
            model, _ = ModelConfig.from_env()
        self.model = model
        self._agent = Agent(
            self.model,
            system_prompt=self.SYSTEM_PROMPT,
            output_type=EvaluationResult,
        )

    def evaluate(self, trend: TrendItem, profile: Optional[UserProfile] = None) -> EvaluationResult:
        """
        评估单个热点是否值得跟进
        """
        if profile is None:
            profile = self._default_profile()

        prompt = self._build_prompt(trend, profile)

        try:
            result = self._agent.run_sync(prompt)
            return result.output
        except Exception as e:
            print(f"[TrendEvaluator] 评估失败: {e}")
            return EvaluationResult(
                should_follow=False,
                reason=f"评估出错: {e}",
            )

    def evaluate_batch(
        self,
        trends: List[TrendItem],
        profile: Optional[UserProfile] = None,
        min_confidence: int = 60,
    ) -> List[tuple[TrendItem, EvaluationResult]]:
        """
        批量评估热点，返回值得跟进的列表
        """
        if profile is None:
            profile = self._default_profile()

        results = []
        for trend in trends:
            eval_result = self.evaluate(trend, profile)
            if eval_result.should_follow and eval_result.confidence >= min_confidence:
                results.append((trend, eval_result))
                print(f"[TrendEvaluator] ✓ {trend.title} (置信度: {eval_result.confidence})")
            else:
                print(f"[TrendEvaluator] ✗ {trend.title} ({eval_result.reason})")
        return results

    @staticmethod
    def _default_profile() -> UserProfile:
        """从环境变量构建默认用户画像"""
        return UserProfile(
            domain=os.getenv("AGENT_DOMAIN", "AI/大模型/Agent开发"),
            tone=os.getenv("AGENT_TONE", "技术干货+实战经验"),
            target_audience=os.getenv("AGENT_AUDIENCE", "程序员、AI从业者、技术爱好者"),
            avoid_topics=[t.strip() for t in os.getenv("AGENT_AVOID_TOPICS", "").split(",") if t.strip()],
        )

    @staticmethod
    def _build_prompt(trend: TrendItem, profile: UserProfile) -> str:
        avoid_str = "、".join(profile.avoid_topics) if profile.avoid_topics else "无"
        return f"""请评估以下热点是否值得跟进：

【热点信息】
标题: {trend.title}
来源: {trend.source}
排名: {trend.rank}
热度: {trend.heat}
标签: {trend.tag}

【博主画像】
领域: {profile.domain}
调性: {profile.tone}
目标受众: {profile.target_audience}
回避话题: {avoid_str}

请给出评估结果。"""


def demo():
    """运行评估 demo"""
    print("=" * 60)
    print("热点评估器 Demo")
    print("=" * 60)

    from content_agent.trend_watcher import JuejinHotSource

    source = JuejinHotSource()
    trends = source.fetch()

    keywords = ["AI", "人工智能", "大模型", "Agent", "ChatGPT", "LLM"]
    matched = source.filter_by_keywords(trends, keywords)

    print(f"\n匹配到 {len(matched)} 条热点，开始评估...\n")

    evaluator = TrendEvaluator()
    results = evaluator.evaluate_batch(matched[:5], min_confidence=50)

    print(f"\n最终推荐跟进: {len(results)} 条")
    for trend, eval_result in results:
        print(f"\n  • {trend.title}")
        print(f"    切入角度: {eval_result.angle}")
        print(f"    内容形式: {eval_result.content_type}")
        print(f"    推荐平台: {', '.join(eval_result.platforms)}")
        print(f"    置信度: {eval_result.confidence}")


if __name__ == "__main__":
    demo()
