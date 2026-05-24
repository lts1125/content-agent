#!/usr/bin/env python3
"""
RAG 效果测试脚本

用法:
    cd /Users/lee/content-agent && source .venv/bin/activate && python test_rag.py
"""

import os
import sys

sys.path.insert(0, '.')

from content_agent.rag.indexer import VaultIndexer


def test_retrieval():
    """测试检索效果"""
    print("=" * 60)
    print("测试 1: RAG 检索效果")
    print("=" * 60)

    indexer = VaultIndexer()

    test_cases = [
        {
            "query": "MCP 协议是什么",
            "expected": "mcp",
        },
        {
            "query": "Agent 开发框架",
            "expected": "agent",
        },
        {
            "query": "抖音图文设计",
            "expected": "douyin",
        },
        {
            "query": "热点监控怎么实现",
            "expected": "trend",
        },
        {
            "query": "RAG 向量检索",
            "expected": "rag",
        },
    ]

    for case in test_cases:
        query = case["query"]
        expected = case["expected"]

        print(f"\n查询: {query}")
        results = indexer.search(query, n_results=3)

        if not results:
            print("  无结果")
            continue

        # 检查 top-1 是否包含预期关键词
        top1 = results[0]
        top1_title = top1["metadata"].get("title", "").lower()
        top1_doc = top1["document"].lower()
        matched = expected in top1_title or expected in top1_doc

        status = "命中" if matched else "未命中"
        print(f"  [{status}] top-1: {top1['metadata'].get('title', 'unknown')}")
        print(f"    距离: {top1['distance']:.4f}")
        print(f"    内容: {top1['document'][:80].replace(chr(10), ' ')}...")

        # 显示其他结果
        for r in results[1:]:
            print(f"    [{r['distance']:.4f}] {r['metadata'].get('title', 'unknown')}")


def test_cross_note():
    """测试跨笔记关联"""
    print("\n" + "=" * 60)
    print("测试 2: 跨笔记语义关联")
    print("=" * 60)

    indexer = VaultIndexer()

    # 测试：用"内容自动化"查询，看是否能找到"P0_trend_scheduler"相关笔记
    query = "内容自动化流程"
    print(f"\n查询: {query}")
    results = indexer.search(query, n_results=5)

    for r in results:
        title = r["metadata"].get("title", "unknown")
        print(f"  [{r['distance']:.4f}] {title}")


def test_rag_in_generation():
    """测试 RAG 在生成中的效果"""
    print("\n" + "=" * 60)
    print("测试 3: RAG 接入内容生成")
    print("=" * 60)

    from automation.topic_executor import TopicExecutor
    from agents.store import _get_conn

    # 列出 accepted 选题
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM topic_suggestions WHERE status = 'accepted' ORDER BY created_at DESC LIMIT ?",
        (5,),
    ).fetchall()
    conn.close()
    accepted = [dict(r) for r in rows]

    if not accepted:
        print("\n没有 accepted 选题，无法测试生成效果")
        print("建议先运行: python main.py --pick-topics")
        print("然后: python main.py --accept-topic <id>")
        return

    print(f"\n找到 {len(accepted)} 个 accepted 选题:")
    for t in accepted:
        print(f"  {t['id']}: {t['title']}")

    # 执行第一个
    topic = accepted[0]
    print(f"\n执行选题: {topic['title']}")
    print("(注意：观察输出中是否有 '【相关笔记参考】' 部分)")

    executor = TopicExecutor()
    result = executor.execute(topic["id"])

    if result["success"]:
        print(f"\n生成成功: task_id={result['task_id']}")
    else:
        print(f"\n生成失败: {result['error']}")


def main():
    print("RAG 效果测试")
    print("=" * 60)

    # 检查 Vault 是否已索引
    indexer = VaultIndexer()
    count = indexer.store.count()
    print(f"当前索引文档数: {count}")

    if count == 0:
        print("\nVault 未索引，开始索引...")
        vault_path = os.getenv("VAULT_PATH", "/Users/lee/content-agent/notes")
        indexer.index_vault(vault_path, clear_existing=True)
        print(f"索引完成: {indexer.store.count()} 条")

    # 运行测试
    test_retrieval()
    test_cross_note()
    test_rag_in_generation()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
