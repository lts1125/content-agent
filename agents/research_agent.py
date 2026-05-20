"""
ResearchAgent — 搜索增强 Agent

由 content_agent/research.py 升级而来。
职责：提取关键词 → 执行搜索 → 摘要资料包。
"""

from typing import List

from agents.schemas import TaskState, ResearchResult
from content_agent.research import (
    research_notes,
    extract_keywords_with_llm,
    heuristic_extract_keywords,
)


class ResearchAgent:
    def __init__(self):
        pass

    def run(self, state: TaskState, engine: str = "duckduckgo") -> TaskState:
        """
        对 state 中的笔记执行搜索增强，填充 research_data。
        """
        # 从 drafts 为空、或从外部传入时，笔记内容在 note_source 里
        # 但 orchestrator 目前把笔记文本直接传给 writer，research 只在这里做
        # 为了兼容，我们需要原始笔记文本。这里暂时用空字符串占位，
        # 实际由 Orchestrator 在调用前把 note_text 塞进 state.metadata
        note_text = state.metadata.get("_raw_note_text", "")
        if not note_text:
            state.research_data = ResearchResult(
                keywords=[], sources=[], key_insights="", confidence=0
            )
            return state

        try:
            # 使用现有的 research_notes 函数
            enhanced = research_notes(
                note_text,
                search_engine=engine,
                max_results=3,
                verbose=False,
                keywords=None,
            )
            # 提取资料摘要（research_notes 已经把摘要拼在 enhanced 里）
            # 我们需要反解出 keywords 和 sources
            # 由于 research_notes 返回的是拼接后的文本，我们重新跑一次关键词提取和搜索
            keywords = heuristic_extract_keywords(note_text)
            # 简化：直接从增强文本中提取 insights（前 1000 字）
            insights = enhanced[:1000] if enhanced != note_text else ""
            state.research_data = ResearchResult(
                keywords=keywords,
                sources=[],  # 底层 research.py 未返回结构化 sources，后续可扩展
                key_insights=insights,
                confidence=50 if insights else 0,
            )
        except Exception:
            # 搜索失败不阻断主流程
            state.research_data = ResearchResult(
                keywords=[], sources=[], key_insights="", confidence=0
            )
        return state
