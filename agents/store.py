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
_SCHEMA_VERSION = 5


def _ensure_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_db()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _get_schema_version() -> int:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
        return row["version"] if row else 1
    except sqlite3.OperationalError:
        return 1
    finally:
        conn.close()


def _column_exists(table: str, column: str) -> bool:
    conn = _get_conn()
    try:
        conn.execute(f"SELECT {column} FROM {table} LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def migrate_publish_queue_v2():
    """publish_queue 增加排期和重试字段"""
    conn = _get_conn()
    text_columns = ["scheduled_at", "error_log", "gate_decision", "gate_reason"]
    for col in text_columns:
        if not _column_exists("publish_queue", col):
            conn.execute(f"ALTER TABLE publish_queue ADD COLUMN {col} TEXT")
    if not _column_exists("publish_queue", "retry_count"):
        conn.execute("ALTER TABLE publish_queue ADD COLUMN retry_count INTEGER DEFAULT 0")
    conn.commit()
    conn.close()


def init_publish_queue_migration():
    migrate_publish_queue_v2()
    conn = _get_conn()
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_queue_scheduled ON publish_queue(scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_queue_status_retry ON publish_queue(status, retry_count);
        """
    )
    conn.commit()
    conn.close()


def _set_schema_version(version: int):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO schema_version (version) VALUES (?) ON CONFLICT(version) DO UPDATE SET version=excluded.version",
        (version,),
    )
    # 清理多行残留：只保留当前版本
    conn.execute("DELETE FROM schema_version WHERE version != ?", (version,))
    conn.commit()
    conn.close()


def init_publish_queue_table():
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS publish_queue (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            title TEXT,
            content TEXT,
            tags TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            note_source TEXT,
            created_at TEXT,
            reviewed_at TEXT,
            published_at TEXT,
            publish_result TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_queue_status ON publish_queue(status);
        CREATE INDEX IF NOT EXISTS idx_queue_created ON publish_queue(created_at);
        """
    )
    conn.commit()
    conn.close()


def init_style_samples_table():
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS style_samples (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            note_source TEXT,
            note_preview TEXT,
            platform TEXT NOT NULL,
            content_preview TEXT,
            content_length INTEGER,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_samples_task ON style_samples(task_id);
        """
    )
    conn.commit()
    conn.close()


def init_content_metrics_table():
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS content_metrics (
            id TEXT PRIMARY KEY,
            queue_item_id TEXT,
            platform TEXT NOT NULL,
            reads INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            collects INTEGER DEFAULT 0,
            import_date TEXT,
            publish_date TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_queue ON content_metrics(queue_item_id);
        CREATE INDEX IF NOT EXISTS idx_metrics_platform ON content_metrics(platform);
        """
    )
    conn.commit()
    conn.close()


def init_style_profiles_table():
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS style_profiles (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            preferred_tone TEXT,
            high_performing_patterns TEXT,
            avg_score INTEGER,
            sample_count INTEGER,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_style_platform ON style_profiles(platform);
        """
    )
    conn.commit()
    conn.close()


def init_topic_suggestions_table():
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS topic_suggestions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            note_file TEXT,
            trending_topic TEXT,
            platforms TEXT,
            reason TEXT,
            priority INTEGER DEFAULT 3,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            generated_task_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_topics_status ON topic_suggestions(status);
        """
    )
    conn.commit()
    conn.close()


def init_ab_test_variants_table():
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ab_test_variants (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            variant_type TEXT NOT NULL,
            variant_content TEXT,
            status TEXT DEFAULT 'pending',
            metrics_id TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ab_task ON ab_test_variants(task_id);
        """
    )
    conn.commit()
    conn.close()


def init_eval_results_table():
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS eval_results (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            platform TEXT,
            content_hash TEXT,
            relevance_score INTEGER,
            readability_score INTEGER,
            originality_score INTEGER,
            practicality_score INTEGER,
            platform_fit_score INTEGER,
            trend_match_score INTEGER,
            overall_score REAL,
            word_count INTEGER,
            char_count INTEGER,
            paragraph_count INTEGER,
            emoji_count INTEGER,
            tag_count INTEGER,
            has_sensitive_words BOOLEAN,
            has_link BOOLEAN,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            latency_ms INTEGER,
            eval_latency_ms INTEGER,
            model TEXT,
            eval_model TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_eval_task ON eval_results(task_id);
        CREATE INDEX IF NOT EXISTS idx_eval_platform ON eval_results(platform);
        CREATE INDEX IF NOT EXISTS idx_eval_created ON eval_results(created_at);
        """
    )
    conn.commit()
    conn.close()


def init_conversation_turns_table():
    """记忆系统: 会话历史表"""
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT    NOT NULL,
            role        TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            platforms   TEXT,
            files       TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            task_id     TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation_turns(session_id);
        CREATE INDEX IF NOT EXISTS idx_conv_created ON conversation_turns(created_at);
        """
    )
    conn.commit()
    conn.close()


def init_user_preferences_table():
    """记忆系统: 用户偏好表"""
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          TEXT    NOT NULL DEFAULT 'default',
            pref_key         TEXT    NOT NULL,
            pref_value       TEXT    NOT NULL,
            source           TEXT,
            confidence       REAL    DEFAULT 0.5,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, pref_key)
        );
        """
    )
    conn.commit()
    conn.close()


