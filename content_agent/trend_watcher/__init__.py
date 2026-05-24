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

__all__ = ["TrendItem", "TrendSource", "WeiboHotSource"]
