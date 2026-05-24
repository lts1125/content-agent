"""
Chroma 向量数据库封装

提供笔记 chunk 的增删查接口
"""

import os
from pathlib import Path
from typing import List, Optional

import chromadb
from chromadb.config import Settings


class ChromaStore:
    """Chroma 向量存储"""

    COLLECTION_NAME = "vault_notes"

    def __init__(self, persist_dir: Optional[str] = None):
        if persist_dir is None:
            persist_dir = os.path.join(
                os.path.expanduser("~"), ".content_agent", "chroma_db"
            )
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.Client(
            Settings(
                persist_directory=str(self.persist_dir),
                anonymized_telemetry=False,
            )
        )
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[dict]] = None,
    ):
        """添加文档到向量库"""
        self._collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> List[dict]:
        """
        向量检索

        Returns:
            [{"id": str, "document": str, "metadata": dict, "distance": float}]
        """
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        items = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                items.append(
                    {
                        "id": doc_id,
                        "document": results["documents"][0][i] if results["documents"] else "",
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else 0.0,
                    }
                )
        return items

    def delete(self, ids: Optional[List[str]] = None, where: Optional[dict] = None):
        """删除文档"""
        if ids:
            self._collection.delete(ids=ids)
        elif where:
            self._collection.delete(where=where)

    def count(self) -> int:
        """文档数量"""
        return self._collection.count()

    def peek(self, n: int = 5) -> List[dict]:
        """查看前 n 条"""
        results = self._collection.peek(limit=n)
        items = []
        for i, doc_id in enumerate(results["ids"]):
            items.append(
                {
                    "id": doc_id,
                    "document": results["documents"][i] if results["documents"] else "",
                    "metadata": results["metadatas"][i] if results["metadatas"] else {},
                }
            )
        return items

    def clear(self):
        """清空集合"""
        self._client.delete_collection(self.COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )


def demo():
    """测试向量存储"""
    store = ChromaStore(persist_dir="/tmp/chroma_demo")
    store.clear()

    # 添加测试数据
    from content_agent.rag.embedder import BGEEmbedder

    embedder = BGEEmbedder()
    texts = [
        "MCP 协议是 AI 工具互联的标准",
        "LangChain 是一个 Agent 开发框架",
        "Python 是最流行的编程语言之一",
        "今天天气真好",
    ]
    vectors = embedder.embed_batch(texts)

    store.add(
        ids=["doc_1", "doc_2", "doc_3", "doc_4"],
        documents=texts,
        embeddings=vectors,
        metadatas=[
            {"source": "note1.md", "title": "MCP协议"},
            {"source": "note2.md", "title": "LangChain"},
            {"source": "note3.md", "title": "Python"},
            {"source": "note4.md", "title": "天气"},
        ],
    )

    print(f"已存储 {store.count()} 条文档")

    # 查询
    query = "AI 怎么调用外部工具"
    query_vec = embedder.embed(query)
    results = store.query(query_vec, n_results=2)

    print(f"\n查询: {query}")
    for r in results:
        print(f"  [{r['distance']:.4f}] {r['document']}")
        print(f"    来源: {r['metadata'].get('source', 'unknown')}")


if __name__ == "__main__":
    demo()
