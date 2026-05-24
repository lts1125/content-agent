"""
Topic Executor — 将接受的选题自动生成为内容

用法:
    from automation.topic_executor import TopicExecutor
    executor = TopicExecutor()
    result = executor.execute(topic_id)  # 根据选题 ID 生成内容
"""

import os
from pathlib import Path
from typing import Optional

from agents import Orchestrator, TaskInput
from agents.store import _get_conn
from automation.publish_queue import PublishQueue, extract_title
from automation.style_profile import StyleProfile


class TopicExecutor:
    """选题执行器：将 accepted 的选题自动生成为内容并入队"""

    def __init__(self, orchestrator: Optional[Orchestrator] = None):
        self.orch = orchestrator or Orchestrator()

    def execute(self, topic_id: str) -> dict:
        """
        执行单个选题生成

        Returns:
            {"success": bool, "task_id": str|None, "queued": int, "error": str|None}
        """
        # 1. 读取选题
        topic = self._get_topic(topic_id)
        if not topic:
            return {"success": False, "error": f"选题不存在: {topic_id}"}

        if topic["status"] != "accepted":
            return {"success": False, "error": f"选题状态不是 accepted: {topic['status']}"}

        # 2. 读取对应笔记
        note_path = self._resolve_note_path(topic["note_file"])
        if not note_path or not note_path.exists():
            return {"success": False, "error": f"笔记文件不存在: {topic['note_file']}"}

        try:
            raw_notes = note_path.read_text(encoding="utf-8")
        except Exception as e:
            return {"success": False, "error": f"读取笔记失败: {e}"}

        # 3. 构建 TaskInput
        platforms = self._parse_platforms(topic.get("platforms", "[]"))
        task_input = TaskInput(
            note_text=raw_notes,
            note_source=str(note_path),
            platforms=platforms,
            enable_research=False,  # 选题阶段已经做过搜索
            skip_edit=True,         # 快速模式，跳过编辑循环
        )

        # 4. 调用 Orchestrator 生成
        try:
            state = self.orch.run(task_input)
        except Exception as e:
            return {"success": False, "error": f"生成失败: {e}"}

        final = state.final_output
        if not final:
            return {"success": False, "error": "生成结果为空"}

        # 5. 入队 PublishQueue
        queued = 0
        content_dict = final.to_content_dict()
        for platform in platforms:
            text = content_dict.get(platform, "")
            if not text:
                continue
            title = extract_title(text)
            tags = final.recommended_tags or ""
            try:
                PublishQueue.add(
                    task_id=state.task_id,
                    platform=platform,
                    title=title,
                    content=text,
                    tags=tags,
                    note_source=str(note_path),
                )
                queued += 1
            except Exception as e:
                print(f"[TopicExecutor] 入队失败 [{platform}]: {e}")

        # 6. 更新选题状态为 generated
        self._mark_generated(topic_id, state.task_id)

        # 7. 记录风格样本
        try:
            for platform in platforms:
                text = content_dict.get(platform, "")
                if text:
                    StyleProfile.record_sample(
                        task_id=state.task_id,
                        note_source=str(note_path),
                        note_text=raw_notes,
                        platform=platform,
                        content=text,
                    )
        except Exception as e:
            print(f"[TopicExecutor] 记录风格样本失败: {e}")

        return {
            "success": True,
            "task_id": state.task_id,
            "queued": queued,
            "error": None,
        }

    def execute_batch(self, limit: int = 10) -> list[dict]:
        """
        批量执行所有 accepted 状态的选题
        """
        topics = self._list_accepted(limit)
        results = []
        for topic in topics:
            print(f"[TopicExecutor] 执行选题: {topic['id']} - {topic['title']}")
            result = self.execute(topic["id"])
            results.append(result)
            if result["success"]:
                print(f"  成功: task_id={result['task_id']}, queued={result['queued']}")
            else:
                print(f"  失败: {result['error']}")
        return results

    # ------------------------------------------------------------------
    # 数据库操作
    # ------------------------------------------------------------------
    @staticmethod
    def _get_topic(topic_id: str) -> Optional[dict]:
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM topic_suggestions WHERE id = ?",
            (topic_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def _list_accepted(limit: int) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM topic_suggestions WHERE status = 'accepted' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def _mark_generated(topic_id: str, task_id: str):
        conn = _get_conn()
        conn.execute(
            "UPDATE topic_suggestions SET status = ?, generated_task_id = ? WHERE id = ?",
            ("generated", task_id, topic_id),
        )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_note_path(note_file: str) -> Optional[Path]:
        """解析笔记文件路径"""
        # 1. 直接作为绝对/相对路径
        p = Path(note_file).expanduser()
        if p.exists():
            return p
        
        # 2. 在 VAULT_PATH 下查找
        vault_path = os.getenv("VAULT_PATH", os.path.expanduser("~/.content_agent/vault"))
        p = Path(vault_path) / note_file
        if p.exists():
            return p
        
        # 3. 在 VAULT_PATH 下递归查找（只匹配文件名）
        vault = Path(vault_path)
        if vault.exists():
            for f in vault.rglob("*.md"):
                if f.name == note_file or f.stem == note_file.replace(".md", ""):
                    return f
        
        return None

    @staticmethod
    def _parse_platforms(platforms_str: str) -> list[str]:
        """解析平台列表 JSON"""
        import json
        try:
            return json.loads(platforms_str)
        except Exception:
            return ["xiaohongshu", "gongzhonghao", "douyin"]


def demo():
    """运行 demo"""
    print("=" * 60)
    print("TopicExecutor Demo")
    print("=" * 60)

    executor = TopicExecutor()

    # 列出 accepted 选题
    accepted = executor._list_accepted(5)
    print(f"\n找到 {len(accepted)} 个 accepted 选题")

    if not accepted:
        print("没有 accepted 选题，请先运行: python main.py --accept-topic <id>")
        return

    for topic in accepted:
        print(f"  • {topic['id']}: {topic['title']}")

    # 执行第一个
    topic = accepted[0]
    print(f"\n执行选题: {topic['title']}")
    result = executor.execute(topic["id"])

    print(f"\n结果: {'成功' if result['success'] else '失败'}")
    if result["success"]:
        print(f"  task_id: {result['task_id']}")
        print(f"  queued: {result['queued']} 个平台")
    else:
        print(f"  error: {result['error']}")


if __name__ == "__main__":
    demo()
