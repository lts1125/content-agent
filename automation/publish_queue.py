"""
待发队列 (Publish Queue)

生成结果按平台拆分后进入队列，等待人工审核或自动发布。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, List, Optional

from agents.store import _get_conn


@dataclass
class QueueItem:
    id: str
    task_id: str
    platform: str
    title: str
    content: str
    tags: str
    status: Literal["pending", "approved", "published", "rejected"]
    note_source: str
    created_at: str
    reviewed_at: Optional[str]
    published_at: Optional[str]
    publish_result: Optional[str]


class PublishQueue:
    @staticmethod
    def add(
        task_id: str,
        platform: str,
        title: str,
        content: str,
        tags: str,
        note_source: str,
    ) -> str:
        """插入队列，返回 item_id"""
        item_id = f"queue_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now().isoformat()
        conn = _get_conn()
        conn.execute(
            """
            INSERT INTO publish_queue
            (id, task_id, platform, title, content, tags, status, note_source, created_at, reviewed_at, published_at, publish_result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (item_id, task_id, platform, title, content, tags, "pending", note_source, created_at, None, None, None),
        )
        conn.commit()
        conn.close()
        return item_id

    @staticmethod
    def list(status: Optional[str] = None, limit: int = 50) -> List[QueueItem]:
        conn = _get_conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM publish_queue WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM publish_queue ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        return [_row_to_item(r) for r in rows]

    @staticmethod
    def get(item_id: str) -> Optional[QueueItem]:
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM publish_queue WHERE id = ?", (item_id,)
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return _row_to_item(row)

    @staticmethod
    def approve(item_id: str) -> bool:
        reviewed_at = datetime.now().isoformat()
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE publish_queue SET status = ?, reviewed_at = ? WHERE id = ?",
            ("approved", reviewed_at, item_id),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    @staticmethod
    def reject(item_id: str) -> bool:
        reviewed_at = datetime.now().isoformat()
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE publish_queue SET status = ?, reviewed_at = ? WHERE id = ?",
            ("rejected", reviewed_at, item_id),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    @staticmethod
    def mark_published(item_id: str, result: str = "") -> bool:
        published_at = datetime.now().isoformat()
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE publish_queue SET status = ?, published_at = ?, publish_result = ? WHERE id = ?",
            ("published", published_at, result, item_id),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    @staticmethod
    def delete(item_id: str) -> bool:
        conn = _get_conn()
        cur = conn.execute("DELETE FROM publish_queue WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    @staticmethod
    def get_oldest_approved() -> Optional[QueueItem]:
        """取最早创建的 approved 项（created_at ASC）"""
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM publish_queue WHERE status = ? ORDER BY created_at ASC LIMIT 1",
            ("approved",),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return _row_to_item(row)


def _row_to_item(row) -> QueueItem:
    return QueueItem(
        id=row["id"],
        task_id=row["task_id"],
        platform=row["platform"],
        title=row["title"] or "",
        content=row["content"] or "",
        tags=row["tags"] or "",
        status=row["status"],
        note_source=row["note_source"] or "",
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
        published_at=row["published_at"],
        publish_result=row["publish_result"],
    )


def extract_title(content: str) -> str:
    """从内容第一行提取标题"""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped.lstrip("#").strip()[:100]
    return ""
