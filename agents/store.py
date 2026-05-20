"""
SQLite 持久化层

存储 TaskState、审稿历史、发布记录。
content_agent/calendar.py 和 scheduler.py 保留自己的 JSON 文件，不纳入此库。
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from agents.schemas import TaskState, WriterOutput, EditVerdict, ResearchResult


DB_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DB_DIR / "content_agent.db"


def _ensure_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_db()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化表结构（幂等）"""
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            note_source TEXT,
            research_data TEXT,
            final_output TEXT,
            metadata TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            draft_index INTEGER NOT NULL,
            xiaohongshu TEXT,
            gongzhonghao TEXT,
            douyin TEXT,
            recommended_tags TEXT,
            revision_notes TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(task_id)
        );

        CREATE TABLE IF NOT EXISTS edit_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            scores TEXT,
            overall INTEGER,
            passed INTEGER,
            verdict TEXT,
            weakest TEXT,
            suggestions TEXT,
            priority TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(task_id)
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
        """
    )
    conn.commit()
    conn.close()


def _research_to_dict(r: Optional[ResearchResult]) -> Optional[dict]:
    if r is None:
        return None
    return {
        "keywords": r.keywords,
        "sources": r.sources,
        "key_insights": r.key_insights,
        "confidence": r.confidence,
    }


def _dict_to_research(d: Optional[dict]) -> Optional[ResearchResult]:
    if d is None:
        return None
    return ResearchResult(**d)


def _writer_output_to_dict(w: Optional[WriterOutput]) -> Optional[dict]:
    if w is None:
        return None
    return {
        "xiaohongshu": w.xiaohongshu,
        "gongzhonghao": w.gongzhonghao,
        "douyin": w.douyin,
        "recommended_tags": w.recommended_tags,
        "revision_notes": w.revision_notes,
    }


def _dict_to_writer_output(d: Optional[dict]) -> Optional[WriterOutput]:
    if d is None:
        return None
    return WriterOutput(**d)


def save_task(state: TaskState):
    """保存或更新一个 TaskState"""
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO tasks (task_id, status, note_source, research_data, final_output, metadata, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_id) DO UPDATE SET
            status=excluded.status,
            research_data=excluded.research_data,
            final_output=excluded.final_output,
            metadata=excluded.metadata,
            updated_at=excluded.updated_at
        """,
        (
            state.task_id,
            state.status,
            state.note_source,
            json.dumps(_research_to_dict(state.research_data), ensure_ascii=False),
            json.dumps(_writer_output_to_dict(state.final_output), ensure_ascii=False),
            json.dumps(state.metadata, ensure_ascii=False),
            state.created_at,
            state.updated_at,
        ),
    )

    # 保存 drafts
    conn.execute("DELETE FROM drafts WHERE task_id = ?", (state.task_id,))
    for idx, d in enumerate(state.drafts):
        conn.execute(
            "INSERT INTO drafts (task_id, draft_index, xiaohongshu, gongzhonghao, douyin, recommended_tags, revision_notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (state.task_id, idx, d.xiaohongshu, d.gongzhonghao, d.douyin, d.recommended_tags, d.revision_notes),
        )

    # 保存 edit_history
    conn.execute("DELETE FROM edit_history WHERE task_id = ?", (state.task_id,))
    for idx, e in enumerate(state.edit_history):
        conn.execute(
            "INSERT INTO edit_history (task_id, attempt, scores, overall, passed, verdict, weakest, suggestions, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                state.task_id,
                idx + 1,
                json.dumps(e.scores, ensure_ascii=False),
                e.overall,
                int(e.passed),
                e.verdict,
                e.weakest,
                json.dumps(e.suggestions, ensure_ascii=False),
                e.priority,
            ),
        )

    conn.commit()
    conn.close()


def load_task(task_id: str) -> Optional[TaskState]:
    """读取单个 TaskState（含 drafts 和 edit_history）"""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        conn.close()
        return None

    task = TaskState(
        task_id=row["task_id"],
        status=row["status"],
        note_source=row["note_source"],
        research_data=_dict_to_research(json.loads(row["research_data"]) if row["research_data"] else None),
        final_output=_dict_to_writer_output(json.loads(row["final_output"]) if row["final_output"] else None),
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

    drafts_rows = conn.execute(
        "SELECT * FROM drafts WHERE task_id = ? ORDER BY draft_index", (task_id,)
    ).fetchall()
    task.drafts = [
        WriterOutput(
            xiaohongshu=r["xiaohongshu"],
            gongzhonghao=r["gongzhonghao"],
            douyin=r["douyin"],
            recommended_tags=r["recommended_tags"],
            revision_notes=r["revision_notes"],
        )
        for r in drafts_rows
    ]

    edit_rows = conn.execute(
        "SELECT * FROM edit_history WHERE task_id = ? ORDER BY attempt", (task_id,)
    ).fetchall()
    task.edit_history = [
        EditVerdict(
            scores=json.loads(r["scores"]) if r["scores"] else {},
            overall=r["overall"],
            passed=bool(r["passed"]),
            verdict=r["verdict"],
            weakest=r["weakest"],
            suggestions=json.loads(r["suggestions"]) if r["suggestions"] else [],
            priority=r["priority"],
        )
        for r in edit_rows
    ]

    conn.close()
    return task


def list_tasks(limit: int = 50, offset: int = 0) -> List[TaskState]:
    """列出最近的任务（不含 drafts 和 edit_history，轻量）"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()

    tasks = []
    for row in rows:
        tasks.append(
            TaskState(
                task_id=row["task_id"],
                status=row["status"],
                note_source=row["note_source"],
                research_data=None,
                final_output=_dict_to_writer_output(json.loads(row["final_output"]) if row["final_output"] else None),
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )
    conn.close()
    return tasks


def delete_task(task_id: str) -> bool:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0
