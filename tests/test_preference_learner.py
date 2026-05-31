"""
偏好学习器 (PreferenceLearner) 单元测试

不依赖外部 LLM，直接测试 preference_learner.py 和 store.py 的集成。
"""

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# 手动加载目标模块（绕过 agents/__init__.py 中的重量级导入链）
# ---------------------------------------------------------------------------
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

# 把 agents 包注册为空模块
agents_pkg = types.ModuleType("agents")
agents_pkg.__path__ = [str(_project_root / "agents")]
sys.modules["agents"] = agents_pkg

# 加载 store.py（只依赖 sqlite3）
_store_spec = importlib.util.spec_from_file_location(
    "agents.store", _project_root / "agents" / "store.py"
)
store_mod = importlib.util.module_from_spec(_store_spec)
sys.modules["agents.store"] = store_mod
_store_spec.loader.exec_module(store_mod)
init_db = store_mod.init_db
save_conversation_turn = store_mod.save_conversation_turn
set_user_preference = store_mod.set_user_preference
get_user_preferences = store_mod.get_user_preferences
clear_old_sessions = store_mod.clear_old_sessions

# 加载 preference_learner.py
_pref_spec = importlib.util.spec_from_file_location(
    "automation.preference_learner", _project_root / "automation" / "preference_learner.py"
)
pref_mod = importlib.util.module_from_spec(_pref_spec)
sys.modules["automation.preference_learner"] = pref_mod
_pref_spec.loader.exec_module(pref_mod)
PreferenceLearner = pref_mod.PreferenceLearner
PlatformStats = pref_mod.PlatformStats


# ---------------------------------------------------------------------------
# 测试辅助函数
# ---------------------------------------------------------------------------

def _insert_fake_eval(conn, platform, overall_score, word_count=500, emoji_count=3,
                       paragraph_count=5, tag_count=3, relevance=7, readability=7,
                       originality=7, practicality=7, platform_fit=7, trend_match=7):
    """插入一条模拟的 eval_results 记录"""
    import time
    eval_id = f"eval_test_{int(time.time() * 1000000)}_{platform}"
    conn.execute(
        """
        INSERT INTO eval_results (
            id, task_id, platform, content_hash,
            relevance_score, readability_score, originality_score, practicality_score,
            platform_fit_score, trend_match_score, overall_score,
            word_count, char_count, paragraph_count, emoji_count, tag_count,
            has_sensitive_words, has_link,
            prompt_tokens, completion_tokens, latency_ms, eval_latency_ms,
            model, eval_model, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (eval_id, "test-task", platform, "hash123",
         relevance, readability, originality, practicality,
         platform_fit, trend_match, overall_score,
         word_count, word_count * 2, paragraph_count, emoji_count, tag_count,
         False, False,
         1000, 2000, 5000, 1000,
         "test-model", "test-eval-model"),
    )
    conn.commit()
    return eval_id


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------

class PreferenceLearnerTest(unittest.TestCase):
    """测试 PreferenceLearner 的核心推断逻辑"""

    def setUp(self):
        self._orig_db = os.environ.get("CONTENT_AGENT_DB")
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        os.environ["CONTENT_AGENT_DB"] = self.tmp_db.name
        init_db()
        # 清空相关表
        conn = store_mod._get_conn()
        conn.execute("DELETE FROM eval_results")
        conn.execute("DELETE FROM user_preferences")
        conn.execute("DELETE FROM conversation_turns")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp_db.close()
        os.unlink(self.tmp_db.name)
        if self._orig_db is not None:
            os.environ["CONTENT_AGENT_DB"] = self._orig_db
        elif "CONTENT_AGENT_DB" in os.environ:
            del os.environ["CONTENT_AGENT_DB"]

    def _insert_samples(self, samples):
        """批量插入评估样本"""
        conn = store_mod._get_conn()
        for s in samples:
            _insert_fake_eval(conn, **s)
        conn.close()

    def test_learn_platform_preference(self):
        """测试平台偏好推断：高分平台被标记为 strong，低分平台被标记为 weak"""
        samples = [
            {"platform": "gongzhonghao", "overall_score": 9, "word_count": 800} for _ in range(5)
        ] + [
            {"platform": "xiaohongshu", "overall_score": 4, "word_count": 300} for _ in range(5)
        ]
        self._insert_samples(samples)

        learner = PreferenceLearner()
        prefs = learner.learn(days=30, min_samples=3)

        self.assertIn("strong_platforms", prefs)
        self.assertIn("gongzhonghao", prefs["strong_platforms"])
        self.assertIn("weak_platforms", prefs)
        self.assertIn("xiaohongshu", prefs["weak_platforms"])

    def test_learn_length_preference(self):
        """测试长度偏好推断"""
        samples = [
            {"platform": "gongzhonghao", "overall_score": 7, "word_count": 2000} for _ in range(5)
        ]
        self._insert_samples(samples)

        learner = PreferenceLearner()
        prefs = learner.learn(days=30, min_samples=3)

        self.assertEqual("long", prefs["preferred_length"])

    def test_learn_style_preference(self):
        """测试风格偏好推断：emoji、段落、标签"""
        samples = [
            {"platform": "xiaohongshu", "overall_score": 7, "word_count": 500,
             "emoji_count": 10, "paragraph_count": 8, "tag_count": 6} for _ in range(5)
        ]
        self._insert_samples(samples)

        learner = PreferenceLearner()
        prefs = learner.learn(days=30, min_samples=3)

        self.assertEqual("high", prefs["emoji_tendency"])
        self.assertEqual("long", prefs["paragraph_tendency"])
        self.assertEqual("high", prefs["tag_tendency"])

    def test_learn_dimension_strength(self):
        """测试评分维度强弱项推断"""
        samples = [
            {"platform": "gongzhonghao", "overall_score": 7, "word_count": 500,
             "relevance": 9, "readability": 9, "originality": 4, "practicality": 4} for _ in range(5)
        ]
        self._insert_samples(samples)

        learner = PreferenceLearner()
        prefs = learner.learn(days=30, min_samples=3)

        self.assertIn("strong_dimensions", prefs)
        self.assertIn("weak_dimensions", prefs)
        self.assertIn("relevance", prefs["strong_dimensions"])
        self.assertIn("originality", prefs["weak_dimensions"])

    def test_learn_no_data(self):
        """测试无数据时返回空"""
        learner = PreferenceLearner()
        prefs = learner.learn(days=30, min_samples=3)
        self.assertEqual({}, prefs)

    def test_learn_not_enough_samples(self):
        """测试样本不足时不做推断"""
        samples = [
            {"platform": "gongzhonghao", "overall_score": 9, "word_count": 500} for _ in range(2)
        ]
        self._insert_samples(samples)

        learner = PreferenceLearner()
        prefs = learner.learn(days=30, min_samples=3)

        # 只有 2 个样本，不满足 min_samples=3
        self.assertNotIn("strong_platforms", prefs)

    def test_report_format(self):
        """测试报告格式包含平台统计"""
        samples = [
            {"platform": "gongzhonghao", "overall_score": 8, "word_count": 1000, "emoji_count": 2} for _ in range(5)
        ]
        self._insert_samples(samples)

        learner = PreferenceLearner()
        report = learner.report(days=30)

        self.assertIn("gongzhonghao", report)
        self.assertIn("5", report)  # 样本数


if __name__ == "__main__":
    unittest.main()
