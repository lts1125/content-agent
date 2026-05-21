"""
agents/ 层的公共数据模型

所有 Agent 间的输入输出结构定义在此，避免循环导入。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Task 生命周期
# ---------------------------------------------------------------------------

@dataclass
class TaskInput:
    """用户提交的任务输入"""
    note_text: str
    note_source: str = ""                    # 文件路径或 "clipboard"
    platforms: List[str] = field(default_factory=lambda: ["xiaohongshu", "gongzhonghao", "douyin"])
    enable_research: bool = False
    search_engine: str = "duckduckgo"        # duckduckgo | tavily
    style: str = "default"                   # 风格画像标识
    batch_mode: bool = False
    concurrent_mode: bool = False            # 是否平台级并发生成
    skip_edit: bool = False                  # 是否跳过 Editor 自动修改循环


@dataclass
class ExecutionPlan:
    """Orchestrator 内部使用的执行计划（纯代码生成，非 LLM）"""
    steps: List[str]
    reasoning: str = ""
    needs_search: bool = False
    target_platforms: List[str] = field(default_factory=list)


@dataclass
class TaskState:
    """贯穿整个任务周期的状态对象"""
    task_id: str
    status: Literal["planned", "researching", "writing", "editing", "done", "failed"] = "planned"
    note_source: str = ""
    research_data: Optional["ResearchResult"] = None
    drafts: List["WriterOutput"] = field(default_factory=list)
    edit_history: List["EditVerdict"] = field(default_factory=list)
    final_output: Optional["WriterOutput"] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# Agent 输出
# ---------------------------------------------------------------------------

class ResearchResult(BaseModel):
    """ResearchAgent 输出"""
    keywords: List[str] = []
    sources: List[dict] = []
    key_insights: str = ""
    confidence: int = 0                      # 0-100


class WriterOutput(BaseModel):
    """WriterAgent 输出

    方案 B：平台字段默认为空字符串，便于 PlatformWriterAgent 合并结果。
    """
    xiaohongshu: str = ""
    gongzhonghao: str = ""
    douyin: str = ""
    recommended_tags: str = ""
    revision_notes: str = ""                 # 本轮修改说明

    def to_content_dict(self) -> dict:
        """传给 content_agent/ 工具层时用的纯内容字典"""
        return {
            "xiaohongshu": self.xiaohongshu,
            "gongzhonghao": self.gongzhonghao,
            "douyin": self.douyin,
            "recommended_tags": self.recommended_tags,
        }


class EditVerdict(BaseModel):
    """EditorAgent 输出"""
    scores: dict = {}                        # {platform: int}
    overall: int = 0
    passed: bool = False
    verdict: Literal["pass", "retry", "human_review"] = "pass"
    weakest: str = ""                        # 最弱平台名称
    suggestions: List[str] = []              # 强制格式：[平台] 第X段: 问题 → 期望
    priority: Literal["high", "medium", "low"] = "medium"


class StyleProfile(BaseModel):
    """FeedbackAgent 输出的风格画像"""
    preferred_tone: str = ""
    high_performing_patterns: List[str] = []
    last_updated: str = ""


class TopicSuggestion(BaseModel):
    """TopicPicker 输出的选题建议"""
    id: str = ""
    title: str
    note_file: str
    trending_topic: str
    platforms: List[str]
    reason: str
    priority: int = 3                        # 1-5
    status: str = "pending"                  # pending | accepted | rejected | generated
    created_at: str = ""
