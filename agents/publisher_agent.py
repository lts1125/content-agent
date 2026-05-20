"""
PublisherAgent — 内容发布 Agent

由 content_agent/publisher.py 升级而来。
职责：调用底层发布工具，记录发布元数据。
"""

from typing import Optional
from pathlib import Path

from agents.schemas import TaskState
from content_agent.publisher import (
    publish_wechat_draft,
    check_kuaifa,
    save_content_as_markdown,
)


class PublisherAgent:
    def __init__(self):
        pass

    def publish_wechat(
        self,
        state: TaskState,
        title: str,
        cover_path: str = "",
        author: str = "",
        digest: str = "",
    ) -> dict:
        """
        发布公众号草稿箱。
        先保存 Markdown 临时文件，再调用 kuaifa。
        """
        if not state.final_output:
            return {"success": False, "message": "❌ 没有最终文案可发布"}

        content = state.final_output.gongzhonghao
        md_path = save_content_as_markdown(title, content)

        result = publish_wechat_draft(
            markdown_path=md_path,
            title=title,
            cover_path=cover_path,
            author=author,
            digest=digest,
        )

        # 记录发布元数据到 state
        state.metadata.setdefault("publish_history", []).append({
            "platform": "wechat",
            "title": title,
            "success": result["success"],
            "message": result["message"],
        })
        return result

    @staticmethod
    def check_kuaifa_status() -> tuple[bool, str]:
        """检查 kuaifa 是否可用"""
        return check_kuaifa()
