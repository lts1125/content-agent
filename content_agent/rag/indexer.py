"""
Vault 笔记索引器

将 Vault 中的 Markdown 笔记切分 chunk，生成向量，存入 Chroma
"""

import re
from pathlib import Path
from typing import List

from content_agent.rag.embedder import BGEEmbedder
from content_agent.rag.vector_store import ChromaStore


class VaultIndexer:
    """Vault 笔记索引器"""

    def __init__(
        self,
        embedder: BGEEmbedder = None,
        store: ChromaStore = None,
    ):
        self.embedder = embedder if embedder is not None else BGEEmbedder()
        self.store = store if store is not None else ChromaStore()

    def index_vault(self, vault_path, clear_existing: bool = False):
        """
        索引整个 Vault 目录

        Args:
            vault_path: Vault 根目录（str 或 Path）
            clear_existing: 是否清空已有索引
        """
        vault_path = Path(vault_path).expanduser()
        if not vault_path.exists():
            print(f"[VaultIndexer] Vault 路径不存在: {vault_path}")
            return

        if clear_existing:
            print("[VaultIndexer] 清空已有索引...")
            self.store.clear()

        # 收集所有 markdown 文件
        md_files = list(vault_path.rglob("*.md"))
        print(f"[VaultIndexer] 发现 {len(md_files)} 个 markdown 文件")

        if not md_files:
            return

        # 切分 chunk
        all_chunks = []
        for md_file in md_files:
            chunks = self._split_file(md_file, vault_path)
            all_chunks.extend(chunks)

        print(f"[VaultIndexer] 共切分 {len(all_chunks)} 个 chunk")

        if not all_chunks:
            return

        # 批量生成向量
        texts = [c["text"] for c in all_chunks]
        print(f"[VaultIndexer] 生成向量...")
        embeddings = self.embedder.embed_batch(texts)

        # 存入 Chroma
        ids = [c["id"] for c in all_chunks]
        metadatas = [c["metadata"] for c in all_chunks]

        self.store.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        print(f"[VaultIndexer] 索引完成，共 {self.store.count()} 条")

    def _split_file(self, md_file: Path, vault_root: Path) -> List[dict]:
        """
        按 Markdown 标题层级切分文件

        Returns:
            [{"id": str, "text": str, "metadata": dict}]
        """
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[VaultIndexer] 读取失败 {md_file}: {e}")
            return []

        # 相对路径作为 source
        rel_path = md_file.relative_to(vault_root)

        # 按 ## 标题切分
        # 匹配 ## 或 ### 开头的行
        pattern = r"^(#{2,3}\s+.+)$"
        parts = re.split(pattern, content, flags=re.MULTILINE)

        chunks = []
        if len(parts) <= 1:
            # 没有二级标题，整篇作为一个 chunk
            chunks.append({
                "id": f"{rel_path}#full",
                "text": content[:2000],  # 限制长度
                "metadata": {
                    "source": str(rel_path),
                    "title": md_file.stem,
                    "heading": "",
                },
            })
        else:
            # 有标题，按标题切分
            # parts[0] 是前言（可能没有标题）
            if parts[0].strip():
                chunks.append({
                    "id": f"{rel_path}#intro",
                    "text": parts[0][:2000],
                    "metadata": {
                        "source": str(rel_path),
                        "title": md_file.stem,
                        "heading": "intro",
                    },
                })

            # 后续是 标题 + 内容 成对出现
            for i in range(1, len(parts), 2):
                if i + 1 < len(parts):
                    heading = parts[i].strip()
                    body = parts[i + 1].strip()
                    text = f"{heading}\n\n{body}"[:2000]

                    heading_slug = re.sub(r"[^\w]", "_", heading.replace("#", "").strip())[:30]
                    chunk_id = f"{rel_path}#{heading_slug}"
                    # 避免重复 ID，添加序号
                    original_id = chunk_id
                    counter = 1
                    while any(c["id"] == chunk_id for c in chunks):
                        chunk_id = f"{original_id}_{counter}"
                        counter += 1
                    chunks.append({
                        "id": chunk_id,
                        "text": text,
                        "metadata": {
                            "source": str(rel_path),
                            "title": md_file.stem,
                            "heading": heading.replace("#", "").strip(),
                        },
                    })

        return chunks

    def search(self, query: str, n_results: int = 5) -> List[dict]:
        """
        语义检索

        Returns:
            [{"id", "document", "metadata", "distance"}]
        """
        query_vec = self.embedder.embed(query)
        return self.store.query(query_vec, n_results=n_results)


def demo():
    """测试索引和检索"""
    import os

    vault_path = os.getenv("VAULT_PATH", os.path.expanduser("~/.content_agent/vault"))

    indexer = VaultIndexer()
    indexer.index_vault(vault_path, clear_existing=True)

    # 测试检索
    queries = [
        "MCP 协议是什么",
        "Agent 开发框架",
        "热点监控怎么实现",
    ]

    for q in queries:
        print(f"\n查询: {q}")
        results = indexer.search(q, n_results=3)
        for r in results:
            print(f"  [{r['distance']:.4f}] {r['metadata'].get('title', 'unknown')}")
            print(f"    {r['document'][:100]}...")


if __name__ == "__main__":
    demo()
