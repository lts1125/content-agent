#!/usr/bin/env python3
"""
记忆系统验证脚本

用法:
    cd /Users/lee/content-agent && .venv/bin/python tests/test_memory.py

不依赖 gradio/sentence_transformers，只验证 SQLite 部分。
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import store


def test_tables():
    """验证表是否创建"""
    print("【测试1】检查数据库表...")
    conn = store._get_conn()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('conversation_turns', 'user_preferences')"
    ).fetchall()
    conn.close()
    names = {r["name"] for r in tables}
    assert "conversation_turns" in names, "conversation_turns 表不存在"
    assert "user_preferences" in names, "user_preferences 表不存在"
    print("✅ 两张表已创建")


def test_conversation_turns():
    """验证会话轮次 CRUD"""
    print("\n【测试2】测试会话轮次...")
    sid = "test_session_001"

    # 清理
    store.clear_session(sid)

    # 保存
    id1 = store.save_conversation_turn(sid, "user", "写篇关于 MCP 的文章", platforms=["gongzhonghao"])
    id2 = store.save_conversation_turn(sid, "assistant", "好的，正在生成...", task_id="t001")
    assert id1 > 0 and id2 > 0, "保存失败"

    # 读取
    turns = store.get_conversation_turns(sid)
    assert len(turns) == 2, f"期望 2 条，实际 {len(turns)} 条"
    assert turns[0]["role"] == "user"
    assert turns[1]["role"] == "assistant"
    assert turns[0]["platforms"] == '["gongzhonghao"]'
    print(f"✅ 保存/读取正常，共 {len(turns)} 轮")

    # 会话列表
    sessions = store.list_sessions(limit=10)
    assert any(s["session_id"] == sid for s in sessions), "会话列表中找不到测试会话"
    print("✅ 会话列表正常")

    # 清理
    deleted = store.clear_session(sid)
    assert deleted == 2, f"期望删除 2 条，实际 {deleted} 条"
    print("✅ 清理正常")


def test_user_preferences():
    """验证用户偏好 CRUD"""
    print("\n【测试3】测试用户偏好...")
    uid = "test_user"

    # 设置
    store.set_user_preference(uid, "preferred_tone", "professional", source="explicit", confidence=1.0)
    store.set_user_preference(uid, "favorite_platforms", ["gongzhonghao", "xiaohongshu"])
    print("✅ 保存偏好成功")

    # 单个读取
    tone = store.get_user_preference(uid, "preferred_tone")
    assert tone == "professional", f"期望 professional，实际 {tone}"
    print(f"✅ 单个读取: preferred_tone = {tone}")

    # 全部读取
    prefs = store.get_user_preferences(uid)
    assert "preferred_tone" in prefs
    assert "favorite_platforms" in prefs
    print(f"✅ 全部读取: {prefs}")

    # 更新
    store.set_user_preference(uid, "preferred_tone", "casual")
    tone2 = store.get_user_preference(uid, "preferred_tone")
    assert tone2 == "casual"
    print("✅ 更新正常")

    # 默认值
    missing = store.get_user_preference(uid, "nonexistent", default="default_val")
    assert missing == "default_val"
    print("✅ 默认值正常")

    # 清理
    conn = store._get_conn()
    conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()
    print("✅ 清理测试数据")


def test_memory_manager_without_vector():
    """验证 MemoryManager 的短期/长期记忆（不触发向量加载）"""
    print("\n【测试4】测试 MemoryManager 短期/长期记忆...")

    from agents.memory import MemoryManager

    mm = MemoryManager(user_id="test_mm")
    sid = "test_mm_session"

    # 清理
    mm.clear_session(sid)

    # 短期
    mm.save_turn(sid, "user", "写篇 Python 文章")
    mm.save_turn(sid, "assistant", "好的！")
    turns = mm.get_recent_turns(sid, max_tokens=4000)
    assert len(turns) == 2
    print(f"✅ 短期记忆: {len(turns)} 轮")

    # 长期
    mm.set_preference("preferred_tone", "humorous")
    mm.set_preference("favorite_platforms", ["douyin"])
    prefs = mm.get_preferences()
    assert prefs.get("preferred_tone") == "humorous"
    print(f"✅ 长期记忆: {prefs}")

    # 清理
    mm.clear_session(sid)
    conn = store._get_conn()
    conn.execute("DELETE FROM user_preferences WHERE user_id = ?", ("test_mm",))
    conn.commit()
    conn.close()
    print("✅ 清理测试数据")


def main():
    print("=" * 50)
    print("记忆系统验证")
    print("=" * 50)

    # 确保数据库表已创建
    store.init_db()

    try:
        test_tables()
        test_conversation_turns()
        test_user_preferences()
        test_memory_manager_without_vector()
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 验证异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 50)
    print("✅ 所有验证通过")
    print("=" * 50)


if __name__ == "__main__":
    main()
