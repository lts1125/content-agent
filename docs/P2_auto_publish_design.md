# P2 自动发布 + 审核门设计文档

> 目标：审核门强制人工确认 + 自动发布到微信公众号/小红书 + 错误恢复
> 分支：`agent-autonomy`
> 依赖：P0 队列 + P1 风格画像
> 风险等级：高（涉及真实账号发布）

---

## 1. 核心原则

1. **审核门不可绕过** — 任何自动发布必须经过人工确认，默认不允许无人审核发布。
2. **分层审核** — CLI 交互确认（本地）+ 排期审核（可提前审核）。
3. **错误可恢复** — 发布失败自动重试，超过上限进入人工干预。
4. **平台差异透明** — 小红书无官方 API，采用 Playwright 模拟操作，必须明确告知用户风险。

---

## 2. 新增模块结构

```
automation/
  gate.py                # 审核门：交互确认 + 排期审核
  executor.py            # 执行器：分发到平台 API / 浏览器自动化
  retry.py               # 重试策略：指数退避 + 最大次数
  xiaohongshu_publisher.py  # 小红书 Playwright 发布实现（模拟操作）

agents/store.py          # 扩展：publish_queue 加 scheduled_at / retry_count / error_log
main.py                  # 扩展：--publish-scheduled / --gate-mode / --retry-failed / --skip-gate (开发调试用)
```

---

## 3. 审核门 (automation/gate.py)

### 职责
- 在任何发布操作前，强制人工确认
- 支持两种模式：即时交互确认、提前审核

### 数据模型

```python
@dataclass
class GateDecision:
    item_id: str
    decision: Literal["approve", "reject", "skip"]
    reviewer: str = "cli_user"          # 谁做的决定
    decided_at: str = ""                # ISO 时间
    reason: str = ""                    # 拒绝理由
```

### 接口

```python
class PublishGate:
    def __init__(self, mode: Literal["interactive", "scheduled", "disabled"] = "interactive")

    def review(self, item: QueueItem) -> GateDecision:
        """
        审核单个队列项。
        mode=interactive: 终端交互打印内容摘要，要求用户输入 y/n
        mode=scheduled: 检查 scheduled_at 是否到达，提前审核的项允许通过
        mode=disabled: 直接通过（仅用于开发调试，打印警告）
        """

    def batch_review(self, items: List[QueueItem]) -> List[GateDecision]:
        """批量审核，用于一次确认多条内容"""

    @staticmethod
    def _interactive_prompt(item: QueueItem) -> GateDecision:
        """终端交互式审核"""
        print(f"\n{'='*60}")
        print(f"📋 待审核内容")
        print(f"   ID:     {item.id}")
        print(f"   平台:   {item.platform}")
        print(f"   标题:   {item.title}")
        print(f"   内容:   {item.content[:200]}...")
        print(f"   标签:   {item.tags}")
        print(f"{'='*60}")
        choice = input("确认发布? [y/回车=确认, n=拒绝, s=跳过]: ").strip().lower()
        if choice in ("", "y", "yes"):
            return GateDecision(item.id, "approve")
        elif choice == "n":
            reason = input("拒绝理由 (可留空): ").strip()
            return GateDecision(item.id, "reject", reason=reason)
        else:
            return GateDecision(item.id, "skip")
```

### 排期审核

```python
def review_scheduled(self, item: QueueItem) -> GateDecision:
    """
    排期审核逻辑：
    1. 如果队列项已经被用户提前审核（status=approved），直接通过
    2. 如果到了 scheduled_at 但还是 pending，进入 interactive 模式等待确认
    3. 如果未到 scheduled_at，返回 skip
    """
```

---

## 4. 执行器 (automation/executor.py)

### 职责
- 获取 `approved` 状态的队列项
- 通过 Gate 审核
- 根据平台分发到对应发布工具
- 记录发布结果 / 失败原因

### 接口

