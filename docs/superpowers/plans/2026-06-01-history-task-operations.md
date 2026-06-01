# History Task Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make uploaded-note memory indexing idempotent and make recent history easier to reuse from the chat UI.

**Architecture:** Add a small SQLite-backed note index registry keyed by content hash, expose it through `MemoryManager.index_note`, and keep UI history as compact Markdown cards inside the existing scroll area. The implementation stays within current Gradio and SQLite patterns.

**Tech Stack:** Python 3.9, SQLite, Gradio, unittest.

---

### Task 1: Uploaded Note Deduplication

**Files:**
- Modify: `agents/store.py`
- Modify: `agents/memory.py`
- Modify: `chat_ui.py`
- Test: `tests/test_memory.py`
- Test: `tests/test_chat_ui.py`

- [x] Add `indexed_notes` table with unique `content_hash`.
- [x] Add store helpers to get/upsert indexed-note records.
- [x] Compute SHA-256 for uploaded note content before vector indexing.
- [x] Skip indexing when the same content hash already exists.
- [x] Return index status so UI can show indexed/skipped state.
- [x] Verify with unit tests.

### Task 2: Compact History Cards

**Files:**
- Modify: `chat_ui.py`
- Test: `tests/test_chat_ui.py`

- [x] Render recent generation history as compact card-like Markdown.
- [x] Include copyable task commands and primary file path.
- [x] Keep the existing limit of 8 and scroll container.
- [x] Verify formatting tests.
