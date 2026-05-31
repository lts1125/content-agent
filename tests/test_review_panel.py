"""
审核面板（ReviewPanel）单元测试

不依赖外部 LLM / Gradio，直接测试 agents/review.py 和 agents/store.py 的核心逻辑。
"""

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# 手动加载目标模块（绕过 agents/__init__.py 中的重量级导入链）
# ---------------------------------------------------------------------------
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

# Mock gradio 以便 chat_ui 能够导入（当前环境 huggingface_hub 版本不兼容）
import unittest.mock

_mock_gr = unittest.mock.MagicMock()
_mock_gr.update = lambda **kwargs: kwargs
_mock_gr.State = lambda initial_value=None: initial_value
_mock_gr.Button = unittest.mock.MagicMock
_mock_gr.Row = unittest.mock.MagicMock
_mock_gr.Column = unittest.mock.MagicMock
_mock_gr.HTML = unittest.mock.MagicMock
_mock_gr.Accordion = unittest.mock.MagicMock
_mock_gr.Textbox = unittest.mock.MagicMock
_mock_gr.Image = unittest.mock.MagicMock
_mock_gr.File = unittest.mock.MagicMock
_mock_gr.Markdown = unittest.mock.MagicMock
_mock_gr.Chatbot = unittest.mock.MagicMock
_mock_gr.Blocks = unittest.mock.MagicMock()
_mock_gr.Blocks.get_api_info = unittest.mock.MagicMock(return_value={"named_endpoints": {}, "unnamed_endpoints": {}})
_mock_gr.JSON = unittest.mock.MagicMock
sys.modules["gradio"] = _mock_gr

# 把 agents 包注册为空模块，防止导入 agents.xxx 时触发 agents/__init__.py
agents_pkg = types.ModuleType("agents")
agents_pkg.__path__ = [str(_project_root / "agents")]
sys.modules["agents"] = agents_pkg

# schemas.py 只依赖 pydantic，可以直接加载
_schemas_spec = importlib.util.spec_from_file_location(
    "agents.schemas", _project_root / "agents" / "schemas.py"
)
schemas_mod = importlib.util.module_from_spec(_schemas_spec)
sys.modules["agents.schemas"] = schemas_mod
_schemas_spec.loader.exec_module(schemas_mod)
EditVerdict = schemas_mod.EditVerdict

# review.py 依赖 schemas.py
_review_spec = importlib.util.spec_from_file_location(
    "agents.review", _project_root / "agents" / "review.py"
)
review_mod = importlib.util.module_from_spec(_review_spec)
sys.modules["agents.review"] = review_mod
_review_spec.loader.exec_module(review_mod)
ReviewManager = review_mod.ReviewManager
ReviewPanel = review_mod.ReviewPanel
ReviewItem = review_mod.ReviewItem
PLATFORM_NAMES = review_mod.PLATFORM_NAMES

# store.py 依赖 schemas.py
_store_spec = importlib.util.spec_from_file_location(
    "agents.store", _project_root / "agents" / "store.py"
)
store_mod = importlib.util.module_from_spec(_store_spec)
sys.modules["agents.store"] = store_mod
_store_spec.loader.exec_module(store_mod)
init_db = store_mod.init_db
save_review_panel = store_mod.save_review_panel
load_review_panel = store_mod.load_review_panel
list_review_panels = store_mod.list_review_panels
get_review_panel_detail = store_mod.get_review_panel_detail

# 尝试加载 chat_ui（已被 gradio mock 保护）
_chat_ui_loaded = False
try:
    import chat_ui

    _chat_ui_loaded = True
except Exception:
    chat_ui = None


# ---------------------------------------------------------------------------
# 测试用辅助函数
# ---------------------------------------------------------------------------

def _make_verdict(overall=65, passed=False, scores=None, suggestions=None):
    """构造一个 mock 的 EditVerdict，避免导入真实 LLM 依赖。"""
    return EditVerdict(
        overall=overall,
        passed=passed,
        verdict="retry" if not passed else "pass",
        scores=scores or {},
        suggestions=suggestions or [],
    )


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------

