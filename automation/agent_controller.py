"""
Agent Controller — Vault Watcher 的回调接收者

读取笔记 → 构建 TaskInput → Orchestrator.run() → PublishQueue + StyleProfile
"""

import os
from pathlib import Path
from typing import List, Optional

from agents import Orchestrator, TaskInput
from automation.publish_queue import PublishQueue, extract_title
from automation.style_profile import StyleProfile
from automation.vault_watcher import VaultWatcher


class AgentController:
    def __init__(
        self,
        orch: Optional[Orchestrator] = None,
        watcher: Optional[VaultWatcher] = None,
    ):
        self.orch = orch or Orchestrator()
        self.watcher = watcher

    @staticmethod
    def _default_platforms() -> List[str]:
        raw = os.getenv("AGENT_DEFAULT_PLATFORMS", "xiaohongshu,gongzhonghao,douyin")
        return [p.strip() for p in raw.split(",") if p.strip()]

    @staticmethod
    def _env_bool(key: str, default: bool) -> bool:
        val = os.getenv(key, "").lower().strip()
        if val in ("1", "true", "yes", "on"):
            return True
        if val in ("0", "false", "no", "off"):
            return False
        return default

    def on_new_note(self, note_path: Path) -> dict:
        """处理单个笔记文件，返回结果摘要"""
        try:
            content = note_path.read_text(encoding="utf-8")
        except Exception as e:
            return {"success": False, "error": f"读取文件失败: {e}"}

        if not content.strip():
            return {"success": False, "error": "文件内容为空"}

        try:
            task_input = TaskInput(
                note_text=content,
                note_source=str(note_path),
                platforms=self._default_platforms(),
                enable_research=self._env_bool("AGENT_AUTO_RESEARCH", False),
                skip_edit=self._env_bool("AGENT_SKIP_EDIT", True),
                style=os.getenv("AGENT_DEFAULT_STYLE", "default"),
                concurrent_mode=False,
            )
            state = self.orch.run(task_input)
        except Exception as e:
            self._move_to_failed(note_path)
            return {"success": False, "error": f"Orchestrator 调用失败: {e}"}

        final = state.final_output
        if final is None:
            self._move_to_failed(note_path)
            return {"success": False, "error": "生成结果为空"}

        queued = 0
        platforms = task_input.platforms
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
                print(f"[AgentController] 插入队列失败 [{platform}]: {e}")

            try:
                StyleProfile.record_sample(
                    task_id=state.task_id,
                    note_source=str(note_path),
                    note_text=content,
                    platform=platform,
                    content=text,
                )
            except Exception as e:
                print(f"[AgentController] 记录风格样本失败 [{platform}]: {e}")

        self._move_to_processed(note_path)
        return {"success": True, "task_id": state.task_id, "queued": queued}

    def process_inbox(self, inbox_dir: Path) -> List[dict]:
        """批量处理 inbox 下所有已有文件"""
        if not inbox_dir.exists():
            return []
        files = sorted(inbox_dir.iterdir())
        results = []
        for f in files:
            if f.is_file() and f.suffix.lower() in (".md", ".txt"):
                result = self.on_new_note(f)
                results.append(result)
        return results

    def _move_to_processed(self, note_path: Path):
        """移动文件到 processed/"""
        if self.watcher:
            self.watcher.move_to_processed(note_path)

    def _move_to_failed(self, note_path: Path):
        """移动文件到 failed/"""
        if self.watcher:
            self.watcher.move_to_failed(note_path)
