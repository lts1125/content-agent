"""
调度配置 (Scheduler Config)

支持 YAML 文件 + 环境变量读取。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class SchedulerConfig:
    scan_cron: str = "0 9 * * *"
    publish_cron: str = "0 10,14,20 * * *"
    vault_path: str = ""
    platforms: List[str] = field(default_factory=list)
    auto_generate: bool = True
    max_daily_publish: int = 3
    # 热点监控配置
    trend_check_cron: str = "*/30 * * * *"
    trend_keywords: List[str] = field(default_factory=list)
    trend_sources: List[str] = field(default_factory=lambda: ["weibo"])
    # 热点评估配置
    trend_min_confidence: int = 60  # LLM 评估最低置信度

    @classmethod
    def from_yaml(cls, path: str) -> "SchedulerConfig":
        p = Path(path).expanduser()
        if not p.exists():
            return cls()
        if not HAS_YAML:
            print("[SchedulerConfig] PyYAML 未安装，使用默认配置")
            return cls()
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        raw_platforms = data.get("platforms", [])
        platforms = [str(p).strip() for p in raw_platforms if p] if raw_platforms else []
        
        raw_trend_kw = data.get("trend_keywords", [])
        trend_keywords = [str(k).strip() for k in raw_trend_kw if k] if raw_trend_kw else []
        
        raw_trend_sources = data.get("trend_sources", ["weibo"])
        trend_sources = [str(s).strip() for s in raw_trend_sources if s] if raw_trend_sources else ["weibo"]
        
        return cls(
            scan_cron=data.get("scan_cron", "0 9 * * *"),
            publish_cron=data.get("publish_cron", "0 10,14,20 * * *"),
            vault_path=data.get("vault_path", ""),
            platforms=platforms,
            auto_generate=data.get("auto_generate", True),
            max_daily_publish=data.get("max_daily_publish", 3),
            trend_check_cron=data.get("trend_check_cron", "*/30 * * * *"),
            trend_keywords=trend_keywords,
            trend_sources=trend_sources,
            trend_min_confidence=data.get("trend_min_confidence", 60),
        )

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        vault = os.getenv("VAULT_PATH", "")
        raw_platforms = os.getenv("AGENT_DEFAULT_PLATFORMS", "")
        platforms = [p.strip() for p in raw_platforms.split(",") if p.strip()] if raw_platforms else []
        
        # 热点监控配置
        raw_trend_kw = os.getenv("AGENT_TREND_KEYWORDS", "")
        trend_keywords = [k.strip() for k in raw_trend_kw.split(",") if k.strip()] if raw_trend_kw else []
        
        raw_trend_sources = os.getenv("AGENT_TREND_SOURCES", "weibo")
        trend_sources = [s.strip() for s in raw_trend_sources.split(",") if s.strip()]
        
        return cls(
            scan_cron=os.getenv("AGENT_SCAN_CRON", "0 9 * * *"),
            publish_cron=os.getenv("AGENT_PUBLISH_CRON", "0 10,14,20 * * *"),
            vault_path=vault,
            platforms=platforms,
            auto_generate=os.getenv("AGENT_AUTO_GENERATE", "true").lower() in ("1", "true", "yes", "on"),
            max_daily_publish=int(os.getenv("AGENT_MAX_DAILY_PUBLISH", "3")),
            trend_check_cron=os.getenv("AGENT_TREND_CRON", "*/30 * * * *"),
            trend_keywords=trend_keywords,
            trend_sources=trend_sources,
            trend_min_confidence=int(os.getenv("AGENT_TREND_MIN_CONFIDENCE", "60")),
        )
