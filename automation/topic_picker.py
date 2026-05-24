"""
Topic Picker — 自动选题

扫描 Vault 笔记 + 搜索热点 → LLM 生成选题建议 → 保存到 topic_suggestions 表
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel
from pydantic_ai import Agent

from agents.schemas import TopicSuggestion
from agents.store import _get_conn
from content_agent.agent_core import ModelConfig
from content_agent.research import research_notes


class TopicSuggestionList(BaseModel):
    suggestions: List[TopicSuggestion]


class TopicPicker:
    def __init__(self, research_agent=None, model=None):
        self.research_agent = research_agent
        if model is None:
            model, _ = ModelConfig.from_env()
        self.model = model

    def scan_vault(self, vault_path: str) -> List[dict]:
        """扫描 Vault 下所有 .md 文件，返回笔记列表"""
        vault = Path(vault_path).expanduser().resolve()
        if not vault.exists():
            return []
        files = []
        for ext in ("*.md", "*.txt"):
            files.extend(vault.rglob(ext))
        result = []
        for f in sorted(files):
            try:
                text = f.read_text(encoding="utf-8")
                title = text.splitlines()[0].lstrip("#").strip() if text else f.stem
                preview = text[:1000]
                result.append({"file": str(f.relative_to(vault)), "title": title, "preview": preview})
            except Exception:
                continue
        return result

    def pick_topics(
        self,
        vault_path: str,
        keywords: Optional[str] = None,
        limit: int = 5,
        trending_hint: Optional[str] = None,
    ) -> List[TopicSuggestion]:
        """
        生成选题建议并保存到 DB

        Args:
            vault_path: Vault 目录路径
            keywords: 搜索关键词
            limit: 最多生成几条建议
            trending_hint: 外部传入的热点文本（如热榜抓取结果），
                          如果提供则跳过搜索，直接使用
        """
        notes = self.scan_vault(vault_path)
        if not notes:
            print("[TopicPicker] Vault 中未找到笔记文件")
            return []

        # 搜索热点（如果未提供 trending_hint）
        if trending_hint:
            trending = trending_hint
            print(f"[TopicPicker] 使用外部热点提示，长度 {len(trending)} 字符")
        else:
            if keywords is None:
                keywords = os.getenv("AGENT_TOPIC_KEYWORDS", "AI Agent, LLM, 大模型")
            try:
                kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if "," in keywords else []
                trending = research_notes(
                    f"最近热点: {keywords}",
                    search_engine="duckduckgo",
                    max_results=5,
                    verbose=False,
                    keywords=kw_list if kw_list else [],
                )
            except Exception as e:
                print(f"[TopicPicker] 搜索热点失败: {e}")
                trending = ""

        # 构建 prompt
        prompt = self._build_prompt(notes, trending, keywords or "AI Agent")

        # 调用 LLM
        try:
            agent = Agent(
                self.model,
                system_prompt="你是一位资深内容策划专家，擅长结合热点和技术笔记生成选题。",
                output_type=TopicSuggestionList,
            )
            result = agent.run_sync(prompt)
            suggestions = result.output.suggestions[:limit]
        except Exception as e:
            print(f"[TopicPicker] LLM 生成失败: {e}")
            return []

        # 保存到 DB，并更新 suggestions 的 id
        now = datetime.now().isoformat()
        conn = _get_conn()
        for s in suggestions:
            sid = f"topic_{uuid.uuid4().hex[:12]}"
            s.id = sid  # 更新对象 id
            conn.execute(
                """
                INSERT INTO topic_suggestions
                (id, title, note_file, trending_topic, platforms, reason, priority, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    s.title,
                    s.note_file,
                    s.trending_topic,
                    json.dumps(s.platforms, ensure_ascii=False),
                    s.reason,
                    s.priority,
                    "pending",
                    now,
                ),
            )
        conn.commit()
        conn.close()
        return suggestions

    @staticmethod
    def _build_prompt(notes: List[dict], trending: str, keywords: str) -> str:
        notes_text = "\n".join(
            [f"{i+1}. {n['file']} - {n['title']}\n预览: {n['preview'][:300]}..." for i, n in enumerate(notes)]
        )
        return f"""你是一位内容策划专家。根据以下笔记和热点，生成选题建议。

【笔记列表】
{notes_text}

【当前热点】（关键词: {keywords}）
{trending[:1500]}

请输出 JSON 格式：{{"suggestions": [{{"title": "...", "note_file": "...", "trending_topic": "...", "platforms": ["xiaohongshu", "gongzhonghao"], "reason": "...", "priority": 5}}, ...]}}

要求：
1. 选题必须基于真实笔记内容，不编造
2. 结合当前热点，提高时效性
3. 每个笔记可对应多个热点，生成多个选题
4. 优先选择有独特视角、能引发讨论的选题
"""

    def list_suggestions(self, status: Optional[str] = None) -> List[TopicSuggestion]:
        conn = _get_conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM topic_suggestions WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM topic_suggestions ORDER BY created_at DESC"
            ).fetchall()
        conn.close()
        return [_row_to_topic(r) for r in rows]

    def accept(self, suggestion_id: str) -> bool:
        """接受选题，并自动触发生成"""
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE topic_suggestions SET status = ? WHERE id = ?",
            ("accepted", suggestion_id),
        )
        conn.commit()
        conn.close()

        if cur.rowcount > 0:
            # 自动触发生成
            try:
                from automation.topic_executor import TopicExecutor
                executor = TopicExecutor()
                result = executor.execute(suggestion_id)
                if result.get("success"):
                    print(f"[TopicPicker] 已自动生成为 task_id={result['task_id']}, 入队 {result['queued']} 个平台")
                else:
                    print(f"[TopicPicker] 自动生成失败: {result.get('error')}")
            except Exception as e:
                print(f"[TopicPicker] 自动触发失败: {e}")
            return True
        return False

    def reject(self, suggestion_id: str) -> bool:
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE topic_suggestions SET status = ? WHERE id = ?",
            ("rejected", suggestion_id),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0


def _row_to_topic(row) -> TopicSuggestion:
    platforms = []
    if row["platforms"]:
        try:
            import json
            platforms = json.loads(row["platforms"])
        except Exception:
            pass
    return TopicSuggestion(
        id=row["id"] or "",
        title=row["title"] or "",
        note_file=row["note_file"] or "",
        trending_topic=row["trending_topic"] or "",
        platforms=platforms,
        reason=row["reason"] or "",
        priority=row["priority"] or 3,
        status=row["status"] or "pending",
        created_at=row["created_at"] or "",
    )
