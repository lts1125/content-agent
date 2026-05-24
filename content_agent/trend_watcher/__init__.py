"""
热点监控模块 — 自动追踪外部热榜，匹配用户领域关键词

用法:
    from content_agent.trend_watcher import WeiboHotSource
    source = WeiboHotSource()
    trends = source.fetch()
    matched = source.filter_by_keywords(trends, ["AI", "Agent", "大模型"])
"""

from content_agent.trend_watcher.base import TrendItem, TrendSource
from content_agent.trend_watcher.weibo_hot import WeiboHotSource
from content_agent.trend_watcher.zhihu_hot import ZhihuHotSource
from content_agent.trend_watcher.juejin_hot import JuejinHotSource
from content_agent.trend_watcher.evaluator import TrendEvaluator, EvaluationResult, UserProfile

__all__ = [
    "TrendItem", "TrendSource",
    "WeiboHotSource", "ZhihuHotSource", "JuejinHotSource",
    "TrendEvaluator", "EvaluationResult", "UserProfile",
]