class ReviewPanelTest(unittest.TestCase):
    """测试 ReviewManager 和 ReviewPanel 的核心逻辑。"""

    def test_create_panel_from_platform_scores(self):
        verdict = _make_verdict(
            overall=65,
            passed=False,
            scores={"gongzhonghao": 70, "xiaohongshu": 60},
            suggestions=["公众号开头太平淡", "小红书emoji不够"],
        )
        panel = ReviewManager.create_panel(verdict, threshold=75)

        self.assertEqual(65, panel.overall)
        self.assertFalse(panel.passed)
        self.assertEqual(2, len(panel.items))
        self.assertEqual("公众号", panel.items[0].dimension)
        self.assertEqual(70, panel.items[0].score)
        self.assertFalse(panel.items[0].passed)
        self.assertEqual("小红书", panel.items[1].dimension)
        self.assertEqual(60, panel.items[1].score)
        self.assertFalse(panel.items[1].passed)

    def test_create_panel_fallback_when_no_platform_scores(self):
        verdict = _make_verdict(
            overall=80,
            passed=True,
            scores={},
            suggestions=["整体不错"],
        )
        panel = ReviewManager.create_panel(verdict, threshold=75)

        self.assertEqual(1, len(panel.items))
        self.assertEqual("综合评分", panel.items[0].dimension)
        self.assertEqual(80, panel.items[0].score)
        self.assertTrue(panel.items[0].passed)

    def test_to_markdown_shows_scores_and_icons(self):
        verdict = _make_verdict(
            overall=65,
            passed=False,
            scores={"gongzhonghao": 70, "xiaohongshu": 60},
            suggestions=["公众号开头太平淡"],
        )
        panel = ReviewManager.create_panel(verdict, threshold=75)
        md = panel.to_markdown()

        self.assertIn("质量检查报告", md)
        self.assertIn("65/100", md)
        self.assertIn("公众号", md)
        self.assertIn("小红书", md)
        self.assertIn("公众号开头太平淡", md)

    def test_effective_score_after_ignore(self):
        verdict = _make_verdict(
            overall=65,
            passed=False,
            scores={"gongzhonghao": 70, "xiaohongshu": 60},
            suggestions=["公众号开头太平淡", "小红书emoji不够"],
        )
        panel = ReviewManager.create_panel(verdict, threshold=75)

        # 忽略前：2 项都未通过
        self.assertEqual(65, panel.effective_score)
        self.assertFalse(panel.effective_passed)

        # 忽略最低分的小红书（60 分）和公众号（70 分），达到忽略上限 2 项
        result = ReviewManager.apply_user_decision(panel, "ignore")
        self.assertEqual("retry", result["action"])
        self.assertEqual(2, panel.ignored_count)
        self.assertFalse(panel.effective_passed)

    def test_ignore_until_passed(self):
        verdict = _make_verdict(
            overall=65,
            passed=False,
            scores={"gongzhonghao": 80, "xiaohongshu": 50},
            suggestions=["公众号开头太平淡", "小红书emoji不够"],
        )
        panel = ReviewManager.create_panel(verdict, threshold=75)

        result = ReviewManager.apply_user_decision(panel, "ignore")
        self.assertEqual("publish", result["action"])
        self.assertTrue(panel.effective_passed)
        self.assertEqual(80, panel.effective_score)

    def test_force_publish_always_returns_publish(self):
        verdict = _make_verdict(
            overall=50,
            passed=False,
            scores={"gongzhonghao": 50},
            suggestions=["质量太差"],
        )
        panel = ReviewManager.create_panel(verdict, threshold=75)

        result = ReviewManager.apply_user_decision(panel, "force_publish")
        self.assertEqual("publish", result["action"])
        self.assertFalse(panel.effective_passed)

    def test_revise_returns_prompt(self):
        verdict = _make_verdict(
            overall=65,
            passed=False,
            scores={"gongzhonghao": 70, "xiaohongshu": 60},
            suggestions=["公众号开头太平淡", "小红书emoji不够"],
        )
        panel = ReviewManager.create_panel(verdict, threshold=75)

        result = ReviewManager.apply_user_decision(panel, "revise")
        self.assertEqual("revise", result["action"])
        self.assertIn("公众号开头太平淡", result["prompt"])
        self.assertIn("小红书emoji不够", result["prompt"])

    def test_can_ignore_more_respects_limit(self):
        verdict = _make_verdict(
            overall=50,
            passed=False,
            scores={"a": 60, "b": 55, "c": 45},
            suggestions=["a开头太平淡", "bemoji不够", "c标题弱"],
        )
        panel = ReviewManager.create_panel(verdict, threshold=75)
        self.assertTrue(panel.can_ignore_more())  # 0 < 2

        # 第一次 ignore 会忽略分数最低的 2 项（c=45, b=55），达到上限
        ReviewManager.apply_user_decision(panel, "ignore")
        self.assertFalse(panel.can_ignore_more())  # 2 < 2 不成立

        # 第二次 ignore 无法再忽略
        ReviewManager.apply_user_decision(panel, "ignore")
        self.assertFalse(panel.can_ignore_more())

    def test_get_revision_prompt_skips_ignored_items(self):
        verdict = _make_verdict(
            overall=50,
            passed=False,
            scores={"a": 60, "b": 55},
            suggestions=["a开头太平淡", "bemoji不够"],
        )
        panel = ReviewManager.create_panel(verdict, threshold=75)
        panel.items[0].ignored = True

        prompt = panel.get_revision_prompt()
        self.assertNotIn("a开头太平淡", prompt)
        self.assertIn("bemoji不够", prompt)

    def test_can_revise_respects_limit(self):
        """can_revise 在达到最大重试次数后返回 False"""
        panel = ReviewPanel(
            overall=60,
            threshold=75,
            passed=False,
            items=[ReviewItem(dimension="口语化", score=55, threshold=75, passed=False, suggestion="添加口语化表达")],
            verdict_text="需修改",
        )
        self.assertTrue(panel.can_revise())  # 0 < 2
        panel.revision_count = 1
        self.assertTrue(panel.can_revise())  # 1 < 2
        panel.revision_count = 2
        self.assertFalse(panel.can_revise())  # 2 >= 2
        panel.revision_count = 3
        self.assertFalse(panel.can_revise())  # 3 >= 2

    def test_to_markdown_shows_revision_count(self):
        """to_markdown 在有重试次数时显示剩余次数"""
        panel = ReviewPanel(
            overall=60,
            threshold=75,
            passed=False,
            items=[ReviewItem(dimension="口语化", score=55, threshold=75, passed=False, suggestion="添加口语化表达")],
            verdict_text="需修改",
            revision_count=1,
        )
        md = panel.to_markdown()
        self.assertIn("已重试", md)
        self.assertIn("1/2", md)
        self.assertIn("剩余 1 次", md)

    def test_to_markdown_no_revision_count_when_zero(self):
        """to_markdown 在重试次数为 0 时不显示重试信息"""
        panel = ReviewPanel(
            overall=60,
            threshold=75,
            passed=False,
            items=[ReviewItem(dimension="口语化", score=55, threshold=75, passed=False, suggestion="添加口语化表达")],
            verdict_text="需修改",
            revision_count=0,
        )
        md = panel.to_markdown()
        self.assertNotIn("已重试", md)


