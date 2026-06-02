import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


import chat_ui
from agents.writer_agent import WriterAgent


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

    def test_api_info_can_be_generated(self):
        demo = chat_ui.create_chat_ui()

        api_info = demo.get_api_info()

        self.assertIsInstance(api_info, dict)


class ChatProgressTest(unittest.TestCase):
    def test_progress_message_marks_done_running_and_pending_steps(self):
        message = chat_ui._format_progress_message([
            {"step": "analyze", "title": "分析需求", "status": "done", "detail": "已识别目标平台：公众号"},
            {"step": "generate", "title": "生成内容", "status": "running", "detail": "正在生成公众号文章"},
            {"step": "evaluate", "title": "质量评估", "status": "pending", "detail": ""},
        ])

        self.assertIn("✅ 分析需求", message)
        self.assertIn("🔄 生成内容", message)
        self.assertIn("○ 质量评估", message)
        self.assertIn("已识别目标平台：公众号", message)

    def test_respond_stream_yields_progress_before_final_response(self):
        class FakeAgent:
            class Memory:
                def get_preferences(self):
                    return {}

            memory = Memory()

            def process_message_stream(self, _message, **_kwargs):
                yield {
                    "type": "progress",
                    "event": {
                        "step": "analyze",
                        "title": "分析需求",
                        "status": "running",
                        "detail": "正在识别需求",
                    },
                }
                yield {
                    "type": "result",
                    "result": {"type": "text", "content": "生成完成"},
                }

        updates = list(chat_ui._respond_stream(FakeAgent(), "帮我写公众号文章", [], None))

        self.assertGreaterEqual(len(updates), 2)
        first_history = updates[0][1]
        final_history = updates[-1][1]
        self.assertEqual("user", first_history[0]["role"])
        self.assertEqual("assistant", first_history[1]["role"])
        self.assertIn("🔄 分析需求", first_history[1]["content"])
        self.assertEqual("生成完成", final_history[-1]["content"])
        self.assertEqual(10, len(updates[-1]))
        self.assertIn("当前默认", updates[-1][-1])

    def test_respond_stream_skips_upload_index_when_uploaded_only(self):
        with TemporaryDirectory() as tmp_dir:
            note_path = Path(tmp_dir) / "note.md"
            note_path.write_text("# 笔记\n\n内容", encoding="utf-8")

            class FakeAgent:
                class Memory:
                    def __init__(self):
                        self.index_called = False

                    def get_preferences(self):
                        return {}

                    def index_note_result(self, *_args, **_kwargs):
                        self.index_called = True
                        raise AssertionError("index_note_result should not be called")

                def __init__(self):
                    self.memory = self.Memory()

                def process_message_stream(self, _message, **kwargs):
                    self.kwargs = kwargs
                    yield {
                        "type": "result",
                        "result": {"type": "text", "content": "生成完成"},
                    }

            agent = FakeAgent()
            updates = list(chat_ui._respond_stream(
                agent,
                "生成公众号文章",
                [],
                str(note_path),
                "只使用上传笔记",
            ))

        self.assertFalse(agent.memory.index_called)
        self.assertEqual("uploaded_only", agent.kwargs["memory_mode"])
        self.assertTrue(agent.kwargs["has_uploaded_note"])
        self.assertNotIn("记忆索引", updates[-1][1][0]["content"])

    def test_save_generated_markdown_files_returns_platform_files(self):
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            content = type(
                "Content",
                (),
                {
                    "gongzhonghao": "# 公众号文章\n\n完整内容",
                    "xiaohongshu": "小红书完整内容",
                },
            )()

            files = chat_ui._save_generated_markdown_files(
                content,
                ["gongzhonghao", "xiaohongshu"],
                output_dir,
            )

            self.assertTrue((output_dir / "gongzhonghao.md").exists())
            self.assertTrue((output_dir / "xiaohongshu.md").exists())
            self.assertIn(str(output_dir / "gongzhonghao.md"), files)
            self.assertIn(str(output_dir / "xiaohongshu.md"), files)
            self.assertIn(str(output_dir / "xiaohongshu.html"), files)
            self.assertIn(str(output_dir / "xiaohongshu.zip"), files)

    def test_format_memory_refs_lists_sources(self):
        refs = [
            {
                "title": "Content Agent 笔记",
                "source": "notes/agent.md",
                "heading": "RAG 引用",
                "snippet": "这里记录了如何把历史笔记注入生成流程。",
            }
        ]

        message = chat_ui._format_memory_refs(refs)

        self.assertIn("本次参考了 1 条历史笔记", message)
        self.assertIn("Content Agent 笔记", message)
        self.assertIn("RAG 引用", message)
        self.assertIn("notes/agent.md", message)

    def test_format_memory_refs_handles_empty_refs(self):
        message = chat_ui._format_memory_refs([])

        self.assertIn("未使用历史笔记", message)

    def test_format_memory_usage_for_uploaded_only(self):
        message = chat_ui._format_memory_usage([], "只使用上传笔记", has_uploaded_note=True)

        self.assertIn("只使用上传笔记", message)
        self.assertIn("未检索历史笔记", message)

    def test_format_memory_usage_for_disabled_memory(self):
        message = chat_ui._format_memory_usage([], "不使用历史记忆", has_uploaded_note=False)

        self.assertIn("已关闭历史记忆", message)

    def test_normalize_memory_mode_accepts_labels_and_values(self):
        self.assertEqual("uploaded_only", chat_ui._normalize_memory_mode("只使用上传笔记"))
        self.assertEqual("disabled", chat_ui._normalize_memory_mode("disabled"))
        self.assertEqual("auto", chat_ui._normalize_memory_mode("未知"))

    def test_build_gongzhonghao_preference_context_maps_preferences(self):
        context, applied = chat_ui._build_gongzhonghao_preference_context(
            {
                "gzh_target_reader": "普通技术人",
                "gzh_default_style": "通俗科普",
                "preferred_length": "medium",
                "weak_dimensions": ["readability", "originality"],
                "emoji_tendency": "low",
            }
        )

        self.assertIn("公众号写作偏好", context)
        self.assertIn("默认读者：普通技术人", context)
        self.assertIn("默认风格：通俗科普", context)
        self.assertIn("公众号目标 1200-1800 字", context)
        self.assertIn("可读性弱项", context)
        self.assertIn("原创性弱项", context)
        self.assertIn("少用 emoji", context)
        self.assertIn("默认读者：普通技术人", applied)
        self.assertIn("默认风格：通俗科普", applied)

    def test_current_writing_requirement_overrides_default_reader_and_style(self):
        context, applied = chat_ui._build_gongzhonghao_preference_context(
            {
                "gzh_target_reader": "普通技术人",
                "gzh_default_style": "通俗科普",
                "preferred_length": "long",
            },
            {
                "audience": "资深工程师",
                "gongzhonghao_mode": "technical_depth",
            },
        )

        self.assertNotIn("默认读者：普通技术人", context)
        self.assertNotIn("默认风格：通俗科普", context)
        self.assertIn("公众号目标 1800-2500 字", context)
        self.assertNotIn("默认读者：普通技术人", applied)
        self.assertNotIn("默认风格：通俗科普", applied)

    def test_format_user_preferences_groups_gongzhonghao_settings(self):
        message = chat_ui._format_user_preferences(
            {
                "gzh_default_style": "通俗科普",
                "gzh_target_reader": "普通技术人",
                "preferred_length": "medium",
            }
        )

        self.assertIn("公众号写作", message)
        self.assertIn("公众号默认风格", message)
        self.assertIn("通俗科普", message)
        self.assertIn("通用偏好", message)
        self.assertIn("默认长度", message)

    def test_format_preference_summary_html_uses_real_preferences(self):
        html = chat_ui._format_preference_summary_html(
            {
                "gzh_target_reader": "普通技术人",
                "gzh_default_style": "通俗科普",
                "preferred_length": "medium",
                "weak_dimensions": ["readability", "originality"],
            }
        )

        self.assertIn("当前默认", html)
        self.assertIn("默认读者：普通技术人", html)
        self.assertIn("默认风格：通俗科普", html)
        self.assertIn("长度：medium", html)
        self.assertIn("弱项强化：readability、originality", html)

    def test_preference_control_defaults_read_saved_preferences(self):
        defaults = chat_ui._preference_control_defaults(
            {
                "gzh_target_reader": "普通技术人",
                "gzh_default_style": "通俗科普",
                "preferred_length": "medium",
                "weak_dimensions": ["readability"],
            }
        )

        self.assertEqual(("普通技术人", "通俗科普", "medium", ["readability"]), defaults)

    def test_preference_control_defaults_handle_empty_preferences(self):
        defaults = chat_ui._preference_control_defaults({})

        self.assertEqual(("未设置", "未设置", "未设置", []), defaults)

    def test_preference_generation_status_shows_empty_state_for_gongzhonghao(self):
        message = chat_ui._format_preference_generation_status([], ["gongzhonghao"])

        self.assertIn("未设置公众号偏好", message)

    def test_preference_generation_status_is_hidden_for_other_platforms(self):
        message = chat_ui._format_preference_generation_status([], ["xiaohongshu"])

        self.assertEqual("", message)

    def test_parse_preference_value_supports_lists(self):
        value = chat_ui._parse_preference_value("readability，originality")

        self.assertEqual(["readability", "originality"], value)

    def test_pref_command_sets_explicit_preference(self):
        class FakeMemory:
            def __init__(self):
                self.prefs = {}

            def set_preference(self, key, value, source="explicit", confidence=1.0):
                self.prefs[key] = {
                    "value": value,
                    "source": source,
                    "confidence": confidence,
                }

            def get_preferences(self):
                return {key: item["value"] for key, item in self.prefs.items()}

        agent = chat_ui.ChatAgent.__new__(chat_ui.ChatAgent)
        agent.memory = FakeMemory()

        result = chat_ui.ChatAgent._handle_system_command(
            agent,
            "#!pref gzh_default_style 通俗科普",
        )

        self.assertEqual("text", result["type"])
        self.assertEqual("通俗科普", agent.memory.prefs["gzh_default_style"]["value"])
        self.assertEqual("explicit", agent.memory.prefs["gzh_default_style"]["source"])
        self.assertIn("公众号默认风格", result["content"])

    def test_pref_command_without_args_shows_help_and_current_preferences(self):
        class FakeMemory:
            def get_preferences(self):
                return {"gzh_default_style": "通俗科普"}

        agent = chat_ui.ChatAgent.__new__(chat_ui.ChatAgent)
        agent.memory = FakeMemory()

        result = chat_ui.ChatAgent._handle_system_command(agent, "#!pref")

        self.assertEqual("text", result["type"])
        self.assertIn("公众号偏好设置", result["content"])
        self.assertIn("#!pref gzh_default_style 通俗科普", result["content"])
        self.assertIn("公众号默认风格", result["content"])

    def test_memory_context_can_skip_note_search(self):
        class FakeMemory:
            def get_preferences(self):
                return {"preferred_length": "medium"}

            def search_notes(self, *_args, **_kwargs):
                raise AssertionError("search_notes should not be called")

        agent = chat_ui.ChatAgent.__new__(chat_ui.ChatAgent)
        agent.memory = FakeMemory()

        context, refs = chat_ui.ChatAgent._build_memory_context_with_refs(
            agent,
            "AI Agent",
            include_notes=False,
        )

        self.assertIn("用户偏好", context)
        self.assertIn("长度偏好: medium", context)
        self.assertEqual([], refs)

    def test_format_generated_history_lists_generated_files(self):
        items = [
            {
                "session_id": "session_abcdef",
                "task_id": "chat_20260601_150000",
                "platforms": '["gongzhonghao"]',
                "files": '["output/chat/20260601_150000/gongzhonghao.md"]',
                "created_at": "2026-06-01 15:00:00",
                "publish_status": "draft_saved",
                "publish_message": "已保存到草稿箱",
            }
        ]

        message = chat_ui._format_generated_history(items)

        self.assertIn("近期生成历史", message)
        self.assertIn("修改 task chat_YYYYMMDD_HHMMSS", message)
        self.assertIn("history-task-card", message)
        self.assertIn("history-card-command", message)
        self.assertIn("修改 task chat_20260601_150000，把开头写得更抓人", message)
        self.assertIn("已保存草稿", message)
        self.assertIn("公众号", message)
        self.assertIn("chat_20260601_150000", message)
        self.assertIn("gongzhonghao.md", message)

    def test_format_generated_history_handles_empty_items(self):
        message = chat_ui._format_generated_history([])

        self.assertIn("暂无生成历史", message)

    def test_format_generated_history_shows_publish_failure_detail_once(self):
        items = [
            {
                "session_id": "session_abcdef",
                "task_id": "chat_20260601_150000",
                "platforms": '["gongzhonghao"]',
                "files": '["output/chat/20260601_150000/gongzhonghao.md"]',
                "created_at": "2026-06-01 15:00:00",
                "publish_status": "failed",
                "publish_message": "发布失败",
                "publish_details": "错误：无法连接到服务器",
            }
        ]

        message = chat_ui._format_generated_history(items)

        self.assertIn("发布失败", message)
        self.assertIn("错误：无法连接到服务器", message)
        self.assertEqual(1, message.count("发布失败"))

    def test_extract_task_id_from_gongzhonghao_file(self):
        task_id = chat_ui._task_id_from_generated_file("output/chat/20260601_150000/gongzhonghao.md")

        self.assertEqual("chat_20260601_150000", task_id)


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

    def test_revision_request_is_treated_as_generation_intent(self):
        intent = chat_ui.ChatAgent()._analyze_intent(
            "修改 task chat_20260601_152531，把开头写得更抓人"
        )

        self.assertEqual("generate", intent["type"])
        self.assertEqual(["gongzhonghao"], intent["platforms"])

    def test_revision_request_without_generate_keyword_is_generation_intent(self):
        intent = chat_ui.ChatAgent()._analyze_intent("把刚才那篇改得更通俗一点")

        self.assertEqual("generate", intent["type"])
        self.assertEqual(["gongzhonghao"], intent["platforms"])

    def test_generic_optimization_topic_is_not_revision_request(self):
        self.assertFalse(chat_ui._is_revision_request("帮我写一篇关于如何优化 Python 性能的公众号文章"))

    def test_target_platform_marker_overrides_revision_suggestions(self):
        platforms = chat_ui._detect_requested_platforms(
            "【目标平台】gongzhonghao\n\n[小红书] 标题缺少 emoji\n[抖音] 缺少画面提示"
        )

        self.assertEqual(["gongzhonghao"], platforms)

    def test_review_revision_message_keeps_previous_platform_content(self):
        panel = type(
            "Panel",
            (),
            {
                "platforms": ["gongzhonghao"],
                "raw_content": type(
                    "Content",
                    (),
                    {
                        "gongzhonghao": "# 上一版公众号\n\n正文",
                        "xiaohongshu": "小红书内容不应作为目标",
                        "douyin": "抖音内容不应作为目标",
                    },
                )(),
                "revision_count": 1,
                "get_revision_prompt": lambda self: "[小红书] 标题缺少 emoji\n[公众号] 开头不够抓人",
            },
        )()

        message = chat_ui._build_review_revision_message(
            panel,
            [{"role": "user", "content": "根据这篇笔记内容生成公众号文章\n\n📚 记忆索引：已新增 20 个笔记片段。"}],
            max_attempts=2,
        )

        self.assertIn("【目标平台】gongzhonghao", message)
        self.assertIn("【上一版公众号】", message)
        self.assertIn("# 上一版公众号", message)
        self.assertIn("[公众号] 开头不够抓人", message)
        self.assertNotIn("[小红书] 标题缺少 emoji", message)
        self.assertNotIn("记忆索引", message)

    def test_extracts_writing_requirements_from_user_request(self):
        intent = chat_ui.ChatAgent()._analyze_intent(
            "帮我写一篇给小白介绍 AI Agent 的公众号文章，讲得通俗易懂一点，像程序员给朋友解释，少用术语，不要太营销"
        )

        self.assertEqual("小白", intent["writing_requirements"]["audience"])
        self.assertEqual("popular_science", intent["writing_requirements"]["gongzhonghao_mode"])
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
        self.assertIn("公众号模式：通俗科普", raw_notes)
        self.assertIn("表达语气：通俗易懂", raw_notes)
        self.assertIn("风格参考：程序员给朋友解释", raw_notes)

    def test_upload_file_content_is_merged_with_user_instruction(self):
        with TemporaryDirectory() as tmp_dir:
            note_path = Path(tmp_dir) / "mcp.md"
            note_path.write_text("# MCP 学习笔记\n\nMCP 可以连接 AI 和外部工具。", encoding="utf-8")

            merged = chat_ui._merge_uploaded_note_with_message(
                "根据这篇笔记生成一篇公众号文章，面向普通人，通俗易懂",
                str(note_path),
            )

        self.assertIn("# MCP 学习笔记", merged)
        self.assertIn("MCP 可以连接 AI 和外部工具", merged)
        self.assertIn("根据以上内容，根据这篇笔记生成一篇公众号文章", merged)
        self.assertIn("面向普通人", merged)

    def test_revision_request_can_target_specific_task(self):
        with TemporaryDirectory() as tmp_dir:
            old_path = Path(tmp_dir) / "old" / "gongzhonghao.md"
            target_path = Path(tmp_dir) / "target" / "gongzhonghao.md"
            old_path.parent.mkdir(parents=True)
            target_path.parent.mkdir(parents=True)
            old_path.write_text("# 旧文章\n\n旧内容", encoding="utf-8")
            target_path.write_text("# 指定文章\n\n指定内容", encoding="utf-8")

            class FakeMemory:
                def list_generated_history(self, limit=50):
                    return [
                        {
                            "task_id": "chat_20260601_100000",
                            "platforms": '["gongzhonghao"]',
                            "files": json.dumps([str(old_path)]),
                            "session_id": "old_session",
                            "created_at": "2026-06-01 10:00:00",
                        },
                        {
                            "task_id": "chat_20260601_110000",
                            "platforms": '["gongzhonghao"]',
                            "files": json.dumps([str(target_path)]),
                            "session_id": "target_session",
                            "created_at": "2026-06-01 11:00:00",
                        },
                    ]

            notes, meta = chat_ui._build_revision_notes_from_history(
                FakeMemory(),
                "修改 task chat_20260601_110000，把开头写得更抓人",
            )

            self.assertIn("# 指定文章", notes)
            self.assertNotIn("# 旧文章", notes)
            self.assertIn("把开头写得更抓人", notes)
            self.assertEqual("chat_20260601_110000", meta["task_id"])

    def test_revision_request_defaults_to_latest_gongzhonghao_history(self):
        with TemporaryDirectory() as tmp_dir:
            latest_path = Path(tmp_dir) / "latest" / "gongzhonghao.md"
            latest_path.parent.mkdir(parents=True)
            latest_path.write_text("# 最近文章\n\n最近内容", encoding="utf-8")

            class FakeMemory:
                def list_generated_history(self, limit=50):
                    return [
                        {
                            "task_id": "chat_20260601_120000",
                            "platforms": '["gongzhonghao"]',
                            "files": json.dumps([str(latest_path)]),
                            "session_id": "latest_session",
                            "created_at": "2026-06-01 12:00:00",
                        }
                    ]

            notes, meta = chat_ui._build_revision_notes_from_history(
                FakeMemory(),
                "把刚才那篇改得更通俗一点",
            )

            self.assertIn("# 最近文章", notes)
            self.assertIn("把刚才那篇改得更通俗一点", notes)
            self.assertEqual("chat_20260601_120000", meta["task_id"])