def init_review_panels_table():
    """审核面板表"""
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS review_panels (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id         TEXT    NOT NULL,
            overall         INTEGER,
            threshold       INTEGER,
            passed          INTEGER,
            verdict_text    TEXT,
            user_decision   TEXT,
            revision_prompt TEXT,
            raw_content     TEXT,
            platforms       TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS review_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            panel_id    INTEGER NOT NULL,
            dimension   TEXT    NOT NULL,
            score       INTEGER,
            threshold   INTEGER,
            passed      INTEGER,
            suggestion  TEXT,
            ignored     INTEGER DEFAULT 0,
            FOREIGN KEY (panel_id) REFERENCES review_panels(id)
        );

        CREATE INDEX IF NOT EXISTS idx_review_task ON review_panels(task_id);
        CREATE INDEX IF NOT EXISTS idx_review_items_panel ON review_items(panel_id);
        """
    )
    conn.commit()
    conn.close()


def migrate_tasks_add_trace():
    """tasks 表增加 trace 字段（执行轨迹持久化）"""
    if not _column_exists("tasks", "trace"):
        conn = _get_conn()
        conn.execute("ALTER TABLE tasks ADD COLUMN trace TEXT")
        conn.commit()
        conn.close()


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

        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );
        """
    )
    conn.commit()
    conn.close()

    # 增量初始化新表（不破坏已有数据）
    init_publish_queue_table()
    init_publish_queue_migration()
    init_style_samples_table()
    init_content_metrics_table()
    init_style_profiles_table()
    init_topic_suggestions_table()
    init_ab_test_variants_table()
    init_eval_results_table()
    migrate_tasks_add_trace()  # P0: 执行轨迹持久化
    init_conversation_turns_table()  # 记忆系统: 会话历史
    init_user_preferences_table()    # 记忆系统: 用户偏好
    init_review_panels_table()       # 审核面板

    # 更新 schema 版本
    _set_schema_version(_SCHEMA_VERSION)


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
        INSERT INTO tasks (task_id, status, note_source, research_data, final_output, metadata, trace, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_id) DO UPDATE SET
            status=excluded.status,
            research_data=excluded.research_data,
            final_output=excluded.final_output,
            metadata=excluded.metadata,
            trace=excluded.trace,
            updated_at=excluded.updated_at
        """,
        (
            state.task_id,
            state.status,
            state.note_source,
            json.dumps(_research_to_dict(state.research_data), ensure_ascii=False),
            json.dumps(_writer_output_to_dict(state.final_output), ensure_ascii=False),
            json.dumps(state.metadata, ensure_ascii=False),
            json.dumps(state.trace, ensure_ascii=False) if state.trace else None,
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
        trace=json.loads(row["trace"]) if row["trace"] else None,
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


# ---- 记忆系统 CRUD ----

def save_conversation_turn(
    session_id: str,
    role: str,
    content: str,
    platforms: Optional[List[str]] = None,
    files: Optional[List[str]] = None,
    task_id: Optional[str] = None,
) -> int:
    """保存一轮会话，返回自增 ID"""
    conn = _get_conn()
    cur = conn.execute(
        """
        INSERT INTO conversation_turns (session_id, role, content, platforms, files, task_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            session_id,
            role,
            content,
            json.dumps(platforms, ensure_ascii=False) if platforms else None,
            json.dumps(files, ensure_ascii=False) if files else None,
            task_id,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid or 0
    conn.close()
    return row_id


def get_conversation_turns(session_id: str, limit: int = 100) -> list:
    """获取指定会话的历史轮次"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM conversation_turns WHERE session_id = ? ORDER BY id ASC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_sessions(limit: int = 20) -> list:
    """列出最近有活动的会话"""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT session_id,
               MAX(created_at) as last_active,
               COUNT(*) as turn_count
        FROM conversation_turns
        GROUP BY session_id
        ORDER BY last_active DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_session(session_id: str) -> int:
    """清除指定会话，返回删除行数"""
    conn = _get_conn()
    cur = conn.execute("DELETE FROM conversation_turns WHERE session_id = ?", (session_id,))
    conn.commit()
    rowcount = cur.rowcount
    conn.close()
    return rowcount


def clear_old_sessions(days: int = 30) -> int:
    """清理 N 天前的会话，返回删除行数"""
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM conversation_turns WHERE created_at < datetime('now', '-{} days')".format(days)
    )
    conn.commit()
    rowcount = cur.rowcount
    conn.close()
    return rowcount


def set_user_preference(
    user_id: str,
    pref_key: str,
    pref_value,
    source: str = "explicit",
    confidence: float = 1.0,
) -> None:
    """设置用户偏好"""
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO user_preferences (user_id, pref_key, pref_value, source, confidence, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(user_id, pref_key) DO UPDATE SET
            pref_value=excluded.pref_value,
            source=excluded.source,
            confidence=excluded.confidence,
            updated_at=datetime('now')
        """,
        (
            user_id,
            pref_key,
            json.dumps(pref_value, ensure_ascii=False),
            source,
            confidence,
        ),
    )
    conn.commit()
    conn.close()