```python
class PublishExecutor:
    def __init__(self, gate: PublishGate | None = None, max_retries: int = 3)

    def execute_one(self, item_id: str) -> dict:
        """执行单个队列项的发布"""
        item = PublishQueue.get(item_id)
        if not item:
            return {"success": False, "error": "队列项不存在"}

        # 1. 审核门
        decision = self.gate.review(item)
        if decision.decision == "reject":
            PublishQueue.reject(item_id)
            return {"success": False, "error": f"审核拒绝: {decision.reason}"}
        if decision.decision == "skip":
            return {"success": False, "error": "用户跳过"}

        # 2. 分平台执行
        result = self._dispatch(item)

        # 3. 记录结果
        if result["success"]:
            PublishQueue.mark_published(item_id, result=result.get("details", ""))
        else:
            self._record_failure(item_id, result.get("error", ""), result.get("retryable", False))

        return result

    def execute_scheduled(self) -> List[dict]:
        """扫描并执行所有到期的排期发布"""
        due_items = self._get_due_items()
        results = []
        for item in due_items:
            results.append(self.execute_one(item.id))
        return results

    def _dispatch(self, item: QueueItem) -> dict:
        if item.platform == "gongzhonghao":
            return self._publish_wechat(item)
        elif item.platform == "xiaohongshu":
            return self._publish_xiaohongshu(item)
        elif item.platform == "douyin":
            return {"success": False, "error": "抖音自动发布暂未实现", "retryable": False}
        else:
            return {"success": False, "error": f"未知平台: {item.platform}", "retryable": False}

    def _publish_wechat(self, item: QueueItem) -> dict:
        """调用 kuaifa CLI 发布到微信公众号"""
        from content_agent.publisher import publish_wechat_draft, save_content_as_markdown
        md_path = save_content_as_markdown(item.title, item.content)
        return publish_wechat_draft(
            markdown_path=md_path,
            title=item.title,
            cover_path="",           # P2 暂不自动上传封面，留给 P3
            author="",
            digest="",
        )

    def _publish_xiaohongshu(self, item: QueueItem) -> dict:
        """调用 Playwright 模拟操作发布到小红书"""
        from automation.xiaohongshu_publisher import XiaohongshuPublisher
        publisher = XiaohongshuPublisher()
        return publisher.publish(
            title=item.title,
            content=item.content,
            tags=item.tags,
        )

    def _record_failure(self, item_id: str, error: str, retryable: bool):
        """记录失败信息到 DB"""
        conn = _get_conn()
        conn.execute(
            "UPDATE publish_queue SET status = ?, error_log = ?, retry_count = retry_count + 1 WHERE id = ?",
            ("failed", error, item_id),
        )
        conn.commit()
        conn.close()

    def _get_due_items(self) -> List[QueueItem]:
        """获取所有已到期的 approved 项"""
        now = datetime.now().isoformat()
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM publish_queue WHERE status = 'approved' AND (scheduled_at IS NULL OR scheduled_at <= ?) ORDER BY created_at ASC",
            (now,),
        ).fetchall()
        conn.close()
        return [_row_to_item(r) for r in rows]
```

---

## 5. 小红书发布 (automation/xiaohongshu_publisher.py)

### 现状
小红书无官方开放的发布 API。主流方案是 Playwright 模拟浏览器操作。

### 设计决策
- **方案 A：Playwright 模拟** — 完全自动化，但存在账号封禁风险、cookie 过期、页面结构变更等问题。
- **方案 B：半自动化** — 自动生成发布页面的 URL 和填充内容，打开浏览器等待用户点击发布。

**采用方案 B作为 P2 MVP**：
- 风险最低，用户可控
- 实现简单，不需要处理复杂的登录和验证码逻辑
- 可以先跑通全流程，后续再升级为方案 A

### 实现

```python
class XiaohongshuPublisher:
    def publish(self, title: str, content: str, tags: str = "") -> dict:
        """
        半自动发布小红书：
        1. 将内容格式化为适合小红书的文本
        2. 打印发布页面的复制粘贴指南
        3. 尝试打开浏览器（如果有 webbrowser 模块）
        """
        formatted = self._format_content(title, content, tags)
        print("\n📱 小红书发布指南")
        print("   请手动复制以下内容到小红书创作者平台: https://creator.xiaohongshu.com")
        print(f"\n{'='*40}")
        print(formatted)
        print(f"{'='*40}\n")

        # 尝试自动打开浏览器
        try:
            import webbrowser
            webbrowser.open("https://creator.xiaohongshu.com")
        except Exception:
            pass

        return {
            "success": True,
            "message": "已生成小红书发布指南，请手动粘贴发布",
            "details": formatted,
            "manual": True,
        }

    def _format_content(self, title: str, content: str, tags: str) -> str:
        """格式化为小红书友好格式"""
        lines = [f"标题: {title}", ""]
        lines.extend(content.splitlines())
        if tags:
            lines.extend(["", f"话题: {tags}"])
        return "\n".join(lines)
```

### 未来升级（P3+）
- 若需要完全自动化，可升级为 Playwright 方案 A：
  ```bash
  pip install playwright
  playwright install chromium
  ```
- 需要 cookie 持久化、验证码处理、图片上传等复杂逻辑

---

## 6. 重试策略 (automation/retry.py)

### 接口

```python
class RetryPolicy:
    def __init__(self, max_retries: int = 3, base_delay: float = 2.0, max_delay: float = 60.0)

    def should_retry(self, error: str, attempt: int) -> bool:
        """
        判断是否应该重试。
        重试元则：
        - 网络问题：timeout, connection, network
        - 限流：rate limit, too many requests
        - 认证过期：auth, token, credential
        - 不重试：内容违规、账号封禁、参数错误
        """
        retryable_keywords = ["timeout", "connection", "network", "rate limit", "too many requests", "temporarily", "unavailable"]
        non_retryable = ["blocked", "banned", "forbidden", "invalid", "rejected", "content violation"]
        e_lower = error.lower()
        if any(k in e_lower for k in non_retryable):
            return False
        return attempt < self.max_retries and any(k in e_lower for k in retryable_keywords)

    def get_delay(self, attempt: int) -> float:
        """指数退避延迟"""
        import random, math
        delay = self.base_delay * (2 ** attempt)
        jitter = random.uniform(0, 1)
        return min(delay + jitter, self.max_delay)
```

