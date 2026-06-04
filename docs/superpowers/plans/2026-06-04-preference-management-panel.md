# Preference Management Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-version preference management panel so users can view and clear learned or explicit writing preferences without touching the database.

**Architecture:** Add narrow delete helpers to the existing preference store and MemoryManager. Add UI callbacks inside the existing “公众号偏好设置” / “记忆与历史入口” area, limited to safe keys: weak dimensions, default reader, default style, and custom prompt.

**Tech Stack:** Python 3.9, SQLite via `agents/store.py`, Gradio in `chat_ui.py`, unittest.

---

### Task 1: Add Preference Delete Helpers

**Files:**
- Modify: `agents/store.py`
- Modify: `agents/memory.py`
- Test: `tests/test_memory.py`

- [ ] Add `delete_user_preference(user_id: str, pref_key: str) -> bool` in `agents/store.py`.
- [ ] Add `delete_preference(self, key: str) -> bool` in `agents/memory.py`.
- [ ] Extend `tests/test_memory.py::test_user_preferences` to set a preference, delete it, and assert it is gone.
- [ ] Run `PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python tests/test_memory.py`.

### Task 2: Add UI Formatting And Callback Helpers

**Files:**
- Modify: `chat_ui.py`
- Test: `tests/test_chat_ui.py`

- [ ] Add `_clear_managed_preferences(memory, keys: list[str]) -> tuple[str, dict]`.
- [ ] Add tests using a fake memory object to confirm clearing known keys removes them and returns refreshed preferences.
- [ ] Run `PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python -m unittest tests/test_chat_ui.py`.

### Task 3: Wire Preference Management UI

**Files:**
- Modify: `chat_ui.py`
- Test: `tests/test_chat_ui.py`

- [ ] Add a small “偏好管理” accordion near existing preference controls.
- [ ] Add buttons:
  - “刷新偏好”
  - “清空弱项学习”
  - “清空公众号默认风格”
  - “清空公众号默认读者”
  - “清空自定义要求”
- [ ] Wire callbacks to refresh `preference_summary`, `pref_detail`, and relevant input controls.
- [ ] Add UI config test assertions for the new labels.

### Task 4: Verify And Commit

**Files:**
- `agents/store.py`
- `agents/memory.py`
- `chat_ui.py`
- `tests/test_memory.py`
- `tests/test_chat_ui.py`
- `docs/feature/design_agent_workbench_next.md`
- `docs/superpowers/plans/2026-06-04-preference-management-panel.md`

- [ ] Run:
  - `PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python -m py_compile chat_ui.py agents/store.py agents/memory.py`
  - `PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python -m unittest tests/test_chat_ui.py`
  - `PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python -m unittest tests/test_review_panel.py`
  - `PYTHONPYCACHEPREFIX=/private/tmp/content-agent-pycache /Users/lee/content-agent/.venv/bin/python tests/test_memory.py`
- [ ] Commit only relevant files with `git commit -m "Add preference management controls"`.