def get_user_preference(user_id: str, pref_key: str, default=None):
    """获取单个偏好"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT pref_value FROM user_preferences WHERE user_id = ? AND pref_key = ?",
        (user_id, pref_key),
    ).fetchone()
    conn.close()
    if row is None:
        return default
    try:
        return json.loads(row["pref_value"])
    except json.JSONDecodeError:
        return row["pref_value"]


def get_user_preferences(user_id: str = "default") -> dict:
    """获取用户全部偏好"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT pref_key, pref_value FROM user_preferences WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    conn.close()
    prefs = {}
    for r in rows:
        try:
            prefs[r["pref_key"]] = json.loads(r["pref_value"])
        except json.JSONDecodeError:
            prefs[r["pref_key"]] = r["pref_value"]
    return prefs


# ---------------------------------------------------------------------------
# 审核面板
# ---------------------------------------------------------------------------

def save_review_panel(panel, task_id: str) -> None:
    """保存审核面板"""
    from agents.review import ReviewPanel, ReviewItem

    conn = _get_conn()
    # 删除旧数据
    old = conn.execute("SELECT id FROM review_panels WHERE task_id = ?", (task_id,)).fetchone()
    if old:
        conn.execute("DELETE FROM review_items WHERE panel_id = ?", (old["id"],))
        conn.execute("DELETE FROM review_panels WHERE id = ?", (old["id"],))

    raw_content_json = ""
    if panel.raw_content is not None:
        try:
            raw_content_json = json.dumps(panel.raw_content.model_dump(), ensure_ascii=False)
        except Exception:
            pass

    cur = conn.execute(
        """
        INSERT INTO review_panels
            (task_id, overall, threshold, passed, verdict_text, user_decision, revision_prompt, raw_content, platforms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            panel.overall,
            panel.threshold,
            int(panel.passed),
            panel.verdict_text,
            panel.user_decision,
            panel.revision_prompt,
            raw_content_json,
            json.dumps(panel.platforms, ensure_ascii=False),
        ),
    )
    panel_id = cur.lastrowid

    for item in panel.items:
        conn.execute(
            """
            INSERT INTO review_items
                (panel_id, dimension, score, threshold, passed, suggestion, ignored)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                panel_id,
                item.dimension,
                item.score,
                item.threshold,
                int(item.passed),
                item.suggestion,
                int(item.ignored),
            ),
        )

    conn.commit()
    conn.close()


