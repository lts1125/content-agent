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

        # 2. 判断内容类型：笔记驱动 vs 热点驱动
        platforms = self._parse_platforms(topic.get("platforms", "[]"))
        
        # 如果有 trending_hint，说明是热点驱动，用热点内容生成
        trending_hint = topic.get("trending_hint", "")
        if trending_hint and "douyin" in platforms:
            return self._execute_trending(topic, trending_hint, platforms)

        # 否则是笔记驱动（原有逻辑）
        return self._execute_note(topic, platforms)

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

    # ------------------------------------------------------------------
    # 笔记驱动（原有逻辑）
    # ------------------------------------------------------------------
    def _execute_note(self, topic: dict, platforms: list[str]) -> dict:
        """基于笔记生成内容"""
        note_path = self._resolve_note_path(topic["note_file"])
        if not note_path or not note_path.exists():
            return {"success": False, "error": f"笔记文件不存在: {topic['note_file']}"}

        try:
            raw_notes = note_path.read_text(encoding="utf-8")
        except Exception as e:
            return {"success": False, "error": f"读取笔记失败: {e}"}

        task_input = TaskInput(
            note_text=raw_notes,
            note_source=str(note_path),
            platforms=platforms,
            enable_research=False,
            skip_edit=True,
        )

        try:
            state = self.orch.run(task_input)
        except Exception as e:
            return {"success": False, "error": f"生成失败: {e}"}

        final = state.final_output
        if not final:
            return {"success": False, "error": "生成结果为空"}

        queued = self._queue_content(state, final, platforms, str(note_path), raw_notes)
        self._mark_generated(topic["id"], state.task_id)

        return {
            "success": True,
            "task_id": state.task_id,
            "queued": queued,
            "error": None,
        }

    # ------------------------------------------------------------------
    # 热点驱动（抖音图文）
    # ------------------------------------------------------------------
    def _execute_trending(self, topic: dict, trending_hint: str, platforms: list[str]) -> dict:
        """基于热点生成抖音图文"""
        from content_agent.douyin_renderer import DouyinRenderer
        from agents.store import generate_task_id

        # 1. 用 LLM 把热点扩展成结构化内容
        content = self._generate_trending_content(trending_hint, topic["title"])
        if not content:
            return {"success": False, "error": "热点内容生成失败"}

        # 2. 生成抖音图文 HTML
        renderer = DouyinRenderer()
        import uuid
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        output_dir = Path("output/douyin") / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        html_path = renderer.render(content, output_dir)

        # 3. 入队（抖音平台存 HTML 路径）
        try:
            PublishQueue.add(
                task_id=task_id,
                platform="douyin",
                title=topic["title"],
                content=content,
                tags="AI,科技,资讯",
                note_source=html_path,
            )
            queued = 1
        except Exception as e:
            print(f"[TopicExecutor] 入队失败 [douyin]: {e}")
            queued = 0

        self._mark_generated(topic["id"], task_id)

        return {
            "success": True,
            "task_id": task_id,
            "queued": queued,
            "error": None,
        }

    def _generate_trending_content(self, trending_hint: str, title: str) -> str:
        """用 LLM 把热点扩展成结构化内容"""
        from pydantic_ai import Agent
        import os

        model = os.getenv("MODEL_PROVIDER", "deepseek")
        agent = Agent(
            model,
            system_prompt="""你是一位科技资讯编辑，擅长把热点新闻改写成适合抖音图文的结构化内容。

输出格式要求：
1. 第一行：#标签（如 #AI资讯 #科技前沿）
2. 第二行：空行
3. 第三行：标题（一句话概括）
4. 空行
5. 用 "1. 2. 3." 分小节，每节配 2-4 个要点（用 "- " 开头）
6. 最后一行：一句金句总结

风格：简洁、有冲击力、适合快速阅读。""",
        )

        try:
            result = agent.run_sync(
                f"热点信息：{trending_hint}\n\n请根据这个热点，生成一篇抖音图文内容。标题：{title}"
            )
            return result.output
        except Exception as e:
            print(f"[TopicExecutor] LLM 生成热点内容失败: {e}")
            # 兜底：直接返回热点信息
            return f"#AI资讯\n\n{title}\n\n{trending_hint}\n\n关注获取更多科技资讯。"

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------
    def _queue_content(self, state, final, platforms: list[str], note_path: str, raw_notes: str) -> int:
        """将生成的内容入队"""
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
                    note_source=note_path,
                )
                queued += 1
            except Exception as e:
                print(f"[TopicExecutor] 入队失败 [{platform}]: {e}")

        # 记录风格样本
        try:
            for platform in platforms:
                text = content_dict.get(platform, "")
                if text:
                    StyleProfile.record_sample(
                        task_id=state.task_id,
                        note_source=note_path,
                        note_text=raw_notes,
                        platform=platform,
                        content=text,
                    )
        except Exception as e:
            print(f"[TopicExecutor] 记录风格样本失败: {e}")

        return queued


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
