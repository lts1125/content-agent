import unittest
from unittest.mock import patch

from agents.collaboration.context import AgentContext
from agents.planning.planner import AutonomousPlanner, _extract_topic
from agents.schemas import WriterOutput
from agents.tools import ToolResult


class PlannerGenerationContextTest(unittest.TestCase):
    def test_extract_topic_prefers_markdown_heading(self):
        raw_notes = "# 给小白介绍 AI Agent\n\n## 搜索资料\n\n[Google] unrelated"

        self.assertEqual("给小白介绍 AI Agent", _extract_topic(raw_notes))

    def test_extract_topic_skips_revision_wrapper_marker(self):
        raw_notes = "【上一版公众号文章】\n# 你发的每一条内容，可能都发错了时间\n\n【修改要求】\n把开头写得更抓人"

        self.assertEqual("你发的每一条内容，可能都发错了时间", _extract_topic(raw_notes))

    def test_search_uses_topic_not_entire_raw_notes(self):
        planner = AutonomousPlanner()
        raw_notes = "# 给小白介绍 AI Agent\n\n## 搜索资料\n\n[Google] unrelated"
        context = AgentContext(topic=_extract_topic(raw_notes), raw_notes=raw_notes)

        with patch("agents.planning.planner.execute_tool") as execute_tool_mock:
            execute_tool_mock.return_value = ToolResult(success=True, data="search result")

            planner._execute_search(context, raw_notes)

        execute_tool_mock.assert_called_once_with("search", query="给小白介绍 AI Agent")

    def test_generate_keeps_raw_notes_when_research_exists(self):
        planner = AutonomousPlanner()
        raw_notes = "# 给小白介绍 AI Agent\n\n## 主题\n\nAI Agent 入门"
        context = AgentContext(
            topic="给小白介绍 AI Agent",
            raw_notes=raw_notes,
            research_report="[Google] unrelated search result",
        )

        with patch("agents.planning.planner.execute_tool") as execute_tool_mock:
            execute_tool_mock.return_value = ToolResult(
                success=True,
                data=WriterOutput(gongzhonghao="draft"),
            )

            planner._execute_generate(context, raw_notes, ["gongzhonghao"])

        sent_notes = execute_tool_mock.call_args.kwargs["raw_notes"]
        self.assertIn("# 给小白介绍 AI Agent", sent_notes)
        self.assertIn("## 补充研究资料", sent_notes)
        self.assertIn("[Google] unrelated search result", sent_notes)


if __name__ == "__main__":
    unittest.main()
