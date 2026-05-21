"""
风格画像 (Style Profile)

P0 仅做样本收集，P1 再引入 LLM 分析。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List

from agents.store import _get_conn


@dataclass
class StyleSample:
    id: str
    task_id: str
    note_source: str
    note_preview: str
    platform: str
    content_preview: str
    content_length: int
    created_at: str


class StyleProfile:
    @staticmethod
    def record_sample(
        task_id: str,
        note_source: str,
        note_text: str,
        platform: str,
        content: str,
    ) -> str:
        """记录风格样本，返回 sample_id"""
        sample_id = f"style_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now().isoformat()
        note_preview = note_text[:500]
        content_preview = content[:500]
        content_length = len(content)

        conn = _get_conn()
        conn.execute(
            """
            INSERT INTO style_samples
            (id, task_id, note_source, note_preview, platform, content_preview, content_length, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sample_id, task_id, note_source, note_preview, platform, content_preview, content_length, created_at),
        )
        conn.commit()
        conn.close()
        return sample_id

    @staticmethod
    def list_samples(limit: int = 100) -> List[StyleSample]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM style_samples ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [
            StyleSample(
                id=r["id"],
                task_id=r["task_id"],
                note_source=r["note_source"] or "",
                note_preview=r["note_preview"] or "",
                platform=r["platform"],
                content_preview=r["content_preview"] or "",
                content_length=r["content_length"] or 0,
                created_at=r["created_at"],
            )
            for r in rows
        ]

    @staticmethod
    def get_profile_hint(platform: str) -> str:
        """P0 占位，P1 实现 LLM 风格分析"""
        return ""
