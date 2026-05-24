"""
热点调度器 (Trend Scheduler)

定时拉取热榜，匹配关键词，生成选题建议。

用法:
    from automation.trend_scheduler import TrendScheduler
    ts = TrendScheduler()
    ts.check_trends()  # 单次检查
    ts.start()         # 启动定时调度
"""

import os
from datetime import datetime
from typing import List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from automation.config import SchedulerConfig
from automation.topic_picker import TopicPicker
from content_agent.trend_watcher import WeiboHotSource, ZhihuHotSource, JuejinHotSource


class TrendScheduler:
    """热点调度器：定时检查热榜，匹配关键词，生成选题"""

    def __init__(self, config: Optional[SchedulerConfig] = None):
        self.config = config or SchedulerConfig.from_env()
        self.scheduler = BackgroundScheduler()
        self._sources = self._init_sources()
        self._picker = TopicPicker()

    def _init_sources(self) -> List:
        """根据配置初始化热榜源"""
        source_map = {
            "weibo": WeiboHotSource,
            "zhihu": ZhihuHotSource,
            "juejin": JuejinHotSource,
        }
        sources = []
        for name in getattr(self.config, "trend_sources", ["weibo"]):
            cls = source_map.get(name)
            if cls:
                sources.append(cls())
            else:
                print(f"[TrendScheduler] 未知热榜源: {name}，跳过")
        return sources

    # ------------------------------------------------------------------
    # 核心逻辑
    # ------------------------------------------------------------------
    def check_trends(self) -> dict:
        """
        单次检查热点。
        返回检查结果摘要。
        """
        keywords = self._get_keywords()
        if not keywords:
            print("[TrendScheduler] 未配置监控关键词，跳过")
            return {"checked": False, "reason": "no_keywords"}

        all_matched = []
        for source in self._sources:
            try:
                trends = source.fetch()
                if not trends:
                    continue
                matched = source.filter_by_keywords(trends, keywords)
                for item in matched:
                    item.source = source.name
                all_matched.extend(matched)
                print(f"[TrendScheduler] {source.name}: {len(trends)} 条热搜，匹配 {len(matched)} 条")
            except Exception as e:
                print(f"[TrendScheduler] {source.name} 抓取失败: {e}")

        if not all_matched:
            print("[TrendScheduler] 无匹配热点")
            return {"checked": True, "matched": 0, "trends": []}

        # 去重（同标题只保留排名最高的）
        seen = {}
        for item in all_matched:
            if item.title not in seen or item.rank < seen[item.title].rank:
                seen[item.title] = item
        unique_matched = sorted(seen.values(), key=lambda x: x.rank)

        print(f"[TrendScheduler] 共 {len(unique_matched)} 条独特匹配热点")
        for item in unique_matched[:10]:
            tag = f"[{item.tag}]" if item.tag else ""
            print(f"  • {item.title} {tag} (来源: {item.source})")

        # 生成选题建议
        if unique_matched:
            trending_hint = self._build_trending_hint(unique_matched)
            suggestions = self._generate_suggestions(trending_hint)
        else:
            suggestions = []

        return {
            "checked": True,
            "matched": len(unique_matched),
            "trends": [{"title": t.title, "source": t.source, "rank": t.rank} for t in unique_matched[:20]],
            "suggestions": len(suggestions),
        }

    def _get_keywords(self) -> List[str]:
        """获取监控关键词"""
        # 1. 环境变量
        env_kw = os.getenv("AGENT_TREND_KEYWORDS", "")
        if env_kw:
            return [k.strip() for k in env_kw.split(",") if k.strip()]

        # 2. 配置对象（后续扩展）
        if hasattr(self.config, "trend_keywords") and self.config.trend_keywords:
            return self.config.trend_keywords

        # 3. 默认关键词
        return ["AI", "人工智能", "大模型", "Agent", "ChatGPT", "LLM"]

    def _build_trending_hint(self, trends: List) -> str:
        """把热点列表拼接成文本，供 TopicPicker 使用"""
        lines = ["【当前热点】"]
        for item in trends[:10]:
            lines.append(f"- {item.title}")
        return "\n".join(lines)

    def _generate_suggestions(self, trending_hint: str) -> List:
        """调用 TopicPicker 生成选题建议"""
        vault_path = os.getenv("VAULT_PATH", os.path.expanduser("~/.content_agent/vault"))

        try:
            keywords = self._get_keywords()
            suggestions = self._picker.pick_topics(
                vault_path=vault_path,
                keywords=keywords[0] if keywords else None,
                trending_hint=trending_hint,
            )
            print(f"[TrendScheduler] 生成 {len(suggestions)} 条选题建议")
            return suggestions
        except Exception as e:
            print(f"[TrendScheduler] 生成选题失败: {e}")
            return []

    # ------------------------------------------------------------------
    # 调度生命周期
    # ------------------------------------------------------------------
    def register_job(self):
        """注册定时任务到 APScheduler"""
        cron = getattr(self.config, "trend_check_cron", "*/30 * * * *")
        self.scheduler.add_job(
            self.check_trends,
            trigger=CronTrigger.from_crontab(cron),
            id="trend_check",
            replace_existing=True,
        )
        print(f"[TrendScheduler] 已注册热点检查任务: {cron}")

    def start(self):
        """启动后台调度"""
        self.register_job()
        self.scheduler.start()
        print("[TrendScheduler] 热点调度器已启动")

    def shutdown(self):
        """停止调度"""
        self.scheduler.shutdown()
        print("[TrendScheduler] 热点调度器已停止")


def demo():
    """运行单次热点检查 demo"""
    print("=" * 60)
    print("热点调度器 Demo")
    print("=" * 60)

    ts = TrendScheduler()
    result = ts.check_trends()

    print("\n结果摘要:")
    for k, v in result.items():
        if k == "trends":
            print(f"  {k}: {len(v)} 条")
        else:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    demo()
