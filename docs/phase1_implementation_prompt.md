# P1 Implementation Task

You are implementing Phase 1 of the content-agent autonomous agent feature. Read the design doc at `docs/P1_agent_intelligence_design.md` first, then implement everything described below.

## Context

- P0 is already done: `automation/` has `VaultWatcher`, `AgentController`, `PublishQueue`, `StyleProfile`.
- DB has tables: `tasks`, `drafts`, `edit_history`, `publish_queue`, `style_samples`, `schema_version`.
- Project uses PydanticAI with multi-provider support.

## Your Task

Implement 3 new modules + DB extensions + CLI extensions. Do NOT change existing P0 behavior.

---

### 1. automation/feedback_agent.py

Implement `FeedbackAgent` class:

- **Data models** (dataclasses):
  ```python
  ContentMetrics(id, queue_item_id, platform, reads, likes, shares, comments, collects, import_date, publish_date)
  StyleProfileRecord(id, platform, preferred_tone, high_performing_patterns: List[str], avg_score, sample_count, created_at, updated_at)
  ```

- **DB table** `content_metrics`:
  ```sql
  id TEXT PRIMARY KEY, queue_item_id TEXT, platform TEXT, reads/likes/shares/comments/collects INTEGER DEFAULT 0, import_date TEXT, publish_date TEXT
  ```
  Add indexes on queue_item_id and platform.

- **DB table** `style_profiles`:
  ```sql
  id TEXT PRIMARY KEY, platform TEXT NOT NULL UNIQUE, preferred_tone TEXT, high_performing_patterns TEXT (JSON list), avg_score INTEGER, sample_count INTEGER, created_at TEXT, updated_at TEXT
  ```

- **Methods**:
  - `import_metrics(self, file_path: Path) -> dict` — supports CSV and JSON formats (see design doc). Parse file, insert into content_metrics, return {"imported": N, "errors": [...]}.
  - `analyze(self, platform: str | None = None) -> StyleProfileRecord` — if platform is None, analyze all platforms.
    1. Load all published queue items for the platform with their content_metrics.
    2. Calculate composite_score = reads + likes*2 + shares*3 + comments*2 + collects*2.
    3. Sort by score, take top 30% as high-performing, bottom 30% as low-performing.
    4. Build LLM prompt comparing high vs low performers.
    5. LLM outputs: preferred_tone (str) + high_performing_patterns (List[str]).
    6. Upsert into style_profiles table.
  - `get_profile(self, platform: str) -> StyleProfileRecord | None`

- **LLM prompt** (use existing ContentAgent model from content_agent/agent_core.py, or accept model param):
  ```
  You are a content analyst. Analyze the difference between high-performing and low-performing content.

  [High-performing content] (score > X):
  {content_1}
  ...

  [Low-performing content] (score < Y):
  {content_2}
  ...

  Output JSON:
  {"preferred_tone": "description of tone", "high_performing_patterns": ["pattern1", "pattern2"]}
  ```

---

### 2. automation/topic_picker.py

Implement `TopicPicker` class:

- Reuse `TopicSuggestion` from `agents/schemas.py` (already defined).
- **DB table** `topic_suggestions`:
  ```sql
  id TEXT PRIMARY KEY, title TEXT, note_file TEXT, trending_topic TEXT, platforms TEXT (JSON list), reason TEXT, priority INTEGER DEFAULT 3, status TEXT DEFAULT 'pending', created_at TEXT
  ```

- **Methods**:
  - `scan_vault(self, vault_path: str) -> List[dict]` — scan all .md files, return list of {"file": str, "title": str, "preview": str (first 1000 chars)}.
  - `pick_topics(self, vault_path: str, keywords: str | None = None, limit: int = 5) -> List[TopicSuggestion]`
    1. Call scan_vault.
    2. Call ResearchAgent to search current trending topics. If keywords provided, search those; otherwise use env `AGENT_TOPIC_KEYWORDS` or default "AI Agent, LLM, 大模型".
    3. Build LLM prompt with notes list + trending topics.
    4. LLM outputs List[TopicSuggestion].
    5. Save each to topic_suggestions table.
    6. Return suggestions.
  - `list_suggestions(self, status: str | None = None) -> List[TopicSuggestion]`
  - `accept(self, suggestion_id: str) -> bool` — update status to "accepted".
  - `reject(self, suggestion_id: str) -> bool` — update status to "rejected".

- **LLM prompt**:
  ```
  You are a content strategist. Based on the notes and trending topics below, generate topic suggestions.

  [Notes]
  1. file.md - preview...

  [Trending Topics]
  - topic1
  - topic2

  Output JSON array, each item: {"title", "note_file", "trending_topic", "platforms": [...], "reason", "priority": 1-5}
  ```

---

### 3. automation/ab_test_framework.py

Implement `ABTestFramework` class:

