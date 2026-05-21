"""
配置模板管理 — 内置 + 用户自定义模板

存储路径: ~/.content_agent/templates.json
"""

import json
import os
from pathlib import Path
from typing import Any, Optional


DEFAULT_BUILT_INS = {
    "xiaohongshu_hot": {
        "name": "小红书爆款",
        "platforms": ["小红书"],
        "enable_research": True,
        "search_engine": "duckduckgo",
        "style": "情绪共鸣",
        "batch_mode": False,
    },
    "all_platform_pro": {
        "name": "三平台全覆盖",
        "platforms": ["小红书", "公众号", "抖音"],
        "enable_research": True,
        "search_engine": "duckduckgo",
        "style": "专业干货",
        "batch_mode": False,
    },
    "douyin_casual": {
        "name": "抖音口播",
        "platforms": ["抖音"],
        "enable_research": False,
        "search_engine": "duckduckgo",
        "style": "轻松口语",
        "batch_mode": False,
    },
    "gongzhonghao_deep": {
        "name": "公众号长文",
        "platforms": ["公众号"],
        "enable_research": True,
        "search_engine": "tavily",
        "style": "专业干货",
        "batch_mode": False,
    },
}


def _storage_path() -> Path:
    d = Path.home() / ".content_agent"
    d.mkdir(parents=True, exist_ok=True)
    return d / "templates.json"


def _load_raw() -> dict:
    p = _storage_path()
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def list_templates() -> dict[str, dict[str, Any]]:
    """返回所有模板 {template_id: {name, ...}}"""
    raw = _load_raw()
    result = {}
    # 内置模板
    for tid, cfg in DEFAULT_BUILT_INS.items():
        result[tid] = cfg
    # 用户模板覆盖同名内置
    for tid, cfg in raw.get("user", {}).items():
        result[tid] = cfg
    return result


def get_template(template_id: str) -> Optional[dict[str, Any]]:
    """获取单个模板的完整配置"""
    all_t = list_templates()
    return all_t.get(template_id)


def save_user_template(template_id: str, config: dict) -> str:
    """保存用户自定义模板，返回状态消息"""
    if template_id in DEFAULT_BUILT_INS:
        return "❌ 不能使用内置模板 ID"

    raw = _load_raw()
    if "user" not in raw:
        raw["user"] = {}

    raw["user"][template_id] = config

    try:
        with open(_storage_path(), "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        return f"✅ 模板已保存: {config.get('name', template_id)}"
    except Exception as e:
        return f"❌ 保存失败: {e}"


def delete_user_template(template_id: str) -> str:
    """删除用户自定义模板"""
    if template_id in DEFAULT_BUILT_INS:
        return "❌ 不能删除内置模板"

    raw = _load_raw()
    if "user" not in raw or template_id not in raw["user"]:
        return "❌ 模板不存在"

    del raw["user"][template_id]
    try:
        with open(_storage_path(), "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        return "✅ 模板已删除"
    except Exception as e:
        return f"❌ 删除失败: {e}"
