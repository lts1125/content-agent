"""
Vault Watcher — 监听 inbox 目录，自动触发内容处理

使用 watchdog.observers.Observer（macOS FSEvents / Linux inotify）
"""

import os
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional, Dict, Tuple

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent


class _InboxEventHandler(FileSystemEventHandler):
    def __init__(self, watcher: "VaultWatcher"):
        self.watcher = watcher

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in (".md", ".txt"):
            return
        self.watcher._handle_file(path)


class VaultWatcher:
    def __init__(
        self,
        vault_path: str,
        inbox_dir: str = "inbox",
        on_new_note: Optional[Callable[[Path], None]] = None,
    ):
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.inbox_path = self.vault_path / inbox_dir
        self.processed_path = self.vault_path / "processed"
        self.failed_path = self.vault_path / "failed"
        self.on_new_note = on_new_note
        self._observer: Optional[Observer] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._recent_processed: Dict[Tuple[str, float], float] = {}
        self._lock = threading.Lock()

    def _ensure_dirs(self):
        self.inbox_path.mkdir(parents=True, exist_ok=True)
        self.processed_path.mkdir(parents=True, exist_ok=True)
        self.failed_path.mkdir(parents=True, exist_ok=True)

    def _is_recently_processed(self, path: Path) -> bool:
        mtime = path.stat().st_mtime
        key = (path.name, mtime)
        with self._lock:
            self._cleanup_recent_cache()
            return key in self._recent_processed

    def _mark_processed(self, path: Path):
        mtime = path.stat().st_mtime
        now = time.time()
        with self._lock:
            self._recent_processed[(path.name, mtime)] = now
            self._cleanup_recent_cache()

    def _cleanup_recent_cache(self):
        cutoff = time.time() - 600  # 10 分钟
        expired = [k for k, v in self._recent_processed.items() if v < cutoff]
        for k in expired:
            del self._recent_processed[k]

    def _handle_file(self, path: Path):
        if not path.exists():
            return
        if self._is_recently_processed(path):
            return
        self._mark_processed(path)

        # 延迟 1 秒，避免大文件正在写入中
        time.sleep(1)
        if not path.exists():
            return

        if self.on_new_note:
            # 回调负责全部处理逻辑（生成 + 入库 + 移动文件）
            # VaultWatcher 只负责检测和触发，不处理文件生命周期
            self.on_new_note(path)

    def _scan_existing(self):
        """启动时扫描 inbox 已有文件"""
        if not self.inbox_path.exists():
            return
        files = sorted(self.inbox_path.iterdir())
        for f in files:
            if f.is_file() and f.suffix.lower() in (".md", ".txt"):
                self._handle_file(f)

    def _move_to(self, src: Path, dest_dir: Path) -> Path:
        """移动文件到目标目录，如有冲突则加时间戳后缀"""
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = dest_dir / f"{src.stem}_{timestamp}{src.suffix}"
        shutil.move(str(src), str(dest))
        return dest

    def move_to_processed(self, src: Path) -> Path:
        return self._move_to(src, self.processed_path)

    def move_to_failed(self, src: Path) -> Path:
        return self._move_to(src, self.failed_path)

    def start(self):
        """阻塞启动监听"""
        self._ensure_dirs()
        self._stop_event.clear()

        # 先处理已有文件
        self._scan_existing()

        handler = _InboxEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.inbox_path), recursive=False)
        self._observer.start()
        print(f"[VaultWatcher] 开始监听: {self.inbox_path}")

        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(1)
        finally:
            self._observer.stop()
            self._observer.join()
            self._observer = None

    def start_background(self) -> threading.Thread:
        """在后台线程启动监听，返回 Thread 对象"""
        self._stop_event.clear()
        t = threading.Thread(target=self.start, daemon=True)
        t.start()
        self._thread = t
        return t

    def stop(self):
        """停止监听"""
        self._stop_event.set()
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