- **Data model** `ABTestVariant` (dataclass):
  ```python
  id, task_id, platform, variant_type (Literal["title", "hook", "style"]), variant_content, status ("pending"/"published"/"result_imported"), metrics_id, created_at
  ```

- **DB table** `ab_test_variants`:
  ```sql
  id TEXT PRIMARY KEY, task_id TEXT, platform TEXT, variant_type TEXT, variant_content TEXT, status TEXT DEFAULT 'pending', metrics_id TEXT, created_at TEXT
  ```

- **Methods**:
  - `generate_variants(self, queue_item_id: str, variant_types: List[str], count: int = 3) -> List[ABTestVariant]`
    1. Load the queue item content from publish_queue.
    2. For each variant_type, generate `count` variants using LLM.
    3. Save to ab_test_variants table.
    4. Return variants.
  - `list_variants(self, task_id: str) -> List[ABTestVariant]`
  - `record_result(self, variant_id: str, metrics_id: str) -> bool`
  - `analyze_results(self, task_id: str) -> dict` — load all variants for task + their metrics, return {"best_variant_id": str, "best_score": int, "all_scores": {...}}

- **LLM prompts**:
  - Title variant: "Generate {count} different titles for this content. Each title should be catchy and suitable for {platform}. Output JSON: {"titles": [...]}"
  - Hook variant: "Generate {count} different opening hooks (first 2 sentences) for this content. Output JSON: {"hooks": [...]}"

---

### 4. Extend agents/store.py

- Bump `_SCHEMA_VERSION` from 2 to 3.
- Add `init_content_metrics_table()`, `init_style_profiles_table()`, `init_topic_suggestions_table()`, `init_ab_test_variants_table()`.
- Call them from `init_db()`.

---

### 5. Extend main.py CLI

Add new arguments (non-mutually-exclusive, can combine with existing args):

```python
parser.add_argument("--import-metrics", metavar="PATH", help="Import platform metrics CSV/JSON")
parser.add_argument("--analyze-feedback", action="store_true", help="Analyze feedback and update style profiles")
parser.add_argument("--show-profile", action="store_true", help="Show current style profile")
parser.add_argument("--platform", help="Filter by platform for --analyze-feedback / --show-profile")
parser.add_argument("--pick-topics", action="store_true", help="Pick topics from vault")
parser.add_argument("--topic-keywords", help="Keywords for topic research (default: env AGENT_TOPIC_KEYWORDS)")
parser.add_argument("--topics", action="store_true", help="List topic suggestions")
parser.add_argument("--topic-status", default="pending", help="Filter topic suggestions by status")
parser.add_argument("--accept-topic", metavar="ID", help="Accept a topic suggestion")
parser.add_argument("--reject-topic", metavar="ID", help="Reject a topic suggestion")
parser.add_argument("--generate-ab", metavar="TYPES", help="Generate A/B variants, e.g. title,hook")
parser.add_argument("--ab-count", type=int, default=3, help="Number of variants per type")
parser.add_argument("--ab-queue-id", help="Queue item ID for A/B test")
parser.add_argument("--ab-results", metavar="TASK_ID", help="Show A/B test results for a task")
```

Implement `_handle_p1_mode(args)` or extend `_handle_agent_mode(args)` to handle these.

Key behaviors:
- `--import-metrics`: parse file, call FeedbackAgent.import_metrics(), print summary.
- `--analyze-feedback`: call FeedbackAgent.analyze(platform=args.platform), print updated profile.
- `--show-profile`: load and print style_profiles for the platform.
- `--pick-topics`: call TopicPicker.pick_topics(), print suggestions.
- `--topics`: list topic suggestions (filtered by status).
- `--accept-topic` / `--reject-topic`: update topic status.
- `--generate-ab`: parse types (comma-separated), call ABTestFramework.generate_variants(), print variants.
- `--ab-results`: call ABTestFramework.analyze_results(), print winner.

---

### 6. Update automation/__init__.py

Export new classes: `FeedbackAgent`, `TopicPicker`, `ABTestFramework`, `ContentMetrics`, `StyleProfileRecord`, `ABTestVariant`.

---

## Constraints

- Do NOT modify existing P0 modules (vault_watcher.py, agent_controller.py, publish_queue.py, style_profile.py).
- Do NOT break existing CLI behavior (generate mode stays default).
- Use type hints throughout.
- Reuse existing DB connection pattern from agents/store.py.
- Handle exceptions gracefully.
- After implementing, run:
  ```bash
  python -c "from automation import FeedbackAgent, TopicPicker, ABTestFramework; print('OK')"
  ```
- Test DB initialization: `python -c "from agents.store import init_db; init_db(); print('DB OK')"`

## Design doc reference

Full design with execution sequence diagrams is in `docs/P1_agent_intelligence_design.md`.
