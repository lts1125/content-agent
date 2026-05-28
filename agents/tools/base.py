"""
工具基类和结果类型
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any
    error: str = ""


class BaseTool(ABC):
    """工具基类"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        pass

    def to_prompt(self) -> str:
        """生成工具描述（用于 prompt）"""
        return f"- {self.name}: {self.description}"
