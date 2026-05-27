# P0 Implementation Task

You are implementing Phase 0 of the content-agent autonomous agent feature. The design doc is at `docs/P0_agent_implementation_design.md`. Read it first, then implement everything described below.

## Context

- This is a Python project using pydantic-ai for LLM agent orchestration.
- Project root: current directory.
- Key existing modules:
  - `agents/orchestrator.py` — Orchestrator that runs WriterAgent → EditorAgent loop
  - `agents/schemas.py` — TaskInput, TaskState, WriterOutput, etc.
  - `agents/store.py` — SQLite persistence (tasks, drafts, edit_history tables)
  - `main.py` — CLI entry point with argparse
  - `content_agent/scheduler.py` — Time-based scheduled tasks (separate concern)
- The project already has `watchdog` installed (used elsewhere).

## Your Task

Implement the following new modules and integrations. Do NOT change existing behavior of `main.py` unless adding new CLI arguments.

### 1. Create `automation/` package

Create these 4 files:

#### `automation/__init__.py`
Export: `VaultWatcher`, `AgentController`, `PublishQueue`, `StyleProfile`, `QueueItem`, `StyleSample`.

#### `automation/vault_watcher.py`
Implement `VaultWatcher` class:
- `__init__(self, vault_path: str, inbox_dir: str = "inbox", on_new_note: Callable[[Path], None] | None = None)`
- Reads `VAULT_PATH` env var; falls back to `~/.content_agent/vault` if not set.
- Watches `$vault_path/$inbox_dir/` for `.md` and `.txt` files using `watchdog.observers.Observer` + `watchdog.events.FileSystemEventHandler`.
- `start()` — blocking; `start_background()` — returns `threading.Thread`; `stop()`.
- On file creation (`on_created`), call `on_new_note(Path(event.src_path))`.
- On startup, scan existing files in inbox and process them (batch).
- After processing, move file to `processed/` or `failed/` subdir under vault_path.
- Deduplication: maintain an in-memory set of `(filename, mtime)` processed in last 10 minutes. Do NOT re-trigger on files already in `processed/`.
- Auto-create `inbox/`, `processed/`, `failed/` if missing.

#### `automation/agent_controller.py`
Implement `AgentController` class:
- `__init__(self, orch: Orchestrator | None = None)`
- `on_new_note(self, note_path: Path) -> dict`:
  1. Read file content (utf-8)
  2. Build `TaskInput` with defaults from env:
     - `platforms` from `AGENT_DEFAULT_PLATFORMS` (default: xiaohongshu,gongzhonghao,douyin)
     - `enable_research` from `AGENT_AUTO_RESEARCH` (default: false)
     - `skip_edit` from `AGENT_SKIP_EDIT` (default: true for P0 fast mode)
     - `style` from `AGENT_DEFAULT_STYLE` (default: "default")
     - `concurrent_mode` = false
  3. Call `orch.run(task_input)` to get `TaskState`
  4. If success: for each platform in enabled_platforms, insert into PublishQueue with status="pending"
  5. Record style samples via `StyleProfile.record_sample()` for each platform
  6. Move file to `vault/processed/`
  7. Return `{"success": True, "task_id": ..., "queued": N}`
- If any step fails: catch exception, log error, move file to `vault/failed/`, return `{"success": False, "error": str(e)}`
- `process_inbox(self, inbox_dir: Path) -> list[dict]` — batch process all existing files.

#### `automation/publish_queue.py`
Implement `PublishQueue` static methods:
- Data model `QueueItem` (dataclass):
  ```python
  id: str; task_id: str; platform: str; title: str; content: str; tags: str
  status: Literal["pending","approved","published","rejected"]
  note_source: str; created_at: str; reviewed_at: str | None; published_at: str | None; publish_result: str | None
  ```
