"""
Agent 协作上下文

提供 Agent 间共享状态、消息通信机制
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class AgentMessage:
    """Agent 间消息"""
    from_agent: str
    to_agent: str
    message_type: str  # "request", "feedback", "result"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AgentContext:
    """共享上下文"""
    task_id: str = ""
    topic: str = ""
    raw_notes: str = ""
    research_report: str = ""
    draft_content: Optional[object] = None
    edit_verdict: Optional[object] = None
    style_profile: Optional[object] = None
    history: List[AgentMessage] = field(default_factory=list)

    def add_message(self, from_agent: str, to_agent: str, message_type: str, content: str):
        """添加消息到历史"""
        self.history.append(AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            content=content
        ))

    def get_messages_for(self, agent_name: str) -> List[AgentMessage]:
        """获取指定 Agent 的消息"""
        return [m for m in self.history if m.to_agent == agent_name]

    def get_last_feedback(self, from_agent: str) -> Optional[AgentMessage]:
        """获取最后一次反馈"""
        feedbacks = [m for m in self.history
                     if m.from_agent == from_agent and m.message_type == "feedback"]
        return feedbacks[-1] if feedbacks else None
