"""
策略定义

定义内容类型和对应策略
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class ContentType(Enum):
    """内容类型"""
    DEEP_DIVE = "深度长文"      # 技术教程、源码分析
    HOT_NEWS = "热点快讯"       # 行业动态、产品发布
    TUTORIAL = "实战教程"       # 手把手教学
    REVIEW = "评测对比"         # 产品评测、方案对比
    OPINION = "观点评论"        # 个人见解、趋势判断
    UNKNOWN = "未知类型"        # 无法识别


@dataclass
class Strategy:
    """执行策略"""
    name: str
    description: str
    content_type: ContentType
    steps: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    max_attempts: int = 3
    threshold: int = 80


# 预设策略
STRATEGIES = {
    ContentType.DEEP_DIVE: Strategy(
        name="深度研究",
        description="适合技术教程、源码分析等深度内容",
        content_type=ContentType.DEEP_DIVE,
        steps=["search", "browse", "analyze", "generate", "evaluate", "modify"],
        tools=["search", "browse", "analyze", "generate", "evaluate"],
        max_attempts=3,
        threshold=80,
    ),
    ContentType.HOT_NEWS: Strategy(
        name="热点快讯",
        description="适合行业动态、产品发布等时效性内容",
        content_type=ContentType.HOT_NEWS,
        steps=["search", "generate", "evaluate"],
        tools=["search", "generate", "evaluate"],
        max_attempts=2,
        threshold=75,
    ),
    ContentType.TUTORIAL: Strategy(
        name="实战教程",
        description="适合手把手教学、代码示例等内容",
        content_type=ContentType.TUTORIAL,
        steps=["read", "execute", "generate", "evaluate"],
        tools=["read", "execute", "generate", "evaluate"],
        max_attempts=3,
        threshold=80,
    ),
    ContentType.REVIEW: Strategy(
        name="评测对比",
        description="适合产品评测、方案对比等内容",
        content_type=ContentType.REVIEW,
        steps=["search", "browse", "analyze", "generate", "evaluate"],
        tools=["search", "browse", "analyze", "generate", "evaluate"],
        max_attempts=3,
        threshold=80,
    ),
    ContentType.OPINION: Strategy(
        name="观点评论",
        description="适合个人见解、趋势判断等内容",
        content_type=ContentType.OPINION,
        steps=["search", "generate", "evaluate"],
        tools=["search", "generate", "evaluate"],
        max_attempts=2,
        threshold=75,
    ),
    ContentType.UNKNOWN: Strategy(
        name="通用策略",
        description="默认策略",
        content_type=ContentType.UNKNOWN,
        steps=["search", "generate", "evaluate"],
        tools=["search", "generate", "evaluate"],
        max_attempts=2,
        threshold=75,
    ),
}
