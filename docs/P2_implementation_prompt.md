# P2 Implementation Task

You are implementing Phase 2 of the content-agent autonomous agent feature. Read the design doc at `docs/P2_auto_publish_design.md` first, then implement everything described below.

## Context

- P0 is done: Vault Watcher, Publish Queue, Agent Controller
- P1 is done: FeedbackAgent, TopicPicker, ABTestFramework
- Existing publisher: `content_agent/publisher.py` has `publish_wechat_draft()` via kuaifa CLI
- Existing queue: `automation/publish_queue.py` has pending/approved/published/rejected states
- Risk level: HIGH — this touches real account publishing. Audit gate must be enforced.

## Your Task

Implement 4 new modules + DB migration + CLI extensions. Do NOT change existing P0/P1 behavior.

---

### 1. automation/gate.py

Implement `PublishGate` class:

- **Data model** `GateDecision`:
  ```python
  @dataclass
  class GateDecision:
      item_id: str
      decision: Literal["approve", "reject", "skip"]
      reviewer: str = "cli_user"
      decided_at: str = ""
      reason: str = ""
  ```

- **Methods**:
  - `__init__(self, mode: Literal["interactive", "scheduled", "disabled"] = "interactive")`
  - `review(self, item: QueueItem) -> GateDecision`
    - `interactive`: print content summary, prompt user `y/enter=approve, n=reject, s=skip`, return GateDecision
    - `scheduled`: if item.status == "approved", return approve; else return skip
    - `disabled`: print WARNING, return approve
  - `batch_review(self, items: List[QueueItem]) -> List[GateDecision]` — for `--publish-all`

---

### 2. automation/executor.py

Implement `PublishExecutor` class:

- **Constructor**: `__init__(self, gate: PublishGate | None = None, max_retries: int = 3)`

- **Methods**:
  - `execute_one(self, item_id: str) -> dict`
    1. Load item from PublishQueue
    2. Run gate.review(item)
    3. If rejected → PublishQueue.reject(item_id), return
    4. If skipped → return
    5. Dispatch by platform:
       - `gongzhonghao` → `_publish_wechat(item)`
       - `xiaohongshu` → `_publish_xiaohongshu(item)`
       - `douyin` → return `{"success": False, "error": "抖音自动发布暂未实现", "retryable": False}`
    6. On success → `PublishQueue.mark_published(item_id, result)`
    7. On failure → `_record_failure(item_id, error, retryable)`

  - `execute_scheduled(self) -> List[dict]` — get due approved items, execute each
  - `_publish_wechat(self, item: QueueItem) -> dict` — reuse `publish_wechat_draft()` from `content_agent/publisher.py`
  - `_publish_xiaohongshu(self, item: QueueItem) -> dict` — delegate to `XiaohongshuPublisher`
  - `_record_failure(self, item_id: str, error: str, retryable: bool)` — update DB status="failed", error_log, retry_count+1
  - `_get_due_items(self) -> List[QueueItem]` — SELECT approved items WHERE scheduled_at IS NULL OR scheduled_at <= now

---

### 3. automation/xiaohongshu_publisher.py

Implement `XiaohongshuPublisher` class (semi-automated, **not** Playwright):

- **Method** `publish(self, title: str, content: str, tags: str = "") -> dict`
  1. Format content for Xiaohongshu (title + body + hashtags)
  2. Print formatted content with clear separator lines
  3. Print instruction: "请手动复制以上内容到小红书创作者平台: https://creator.xiaohongshu.com"
  4. Try `webbrowser.open("https://creator.xiaohongshu.com")`
  5. Return `{"success": True, "message": "已生成发布指南", "manual": True, "details": formatted}`

- **Method** `_format_content(self, title, content, tags) -> str`

Do NOT add Playwright or browser automation. Keep it lightweight and safe.

---

### 4. automation/retry.py

Implement `RetryPolicy` class:

