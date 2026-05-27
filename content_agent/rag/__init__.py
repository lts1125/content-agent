"""
RAG 模块 - 检索增强生成

提供基于 BGE 嵌入的向量检索能力，用于：
1. 笔记语义检索（替代关键词匹配）
2. 热点相关笔记查找
"""

from content_agent.rag.embedder import BGEEmbedder
from content_agent.rag.vector_store import ChromaStore
from content_agent.rag.indexer import VaultIndexer

__all__ = ["BGEEmbedder", "ChromaStore", "VaultIndexer"]