---

## 7. DB 扩展

### publish_queue 表扩展

```sql
-- 添加排期和重试字段
ALTER TABLE publish_queue ADD COLUMN scheduled_at TEXT;
ALTER TABLE publish_queue ADD COLUMN retry_count INTEGER DEFAULT 0;
ALTER TABLE publish_queue ADD COLUMN error_log TEXT;
ALTER TABLE publish_queue ADD COLUMN gate_decision TEXT;  -- approve | reject | skip
ALTER TABLE publish_queue ADD COLUMN gate_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_queue_scheduled ON publish_queue(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_queue_status_retry ON publish_queue(status, retry_count);
```

> 注意：SQLite 从 3.35.0 开始支持 ALTER TABLE DROP COLUMN，但 ADD COLUMN 一直支持。
> 为保证兼容，在 `init_db()` 中检查列是否存在，不存在则 ADD COLUMN。

### 列存在性检查（agents/store.py 增加）

```python
def _column_exists(table: str, column: str) -> bool:
    conn = _get_conn()
    try:
        conn.execute(f"SELECT {column} FROM {table} LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()

def migrate_publish_queue_v2():
    """publish_queue 增加排期和重试字段"""
    conn = _get_conn()
    columns = ["scheduled_at", "retry_count", "error_log", "gate_decision", "gate_reason"]
    for col in columns:
        if not _column_exists("publish_queue", col):
            conn.execute(f"ALTER TABLE publish_queue ADD COLUMN {col} TEXT")
    conn.commit()
    conn.close()
```

---

## 8. CLI 扩展 (main.py)

```bash
# 执行审核门 + 发布
python main.py --publish-next                  # 交互式审核并发布下一个 approved 项（已存在，增强审核门）
python main.py --publish-all                   # 批量审核并发布所有 approved 项
python main.py --publish-scheduled             # 执行所有到期的排期发布

# 排期
python main.py --schedule <id> --at "2026-05-25 09:00"   # 为队列项设置发布时间
python main.py --unschedule <id>                         # 取消排期

# 审核门模式
python main.py --gate-mode interactive         # 终端交互确认（默认）
python main.py --gate-mode scheduled           # 排期自动审核（已 approved 则自动通过）
python main.py --skip-gate                     # 开发调试：跳过审核门（打印警告）

# 错误恢复
python main.py --retry-failed                  # 重试所有 failed 状态且未超过最大次数的项
python main.py --max-retries 3                 # 设置最大重试次数

# 查看发布状态
python main.py --queue --status failed         # 查看发布失败的项
```

---

## 9. 执行流程图

### 单条发布流程
```
用户 → python main.py --publish-next
              ↓
        PublishQueue.get_oldest_approved()
              ↓
        PublishGate.review(item)     # 交互式确认
              ↓
        用户输入 y → approve
              ↓
        PublishExecutor._dispatch(item)
              ↓
        平台判断：
          gongzhonghao → kuaifa CLI 发布
          xiaohongshu  → 打印发布指南 + 打开浏览器
          douyin       → 返回"未实现"
              ↓
        成功 → mark_published()
        失败 → 记录 error_log + retry_count
              ↓
        如果 retryable 且 retry_count < max_retries
              ↓
        等待 RetryPolicy.get_delay() 后重试
```

### 排期发布流程
```
Hermes Cronjob → python main.py --publish-scheduled --gate-mode scheduled
              ↓
        PublishExecutor.execute_scheduled()
              ↓
        查询到期的 approved 项
              ↓
        对每项执行发布（跳过 Gate，因为已经提前审核）
              ↓
        记录结果
```

---

## 10. 安全与风险

| 风险 | 对策 |
|---|---|
| 无人审核自动发布 | `--skip-gate` 需要明确指定，默认强制交互确认 |
| 账号封禁（小红书） | 采用方案 B（半自动），手动点击最后一步 |
| kuaifa 认证过期 | 发布失败时提示用户重新登录 kuaifa |
| 内容违规被封 | 发布前保留敏感词检查（已存在） |
| 限流被限制 | 排期策略避免集中发布，重试时增加延迟 |

---

## 11. MVP Checklist

1. [ ] 实现 `PublishGate`：interactive / scheduled / disabled 三种模式
2. [ ] 实现 `PublishExecutor`：分发到微信公众号 + 小红书
3. [ ] 实现 `XiaohongshuPublisher`：半自动方案 B
4. [ ] 实现 `RetryPolicy`：指数退避 + 关键词判断
5. [ ] 扩展 DB：publish_queue 加 5 个字段
6. [ ] 扩展 CLI：--publish-all / --publish-scheduled / --schedule / --gate-mode / --retry-failed
7. [ ] 端到端测试：生成文案 → 审核 → 发布公众号草稿箱

---

## 12. 与 P3 的衔接

- P3 可能涉及多账号管理、自动回复评论等，P2 的 `gate_decision` 字段留了 reviewer 扩展
- P2 的 `scheduled_at` 为 P3 的"智能排期"（根据历史数据选择最佳时段）打基础
- P2 的 `RetryPolicy` 为 P3 的错误自愈机制提供框架
