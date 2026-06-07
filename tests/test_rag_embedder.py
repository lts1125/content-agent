import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from content_agent.rag.embedder import BGEEmbedder


class RagEmbedderConfigTest(unittest.TestCase):
    def test_default_fastembed_model_is_chinese_bge(self):
        with patch.dict(os.environ, {}, clear=True):
            embedder = BGEEmbedder()

        self.assertEqual("BAAI/bge-small-zh-v1.5", embedder.model_name)
        self.assertIsNone(embedder.cache_dir)

    def test_cache_dir_can_be_configured_for_docker_volume(self):
        with patch.dict(os.environ, {"RAG_MODEL_CACHE_DIR": "/app/data/fastembed_cache"}, clear=True):
            embedder = BGEEmbedder()

        self.assertEqual("BAAI/bge-small-zh-v1.5", embedder.model_name)
        self.assertEqual("/app/data/fastembed_cache", embedder.cache_dir)

    def test_legacy_model_path_directory_becomes_cache_dir(self):
        with TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"RAG_MODEL_PATH": tmp_dir}, clear=True):
                embedder = BGEEmbedder()

        self.assertEqual("BAAI/bge-small-zh-v1.5", embedder.model_name)
        self.assertEqual(str(Path(tmp_dir)), embedder.cache_dir)


if __name__ == "__main__":
    unittest.main()
