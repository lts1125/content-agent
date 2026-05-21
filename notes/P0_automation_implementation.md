# P0 Agent 化实现笔记

> 实现时间：2026-05-21  
> 目标：Vault 监听自动触发 → 内容生成 → 进入待发队列 + 风格画像持久化

---

## 架构图

```
┌─────────────┐     on_created      ┌──────────────────┐
│  Vault      │ ──────────────────▶ │ AgentController  │
│  Watcher    │                     │                  │
│ (watchdog)  │                     │ 1. 读取文件内容   │
└─────────────┘                     │ 2. 构建 TaskInput │
                                    │ 3. orch.run()    │
                                    └────────┬─────────┘
                                             │
                              ┌──────────────┼──────────────┐
                              ▼              ▼              ▼
                       ┌──────────┐  ┌──────────┐  ┌────────────┐
                       │ Publish  │  │ Publish  │  │ StyleProfile│
                       │ Queue    │  │ Queue    │  │            │
                       │(平台A)   │  │(平台B)   │  │ record_sample
                       └──────────┘  └──────────┘  └────────────┘
```

---

## 关键设计决策

### 1. 文件移动权责划分

**问题**：VaultWatcher 和 AgentController 都可能移动文件，容易造成重复移动或异常链。

**决策**：
- **VaultWatcher**：只负责检测文件变动 + 调用回调。即使回调抛异常，也不再移动文件。
- **AgentController**：负责全部处理逻辑（读取 → 生成 → 入库 → 移动文件到 `processed/` 或 `failed/`）。

这样权责清晰：Watcher 是"传感器"，Controller 是"执行器"。

### 2. 去重机制

**需求**：启动时扫描已有文件 + watchdog 实时监听，同一文件可能被触发两次。

**实现**：
- 使用 `Dict[(filename, mtime), timestamp]` 记录最近处理过的文件指纹
- 10 分钟过期自动清理（cutoff = time.time() - 600）
- 文件处理完后会被移出 inbox，watchdog 不会再次触发，所以内存占用极小

### 3. DB 版本化迁移

**需求**：SQLite 无内置迁移工具，新增表不能破坏已有数据。

**实现**：
- 引入 `_SCHEMA_VERSION = 2` 常量和 `schema_version` 表
- `init_db()` 使用 `CREATE TABLE IF NOT EXISTS` 和 `CREATE INDEX IF NOT EXISTS`
- 新表（`publish_queue`, `style_samples`）通过独立的 `init_*_table()` 函数创建，保证幂等
- 未来版本升级时，可对比 `schema_version` 执行增量 DDL

### 4. AgentController 与 VaultWatcher 的协作

**问题**：AgentController 需要移动文件到 `processed/` / `failed/`，但不应该知道 vault 路径的具体结构。

**实现**：
- `AgentController.__init__` 接收 `watcher: VaultWatcher | None` 参数
- 文件移动通过 `self.watcher.move_to_processed()` / `move_to_failed()` 完成
- `main.py` 中先创建 watcher，再传入 controller：
  ```python
  watcher = VaultWatcher(vault_path=vault_path, inbox_dir=inbox_dir)
  controller = AgentController(watcher=watcher)
  watcher.on_new_note = controller.on_new_note
  ```

### 5. 标题提取

**实现**：`extract_title(content)` 取内容第一行非空文本，去掉前导 `#`，截断到 100 字符。

---

## 踩坑记录

### 1. `_extract_title` 被外部导入（封装破坏）

初版中 `agent_controller.py` 从 `publish_queue.py` 导入了 `_extract_title`（下划线前缀表示私有）。

**修复**：重命名为公开的 `extract_title()`。

### 2. AgentController 重复创建 VaultWatcher 实例

初版中 `_move_to_processed` / `_move_to_failed` 每次都 `VaultWatcher(str(vault))` 新建实例。

**修复**：`AgentController` 初始化时接收 watcher 实例，复用同一个对象。

### 3. `--publish-next` 取最早项逻辑 hacky

初版依赖 `ORDER BY created_at DESC` 然后取 `[-1]` 来获取最早项，不够直观。

**修复**：`PublishQueue.get_oldest_approved()` 方法，使用 `ORDER BY created_at ASC LIMIT 1`。

### 4. watchdog 未安装

项目环境中实际没有 watchdog，运行时 `ModuleNotFoundError`。

**处理**：`pip install watchdog` 安装即可。生产环境应在 requirements 中声明。

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VAULT_PATH` | 笔记库根目录 | `~/.content_agent/vault` |
| `VAULT_INBOX` | 监听子目录 | `inbox` |
| `AGENT_DEFAULT_PLATFORMS` | 默认生成平台 | `xiaohongshu,gongzhonghao,douyin` |
| `AGENT_AUTO_RESEARCH` | 是否自动启用搜索增强 | `false` |
| `AGENT_SKIP_EDIT` | 是否跳过 Editor 审稿 | `true`（P0 快速模式） |
| `AGENT_DEFAULT_STYLE` | 默认风格画像 | `default` |

---

## 目录约定

```
$VAULT_PATH/
  inbox/          # 放入这里的文件会被自动处理
  processed/      # 处理成功的文件移到这里
  failed/         # 处理失败的文件移到这里（保留原始文件名 + 时间戳后缀）
```

---

## P1 衔接计划

- `publish_queue` 表扩展 `scheduled_at` 字段支持排期发布
- `style_samples` 表引入 LLM 分析，输出到 `style_profiles` 表
- `--watch` 支持配置 `auto_publish=true` 自动发布 approved 项
