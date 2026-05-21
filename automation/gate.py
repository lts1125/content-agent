"""
审核门 (Publish Gate)

在任何发布操作前强制人工确认，支持交互式 / 排期 / 禁用三种模式。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, List

from automation.publish_queue import QueueItem


@dataclass
class GateDecision:
    item_id: str
    decision: Literal["approve", "reject", "skip"]
    reviewer: str = "cli_user"
    decided_at: str = ""
    reason: str = ""


class PublishGate:
    def __init__(self, mode: Literal["interactive", "scheduled", "disabled"] = "interactive"):
        self.mode = mode

    def review(self, item: QueueItem) -> GateDecision:
        if self.mode == "interactive":
            return self._interactive_prompt(item)
        if self.mode == "scheduled":
            return self._review_scheduled(item)
        if self.mode == "disabled":
            print("\n⚠️  WARNING: 审核门已禁用，自动通过（仅用于开发调试）")
            return GateDecision(
                item_id=item.id,
                decision="approve",
                reviewer="disabled",
                decided_at=datetime.now().isoformat(),
                reason="gate disabled",
            )
        return GateDecision(item.id, "skip", reason="unknown mode")

    def batch_review(self, items: List[QueueItem]) -> List[GateDecision]:
        results = []
        for item in items:
            results.append(self.review(item))
        return results

    @staticmethod
    def _interactive_prompt(item: QueueItem) -> GateDecision:
        print(f"\n{'='*60}")
        print(f"📋 待审核内容")
        print(f"   ID:     {item.id}")
        print(f"   平台:   {item.platform}")
        print(f"   标题:   {item.title}")
        print(f"   内容:   {item.content[:200]}...")
        print(f"   标签:   {item.tags}")
        print(f"{'='*60}")
        try:
            choice = input("确认发布? [y/回车=确认, n=拒绝, s=跳过]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "s"
        decided_at = datetime.now().isoformat()
        if choice in ("", "y", "yes"):
            return GateDecision(item.id, "approve", decided_at=decided_at)
        elif choice == "n":
            try:
                reason = input("拒绝理由 (可留空): ").strip()
            except (EOFError, KeyboardInterrupt):
                reason = ""
            return GateDecision(item.id, "reject", decided_at=decided_at, reason=reason)
        else:
            return GateDecision(item.id, "skip", decided_at=decided_at)

    @staticmethod
    def _review_scheduled(item: QueueItem) -> GateDecision:
        decided_at = datetime.now().isoformat()
        if item.status == "approved":
            return GateDecision(item.id, "approve", decided_at=decided_at, reason="scheduled approved")
        return GateDecision(item.id, "skip", decided_at=decided_at, reason="not approved")
