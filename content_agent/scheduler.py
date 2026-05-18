"""
定时任务调度器 — 基于 schedule 库

功能：
- 按计划自动生成文案（每天/每周固定时间）
- 配置持久化到 ~/.content_agent/schedule.json
- 日志保存到 ~/.content_agent/logs/
- Web UI 中可管理（增删改查、立即执行）

安装依赖：
    pip install schedule
"""

import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import schedule
except ImportError:
    schedule = None


@dataclass
class ScheduledTask:
    id: str
    name: str
    input_dir: str
    output_dir: str
    hour: int
    minute: int
    weekdays: list[int]          # 0=周一, 6=周日；空列表=每天
    enabled: bool
    last_run: Optional[str] = None
    last_status: Optional[str] = None


class TaskScheduler:
    CONFIG_DIR = Path.home() / ".content_agent"
    CONFIG_FILE = CONFIG_DIR / "schedule.json"
    LOG_DIR = CONFIG_DIR / "logs"

    def __init__(self):
        if schedule is None:
            raise ImportError(
                "定时任务功能需要 schedule 库，请运行: pip install schedule"
            )
        self.tasks: dict[str, ScheduledTask] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._load()

    # --------------------- 配置持久化 ---------------------
    def _load(self):
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for t in data.get("tasks", []):
                        # 兼容旧字段
                        if "weekdays" not in t:
                            t["weekdays"] = []
                        task = ScheduledTask(**t)
                        self.tasks[task.id] = task
                        if task.enabled:
                            self._schedule_task(task)
            except Exception as e:
                print(f"[定时任务] 加载配置失败: {e}")

    def _save(self):
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {"tasks": [asdict(t) for t in self.tasks.values()]}
        with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # --------------------- 调度注册 ---------------------
    def _schedule_task(self, task: ScheduledTask):
        """把单个任务注册到 schedule"""
        def job():
            # 在线程中执行，避免阻塞调度循环
            threading.Thread(
                target=self._run_task,
                args=(task.id,),
                daemon=True,
            ).start()

        time_str = f"{task.hour:02d}:{task.minute:02d}"
        if task.weekdays:
            day_names = [
                "monday", "tuesday", "wednesday",
                "thursday", "friday", "saturday", "sunday",
            ]
            for wd in task.weekdays:
                getattr(schedule.every(), day_names[wd]).at(time_str).do(job)
        else:
            schedule.every().day.at(time_str).do(job)

    # --------------------- 任务执行 ---------------------
    def _run_task(self, task_id: str):
        """执行一次生成任务"""
        task = self.tasks.get(task_id)
        if not task or not task.enabled:
            return

        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = self.LOG_DIR / f"{task.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        task.last_run = datetime.now().isoformat()

        try:
            input_path = Path(task.input_dir).expanduser()

            # 判断是文件还是目录：文件则只处理该文件，目录则遍历
            if input_path.is_file():
                unique_files = [input_path]
            else:
                note_files = []
                for ext in ("*.md", "*.txt"):
                    note_files.extend(input_path.glob(ext))
                    note_files.extend(input_path.rglob(ext))
                seen = set()
                unique_files = []
                for p in note_files:
                    sp = str(p)
                    if sp not in seen:
                        seen.add(sp)
                        unique_files.append(p)

            if not unique_files:
                task.last_status = "no_notes"
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().isoformat()}] 无笔记文件\n")
                self._save()
                return

            # 组装命令
            project_root = Path(__file__).parent.parent
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "-i", str(input_path), "-o", task.output_dir]
            else:
                cmd = [sys.executable, "-m", "main", "-i", str(input_path), "-o", task.output_dir]

            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] 启动: {task.name}\n")
                f.write(f"命令: {' '.join(cmd)}\n")
                f.write(f"笔记: {len(unique_files)} 个\n\n")

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=project_root,
                )
                f.write(result.stdout)
                if result.stderr:
                    f.write("\n[STDERR]\n")
                    f.write(result.stderr)
                f.write(f"\n退出码: {result.returncode}\n")

            task.last_status = "success" if result.returncode == 0 else f"failed({result.returncode})"

        except Exception as e:
            task.last_status = f"error: {e}"
            try:
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().isoformat()}] 异常: {e}\n")
            except Exception:
                pass

        self._save()

    # --------------------- 公共接口 ---------------------
    def add_task(
        self,
        name: str,
        input_dir: str,
        output_dir: str,
        hour: int,
        minute: int,
        weekdays: list[int],
    ) -> str:
        task_id = f"task_{int(time.time() * 1000)}"
        task = ScheduledTask(
            id=task_id,
            name=name or "未命名任务",
            input_dir=input_dir or "notes",
            output_dir=output_dir or "output",
            hour=hour,
            minute=minute,
            weekdays=weekdays,
            enabled=True,
        )
        self.tasks[task_id] = task
        self._schedule_task(task)
        self._save()
        return task_id

    def remove_task(self, task_id: str) -> bool:
        if task_id in self.tasks:
            del self.tasks[task_id]
            schedule.clear()
            for t in self.tasks.values():
                if t.enabled:
                    self._schedule_task(t)
            self._save()
            return True
        return False

    def toggle_task(self, task_id: str) -> Optional[bool]:
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.enabled = not task.enabled
            schedule.clear()
            for t in self.tasks.values():
                if t.enabled:
                    self._schedule_task(t)
            self._save()
            return task.enabled
        return None

    def list_tasks(self) -> list[dict]:
        return [asdict(t) for t in self.tasks.values()]

    def run_now(self, task_id: str) -> bool:
        if task_id in self.tasks:
            threading.Thread(
                target=self._run_task,
                args=(task_id,),
                daemon=True,
            ).start()
            return True
        return False

    def get_task(self, task_id: str) -> Optional[dict]:
        t = self.tasks.get(task_id)
        return asdict(t) if t else None

    # --------------------- 生命周期 ---------------------
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[定时任务] 调度器已启动，共 {len([t for t in self.tasks.values() if t.enabled])} 个任务")

    def _loop(self):
        while self._running:
            schedule.run_pending()
            time.sleep(30)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def is_running(self) -> bool:
        return self._running
