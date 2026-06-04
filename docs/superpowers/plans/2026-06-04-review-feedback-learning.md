# Review Feedback Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build conservative learning from review-panel decisions so repeated accepted fixes update `weak_dimensions`, while ignored and forced decisions remain visible but do not pollute writing preferences.

**Architecture:** Reuse existing `review_panels` and `review_items` tables. Add deterministic aggregation helpers in `agents/store.py`, then surface a short summary and trigger learning from `chat_ui.py` review actions.

**Tech Stack:** Python 3.9, SQLite via `agents/store.py`, Gradio UI in `chat_ui.py`, unittest.

---

### Task 1: Store-Level Feedback Aggregation

**Files:**
- Modify: `agents/store.py`
- Test: `tests/test_review_panel.py`

- [ ] **Step 1: Write failing tests**

Add tests that save review panels with `user_decision` and ignored items, then assert:

```python
feedback = store_mod.summarize_review_feedback(limit=20)
self.assertIn("公众号", feedback["accepted_dimensions"])
self.assertIn("代码示例", feedback["ignored_dimensions"])
self.assertEqual([], feedback["force_publish_dimensions"])
```

Also add a test that three recent `revise` decisions for the same dimension produce:

```python
self.assertEqual(["公众号"], store_mod.infer_weak_dimensions_from_review_feedback(limit=5, min_count=3))
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python -m unittest tests/test_review_panel.py
```

Expected: fails because `summarize_review_feedback` and `infer_weak_dimensions_from_review_feedback` are not defined.

- [ ] **Step 3: Implement store helpers**

Add:

```python
def list_review_feedback(limit: int = 20) -> List[dict]:
    """Return recent review panels with their items for feedback learning."""
```

Add:

```python
def summarize_review_feedback(limit: int = 20) -> dict:
    """Aggregate accepted revise dimensions, ignored dimensions, and force-publish count."""
```

Add:

```python
def infer_weak_dimensions_from_review_feedback(limit: int = 5, min_count: int = 3) -> List[str]:
    """Infer conservative weak dimensions from repeated revise decisions."""
```

Use only failed, non-ignored items for `revise`; only ignored items for `ignore`; do not infer weak dimensions from `force_publish`.

- [ ] **Step 4: Run tests**

Run the same `tests/test_review_panel.py`; expected PASS.

### Task 2: Preference Learning Adapter

**Files:**
- Modify: `chat_ui.py`
- Test: `tests/test_chat_ui.py`

- [ ] **Step 1: Write failing tests**

Add tests for:

```python
summary = chat_ui._format_review_feedback_summary({
    "accepted_dimensions": ["公众号"],
    "ignored_dimensions": ["代码示例"],
    "force_publish_count": 1,
})
self.assertIn("最近常采纳修改", summary)
self.assertIn("公众号", summary)
self.assertIn("最近常忽略", summary)
```

Add a fake memory test:

```python
changed = chat_ui._learn_review_feedback_preferences(memory, ["readability"])
self.assertTrue(changed)
self.assertIn("readability", memory.values["weak_dimensions"])
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python -m unittest tests/test_chat_ui.py
```

Expected: fails because the helper functions are not defined.

- [ ] **Step 3: Implement chat UI helpers**

Add:

```python
def _format_review_feedback_summary(summary: dict) -> str:
    """Format conservative review feedback for the preference summary card."""
```

Add:

```python
def _learn_review_feedback_preferences(memory, weak_dimensions: list[str]) -> bool:
    """Merge inferred weak dimensions into memory preference without removing explicit values."""
```

Add a mapping from Chinese review dimensions to current prompt keys:

```python
{
    "公众号": "readability",
    "可读性": "readability",
    "原创性": "originality",
    "实用性": "practicality",
}
```

- [ ] **Step 4: Run tests**

Run `tests/test_chat_ui.py`; expected PASS.

### Task 3: Wire UI Review Decisions

**Files:**
- Modify: `chat_ui.py`
- Test: `tests/test_chat_ui.py`

- [ ] **Step 1: Persist review decisions**

After `ReviewManager.apply_user_decision(panel, decision)`, call `ReviewManager.save_panel(panel, task_id)` when the panel has a task id or use an attached `panel.task_id` fallback if available.

- [ ] **Step 2: Trigger conservative preference learning**

After saving a review decision, call store inference:

```python
from agents.store import infer_weak_dimensions_from_review_feedback, summarize_review_feedback
weak = infer_weak_dimensions_from_review_feedback(limit=5, min_count=3)
_learn_review_feedback_preferences(agent.memory, weak)
```

Then refresh `preference_summary` with `_format_preference_summary_html(_get_agent_preferences(agent))`.

- [ ] **Step 3: Display review feedback summary**

Include `_format_review_feedback_summary(summarize_review_feedback(limit=20))` inside `_format_preference_summary_html`.

- [ ] **Step 4: Run verification**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python -m py_compile chat_ui.py agents/store.py agents/memory.py
PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python -m unittest tests/test_review_panel.py
PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python -m unittest tests/test_chat_ui.py
PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python tests/test_memory.py
```

Expected: all pass.

### Task 4: Commit

**Files:**
- `agents/store.py`
- `chat_ui.py`
- `tests/test_review_panel.py`
- `tests/test_chat_ui.py`
- `docs/superpowers/plans/2026-06-04-review-feedback-learning.md`

- [ ] **Step 1: Review diff**

Run:

```bash
git diff --stat -- agents/store.py chat_ui.py tests/test_review_panel.py tests/test_chat_ui.py docs/superpowers/plans/2026-06-04-review-feedback-learning.md
git diff --check -- agents/store.py chat_ui.py tests/test_review_panel.py tests/test_chat_ui.py docs/superpowers/plans/2026-06-04-review-feedback-learning.md
```

- [ ] **Step 2: Commit only relevant files**

Run:

```bash
git add agents/store.py chat_ui.py tests/test_review_panel.py tests/test_chat_ui.py docs/superpowers/plans/2026-06-04-review-feedback-learning.md
git commit -m "Add review feedback learning"
```
