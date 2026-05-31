"""
偏好学习器 (Preference Learner)

从 eval_results 表分析用户生成内容的质量数据，
推断用户偏好并更新到 user_preferences 表。

使用方式:
    from automation.preference_learner import PreferenceLearner
    learner = PreferenceLearner()
    learner.learn(days=30)  # 分析最近 30 天的数据
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from agents import store


@dataclass
class PlatformStats:
    """单个平台的统计结果"""
    platform: str
    sample_count: int
    avg_overall: float
    avg_word_count: float
    avg_char_count: float
    avg_paragraph_count: float
    avg_emoji_count: float
    avg_tag_count: float
    avg_relevance: float
    avg_readability: float
    avg_originality: float
    avg_practicality: float
    avg_platform_fit: float
    avg_trend_match: float


class PreferenceLearner:
    """
    偏好学习器

    通过分析历史评估数据，推断用户的内容创作偏好。
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id

    def learn(self, days: int = 30, min_samples: int = 3) -> Dict[str, Any]:
        """
        从 eval_results 学习用户偏好并持久化。

        Args:
            days: 分析最近多少天的数据
            min_samples: 每个平台最少需要多少样本才做推断

        Returns:
            学习到的偏好字典
        """
        stats = store.get_eval_stats_by_platform(days=days)
        if not stats:
            print("[PreferenceLearner] 没有足够的历史评估数据")
            return {}

        platforms = [PlatformStats(**s) for s in stats]

        prefs = {}
        prefs.update(self._infer_platform_preference(platforms, min_samples))
        prefs.update(self._infer_length_preference(platforms))
        prefs.update(self._infer_style_preference(platforms, min_samples))
        prefs.update(self._infer_dimension_strength(platforms, min_samples))

        # 持久化到数据库
        for key, value in prefs.items():
            store.set_user_preference(
                user_id=self.user_id,
                pref_key=key,
                pref_value=value,
                source="inferred",
                confidence=self._calc_confidence(platforms, key, min_samples),
            )

        print(f"[PreferenceLearner] 已更新 {len(prefs)} 条偏好")
        return prefs

    def _infer_platform_preference(
        self, platforms: List[PlatformStats], min_samples: int
    ) -> Dict[str, Any]:
        """
        推断平台偏好。

        - strong_platforms: 得分持续高的平台
        - weak_platforms: 得分持续偏低的平台
        """
        strong = []
        weak = []

        for p in platforms:
            if p.sample_count < min_samples:
                continue
            if p.avg_overall >= 8.0:
                strong.append(p.platform)
            elif p.avg_overall <= 5.0:
                weak.append(p.platform)

        prefs = {}
        if strong:
            prefs["strong_platforms"] = strong
        if weak:
            prefs["weak_platforms"] = weak
        return prefs

    def _infer_length_preference(self, platforms: List[PlatformStats]) -> Dict[str, Any]:
        """
        推断文章长度偏好。

        按所有平台的平均字数综合判断。
        """
        if not platforms:
            return {}

        total_words = sum(p.avg_word_count * p.sample_count for p in platforms)
        total_samples = sum(p.sample_count for p in platforms)
        if total_samples == 0:
            return {}

        avg_words = total_words / total_samples

        if avg_words < 500:
            length = "short"
        elif avg_words <= 1500:
            length = "medium"
        else:
            length = "long"

        return {"preferred_length": length, "avg_word_count": int(avg_words)}

    def _infer_style_preference(
        self, platforms: List[PlatformStats], min_samples: int
    ) -> Dict[str, Any]:
        """
        推断风格偏好。

        - emoji_tendency: emoji 使用倾向 (low / medium / high)
        - paragraph_tendency: 段落数偏好 (short / medium / long)
        - tag_tendency: 标签使用倾向 (low / medium / high)
        """
        if not platforms:
            return {}

        total_samples = sum(p.sample_count for p in platforms)
        if total_samples == 0:
            return {}

        avg_emoji = sum(p.avg_emoji_count * p.sample_count for p in platforms) / total_samples
        avg_para = sum(p.avg_paragraph_count * p.sample_count for p in platforms) / total_samples
        avg_tag = sum(p.avg_tag_count * p.sample_count for p in platforms) / total_samples

        prefs = {}

        # emoji 倾向
        if avg_emoji < 2:
            prefs["emoji_tendency"] = "low"
        elif avg_emoji <= 8:
            prefs["emoji_tendency"] = "medium"
        else:
            prefs["emoji_tendency"] = "high"

        # 段落倾向
        if avg_para < 3:
            prefs["paragraph_tendency"] = "short"
        elif avg_para <= 7:
            prefs["paragraph_tendency"] = "medium"
        else:
            prefs["paragraph_tendency"] = "long"

        # 标签倾向
        if avg_tag < 2:
            prefs["tag_tendency"] = "low"
        elif avg_tag <= 5:
            prefs["tag_tendency"] = "medium"
        else:
            prefs["tag_tendency"] = "high"

        return prefs

    def _infer_dimension_strength(
        self, platforms: List[PlatformStats], min_samples: int
    ) -> Dict[str, Any]:
        """
        推断各评分维度的强弱项。

        找出用户内容持续得分高/低的维度。
        """
        if not platforms:
            return {}

        # 累加所有平台的各维度得分
        dims = {
            "relevance": [],
            "readability": [],
            "originality": [],
            "practicality": [],
            "platform_fit": [],
            "trend_match": [],
        }

        for p in platforms:
            if p.sample_count < min_samples:
                continue
            dims["relevance"].append(p.avg_relevance)
            dims["readability"].append(p.avg_readability)
            dims["originality"].append(p.avg_originality)
            dims["practicality"].append(p.avg_practicality)
            dims["platform_fit"].append(p.avg_platform_fit)
            dims["trend_match"].append(p.avg_trend_match)

        strong_dims = []
        weak_dims = []
        for dim_name, scores in dims.items():
            if not scores:
                continue
            avg = sum(scores) / len(scores)
            if avg >= 8.0:
                strong_dims.append(dim_name)
            elif avg <= 5.0:
                weak_dims.append(dim_name)

        prefs = {}
        if strong_dims:
            prefs["strong_dimensions"] = strong_dims
        if weak_dims:
            prefs["weak_dimensions"] = weak_dims
        return prefs

    def _calc_confidence(
        self, platforms: List[PlatformStats], key: str, min_samples: int
    ) -> float:
        """根据样本量计算可信度"""
        total_samples = sum(p.sample_count for p in platforms)
        if total_samples == 0:
            return 0.0

        # 样本越多可信度越高，但递减
        base_confidence = min(1.0, total_samples / (min_samples * 5))
        return round(base_confidence, 2)

    def report(self, days: int = 30) -> str:
        """
        生成偏好学习报告（Markdown 格式）。

        用于用户查看当前推断出的偏好。
        """
        stats = store.get_eval_stats_by_platform(days=days)
        if not stats:
            return "暂无足够的评估数据来生成偏好报告。"

        lines = ["## 评估数据统计", ""]
        lines.append("| 平台 | 样本数 | 平均得分 | 平均字数 | 平均 emoji | 平均标签 |")
        lines.append("|-------|--------|----------|----------|-------------|----------|")
        for s in stats:
            lines.append(
                f"| {s['platform']} | {s['sample_count']} | {s['avg_overall']:.1f} | "
                f"{int(s['avg_word_count'])} | {s['avg_emoji_count']:.1f} | {s['avg_tag_count']:.1f} |"
            )

        # 当前已学习的偏好
        prefs = store.get_user_preferences(self.user_id)
        if prefs:
            lines.extend(["", "## 已推断偏好", ""])
            for k, v in prefs.items():
                lines.append(f"- **{k}**: {v}")
        else:
            lines.extend(["", "暂无已推断偏好。运行 `learn()` 后重试。"])

        return "\n".join(lines)


