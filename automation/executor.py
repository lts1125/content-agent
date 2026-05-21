"""
发布执行器 (Publish Executor)

获取 approved 队列项 → 通过审核门 → 按平台分发 → 记录结果。
"""

import time
from datetime import datetime
from typing import List, Optional

from automation.gate import PublishGate, GateDecision
from automation.publish_queue import PublishQueue, QueueItem
from automation.retry import RetryPolicy


class PublishExecutor:
    def __init__(self, gate: Optional[PublishGate] = None, max_retries: int = 3):
        self.gate = gate or PublishGate()
        self.max_retries = max_retries
        self.retry_policy = RetryPolicy(max_retries=max_retries)

    def execute_one(self, item_id: str, skip_gate: bool = False) -> dict:
        item = PublishQueue.get(item_id)
        if item is None:
            return {"success": False, "error": "队列项不存在", "retryable": False}

        if not skip_gate:
            decision = self.gate.review(item)
            if decision.decision == "reject":
                PublishQueue.reject(item_id)
                return {"success": False, "error": f"审核拒绝: {decision.reason}", "retryable": False}
            if decision.decision == "skip":
                return {"success": False, "error": "用户跳过", "retryable": False}

        result = self._dispatch(item)

        if result.get("success"):
            PublishQueue.mark_published(item_id, result=str(result.get("details", "")))
        else:
            self._record_failure(item_id, result.get("error", ""), result.get("retryable", False))

        return result

    def execute_scheduled(self) -> List[dict]:
        items = self._get_due_items()
        results = []
        for item in items:
            results.append(self.execute_one(item.id))
        return results

    def _dispatch(self, item: QueueItem) -> dict:
        if item.platform == "gongzhonghao":
            return self._publish_wechat(item)
        if item.platform == "xiaohongshu":
            return self._publish_xiaohongshu(item)
        if item.platform == "douyin":
            return {"success": False, "error": "抖音自动发布暂未实现", "retryable": False}
        return {"success": False, "error": f"未知平台: {item.platform}", "retryable": False}

    @staticmethod
    def _publish_wechat(item: QueueItem) -> dict:
        from content_agent.publisher import publish_wechat_draft, save_content_as_markdown
        try:
            md_path = save_content_as_markdown(item.title, item.content)
            result = publish_wechat_draft(
                markdown_path=md_path,
                title=item.title,
                cover_path="",
                author="",
                digest="",
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e), "retryable": True}

    @staticmethod
    def _publish_xiaohongshu(item: QueueItem) -> dict:
        from automation.xiaohongshu_publisher import XiaohongshuPublisher
        publisher = XiaohongshuPublisher()
        return publisher.publish(
            title=item.title,
            content=item.content,
            tags=item.tags,
        )

    def _record_failure(self, item_id: str, error: str, retryable: bool):
        from agents.store import _get_conn
        conn = _get_conn()
        conn.execute(
            """
            UPDATE publish_queue
            SET status = ?, error_log = ?, retry_count = retry_count + 1
            WHERE id = ?
            """,
            ("failed", error, item_id),
        )
        conn.commit()
        conn.close()

        if not retryable:
            return

        item = PublishQueue.get(item_id)
        if item is None:
            return

        attempt = item.retry_count - 1
        if not self.retry_policy.should_retry(error, attempt):
            return

        delay = self.retry_policy.get_delay(attempt)
        print(f"   ⏳ 将在 {delay:.1f} 秒后重试...")
        time.sleep(delay)

        # 重试时直接 dispatch，不走 gate
        result = self._dispatch(item)
        if result.get("success"):
            PublishQueue.mark_published(item_id, result=str(result.get("details", "")))
        else:
            self._record_failure(item_id, result.get("error", ""), result.get("retryable", False))

    @staticmethod
    def _get_due_items() -> List[QueueItem]:
        from agents.store import _get_conn
        now = datetime.now().isoformat()
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT * FROM publish_queue
            WHERE status = 'approved'
              AND (scheduled_at IS NULL OR scheduled_at <= ?)
            ORDER BY created_at ASC
            """,
            (now,),
        ).fetchall()
        conn.close()
        from automation.publish_queue import _row_to_item
        return [_row_to_item(r) for r in rows]
