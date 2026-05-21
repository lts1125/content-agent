# P0 Agent 化实现设计文档

> 目标：Vault 监听自动触发 → 内容生成 → 进入待发队列 + 风格画像持久化
> 分支：`agent-autonomy`

---

## 1. 新增模块结构

```
automation/
  __init__.py
  vault_watcher.py      # Vault 文件监听
  agent_controller.py   # 自动触发 Orchestrator
  publish_queue.py      # 待发队列 CRUD
  style_profile.py      # 风格画像提取与存储

agents/store.py         # 扩展：新增 publish_queue / style_profiles 表
main.py                 # 扩展：--watch / --queue / --publish-next CLI
ui/tabs/queue_tab.py    # Gradio Tab：队列管理（P0 后补，先做 CLI）
```

---

## 2. Vault Watcher (automation/vault_watcher.py)

### 职责
- 监听 `VAULT_PATH/inbox/` 目录下的 `.md` / `.txt` 文件变动
- 新文件出现时触发回调（Agent Controller）
- 文件处理完后移动到 `processed/` 或 `failed/`
- 避免重复处理（通过文件移动 + 已处理指纹缓存）

### 配置（环境变量）
```bash
VAULT_PATH=/Users/lee/content-agent/notes          # 笔记库根目录
VAULT_INBOX=subdir                                  # 监听子目录，默认 inbox/
VAULT_WATCH_INTERVAL=1.0                            # 轮询间隔（fallback）
```

### 目录约定
```
$VAULT_PATH/
  inbox/          # 放入这里的文件会被自动处理
  processed/      # 处理成功的文件移到这里
  failed/         # 处理失败的文件移到这里，保留原始文件名 + 时间戳后缀
```

### 核心类
```python
class VaultWatcher:
    def __init__(self, vault_path: str, inbox_dir: str = "inbox",
                 on_new_note: Callable[[Path], None] | None = None)
    def start(self)          # 启动监听（阻塞当前线程）
    def start_background(self) -> threading.Thread   # 后台线程启动
    def stop(self)
```

### 去重机制
- 文件移动到 `processed/` 后即脱离监听范围
- 启动时扫描 `inbox/`，批量处理已有文件
- 使用 `filecmp` 或文件名 + mtime 作为指纹，10 分钟内同名文件不重复触发

### 依赖
- `watchdog` 库（macOS 用 FSEvents，Linux 用 inotify）
- 已在项目环境中可用

---

## 3. Agent Controller (automation/agent_controller.py)

### 职责
- Vault Watcher 的回调接收者
- 读取笔记文件 → 构建 `TaskInput` → 调用 `Orchestrator.run()`
- 生成完成后将结果推入 Publish Queue
- 异常处理和文件归档

### 配置（环境变量）
```bash
AGENT_DEFAULT_PLATFORMS=xiaohongshu,gongzhonghao,douyin
AGENT_AUTO_RESEARCH=false          # P0 默认关闭，降低 token 消耗
AGENT_DEFAULT_STYLE=default
AGENT_SKIP_EDIT=true               # P0 快速模式，1 次 LLM 出稿
```

### 核心流程
```
on_new_note(file_path):
  1. 读取文件内容
  2. 构建 TaskInput（使用默认配置）
  3. 调用 Orchestrator.run(task_input)
  4. 将 final_output 按平台拆分，逐条插入 publish_queue（status=pending）
  5. 将文件移动到 processed/
  6. 更新 style_profile（记录原始笔记 + 生成结果作为样本）
```

### 核心类
```python
class AgentController:
    def __init__(self, orch: Orchestrator | None = None)
    def on_new_note(self, note_path: Path) -> dict   # 处理单文件，返回结果摘要
    def process_inbox(self, inbox_dir: Path) -> list[dict]   # 批量处理（启动时）
```

---

## 4. Publish Queue (automation/publish_queue.py)

### 数据模型

```python
@dataclass
class QueueItem:
    id: str                          # queue_ + uuid
    task_id: str                     # 关联 Orchestrator task_id
    platform: str                    # xiaohongshu / gongzhonghao / douyin
    title: str                       # 文章标题（从内容第一行提取）
    content: str                     # 完整文案
    tags: str                        # 推荐标签
    status: Literal["pending", "approved", "published", "rejected"]
    note_source: str                 # 原始笔记路径
    created_at: str
    reviewed_at: str | None
    published_at: str | None
    publish_result: str | None       # 发布结果/错误信息
```

### 数据库表（扩展 agents/store.py）

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

### CRUD 接口
```python
class PublishQueue:
    @staticmethod
    def add(task_id: str, platform: str, title: str, content: str,
            tags: str, note_source: str) -> str   # 返回 item_id
    @staticmethod
    def list(status: str | None = None, limit: int = 50) -> list[QueueItem]
    @staticmethod
    def get(item_id: str) -> QueueItem | None
    @staticmethod
    def approve(item_id: str) -> bool
    @staticmethod
    def reject(item_id: str) -> bool
    @staticmethod
    def mark_published(item_id: str, result: str = "") -> bool
    @staticmethod
    def delete(item_id: str) -> bool
```

---

## 5. Style Profile (automation/style_profile.py)

### 职责
- P0 只做**样本收集**，不做 LLM 分析（避免增加复杂度）
- 每次生成后，将（原始笔记 + 生成结果）作为样本存入数据库
- P1 再引入 LLM 分析，从样本中提取风格画像

### 数据模型