class GongzhonghaoPopularPromptTest(unittest.TestCase):
    def _writer_without_model_init(self):
        agent = WriterAgent.__new__(WriterAgent)
        agent._load_style_profile = lambda platform: ""
        return agent

    def test_popular_science_prompt_uses_plain_language_rules(self):
        agent = self._writer_without_model_init()

        prompt = agent._build_draft_prompt(
            "# MCP 协议\n\n## 写作要求\n\n- 目标读者：普通人\n- 公众号模式：通俗科普\n- 表达语气：通俗易懂",
            ["gongzhonghao"],
        )

        self.assertIn("【公众号文章：通俗科普模式】", prompt)
        self.assertIn("不假设读者懂编程", prompt)
        self.assertIn("所有技术术语都必须先用一句人话解释", prompt)
        self.assertIn("除非原始笔记明确要求，不要把代码块作为主体内容", prompt)
        self.assertNotIn("- 包含具体的命令行代码块", prompt)

    def test_default_gongzhonghao_prompt_keeps_professional_rules(self):
        agent = self._writer_without_model_init()

        prompt = agent._build_draft_prompt("# MCP 协议\n\n技术学习笔记", ["gongzhonghao"])

        self.assertIn("【公众号文章】", prompt)
        self.assertIn("- 包含具体的命令行代码块", prompt)
        self.assertNotIn("【公众号文章：通俗科普模式】", prompt)


if __name__ == "__main__":
    unittest.main()