- **Constructor**: `__init__(self, max_retries: int = 3, base_delay: float = 2.0, max_delay: float = 60.0)`

- **Methods**:
  - `should_retry(self, error: str, attempt: int) -> bool`
    - retryable keywords: timeout, connection, network, rate limit, too many requests, temporarily, unavailable
    - non-retryable: blocked, banned, forbidden, invalid, rejected, content violation
    - return `attempt < max_retries and any(retryable in error.lower()) and not any(non_retryable in error.lower())`
  - `get_delay(self, attempt: int) -> float` — exponential backoff with jitter: `min(base_delay * 2^attempt + random(0,1), max_delay)`

---

### 5. DB Migration (agents/store.py)

- Bump `_SCHEMA_VERSION` from 3 to 4.
- Add helper `_column_exists(table, column) -> bool`.
- Add migration function `migrate_publish_queue_v2()`:
  - For each column in `["scheduled_at", "retry_count", "error_log", "gate_decision", "gate_reason"]`:
    - If not exists: `ALTER TABLE publish_queue ADD COLUMN {col} TEXT`
  - `retry_count` should be INTEGER DEFAULT 0, not TEXT. Use a separate check for that.
- Add `init_publish_queue_migration()` that runs the migration.
- Call it from `init_db()` after `init_publish_queue_table()`.
- Add indexes:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_queue_scheduled ON publish_queue(scheduled_at);
  CREATE INDEX IF NOT EXISTS idx_queue_status_retry ON publish_queue(status, retry_count);
  ```

---

### 6. CLI Extensions (main.py)

Add new arguments:

```python
parser.add_argument("--publish-all", action="store_true", help="批量审核并发布所有 approved 项")
parser.add_argument("--publish-scheduled", action="store_true", help="执行到期的排期发布")
parser.add_argument("--schedule", metavar="ID", help="为队列项设置排期时间")
parser.add_argument("--at", metavar="TIME", help="排期时间，如 '2026-05-25 09:00'")
parser.add_argument("--unschedule", metavar="ID", help="取消排期")
parser.add_argument("--gate-mode", default="interactive", choices=["interactive", "scheduled", "disabled"], help="审核门模式")
parser.add_argument("--skip-gate", action="store_true", help="开发调试：跳过审核门（打印警告）")
parser.add_argument("--retry-failed", action="store_true", help="重试所有 failed 状态的项")
parser.add_argument("--max-retries", type=int, default=3, help="最大重试次数")
```

Implement handlers in `_handle_agent_mode(args)`:

- `--publish-next` (existing): enhance to use PublishExecutor with gate
- `--publish-all`: load all approved items, batch gate review, publish each
- `--publish-scheduled`: call `executor.execute_scheduled()`
- `--schedule ID --at TIME`: update queue item `scheduled_at`
- `--unschedule ID`: set `scheduled_at = NULL`
- `--retry-failed`: load failed items with retry_count < max_retries, attempt publish again
- `--skip-gate`: if set, override gate_mode to "disabled" with a big warning print

---

### 7. Update automation/__init__.py

Export new classes: `PublishGate`, `GateDecision`, `PublishExecutor`, `RetryPolicy`, `XiaohongshuPublisher`.

---

## Constraints

- Do NOT modify existing P0/P1 modules.
- Do NOT break existing CLI behavior.
- `XiaohongshuPublisher` must NOT use Playwright or browser automation.
- Gate default mode must be `interactive` — never auto-approve without user input unless `--skip-gate` is explicitly passed.
- Use type hints throughout.
- After implementing, run:
  ```bash
  python -c "from automation import PublishGate, PublishExecutor, RetryPolicy, XiaohongshuPublisher; print('OK')"
  ```
- Test DB migration: `python -c "from agents.store import init_db; init_db(); print('DB OK')"`

## Design doc reference

Full design with execution sequence diagrams is in `docs/P2_auto_publish_design.md`.
