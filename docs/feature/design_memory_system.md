# 记忆系统设计文档

> 目标：将 content-agent 从“无状态脚本”升级为“有记忆的 Agent”，支持短期会话记忆、长期用户偏好、向量语义检索三个维度。

---

## 一、现状分析

| 维度 | 现状 | 问题 |
|------|------|------|
| 短期记忆 | `ChatAgent.history` 只保存当次会话消息，进程重启消失 | 无上下文窗口管理，长文本可能撑爆 token |
| 长期记忆 | 无 | 用户每次都要重新说明风格偏好，没有学习能力 |
| 向量记忆 | `test_rag.py` 有 `VaultIndexer`，但未集成到主流程 | 用户上传笔记后不会自动入库，生成时也不会自动检索 |

**已有基础（可复用）：**
- `content_agent/rag/` 下已有 `BGEEmbedder`（BAAI/bge-small-zh-v1.5，512维）、`ChromaStore`、`VaultIndexer`
- `data/content_agent.db` 已有 SQLite 数据库，包含 tasks、style_profiles 等表
- `agents/store.py` 已有数据库操作封装

---

## 二、设计原则

1. **逐层抽象**：上层业务代码只和 `MemoryManager` 交互，不直接操作 SQLite/Chroma
2. **懒加载**：模型和向量库不在进程启动时加载，第一次使用时才初始化
3. **幽默调度**：向量检索失败（模型未下载、库为空）不阻断主流程，只是不附加素材
4. **适配单用户**：当前没有多租户需求，但表结构留 `user_id` 字段为未来扩展做预留

---

## 三、数据模型

### 3.1 短期记忆 — 会话历史（SQLite）

新增表 `conversation_turns`：

```sql
CREATE TABLE IF NOT EXISTS conversation_turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,          -- 会话唯一 ID
    role        TEXT    NOT NULL,          -- 'user' | 'assistant' | 'system'
    content     TEXT    NOT NULL,
    platforms   TEXT,                      -- JSON 数组，用户指定的平台
    files       TEXT,                      -- JSON 数组，上传的文件路径
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    task_id     TEXT                       -- 如果生成了内容，关联 task_id
);

CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation_turns(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_created ON conversation_turns(created_at);
```

### 3.2 长期记忆 — 用户偏好（SQLite）

新增表 `user_preferences`：

```sql
CREATE TABLE IF NOT EXISTS user_preferences (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          TEXT    NOT NULL DEFAULT 'default',
    pref_key         TEXT    NOT NULL,    -- 'preferred_tone'、'favorite_platforms'、'auto_publish'等
    pref_value       TEXT    NOT NULL,    -- JSON 字符串
    source           TEXT,                -- 'explicit'(用户明确设置)、'inferred'(模型推断)
    confidence       REAL    DEFAULT 0.5, -- 推断可信度，explicit 时为 1.0
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, pref_key)
);
```

基础偏好键：

| pref_key | 说明 | 示例值 |
|---------|------|--------|
| `preferred_tone` | 口语风格 | `"professional"` / `"casual"` / `"humorous"` |
| `favorite_platforms` | 常用平台 | `["gongzhonghao", "xiaohongshu"]` |
| `preferred_length` | 文章长度偏好 | `"short"` / `"medium"` / `"long"` |
| `auto_publish` | 是否默认发布 | `false` |
| `custom_prompt` | 用户自定义 prompt 后缀 | `"每段都要有小标题"` |

### 3.3 向量记忆 — 笔记 chunk（Chroma）

重用现有 `ChromaStore`，只需扩充 metadata 字段：

```python
metadata = {
    "source": str(rel_path),           # 笔记文件路径
    "title": md_file.stem,             # 笔记标题
    "heading": heading,                # 小标题
    "chunk_index": 0,                  # chunk 序号
    "user_id": "default",              # 预留
    "indexed_at": "2026-05-31T10:00:00",
}
```

---

## 四、接口设计

### 4.1 MemoryManager 类

位置：`agents/memory.py`

```python
class MemoryManager:
    """
    记忆管理器：统一封装短期、长期、向量三种记忆。
    
    使用示例：
        mm = MemoryManager()
        mm.save_turn(session_id, role="user", content="写篇关于 MCP 的文章")
        mm.save_turn(session_id, role="assistant", content="好的...", task_id="t123")
        
        # 获取短期记忆（带窗口限制）
        turns = mm.get_recent_turns(session_id, max_tokens=4000)
        
        # 获取长期偏好
        prefs = mm.get_preferences()
        
        # 向量检索
        notes = mm.search_notes("编程语言模型接口", top_k=3)
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self._indexer: VaultIndexer | None = None   # 懒加载

    # ---- 短期记忆 ----
    def save_turn(self, session_id: str, role: str, content: str,
                  platforms: list = None, files: list = None, task_id: str = None) -> None
    def get_recent_turns(self, session_id: str, max_tokens: int = 4000,
                         max_turns: int = 20) -> list[ConversationTurn]
    def get_session_summary(self, session_id: str) -> str
    def list_sessions(self, limit: int = 20) -> list[dict]   # 最近会话列表

    # ---- 长期记忆 ----
    def set_preference(self, key: str, value: any,
                       source: str = "explicit", confidence: float = 1.0) -> None
    def get_preference(self, key: str, default=None) -> any
    def get_preferences(self) -> dict   # 返回全部偏好字典
    def infer_preferences_from_history(self) -> dict  # 从历史生成中推断偏好

    # ---- 向量记忆 ----
    def index_note(self, file_path: str | Path, clear_existing: bool = False) -> int
        """将单个 Markdown 笔记文件索引到向量库，返回索引的 chunk 数量"""
    def search_notes(self, query: str, top_k: int = 5,
                     min_score: float = 0.3) -> list[NoteChunk]
    def get_index_stats(self) -> dict   # 索引统计信息

    # ---- 清理 ----
    def clear_session(self, session_id: str) -> None
    def clear_all_sessions(self, days: int = 30) -> int  # 清理 N 天前的会话
```

