# B1 — 自触发能力设计

> 让 content-agent 从"点击工具"进化为"自己跑的 Agent"。

---

## 1. 目标

�用户无需每次手动运行 `python main.py`，Agent 按预设规则自动执行：

1. 定时扫描 Vault → 检测新笔记
2. 自动生成文案 → 入待发队列
3. 按排期触发发布 → 过审核门 → 发布
4. 用户只做审批和监控

---

## 2. 方案概述

提供两种运行模式，不锁死任何外部系统：

| 模式 | 命令 | 适用场景 |
|---|---|---|
| 单次执行 | `kuaifa schedule --once` | 外部 Cron/Hermes 定时调用 |
| 常驻后台 | `kuaifa daemon` | 用户手动启动，后台自己跑 |

底层用 APScheduler，任务配置存 SQLite，不依赖第三方服务。

---

## 3. 新增模块

### 3.1 `automation/scheduler.py`

封装 APScheduler，管理定时任务。

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

class TaskScheduler:
    def __init__(self, config: SchedulerConfig):
        self.scheduler = BackgroundScheduler()
        self.config = config

    def register_tasks(self):
        self.scheduler.add_job(
            self.run_scan,
            trigger=CronTrigger.from_crontab(self.config.scan_cron),
            id='vault_scan',
            replace_existing=True
        )
        self.scheduler.add_job(
            self.run_publish,
            trigger=CronTrigger.from_crontab(self.config.publish_cron),
            id='publish_queue',
            replace_existing=True
        )
        # 其他任务...

    def run_scan(self):
        # 调用 VaultWatcher + AgentController
        pass

    def run_publish(self):
        # 调用 PublishExecutor
        pass

    def start(self):
        self.scheduler.start()

    def shutdown(self):
        self.scheduler.shutdown()
```

### 3.2 `automation/config.py`

调度配置模型。

```python
@dataclass
class SchedulerConfig:
    scan_cron: str = "0 9 * * *"      # 每天 9:00 扫描
    publish_cron: str = "0 10,14,20 * * *"  # 每天 10/14/20 点尝试发布
    vault_path: str = ""
    platforms: list[str] = None
    auto_generate: bool = True       # 扫描后是否自动生成
    auto_enqueue: bool = True        # 生成后是否自动入队
    max_daily_publish: int = 3       # 每日最大发布数
```

### 3.3 CLI 扩展

main.py 新增参数：

```python
parser.add_argument("--schedule-once", action="store_true",
                    help="单次执行调度任务（扫描+生成+发布）")
parser.add_argument("--daemon", action="store_true",
                    help="常驻后台运行")
parser.add_argument("--config", type=str,
                    help="调度配置文件路径（YAML）")
```

示例：
```bash
# 单次执行
kuaifa schedule --once

# 常驻后台
kuaifa daemon --config schedule.yaml

# Hermes cronjob 调用
0 9 * * * cd /path && kuaifa schedule --once
```

---

## 4. 任务流水线

### 4.1 Vault 扫描任务 (scan)

1. VaultWatcher 扫描新笔记
2. 如果 `auto_generate=True`，自动调用 AgentController 生成文案
3. 如果 `auto_enqueue=True`，自动入待发队列（status=pending）
4. 通知用户（Feishu/Terminal）

### 4.2 发布任务 (publish)

1. 检查待发队列中 `status=approved` 且 `scheduled_time <= now` 的项
2. 检查今日已发布数量 < `max_daily_publish`
3. 调用 PublishExecutor.execute_one()
4. 记录结果

---

## 5. 与现有代码的集成

| 新增模块 | 复用的现有模块 |
|---|---|
| TaskScheduler | VaultWatcher, AgentController, PublishExecutor |
| SchedulerConfig | 无（新配置） |
| CLI 扩展 | 无（main.py 新增参数） |

无需改动任何现有核心逻辑，只是增加"调度层"包裹调用。

---

## 6. 配置文件示例

`schedule.yaml`：

```yaml
vault_path: "~/obsidian/notes"
platforms:
  - xiaohongshu
  - wechat
scan_cron: "0 9 * * *"
publish_cron: "0 10,14,20 * * *"
auto_generate: true
auto_enqueue: true
max_daily_publish: 3
notification:
  feishu_webhook: ""
  terminal: true
```

---

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| 定时触发太频繁 | Cron 表达式可配置，默认每天一次扫描 |
| 后台进程占用资源 | APScheduler 极轻量，无任务时归零 CPU |
| 误触发生成大量文案 | `max_daily_publish` 限制 – 入队不代表发布 |
| 没有 Vault 新文件白跑 | 完整日志记录，用户可查看扫描结果 |

---

## 8. MVP 范围

只做以下，保持轻量：

1. `TaskScheduler` 类（扫描+发布两个任务）
2. YAML 配置读取
3. CLI `--schedule-once` 和 `--daemon`
4. 日志输出（含扫描结果、发布结果）

不做：
- B2 目标驱动（下一阶段）
- 复杂排期算法（用 Cron 表达式足够）
- 多进程/分布式（单机 SQLite 足够）

---

## 9. 检查清单

- [ ] TaskScheduler 实现
- [ ] YAML 配置读取
- [ ] CLI `--schedule-once` 支持
- [ ] CLI `--daemon` 支持
- [ ] 与 VaultWatcher 集成
- [ ] 与 PublishExecutor 集成
- [ ] 日志输出
- [ ] 文档更新

---

这份设计需要修改吗？