```python
@dataclass
class StyleSample:
    id: str
    task_id: str
    note_source: str
    note_preview: str          # 原始笔记前 500 字
    platform: str
    content_preview: str       # 生成内容前 500 字
    content_length: int
    created_at: str
```

### 数据库表（扩展 agents/store.py）

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

### 接口
```python
class StyleProfile:
    @staticmethod
    def record_sample(task_id: str, note_source: str, note_text: str,
                      platform: str, content: str)
    @staticmethod
    def list_samples(limit: int = 100) -> list[StyleSample]
    @staticmethod
    def get_profile_hint(platform: str) -> str   # P0 返回空字符串，P1 实现
```

---

## 6. CLI 扩展 (main.py)

### 新增参数
```bash
# 启动 Vault 监听（前台）
python main.py --watch

# 查看待发队列
python main.py --queue
python main.py --queue --status pending     # 筛选状态
python main.py --queue --limit 20

# 审核操作
python main.py --approve <queue_id>
python main.py --reject <queue_id>

# 手动发布队列中的下一个 approved 项目
python main.py --publish-next

# 批量处理 inbox（不启动监听，处理完即退出）
python main.py --process-inbox
```

### 参数解析器扩展
```python
watch_group = parser.add_mutually_exclusive_group()
watch_group.add_argument("--watch", action="store_true", help="启动 Vault 监听模式")
watch_group.add_argument("--process-inbox", action="store_true", help="批量处理 inbox 后退出")
parser.add_argument("--queue", action="store_true", help="查看待发队列")
parser.add_argument("--status", default="pending", help="队列筛选状态")
parser.add_argument("--approve", help="审核通过指定队列项")
parser.add_argument("--reject", help="拒绝指定队列项")
parser.add_argument("--publish-next", action="store_true", help="发布下一个 approved 项")
```

---

## 7. 执行时序图

```
用户 ──→ 将 note.md 放入 vault/inbox/
          │
          ▼
   VaultWatcher (watchdog)
          │ on_created 事件
          ▼
   AgentController.on_new_note()
          │
          ├──→ 读取文件内容
          ├──→ 构建 TaskInput（默认配置）
          ├──→ Orchestrator.run(task_input)
          │       ├──→ WriterAgent
          │       ├──→ EditorAgent (skip if skip_edit=true)
          │       └──→ final_output
          │
          ├──→ PublishQueue.add() × N 平台
          │       └──→ SQLite insert (status=pending)
          │
          ├──→ StyleProfile.record_sample() × N 平台
          │       └──→ SQLite insert
          │
          └──→ 移动文件到 vault/processed/

用户 ──→ python main.py --queue
          └──→ 查看所有 pending 项目

用户 ──→ python main.py --approve <id>
          └──→ 更新 status=approved

用户 ──→ python main.py --publish-next
          └──→ 取第一个 approved → 调用 Publisher → status=published
```

---

## 8. 数据库迁移策略

由于 SQLite 无内置迁移工具，采用**版本化 init_db**：

```python
# agents/store.py
_SCHEMA_VERSION = 2   # 当前版本

def init_db():
    _ensure_db()
    conn = _get_conn()
    # 1. 创建旧表（如果缺失）
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (...);
        CREATE TABLE IF NOT EXISTS drafts (...);
        CREATE TABLE IF NOT EXISTS edit_history (...);
        -- P0 新增：
        CREATE TABLE IF NOT EXISTS publish_queue (...);
        CREATE TABLE IF NOT EXISTS style_samples (...);
        -- 版本记录
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
    """)
    # 2. 如果 schema_version 不存在或版本 < 2，执行增量 DDL
    # ...
    conn.commit()
    conn.close()
```

---

## 9. 错误处理与边界情况

| 场景 | 处理 |
|---|---|
| inbox 放入非 md/txt 文件 | 忽略，不触发 |
| Orchestrator 生成失败 | 文件移动到 `failed/`，记录错误日志 |
| 文件内容为空 | 记录 warning，移动到 `failed/` |
| Vault 路径未配置 | `--watch` 启动时报错并退出 |
| inbox 目录不存在 | 自动创建 |
| 文件正在写入中（大文件） | watchdog 有稳定检测，或延迟 1 秒再读 |
| 同一文件重复放入 inbox | 移动到 processed/ 后不再监听 |

---

## 10. 最小可验证步骤（MVP Checklist）

1. [ ] 创建 `automation/` 目录和 4 个模块
2. [ ] 扩展 `agents/store.py`：新增 `publish_queue` / `style_samples` 表
3. [ ] 实现 `VaultWatcher`：能监听 inbox 并回调
4. [ ] 实现 `AgentController`：连接 Watcher → Orchestrator → Queue
5. [ ] 扩展 `main.py` CLI：`--watch` / `--queue` / `--approve` / `--publish-next`
6. [ ] 端到端测试：放入一个 .md → 自动处理 → 查队列能看到 pending 项
7. [ ] 文件正确归档到 processed/

---

## 11. 与 P1/P2 的衔接

- P0 的 `publish_queue` 表在 P1 中扩展 `scheduled_at` 字段支持排期
- P0 的 `style_samples` 表在 P1 中被 LLM 分析，输出到 `style_profiles` 表
- P0 的 `--watch` 在 P2 中支持自动发布（配置 `auto_publish=true`）

---

**下一步**：用 Claude Code 按此设计文档实现。先实现核心数据层 + Vault Watcher，再连接 Agent Controller，最后补 CLI。
