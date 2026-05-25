"""
智能排期 - 根据平台特性和历史数据推荐最佳发布时间
"""

import random
from datetime import datetime, timedelta
from typing import Optional

from agents.store import _get_conn


class SmartScheduler:
    """智能排期器"""

    # 各平台最佳时段（基于行业经验）
    PLATFORM_SLOTS = {
        "gongzhonghao": [
            (8, 9),    # 早高峰
            (12, 13),  # 午休
            (21, 22),  # 睡前
        ],
        "xiaohongshu": [
            (11, 13),  # 午休
            (19, 22),  # 晚上
        ],
        "douyin": [
            (7, 9),    # 早高峰
            (12, 13),  # 午休
            (18, 22),  # 晚上
        ],
    }

    def __init__(self):
        self.conn = _get_conn()

    def recommend_time(
        self,
        platform: str,
        content_type: str = "",
        days_ahead: int = 1,
    ) -> datetime:
        """
        推荐最佳发布时间

        Args:
            platform: 平台名称
            content_type: 内容类型（可选）
            days_ahead: 提前几天（默认明天）

        Returns:
            推荐的发布时间
        """
        # 1. 获取基础时段
        slots = self.PLATFORM_SLOTS.get(platform, [(9, 21)])

        # 2. 计算各时段评分
        best_slot = None
        best_score = -1

        for start_hour, end_hour in slots:
            score = self._score_slot(platform, start_hour, end_hour, days_ahead)
            if score > best_score:
                best_score = score
                best_slot = (start_hour, end_hour)

        # 3. 在最佳时段内随机选具体时间点
        if best_slot:
            start_hour, end_hour = best_slot
            hour = random.randint(start_hour, end_hour - 1)
            minute = random.choice([0, 15, 30, 45])
        else:
            hour = 9
            minute = 0

        # 4. 构建日期时间
        now = datetime.now()
        target_date = now + timedelta(days=days_ahead)

        # 如果推荐时间已过，顺延到下一个时段
        recommended = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if recommended < now:
            recommended += timedelta(days=1)

        return recommended

    def _score_slot(self, platform: str, start_hour: int, end_hour: int, days_ahead: int) -> float:
        """评分时段"""
        score = 100.0

        # 1. 检查该时段是否已有排期（竞争减分）
        conflict_count = self._count_conflicts(platform, start_hour, end_hour, days_ahead)
        score -= conflict_count * 20  # 每个冲突减 20 分

        # 2. 周末加成（周末早上效果更好）
        target_date = datetime.now() + timedelta(days=days_ahead)
        if target_date.weekday() >= 5:  # 周末
            if start_hour >= 9:
                score += 10

        # 3. 时段偏好（中午和晚上加分）
        if 11 <= start_hour <= 13 or 19 <= start_hour <= 21:
            score += 15

        return max(score, 0)

    def _count_conflicts(self, platform: str, start_hour: int, end_hour: int, days_ahead: int) -> int:
        """统计该时段已有排期数量"""
        target_date = datetime.now() + timedelta(days=days_ahead)
        date_str = target_date.strftime("%Y-%m-%d")

        rows = self.conn.execute(
            """
            SELECT COUNT(*) as count FROM publish_queue
            WHERE platform = ? AND scheduled_at LIKE ?
            AND CAST(substr(scheduled_at, 12, 2) AS INTEGER) BETWEEN ? AND ?
            """,
            (platform, f"{date_str}%", start_hour, end_hour),
        ).fetchall()

        return rows[0]["count"] if rows else 0

    def auto_schedule(self, queue_id: str, platform: str, days_ahead: int = 1) -> Optional[str]:
        """
        自动为队列项设置排期

        Returns:
            排期时间字符串，或 None（失败）
        """
        recommended = self.recommend_time(platform, days_ahead=days_ahead)
        time_str = recommended.strftime("%Y-%m-%d %H:%M")

        try:
            from automation.publish_queue import PublishQueue
            ok = PublishQueue.update_schedule(queue_id, time_str)
            if ok:
                print(f"[SmartScheduler] 已排期: {queue_id} -> {time_str}")
                return time_str
            else:
                print(f"[SmartScheduler] 排期失败: {queue_id}")
                return None
        except Exception as e:
            print(f"[SmartScheduler] 排期异常: {e}")
            return None

    def close(self):
        self.conn.close()


def demo():
    """测试智能排期"""
    scheduler = SmartScheduler()

    for platform in ["gongzhonghao", "xiaohongshu", "douyin"]:
        time = scheduler.recommend_time(platform, days_ahead=1)
        print(f"{platform}: {time.strftime('%Y-%m-%d %H:%M')}")

    scheduler.close()


if __name__ == "__main__":
    demo()