### 4.2 ConversationTurn 数据类

```python
from dataclasses import dataclass

@dataclass
class ConversationTurn:
    id: int
    session_id: str
    role: str           # 'user' | 'assistant' | 'system'
    content: str
    platforms: list     # 用户指定的平台
    files: list         # 上传文件路径
    created_at: str
    task_id: str | None
```

### 4.3 NoteChunk 数据类

```python
@dataclass
class NoteChunk:
    id: str
    text: str
    source: str         # 文件路径
    title: str          # 笔记标题
    heading: str        # 小标题
    distance: float     # 相似度（0-1，越小越相似）
```

---

## 五、集成点

### 5.1 ChatAgent 集成

修改 `chat_ui.py` 中的 `ChatAgent`：

```python
class ChatAgent:
    def __init__(self):
        self.selector = StrategySelector()
        self.planner = AutonomousPlanner()
        self.memory = MemoryManager()          # 新增
        self.session_id = str(uuid.uuid4())    # 新增

    def process_message_stream(self, user_message: str, uploaded_file=None):
        # 1. 保存用户消息到短期记忆
        self.memory.save_turn(self.session_id, "user", user_message)

        # 2. 获取长期偏好，注入到 prompt
        prefs = self.memory.get_preferences()
        tone_hint = f"风格偏好：{prefs.get('preferred_tone', 'professional')}" if prefs else ""

        # 3. 检索相关笔记
        notes = self.memory.search_notes(user_message, top_k=3)
        note_context = _format_notes(notes) if notes else ""

        # 4. 构建带记忆的 system prompt
        # ... 现有逻辑 ...

        # 5. 生成完成后，保存 assistant 回复
        self.memory.save_turn(self.session_id, "assistant", result_text, task_id=task_id)
```

### 5.2 上传笔记自动索引

修改 `_merge_uploaded_note_with_message()` 或其调用点：

```python
# 用户上传笔记后，立即索引
note_text = _read_uploaded_note_file(uploaded_file)
if note_text:
    # 保存临时文件
    temp_path = _save_note_temp(uploaded_file)
    # 索引到向量库
    self.memory.index_note(temp_path)
```

### 5.3 偏好学习

在内容生成成功后，开启后台任务分析用户行为：

```python
def _learn_from_generation(self, task_id: str):
    """从一次完整生成中学习偏好"""
    # 从 eval_results 读取评分
    # 如果某个平台的文章分数持续偏低，推断用户可能不适合该平台
    # 如果某种风格的文章分数高，推断用户偏好该风格
    pass
```

---

## 六、实现步骤

### Step 1: 数据库表创建

在 `agents/store.py` 中新增 `init_memory_tables()`，在 `init_db()` 中调用。

### Step 2: 实现 MemoryManager

新建 `agents/memory.py`，实现上述接口。

### Step 3: ChatAgent 集成

修改 `chat_ui.py` 中的 `ChatAgent`：
- `__init__` 中初始化 `MemoryManager`
- `process_message_stream` 中添加保存轮次、检索笔记、注入偏好
- 生成完成后保存 assistant 回复

### Step 4: 向量库工具化

在 Chat UI 中增加按钮/命令：
- `#!index` — 手动触发 Vault 重新索引
- `#!search <query>` — 测试向量检索
- 系统指令区增加显示当前偏好和索引状态

### Step 5: 偏好学习（可选，第一版可用 hardcoded 偏好代替）

在 `automation/` 下新增 `preference_learner.py`，定期分析 `eval_results` 表更新偏好。

---

## 七、关键边界条件

1. **token 窗口：**短期记忆最多保留近 20 轮（约 4000 tokens），超出时考虑模型摘要压缩
2. **向量库性能：**Chroma 在单机场景下支持数十万条 chunk，足够个人笔记库
3. **模型加载：**BGE 模型第一次加载约 100MB，可接受的启动耗时
4. **数据隔离：**当前不实现多用户，user_id 固定为 `default`，但接口留有 user_id 参数
5. **错误处理：**向量检索失败时返回空列表，不招致生成中断
