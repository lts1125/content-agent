"""
TrendSource 抽象基类 — 定义热榜源的标准接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class TrendItem:
    """单条热点条目"""
    rank: int                # 排名
    title: str               # 标题
    url: str = ""            # 链接
    heat: str = ""           # 热度值（如 "123万"）
    tag: str = ""            # 标签（如 "爆", "热", "新"）
    source: str = ""         # 来源标识


class TrendSource(ABC):
    """热榜源抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """源名称，如 weibo, zhihu"""
        pass

    @abstractmethod
    def fetch(self) -> List[TrendItem]:
        """拉取当前热榜，返回 TrendItem 列表"""
        pass

    def filter_by_keywords(self, trends: List[TrendItem], keywords: List[str]) -> List[TrendItem]:
        """按关键词过滤热榜（大小写不敏感）"""
        if not keywords:
            return trends
        keywords_lower = [k.lower() for k in keywords]
        matched = []
        for item in trends:
            title_lower = item.title.lower()
            for kw in keywords_lower:
                if kw in title_lower:
                    matched.append(item)
                    break
        return matched
