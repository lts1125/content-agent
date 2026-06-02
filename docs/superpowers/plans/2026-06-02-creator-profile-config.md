# Creator Profile Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add creator account positioning configuration to the existing chat UI and inject it into the creator workflow prompt.

**Architecture:** Reuse the current user preference storage through `MemoryManager.set_preference()` and `get_preferences()`. Add creator profile keys to `chat_ui.py`, render them in the preference summary and user preference view, and pass them into `_creator_workflow_prompt()`.

**Tech Stack:** Python 3.9+, Gradio, unittest.

---

### Task 1: Add Tests For Creator Profile Context

**Files:**
- Modify: `tests/test_chat_ui.py`

- [x] **Step 1: Write failing tests**

Add tests for creator profile prompt injection and UI visibility:

```python
def test_creator_profile_context_formats_account_positioning(self):
    context, applied = chat_ui._build_creator_profile_context({
        "creator_domain": "AI 工具",
        "creator_audience": "职场创作者",
        "creator_persona": "专业但接地气",
        "creator_forbidden_phrases": ["家人们", "割韭菜"],
        "creator_columns": ["工具测评", "实战教程"],
        "creator_benchmark_accounts": "某 AI 工具博主",
    })

    self.assertIn("创作者账号定位", context)
    self.assertIn("账号领域：AI 工具", context)
    self.assertIn("目标受众：职场创作者", context)
    self.assertIn("人设语气：专业但接地气", context)
    self.assertIn("禁用表达：家人们、割韭菜", context)
    self.assertIn("固定栏目：工具测评、实战教程", context)
    self.assertIn("标杆账号：某 AI 工具博主", context)
    self.assertIn("账号领域：AI 工具", applied)

def test_creator_workflow_prompt_includes_creator_profile(self):
    prompt = chat_ui._creator_workflow_prompt({
        "creator_domain": "AI 工具",
        "creator_audience": "职场创作者",
    })

    self.assertIn("创作者账号定位", prompt)
    self.assertIn("账号领域：AI 工具", prompt)
    self.assertIn("目标受众：职场创作者", prompt)

def test_creator_profile_controls_are_visible_in_ui_config(self):
    demo = chat_ui.create_chat_ui()
    labels = json.dumps(demo.get_config_file(), ensure_ascii=False, default=str)

    self.assertIn("创作者账号定位", labels)
    self.assertIn("账号领域", labels)
    self.assertIn("目标受众", labels)
    self.assertIn("人设语气", labels)
```

- [x] **Step 2: Run RED tests**

Run: `/Users/lee/content-agent/.venv/bin/python -m unittest tests.test_chat_ui.ChatProgressTest.test_creator_profile_context_formats_account_positioning tests.test_chat_ui.ChatProgressTest.test_creator_workflow_prompt_includes_creator_profile tests.test_chat_ui.ChatUiConfigTest.test_creator_profile_controls_are_visible_in_ui_config`

Expected: fail because creator profile helpers and UI copy are not implemented.

### Task 2: Implement Creator Profile Prompt Helpers

**Files:**
- Modify: `chat_ui.py`

- [x] **Step 1: Add allowed preference keys and helpers**

Add `creator_domain`, `creator_audience`, `creator_persona`, `creator_forbidden_phrases`, `creator_columns`, and `creator_benchmark_accounts` to allowed keys and formatting labels.

- [x] **Step 2: Add `_build_creator_profile_context()`**

Implement a helper that formats non-empty creator profile preferences into Markdown context and returns applied labels.

- [x] **Step 3: Update `_creator_workflow_prompt()`**

Accept an optional preferences dict and append creator profile context when present.

- [x] **Step 4: Run GREEN tests**

Run the three focused tests from Task 1.

Expected: pass.

### Task 3: Add Creator Profile UI Controls

**Files:**
- Modify: `chat_ui.py`

- [x] **Step 1: Add profile defaults and save handler**

Create a small defaults helper and a save function that writes creator profile fields through `agent.memory.set_preference()`.

- [x] **Step 2: Add UI accordion**

Add a `创作者账号定位` accordion near existing preference controls with inputs for account domain, audience, persona, forbidden phrases, columns, and benchmark accounts.

- [x] **Step 3: Wire creator workflow button to preferences**

Change `quick_creator()` to call `_creator_workflow_prompt(_get_agent_preferences(agent))`.

- [x] **Step 4: Run UI config tests**

Run: `/Users/lee/content-agent/.venv/bin/python -m unittest tests.test_chat_ui.ChatUiConfigTest`

Expected: pass.

### Task 4: Update Plan And Verify

**Files:**
- Modify: `docs/superpowers/plans/2026-06-02-creator-profile-config.md`
- Test: `tests/test_chat_ui.py`

- [x] **Step 1: Run full chat UI tests**

Run: `/Users/lee/content-agent/.venv/bin/python -m unittest tests.test_chat_ui`

Expected: 46+ tests pass.

- [x] **Step 2: Mark this checklist complete**

Update each checkbox in this plan to `[x]` before committing.

- [x] **Step 3: Commit**

Run:

```bash
git add chat_ui.py tests/test_chat_ui.py docs/superpowers/plans/2026-06-02-creator-profile-config.md
git commit -m "feat: add creator profile config"
```
