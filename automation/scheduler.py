"""
任务调度器 (Task Scheduler)

基于 APScheduler 的定时任务调度，支持 Vault 扫描和队列发布。
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from automation.config import SchedulerConfig
from automation.executor import PublishExecutor
from automation.gate import PublishGate
from automation.vault_watcher import VaultWatcher
from automation.agent_controller import AgentController


class TaskScheduler:
    def __init__(self, config: Optional[SchedulerConfig] = None):
        self.config = config or SchedulerConfig.from_env()
        self.scheduler = BackgroundScheduler()

    def _get_vault_watcher(self) -> VaultWatcher:
        vault_path = self.config.vault_path or os.getenv(
            "VAULT_PATH", os.path.expanduser("~/.content_agent/vault")
        )
        return VaultWatcher(vault_path=vault_path)

    def _get_agent_controller(self, watcher: VaultWatcher) -> AgentController:
        return AgentController(watcher=watcher)

    def _get_publish_executor(self) -> PublishExecutor:
        return PublishExecutor(
            gate=PublishGate(mode="scheduled"),
            max_retries=3,
        )

    def register_tasks(self):
        self.scheduler.add_job(
            self.run_scan,
            trigger=CronTrigger.from_crontab(self.config.scan_cron),
            id="vault_scan",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.run_publish,
            trigger=CronTrigger.from_crontab(self.config.publish_cron),
            id="publish_queue",
            replace_existing=True,
        )

    def run_scan(self):
        now = datetime.now().isoformat()
        print(f"[TaskScheduler] {now} 开始扫描 Vault...")

        if not self.config.auto_generate:
            print("[TaskScheduler] auto_generate=False，跳过自动生成")
            return

        watcher = self._get_vault_watcher()
        controller = self._get_agent_controller(watcher)
        results = controller.process_inbox(watcher.inbox_path)

        if not results:
            print("[TaskScheduler] inbox 为空，无需处理")
            return

        success = sum(1 for r in results if r.get("success"))
        print(f"[TaskScheduler] 扫描完成: {success}/{len(results)} 成功")

    def run_publish(self):
        now = datetime.now().isoformat()
        print(f"[TaskScheduler] {now} 开始执行发布...")

        published_today = self._count_published_today()
        if published_today >= self.config.max_daily_publish:
            print(
                f"[TaskScheduler] 今日已发布 {published_today} 条，"
                f"达到上限 {self.config.max_daily_publish}，跳过"
            )
            return

        executor = self._get_publish_executor()
        due_items = executor._get_due_items()
        if not due_items:
            print("[TaskScheduler] 没有到期的 approved 项")
            return

        slots = self.config.max_daily_publish - published_today
        print(f"[TaskScheduler] 今日剩余发布额度: {slots}，到期项: {len(due_items)}")

        for item in due_items[:slots]:
            print(f"[TaskScheduler] 发布 {item.id} ({item.platform})...")
            result = executor.execute_one(item.id)
            if result.get("success"):
                print("   ✅ 成功")
            else:
                print(f"   ❌ 失败: {result.get('error', '未知错误')}")

    @staticmethod
    def _count_published_today() -> int:
        from agents.store import _get_conn
        conn = _get_conn()
        row = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM publish_queue
            WHERE status = 'published'
              AND published_at >= date('now', 'start of day')
              AND published_at < date('now', 'start of day', '+1 day')
            """,
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0

    def start(self):
        self.register_tasks()
        self.scheduler.start()
        print("[TaskScheduler] 调度器已启动")
        print(f"  - 扫描任务: {self.config.scan_cron}")
        print(f"  - 发布任务: {self.config.publish_cron}")

    def shutdown(self):
        self.scheduler.shutdown()
        print("[TaskScheduler] 调度器已停止")

    def run_once(self):
        """单次执行：扫描 + 发布"""
        self.run_scan()
        self.run_publish()