class ReviewDatabaseTest(unittest.TestCase):
    """测试 review 相关的数据库操作。"""

    def setUp(self):
        self._orig_db = os.environ.get("CONTENT_AGENT_DB")
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        os.environ["CONTENT_AGENT_DB"] = self.tmp_db.name
        init_db()
        # 每个测试前清空 review 表，避免测试间相互干扰
        conn = store_mod._get_conn()
        conn.execute("DELETE FROM review_items")
        conn.execute("DELETE FROM review_panels")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp_db.close()
        os.unlink(self.tmp_db.name)
        if self._orig_db is not None:
            os.environ["CONTENT_AGENT_DB"] = self._orig_db
        elif "CONTENT_AGENT_DB" in os.environ:
            del os.environ["CONTENT_AGENT_DB"]

    def test_save_and_load_review_panel(self):
        verdict = _make_verdict(
            overall=65,
            passed=False,
            scores={"gongzhonghao": 70, "xiaohongshu": 60},
            suggestions=["公众号开头太平淡"],
        )
        panel = ReviewManager.create_panel(verdict, threshold=75)
        panel.platforms = ["gongzhonghao", "xiaohongshu"]

        @dataclass
        class FakeContent:
            gongzhonghao: str = "test gzh"
            xiaohongshu: str = "test xhs"

        panel.raw_content = FakeContent()

        task_id = "test-task-001"
        save_review_panel(panel, task_id)

        panels = list_review_panels()
        self.assertEqual(1, len(panels))
        self.assertEqual(task_id, panels[0]["task_id"])

        loaded = load_review_panel(task_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(65, loaded.overall)
        self.assertEqual(2, len(loaded.items))
        self.assertEqual("公众号", loaded.items[0].dimension)

    def test_list_panels_returns_empty_when_no_data(self):
        panels = list_review_panels()
        self.assertEqual([], panels)

    def test_get_review_panel_detail_returns_full_data(self):
        verdict = _make_verdict(
            overall=65,
            passed=False,
            scores={"gongzhonghao": 70, "xiaohongshu": 60},
            suggestions=["公众号开头太平淡", "小红书emoji不够"],
        )
        panel = ReviewManager.create_panel(verdict, threshold=75)
        panel.platforms = ["gongzhonghao", "xiaohongshu"]
        save_review_panel(panel, "detail-task-001")

        # 先列出获取 panel_id
        panels = list_review_panels()
        self.assertEqual(1, len(panels))
        panel_id = panels[0]["id"]

        detail = get_review_panel_detail(panel_id)
        self.assertIsNotNone(detail)
        self.assertEqual("detail-task-001", detail["task_id"])
        self.assertEqual(65, detail["overall"])
        self.assertEqual(75, detail["threshold"])
        self.assertFalse(detail["passed"])
        self.assertEqual(2, len(detail["items"]))

        # 按分数从低到高排序
        self.assertEqual("小红书", detail["items"][0]["dimension"])
        self.assertEqual(60, detail["items"][0]["score"])
        self.assertEqual("公众号", detail["items"][1]["dimension"])
        self.assertEqual(70, detail["items"][1]["score"])

    def test_get_review_panel_detail_returns_none_for_invalid_id(self):
        detail = get_review_panel_detail(99999)
        self.assertIsNone(detail)


@unittest.skipUnless(_chat_ui_loaded, "chat_ui 依赖未就绪，跳过集成测试")
class ChatUiReviewIntegrationTest(unittest.TestCase):
    """测试 chat_ui 层面对 review 类型结果的处理。"""

    def test_result_to_response_shows_review_flag(self):
        result = {
            "type": "review",
            "content": "## 质量检查报告\n\n...",
            "panel": None,
        }
        response, gzh_path, files, show_review = chat_ui._result_to_response(result)

        self.assertIn("质量检查报告", response)
        self.assertEqual("", gzh_path)
        self.assertEqual([], files)
        self.assertTrue(show_review)

    def test_respond_stream_yields_review_panel_on_low_score(self):
        @dataclass
        class FakePanel:
            overall: int = 60
            threshold: int = 75
            passed: bool = False
            verdict_text: str = "需修改"
            raw_content: object = None
            platforms: list = None
            items: list = None
            user_decision: str = None
            revision_prompt: str = ""

            def to_markdown(self):
                return "## 检查报告"

            def get_revision_prompt(self):
                return "修改标题"

            def effective_passed(self):
                return False

            @property
            def ignored_count(self):
                return 0

        fake_panel = FakePanel()
        fake_panel.platforms = ["gongzhonghao"]

        class FakeAgent:
            def process_message_stream(self, _message):
                yield {
                    "type": "progress",
                    "event": {
                        "step": "evaluate",
                        "title": "质量评估",
                        "status": "running",
                        "detail": "正在评分",
                    },
                }
                yield {
                    "type": "result",
                    "result": {
                        "type": "review",
                        "content": fake_panel.to_markdown(),
                        "panel": fake_panel,
                        "raw_content": None,
                        "platforms": ["gongzhonghao"],
                    },
                }

        updates = list(chat_ui._respond_stream(FakeAgent(), "写一篇文章", [], None))

        self.assertGreaterEqual(len(updates), 2)
        final = updates[-1]
        self.assertEqual(9, len(final))

        review_row_update = final[7]
        self.assertTrue(review_row_update.get("visible", False))

        review_state_value = final[8]
        self.assertIsNotNone(review_state_value)
        self.assertEqual(60, review_state_value.overall)


if __name__ == "__main__":
    unittest.main()
