"""
BGE 嵌入模型封装

使用 BAAI/bge-small-zh-v1.5 生成文本向量。
优先加载本地模型，避免离线环境下检索阶段卡在 HuggingFace 联网检查。
"""

import os
from pathlib import Path
from typing import List

import numpy as np


class BGEEmbedder:
    """BGE 文本嵌入模型"""

    MODEL_NAME = "BAAI/bge-small-zh-v1.5"
    DIMENSION = 512

    def __init__(self, model_path: str = None):
        self._model = None
        self.model_path = model_path or os.getenv("RAG_MODEL_PATH") or os.getenv("BGE_MODEL_PATH")

    def _resolve_model_path(self) -> str:
        """返回优先使用的模型路径或模型名。"""
        if self.model_path:
            p = Path(self.model_path).expanduser()
            if p.exists():
                return str(p)
            print(f"[BGEEmbedder] 本地模型路径不存在，回退到模型名: {p}")

        snapshot = self._find_hf_snapshot()
        if snapshot:
            return str(snapshot)

        return self.MODEL_NAME

    @staticmethod
    def _find_hf_snapshot() -> Path:
        """查找 HuggingFace 默认缓存中的完整 snapshot。"""
        cache_root = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface"))
        model_root = cache_root / "hub" / "models--BAAI--bge-small-zh-v1.5" / "snapshots"
        if not model_root.exists():
            return None

        required = ("modules.json", "config.json", "config_sentence_transformers.json")
        for snapshot in sorted(model_root.iterdir(), reverse=True):
            if snapshot.is_dir() and all((snapshot / name).exists() for name in required):
                return snapshot
        return None

    def _load_model(self):
        """延迟加载模型"""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            model_name_or_path = self._resolve_model_path()
            local_only = Path(model_name_or_path).expanduser().exists()
            print(f"[BGEEmbedder] 加载模型: {model_name_or_path}")
            self._model = SentenceTransformer(
                model_name_or_path,
                local_files_only=local_only,
            )
            print(f"[BGEEmbedder] 模型加载完成")
        return self._model

    def embed(self, text: str) -> List[float]:
        """单条文本嵌入"""
        model = self._load_model()
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """批量文本嵌入"""
        if not texts:
            return []
        model = self._load_model()
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 50,
        )
        return [v.tolist() for v in vectors]

    def similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算两个向量的余弦相似度"""
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))


def demo():
    """测试嵌入效果"""
    embedder = BGEEmbedder()

    texts = [
        "MCP 协议是 AI 工具互联的标准",
        "Model Context Protocol 让 AI 调用外部工具",
        "今天天气真好，适合出去玩",
    ]

    print("生成向量...")
    vectors = embedder.embed_batch(texts)

    print(f"\n文本1: {texts[0]}")
    print(f"文本2: {texts[1]}")
    print(f"相似度: {embedder.similarity(vectors[0], vectors[1]):.4f}")

    print(f"\n文本1: {texts[0]}")
    print(f"文本3: {texts[2]}")
    print(f"相似度: {embedder.similarity(vectors[0], vectors[2]):.4f}")


if __name__ == "__main__":
    demo()