def load_review_panel(task_id: str) -> Optional["ReviewPanel"]:
    """加载审核面板"""
    from agents.review import ReviewPanel, ReviewItem

    conn = _get_conn()
    row = conn.execute("SELECT * FROM review_panels WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        conn.close()
        return None

    items_rows = conn.execute(
        "SELECT * FROM review_items WHERE panel_id = ?", (row["id"],)
    ).fetchall()
    conn.close()

    items = []
    for r in items_rows:
        items.append(
            ReviewItem(
                dimension=r["dimension"],
                score=r["score"],
                threshold=r["threshold"],
                passed=bool(r["passed"]),
                suggestion=r["suggestion"] or "",
                ignored=bool(r["ignored"]),
            )
        )

    panel = ReviewPanel(
        overall=row["overall"],
        threshold=row["threshold"],
        passed=bool(row["passed"]),
        items=items,
        verdict_text=row["verdict_text"] or "",
        user_decision=row["user_decision"],
        revision_prompt=row["revision_prompt"] or "",
        platforms=json.loads(row["platforms"]) if row["platforms"] else [],
    )

    if row["raw_content"]:
        try:
            from agents.schemas import WriterOutput
            panel.raw_content = WriterOutput(**json.loads(row["raw_content"]))
        except Exception:
            pass

    return panel


def list_review_panels(limit: int = 50) -> List[dict]:
    """列出审核面板列表，按创建时间倒序"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, task_id, overall, threshold, passed, verdict_text, user_decision, created_at "
        "FROM review_panels ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "task_id": r["task_id"],
            "overall": r["overall"],
            "threshold": r["threshold"],
            "passed": bool(r["passed"]),
            "verdict_text": r["verdict_text"] or "",
            "user_decision": r["user_decision"],
            "created_at": r["created_at"],
        })
    return result


def get_review_panel_detail(panel_id: int) -> Optional[dict]:
    """根据 panel_id 查询审核面板详情，包含所有评分项"""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM review_panels WHERE id = ?", (panel_id,)).fetchone()
    if row is None:
        conn.close()
        return None

    items_rows = conn.execute(
        "SELECT * FROM review_items WHERE panel_id = ? ORDER BY score ASC", (panel_id,)
    ).fetchall()
    conn.close()

    items = []
    for r in items_rows:
        items.append({
            "dimension": r["dimension"],
            "score": r["score"],
            "threshold": r["threshold"],
            "passed": bool(r["passed"]),
            "suggestion": r["suggestion"] or "",
            "ignored": bool(r["ignored"]),
        })

    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "overall": row["overall"],
        "threshold": row["threshold"],
        "passed": bool(row["passed"]),
        "verdict_text": row["verdict_text"] or "",
        "user_decision": row["user_decision"],
        "revision_prompt": row["revision_prompt"] or "",
        "created_at": row["created_at"],
        "items": items,
    }
