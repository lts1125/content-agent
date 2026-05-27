"""
多 Agent 协作模块

提供 Agent 间通信、共享上下文、协作流程编排
"""

from .context import AgentContext, AgentMessage
from .orchestrator import Orchestrator

__all__ = ["AgentContext", "AgentMessage", "Orchestrator"]
