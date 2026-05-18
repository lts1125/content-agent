"""
内容日历管理 — 记录和跟踪内容发布计划

数据持久化到 ~/.content_agent/calendar.json
"""

import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class CalendarEntry:
    id: str
    title: str
    topic: str
    platforms: list[str]
    scheduled_date: str       # YYYY-MM-DD
    status: str               # draft, scheduled, generated, published
    note_file: str            # 关联笔记文件路径
    created_at: str
    updated_at: str


class ContentCalendar:
    CONFIG_DIR = Path.home() / ".content_agent"
    DATA_FILE = CONFIG_DIR / "calendar.json"

    STATUS_MAP = {
        "草稿": "draft",
        "已排期": "scheduled",
        "已生成": "generated",
        "已发布": "published",
    }
    STATUS_MAP_REVERSE = {v: k for k, v in STATUS_MAP.items()}

    def __init__(self):
        self.entries: dict[str, CalendarEntry] = {}
        self._load()

    def _load(self):
        if self.DATA_FILE.exists():
            try:
                with open(self.DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for e in data.get("entries", []):
                        entry = CalendarEntry(**e)
                        self.entries[entry.id] = entry
            except Exception as e:
                print(f"[内容日历] 加载配置失败: {e}")

    def _save(self):
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {"entries": [asdict(e) for e in self.entries.values()]}
        with open(self.DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add(
        self,
        title: str,
        topic: str,
        platforms: list[str],
        scheduled_date: str,
        note_file: str,
        status: str = "draft",
    ) -> str:
        entry_id = f"cal_{int(time.time() * 1000)}"
        now = datetime.now().isoformat()
        entry = CalendarEntry(
            id=entry_id,
            title=title or "未命名",
            topic=topic or "",
            platforms=platforms,
            scheduled_date=scheduled_date or datetime.now().strftime("%Y-%m-%d"),
            status=self.STATUS_MAP.get(status, status),
            note_file=note_file or "",
            created_at=now,
            updated_at=now,
        )
        self.entries[entry_id] = entry
        self._save()
        return entry_id

    def update(self, entry_id: str, **kwargs) -> bool:
        if entry_id not in self.entries:
            return False
        entry = self.entries[entry_id]
        for k, v in kwargs.items():
            if hasattr(entry, k):
                if k == "status":
                    v = self.STATUS_MAP.get(v, v)
                setattr(entry, k, v)
        entry.updated_at = datetime.now().isoformat()
        self._save()
        return True

    def delete(self, entry_id: str) -> bool:
        if entry_id in self.entries:
            del self.entries[entry_id]
            self._save()
            return True
        return False

    def list_entries(
        self,
        filter_status: Optional[str] = None,
        filter_date_from: Optional[str] = None,
        filter_date_to: Optional[str] = None,
    ) -> list[dict]:
        entries = list(self.entries.values())
        if filter_status:
            code = self.STATUS_MAP.get(filter_status, filter_status)
            entries = [e for e in entries if e.status == code]
        if filter_date_from:
            entries = [e for e in entries if e.scheduled_date >= filter_date_from]
        if filter_date_to:
            entries = [e for e in entries if e.scheduled_date <= filter_date_to]
        return [
            {
                **asdict(e),
                "status_display": self.STATUS_MAP_REVERSE.get(e.status, e.status),
            }
            for e in sorted(entries, key=lambda x: (x.scheduled_date, x.created_at))
        ]

    def get_today_entries(self) -> list[dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.list_entries(filter_date_from=today, filter_date_to=today)

    def get_upcoming(self, days: int = 7) -> list[dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        return self.list_entries(filter_date_from=today, filter_date_to=future)

    def get_entry(self, entry_id: str) -> Optional[dict]:
        e = self.entries.get(entry_id)
        if e:
            return {**asdict(e), "status_display": self.STATUS_MAP_REVERSE.get(e.status, e.status)}
        return None
