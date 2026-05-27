import unittest


import chat_ui


class ChatUiConfigTest(unittest.TestCase):
    def test_event_outputs_are_registered_components(self):
        demo = chat_ui.create_chat_ui()
        config = demo.get_config_file()
        component_ids = {component["id"] for component in config["components"]}

        missing = []
        for dependency in config["dependencies"]:
            for output_id in dependency["outputs"]:
                if output_id not in component_ids:
                    missing.append((dependency["id"], output_id))

        self.assertEqual([], missing)


class ChatIntentTest(unittest.TestCase):
    def test_tail_instruction_wins_over_body_platform_mentions(self):
        message = """我为什么要做一个 Content Agent

核心问题：为什么需要这个项目？

内容要点：
- 自己有很多技术学习笔记，但转成公众号/抖音/小红书很耗时间。
- 我不想只做一个内容生成工具，而是想做一个能理解素材、改写和生成内容的 Agent。
- 这个项目也是我实践 Agent 写作流程的记录。

根据以上内容生成一篇公众号文章"""

        intent = chat_ui.ChatAgent()._analyze_intent(message)

        self.assertEqual(["gongzhonghao"], intent["platforms"])
        self.assertTrue(intent["has_source_material"])
        self.assertIn("公众号/抖音/小红书", intent["topic"])
        self.assertIn("改写和生成内容", intent["topic"])
        self.assertNotIn("根据以上内容", intent["topic"])

    def test_simple_topic_keeps_original_words(self):
        intent = chat_ui.ChatAgent()._analyze_intent(
            "帮我写一篇给小白介绍 AI Agent 的微信公众号文章"
        )

        self.assertEqual(["gongzhonghao"], intent["platforms"])
        self.assertFalse(intent["has_source_material"])
        self.assertIn("介绍 AI Agent", intent["topic"])
        self.assertNotIn("公众号文章", intent["topic"])

    def test_extracts_writing_requirements_from_user_request(self):
        intent = chat_ui.ChatAgent()._analyze_intent(
            "帮我写一篇给小白介绍 AI Agent 的公众号文章，讲得通俗易懂一点，像程序员给朋友解释，少用术语，不要太营销"
        )

        self.assertEqual("小白", intent["writing_requirements"]["audience"])
        self.assertIn("通俗易懂", intent["writing_requirements"]["tone"])
        self.assertIn("程序员给朋友解释", intent["writing_requirements"]["style_reference"])
        self.assertIn("少用术语", intent["writing_requirements"]["avoid"])
        self.assertIn("不要太营销", intent["writing_requirements"]["avoid"])
        self.assertNotIn("公众号文章", intent["topic"])

    def test_generation_notes_include_writing_requirements(self):
        agent = chat_ui.ChatAgent()
        intent = agent._analyze_intent(
            "帮我写一篇给小白介绍 AI Agent 的公众号文章，讲得通俗易懂一点，像程序员给朋友解释"
        )

        raw_notes = chat_ui._build_generation_notes("AI Agent 入门", "", intent)

        self.assertIn("## 写作要求", raw_notes)
        self.assertIn("目标读者：小白", raw_notes)
        self.assertIn("表达语气：通俗易懂", raw_notes)
        self.assertIn("风格参考：程序员给朋友解释", raw_notes)


if __name__ == "__main__":
    unittest.main()
