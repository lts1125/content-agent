# Creator Workflow Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record the creator/self-media productization priorities and add a clear first workflow entry to the existing chat UI.

**Architecture:** Keep the existing `chat_ui.py` as the recommended interface. Add a reusable prompt builder and a UI shortcut that fills/runs a creator content repurposing workflow across WeChat, Xiaohongshu, and Douyin.

**Tech Stack:** Python 3.9+, Gradio, unittest.

---

### Task 1: Record Productization Roadmap

**Files:**
- Create: `docs/creator_self_media_roadmap.md`

- [x] **Step 1: Write the roadmap document**

Create `docs/creator_self_media_roadmap.md` with the ranked priorities:

```markdown
# 创作者自媒体副业产品化路线图

## 定位

面向创作者和自媒体账号的 AI 内容工作流自动化工具。核心价值不是单次 AI 改写，而是把一份原始素材稳定复用成多平台可发布资产。

## 优先级

1. 创作者工作流首页 / 主流程
2. 账号定位配置
3. 一键内容包导出
4. 样板案例库
5. 审核、反馈学习和风格记忆

## 第一阶段交付

先在现有聊天式 UI 中加入清晰的“创作者内容复用工作流”入口，让用户可以上传文章、课程笔记或想法，并一键生成公众号、小红书、抖音脚本和配图素材。
```

- [x] **Step 2: Review for incomplete markers**

Run: `rg "PLACEHOLDER|INCOMPLETE" docs/creator_self_media_roadmap.md`

Expected: no matches.

### Task 2: Add Creator Workflow Prompt Tests

**Files:**
- Modify: `tests/test_chat_ui.py`

- [x] **Step 1: Write failing tests**

Add tests that require `chat_ui._creator_workflow_prompt()` and visible UI copy:

```python
    def test_creator_workflow_prompt_requests_multi_platform_delivery(self):
        prompt = chat_ui._creator_workflow_prompt()

        self.assertIn("创作者内容复用工作流", prompt)
        self.assertIn("公众号", prompt)
        self.assertIn("小红书", prompt)
        self.assertIn("抖音", prompt)
        self.assertIn("标题库", prompt)
        self.assertIn("发布日历", prompt)

    def test_creator_workflow_entry_is_visible_in_ui_config(self):
        demo = chat_ui.create_chat_ui()
        labels = json.dumps(demo.get_config_file(), ensure_ascii=False)

        self.assertIn("创作者工作流", labels)
        self.assertIn("一键内容复用", labels)
```

- [x] **Step 2: Run tests to verify RED**

Run: `python -m unittest tests.test_chat_ui.ChatProgressTest.test_creator_workflow_prompt_requests_multi_platform_delivery tests.test_chat_ui.ChatUiConfigTest.test_creator_workflow_entry_is_visible_in_ui_config`

Expected: fail because `_creator_workflow_prompt` does not exist and UI copy is missing.

### Task 3: Implement Creator Workflow Entry

**Files:**
- Modify: `chat_ui.py`

- [x] **Step 1: Add prompt builder**

Add `_creator_workflow_prompt()` near UI helper functions:

```python
def _creator_workflow_prompt() -> str:
    return (
        "创作者内容复用工作流：请根据我提供的素材，生成一套可直接交付的多平台内容资产。\n\n"
        "【目标平台】gongzhonghao,xiaohongshu,douyin\n\n"
        "请输出：\n"
        "1. 公众号长文：结构完整，适合知识型创作者发布。\n"
        "2. 小红书笔记：标题抓人、要点清晰，适合图文卡片。\n"
        "3. 抖音口播脚本：开头有钩子，短句表达，包含画面提示。\n"
        "4. 标题库：给每个平台至少 3 个备选标题。\n"
        "5. 发布日历：给出未来 7 天的内容拆分建议。\n\n"
        "如果我上传了笔记，请优先忠实复用上传素材；如果没有上传，请先围绕输入主题生成。"
    )
```

- [x] **Step 2: Add UI button and copy**

Change the header title/subtitle and input panel copy to mention creator content reuse. Add a button labeled `创作者工作流` and wire it to `_respond_stream(agent, _creator_workflow_prompt(), [], None)`.

- [x] **Step 3: Run tests to verify GREEN**

Run: `python -m unittest tests.test_chat_ui.ChatProgressTest.test_creator_workflow_prompt_requests_multi_platform_delivery tests.test_chat_ui.ChatUiConfigTest.test_creator_workflow_entry_is_visible_in_ui_config`

Expected: pass.

### Task 4: Run Focused Verification

**Files:**
- Test: `tests/test_chat_ui.py`

- [x] **Step 1: Run chat UI tests**

Run: `python -m unittest tests.test_chat_ui`

Expected: pass.

- [x] **Step 2: Check roadmap file**

Run: `rg "创作者工作流首页|账号定位配置|一键内容包导出|样板案例库|反馈学习" docs/creator_self_media_roadmap.md`

Expected: all five priorities are present.