- CRUD methods: `add()`, `list()`, `get()`, `approve()`, `reject()`, `mark_published()`, `delete()`
- Store in SQLite using `agents/store.py`'s `_get_conn()` pattern (reuse the same DB at `data/content_agent.db`).
- Table schema:
  ```sql
  CREATE TABLE IF NOT EXISTS publish_queue (
      id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      platform TEXT NOT NULL,
      title TEXT,
      content TEXT,
      tags TEXT,
      status TEXT NOT NULL DEFAULT 'pending',
      note_source TEXT,
      created_at TEXT,
      reviewed_at TEXT,
      published_at TEXT,
      publish_result TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_queue_status ON publish_queue(status);
  CREATE INDEX IF NOT EXISTS idx_queue_created ON publish_queue(created_at);
  ```
- `title` extraction: take first non-empty line from content, strip `#` and whitespace, truncate to 100 chars.

#### `automation/style_profile.py`
Implement `StyleProfile` static methods:
- Data model `StyleSample` (dataclass):
  ```python
  id: str; task_id: str; note_source: str; note_preview: str; platform: str
  content_preview: str; content_length: int; created_at: str
  ```
- `record_sample(task_id, note_source, note_text, platform, content)`:
  - `note_preview` = first 500 chars of note_text
  - `content_preview` = first 500 chars of content
  - `content_length` = len(content)
- `list_samples(limit=100)` → list[StyleSample]
- `get_profile_hint(platform: str) -> str` → return empty string for P0 (placeholder for P1)
- Table schema:
  ```sql
  CREATE TABLE IF NOT EXISTS style_samples (
      id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      note_source TEXT,
      note_preview TEXT,
      platform TEXT NOT NULL,
      content_preview TEXT,
      content_length INTEGER,
      created_at TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_samples_task ON style_samples(task_id);
  ```

### 2. Extend `agents/store.py`

Add `init_publish_queue_table()` and `init_style_samples_table()` functions, and call them from `init_db()`.
Also bump a `_SCHEMA_VERSION = 2` constant and add schema_version tracking table for future migrations.

### 3. Extend `main.py` CLI

Add new mutually exclusive argument group for agent mode:
```python
agent_group = parser.add_mutually_exclusive_group()
agent_group.add_argument("--watch", action="store_true", help="启动 Vault 监听模式")
agent_group.add_argument("--process-inbox", action="store_true", help="批量处理 inbox 后退出")
parser.add_argument("--queue", action="store_true", help="查看待发队列")
parser.add_argument("--status", default="pending", help="队列筛选状态")
parser.add_argument("--approve", metavar="ID", help="审核通过指定队列项")
parser.add_argument("--reject", metavar="ID", help="拒绝指定队列项")
parser.add_argument("--publish-next", action="store_true", help="手动发布下一个 approved 项")
```

Implement handlers:
- `--watch`: init DB, create VaultWatcher + AgentController, start blocking watch
- `--process-inbox`: init DB, process all files in inbox once, print summary, exit
- `--queue`: print table of queue items (status-filtered)
- `--approve ID`: update status to approved
- `--reject ID`: update status to rejected
- `--publish-next`: find first approved item, call appropriate publisher (P0: just print "would publish to {platform}" and mark as published)

### 4. Create `.env.example` entries (commented)

Add to `.env.example`:
```bash
# Agent Mode Config
# VAULT_PATH=/Users/lee/content-agent/notes
# VAULT_INBOX=inbox
# AGENT_DEFAULT_PLATFORMS=xiaohongshu,gongzhonghao,douyin
# AGENT_AUTO_RESEARCH=false
# AGENT_SKIP_EDIT=true
# AGENT_DEFAULT_STYLE=default
```

## Constraints

- Do NOT modify existing `Orchestrator`, `WriterAgent`, `EditorAgent` logic.
- Do NOT break existing `main.py` behavior (generate mode stays default).
- Use type hints throughout.
- Reuse existing patterns from `agents/store.py` for DB operations.
- Handle exceptions gracefully; never crash the watcher on a single bad file.
- After implementing, run `python -c "from automation import VaultWatcher, AgentController, PublishQueue, StyleProfile; print('OK')"` to verify imports.
- Run `python main.py --process-inbox` (should work even if inbox empty — print "no files to process" and exit 0).

## Design doc reference

Full design with execution sequence diagram is in `docs/P0_agent_implementation_design.md`.
