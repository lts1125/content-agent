"""
记忆管理器：统一封装短期、长期、向量三种记忆。

使用示例：
    mm = MemoryManager()
    mm.save_turn(session_id, role="user", content="写篇关于 MCP 的文章")
    mm.save_turn(session_id, role="assistant", content="好的...", task_id="t123")

    # 获取短期记忆（带窗口限制）
    turns = mm.get_recent_turns(session_id, max_tokens=4000)

    # 获取长期偏好
    prefs = mm.get_preferences()

    # 向量检索
    notes = mm.search_notes("编程语言模型接口", top_k=3)
"""

from __future__ import annotations

import os
import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Any, Union

from content_agent.rag.indexer import VaultIndexer
from agents import store


@dataclass
class ConversationTurn:
    """会话轮次"""
    id: int
    session_id: str
    role: str
    content: str
    platforms: list
    files: list
    created_at: str
    task_id: Optional[str]


@dataclass
class NoteChunk:
    """向量检索结果"""
    id: str
    text: str
    source: str
    title: str
    heading: str
    distance: float


@dataclass
class IndexNoteResult:
    """笔记索引结果。"""
    chunks: int
    skipped: bool = False
    reason: str = ""
    content_hash: str = ""
    existing_source: str = ""


class MemoryManager:
    """
    记忆管理器

    统一封装短期（会话历史）、长期（用户偏好）、向量（笔记 RAG）三种记忆。
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self._indexer: Optional[VaultIndexer] = None

    # ------------------------------------------------------------------
    # 懒加载：向量索引器
    # ------------------------------------------------------------------
    def _get_indexer(self) -> Optional[VaultIndexer]:
        """懒加载 VaultIndexer，失败时返回 None 而不抛出异常"""
        if self._indexer is not None:
            return self._indexer
        try:
            self._indexer = VaultIndexer()
            return self._indexer
        except Exception as e:
            print(f"[MemoryManager] 向量索引器初始化失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 短期记忆
    # ------------------------------------------------------------------
    def save_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        platforms: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        task_id: Optional[str] = None,
        memory_refs: Optional[List[dict]] = None,
    ) -> int:
        """保存一轮会话，返回自增 ID"""
        return store.save_conversation_turn(
            session_id=session_id,
            role=role,
            content=content,
            platforms=platforms,
            files=files,
            task_id=task_id,
            memory_refs=memory_refs,
        )

    def get_recent_turns(
        self,
        session_id: str,
        max_tokens: int = 4000,
        max_turns: int = 20,
    ) -> List[ConversationTurn]:
        """
        获取近期会话轮次，按 token 窗口裁剪。

        策略：从最近的开始往前数，直到累计 token 数超过 max_tokens
        或轮次超过 max_turns。
        """
        raw_turns = store.get_conversation_turns(session_id, limit=max_turns * 2)
        if not raw_turns:
            return []

        # 从后往前数，保持最近的轮次
        raw_turns = raw_turns[-max_turns:]

        turns = []
        total_tokens = 0
        for r in reversed(raw_turns):
            turn = ConversationTurn(
                id=r["id"],
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                platforms=_safe_json_load(r.get("platforms"), []),
                files=_safe_json_load(r.get("files"), []),
                created_at=r["created_at"],
                task_id=r.get("task_id"),
            )
            turn_tokens = _estimate_tokens(turn.content)
            if total_tokens + turn_tokens > max_tokens and turns:
                # 已经有内容且超出限制，停止添加
                break
            total_tokens += turn_tokens
            turns.insert(0, turn)  # 保持时间顺序

        return turns

    def get_session_summary(self, session_id: str) -> str:
        """获取会话摘要（简单版）"""
        turns = store.get_conversation_turns(session_id, limit=10)
        if not turns:
            return "无会话记录"
        lines = []
        for t in turns:
            role_label = "用户" if t["role"] == "user" else "Agent"
            content = t["content"][:80].replace("\n", " ")
            lines.append(f"{role_label}: {content}...")
        return "\n".join(lines)

    def list_sessions(self, limit: int = 20) -> List[dict]:
        """列出最近有活动的会话"""
        return store.list_sessions(limit=limit)

    def list_generated_history(self, limit: int = 20) -> List[dict]:
        """列出最近有生成文件的历史记录。"""
        return store.list_generated_turns(limit=limit)

    def clear_session(self, session_id: str) -> int:
        """清除指定会话"""
        return store.clear_session(session_id)

    def clear_all_sessions(self, days: int = 30) -> int:
        """清理 N 天前的会话"""
        return store.clear_old_sessions(days=days)

    # ------------------------------------------------------------------
    # 长期记忆
    # ------------------------------------------------------------------
    def set_preference(
        self,
        key: str,
        value: Any,
        source: str = "explicit",
        confidence: float = 1.0,
    ) -> None:
        """设置用户偏好"""
        store.set_user_preference(
            user_id=self.user_id,
            pref_key=key,
            pref_value=value,
            source=source,
            confidence=confidence,
        )

    def get_preference(self, key: str, default: Any = None) -> Any:
        """获取单个偏好"""
        return store.get_user_preference(self.user_id, key, default)

    def get_preferences(self) -> dict:
        """获取用户全部偏好"""
        return store.get_user_preferences(self.user_id)

    def delete_preference(self, key: str) -> bool:
        """删除单个用户偏好"""
        return store.delete_user_preference(self.user_id, key)

    def infer_preferences_from_history(self) -> dict:
        """
        从历史生成中推断偏好（简单版）。

        当前实现只做基础统计，复杂推断可以后续接入 LLM。
        """
        prefs = {}

        # 统计常用平台
        sessions = store.list_sessions(limit=50)
        session_ids = [s["session_id"] for s in sessions]
        platform_counter = {}
        for sid in session_ids:
            turns = store.get_conversation_turns(sid, limit=100)
            for t in turns:
                ps = _safe_json_load(t.get("platforms"), [])
                for p in ps:
                    platform_counter[p] = platform_counter.get(p, 0) + 1

        if platform_counter:
            # 按频次排序，取 top-3
            sorted_platforms = sorted(platform_counter.items(), key=lambda x: x[1], reverse=True)
            top_platforms = [p for p, _ in sorted_platforms[:3]]
            prefs["favorite_platforms"] = top_platforms

        # 如果已有明确偏好，保留并合并
        existing = self.get_preferences()
        for k, v in existing.items():
            if k not in prefs:
                prefs[k] = v

        return prefs

    # ------------------------------------------------------------------
    # 向量记忆
    # ------------------------------------------------------------------
    def index_note_result(self, file_path: Union[str, Path], clear_existing: bool = False) -> IndexNoteResult:
        """
        将单个 Markdown 笔记文件索引到向量库，返回索引的 chunk 数量。

        也支持传入目录，会索引该目录下所有 .md 文件。
        """
        indexer = self._get_indexer()
        if indexer is None:
            return IndexNoteResult(chunks=0, reason="vector_unavailable")

        path = Path(file_path).expanduser()
        if not path.exists():
            print(f"[MemoryManager] 文件不存在: {path}")
            return IndexNoteResult(chunks=0, reason="missing_file")

        try:
            if path.is_file() and path.suffix.lower() in (".md", ".txt"):
                content = path.read_bytes()
                content_hash = hashlib.sha256(content).hexdigest()
                existing = store.get_indexed_note_by_hash(content_hash)
                if existing and not clear_existing:
                    return IndexNoteResult(
                        chunks=0,
                        skipped=True,
                        reason="duplicate",
                        content_hash=content_hash,
                        existing_source=existing.get("source_path") or "",
                    )

                # 单文件：使用 VaultIndexer 的内部方法索引
                chunks = indexer._split_file(path, path.parent)
                if not chunks:
                    store.save_indexed_note(str(path), content_hash, 0)
                    return IndexNoteResult(chunks=0, content_hash=content_hash, reason="empty")
                texts = [c["text"] for c in chunks]
                embeddings = indexer.embedder.embed_batch(texts)
                ids = [c["id"] for c in chunks]
                metadatas = [c["metadata"] for c in chunks]
                indexer.store.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
                store.save_indexed_note(str(path), content_hash, len(chunks))
                return IndexNoteResult(chunks=len(chunks), content_hash=content_hash)
            elif path.is_dir():
                # 目录：使用现有的 index_vault
                before = indexer.store.count()
                indexer.index_vault(path, clear_existing=clear_existing)
                after = indexer.store.count()
                return IndexNoteResult(chunks=after - before)
            else:
                return IndexNoteResult(chunks=0, reason="unsupported_file")
        except Exception as e:
            print(f"[MemoryManager] 索引失败: {e}")
            return IndexNoteResult(chunks=0, reason=str(e))

    def index_note(self, file_path: Union[str, Path], clear_existing: bool = False) -> int:
        """兼容旧调用：只返回新增 chunk 数量。"""
        return self.index_note_result(file_path, clear_existing=clear_existing).chunks

    def search_notes(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.3,
    ) -> List[NoteChunk]:
        """
        语义检索相关笔记 chunk。

        min_score 是余弦距离阈值（Chroma 使用 cosine 距离，范围 0-2，
        0 表示完全相同），默认 0.3 意味着只返回较相关的结果。
        """
        indexer = self._get_indexer()
        if indexer is None:
            return []

        try:
            results = indexer.search(query, n_results=top_k)
        except Exception as e:
            print(f"[MemoryManager] 检索失败: {e}")
            return []

        chunks = []
        for r in results:
            # cosine 距离，过滤较差的结果
            if r["distance"] > min_score:
                continue
            chunks.append(NoteChunk(
                id=r["id"],
                text=r["document"],
                source=r["metadata"].get("source", ""),
                title=r["metadata"].get("title", ""),
                heading=r["metadata"].get("heading", ""),
                distance=r["distance"],
            ))
        return chunks

    def get_index_stats(self) -> dict:
        """获取向量库统计信息"""
        indexer = self._get_indexer()
        if indexer is None:
            return {"status": "unavailable", "count": 0}
        try:
            return {
                "status": "ready",
                "count": indexer.store.count(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "count": 0}


def _safe_json_load(value, default=None):
    """安全解析 JSON 字符串"""
    if value is None:
        return default if default is not None else []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        import json
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default if default is not None else []
    return default if default is not None else []


def _estimate_tokens(text: str) -> int:
    """
    简单估算 token 数。

    中文约 1 token/字，英文约 1 token/4 chars。
    这里用一个保守估算：总字符数 / 2 （假设混合文本）。
    """
    if not text:
        return 0
    # 保守估算：每个字符约 0.75 token（中英混合平均）
    return int(len(text) * 0.75) + 1