def run_learning_task(days: int = 30, min_samples: int = 3):
    """
    后台任务入口：执行一次偏好学习。

    可以通过 APScheduler 定期调用：
        from automation.scheduler import TaskScheduler
        scheduler.add_job(run_learning_task, 'cron', hour=3)
    """
    print(f"[PreferenceLearner] 开始学习，分析最近 {days} 天数据...")
    learner = PreferenceLearner()
    prefs = learner.learn(days=days, min_samples=min_samples)
    if prefs:
        print(f"[PreferenceLearner] 学习完成，更新偏好:")
        for k, v in prefs.items():
            print(f"  - {k}: {v}")
    else:
        print("[PreferenceLearner] 没有推断出新偏好")
    return prefs


if __name__ == "__main__":
    # CLI 入口: python automation/preference_learner.py [--days 30] [--report]
    import argparse

    parser = argparse.ArgumentParser(description="偏好学习工具")
    parser.add_argument("--days", type=int, default=30, help="分析最近多少天的数据")
    parser.add_argument("--min-samples", type=int, default=3, help="每平台最少样本数")
    parser.add_argument("--report", action="store_true", help="只生成报告不学习")
    parser.add_argument("--user-id", type=str, default="default", help="用户 ID")
    args = parser.parse_args()

    learner = PreferenceLearner(user_id=args.user_id)
    if args.report:
        print(learner.report(days=args.days))
    else:
        prefs = learner.learn(days=args.days, min_samples=args.min_samples)
        if prefs:
            print("\n--- 报告 ---")
            print(learner.report(days=args.days))
