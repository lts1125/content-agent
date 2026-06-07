"""
BGE 嵌入模型封装（fastembed 轻量版）

使用 BAAI/bge-small-zh-v1.5 ONNX 模型，无需 PyTorch。
"""

import os
from pathlib import Path
from typing import List

import numpy as np


class BGEEmbedder:
    """BGE 文本嵌入模型（ONNX 轻量版）"""

    MODEL_NAME = "BAAI/bge-small-zh-v1.5"
    DIMENSION = 512

    def __init__(self, model_path: str = None):
        self._model = None
        legacy_path = os.getenv("RAG_MODEL_PATH") or os.getenv("BGE_MODEL_PATH")
        configured_model = model_path or os.getenv("RAG_MODEL_NAME")
        self.model_name = configured_model or self.MODEL_NAME
        self.cache_dir = os.getenv("RAG_MODEL_CACHE_DIR")

        # 兼容旧配置：如果 RAG_MODEL_PATH/BGE_MODEL_PATH 指向本地目录，
        # 在 fastembed 中作为缓存目录使用；否则把它当作模型名。
        if not configured_model and legacy_path:
            path = Path(legacy_path).expanduser()
            if path.exists():
                self.cache_dir = str(path)
            else:
                self.model_name = legacy_path

    def _load_model(self):
        """延迟加载模型"""
        if self._model is None:
            from fastembed import TextEmbedding

            print(f"[BGEEmbedder] 加载模型: {self.model_name}")
            self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
            print(f"[BGEEmbedder] 模型加载完成")
        return self._model

    def embed(self, text: str) -> List[float]:
        """单条文本嵌入"""
        model = self._load_model()
        vectors = list(model.embed([text]))
        vector = vectors[0]
        # fastembed 已经做了归一化，但再归一化一次确保
        normalized = vector / (np.linalg.norm(vector) + 1e-12)
        return normalized.tolist()

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """批量文本嵌入"""
        if not texts:
            return []
        model = self._load_model()
        vectors = list(model.embed(texts, batch_size=batch_size))
        # 归一化
        normalized = []
        for v in vectors:
            nv = v / (np.linalg.norm(v) + 1e-12)
            normalized.append(nv.tolist())
        return normalized

    def similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算两个向量的余弦相似度"""
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-12))


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
