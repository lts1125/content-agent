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


def test_generated_history():
    """验证生成历史查询只返回带文件的 assistant 轮次"""
    print("\n【测试2.1】测试生成历史...")
    sid = "test_generated_history"
    store.clear_session(sid)

    store.save_conversation_turn(sid, "user", "写篇公众号文章")
    store.save_conversation_turn(sid, "assistant", "普通回复")
    store.save_conversation_turn(
        sid,
        "assistant",
        "已生成公众号文章",
        platforms=["gongzhonghao"],
        files=["/tmp/gongzhonghao.md"],
        task_id="chat_20260601_120000",
        memory_refs=[
            {
                "title": "MCP 笔记",
                "source": "notes/mcp.md",
                "heading": "背景",
            }
        ],
    )

    items = store.list_generated_turns(limit=5)
    matched = [i for i in items if i["session_id"] == sid]
    assert len(matched) == 1, f"期望 1 条生成历史，实际 {len(matched)} 条"
    assert matched[0]["task_id"] == "chat_20260601_120000"
    assert "gongzhonghao.md" in matched[0]["files"]
    assert "MCP 笔记" in matched[0]["memory_refs"]
    print("✅ 生成历史查询正常")

    deleted = store.clear_session(sid)
    assert deleted == 3, f"期望删除 3 条，实际 {deleted} 条"


def test_indexed_note_registry():
    """验证上传笔记索引注册表按内容 hash 去重"""
    print("\n【测试2.2】测试笔记索引去重注册表...")
    content_hash = "test_hash_001"
    source_path = "/tmp/content-agent-note.md"

    store.delete_indexed_note(content_hash)
    assert store.get_indexed_note_by_hash(content_hash) is None

    store.save_indexed_note(
        source_path=source_path,
        content_hash=content_hash,
        indexed_chunks=3,
    )
    first = store.get_indexed_note_by_hash(content_hash)
    assert first is not None, "索引记录未保存"
    assert first["source_path"] == source_path
    assert first["indexed_chunks"] == 3

    store.save_indexed_note(
        source_path="/tmp/renamed-note.md",
        content_hash=content_hash,
        indexed_chunks=5,
    )
    second = store.get_indexed_note_by_hash(content_hash)
    assert second["source_path"] == "/tmp/renamed-note.md"
    assert second["indexed_chunks"] == 5

    store.delete_indexed_note(content_hash)
    print("✅ 笔记索引去重注册表正常")


def test_publish_status_joins_generated_history():
    """验证公众号草稿箱发布状态能回显到生成历史"""
    print("\n【测试2.3】测试发布状态回写历史...")
    sid = "test_publish_status_history"
    task_id = "chat_20260601_170000"
    store.clear_session(sid)
    store.delete_publish_status(task_id, "gongzhonghao")

    store.save_conversation_turn(
        sid,
        "assistant",
        "已生成公众号文章",
        platforms=["gongzhonghao"],
        files=["output/chat/20260601_170000/gongzhonghao.md"],
        task_id=task_id,
    )
    store.save_publish_status(
        task_id=task_id,
        platform="gongzhonghao",
        status="draft_saved",
        message="已保存到草稿箱",
        details="ok",
    )

    items = store.list_generated_turns(limit=10)
    matched = [i for i in items if i["task_id"] == task_id]
    assert len(matched) == 1, f"期望 1 条发布状态历史，实际 {len(matched)} 条"
    assert matched[0]["publish_status"] == "draft_saved"
    assert matched[0]["publish_message"] == "已保存到草稿箱"

    store.delete_publish_status(task_id, "gongzhonghao")
    store.clear_session(sid)
    print("✅ 发布状态回写历史正常")


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

    # 删除
    deleted = store.delete_user_preference(uid, "preferred_tone")
    assert deleted is True
    missing_after_delete = store.get_user_preference(uid, "preferred_tone", default=None)
    assert missing_after_delete is None
    deleted_again = store.delete_user_preference(uid, "preferred_tone")
    assert deleted_again is False
    print("✅ 删除正常")

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


def test_memory_manager_skips_duplicate_note_content():
    """验证 MemoryManager 对同内容上传只写入一次向量库"""
    print("\n【测试5】测试上传笔记内容去重...")
    from agents.memory import MemoryManager

    class FakeEmbedder:
        def embed_batch(self, texts):
            return [[0.1, 0.2] for _ in texts]

    class FakeStore:
        def __init__(self):
            self.add_calls = 0

        def add(self, ids, documents, embeddings, metadatas):
            self.add_calls += 1

    class FakeIndexer:
        def __init__(self):
            self.embedder = FakeEmbedder()
            self.store = FakeStore()

        def _split_file(self, path, root):
            return [{
                "id": "chunk-1",
                "text": path.read_text(encoding="utf-8"),
                "metadata": {"source": str(path), "title": path.stem},
            }]

    with tempfile.TemporaryDirectory() as tmp_dir:
        note_path = Path(tmp_dir) / "note.md"
        note_path.write_text("# 同一篇笔记\n\n重复上传应该跳过索引。", encoding="utf-8")

        mm = MemoryManager()
        fake_indexer = FakeIndexer()
        mm._get_indexer = lambda: fake_indexer

        first = mm.index_note_result(note_path)
        second = mm.index_note_result(note_path)

        assert first.chunks == 1
        assert not first.skipped
        assert second.chunks == 0
        assert second.skipped
        assert second.reason == "duplicate"
        assert fake_indexer.store.add_calls == 1

        store.delete_indexed_note(first.content_hash)
    print("✅ 上传笔记重复内容会跳过索引")


def main():
    print("=" * 50)
    print("记忆系统验证")
    print("=" * 50)

    # 确保数据库表已创建
    store.init_db()

    try:
        test_tables()
        test_conversation_turns()
        test_generated_history()
        test_indexed_note_registry()
        test_publish_status_joins_generated_history()
        test_user_preferences()
        test_memory_manager_without_vector()
        test_memory_manager_skips_duplicate_note_content()
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
