"""
搜索增强模块 - 在生成文案前自动搜索相关背景资料

支持的搜索引擎：
- DuckDuckGo (默认，免费，无需 API key)
- Tavily (需要 TAVILY_API_KEY，效果更好)
"""

import os
from typing import List, Optional

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False


def duckduckgo_search(query: str, max_results: int = 5) -> List[dict]:
    """
    DuckDuckGo 搜索，免费，无需 API key

    Args:
        query: 搜索关键词
        max_results: 最大返回结果数

    Returns:
        搜索结果列表，每项包含 title, href, body
    """
    if not HAS_DDGS:
        raise ImportError(
            "请先安装 duckduckgo-search: pip install duckduckgo-search"
        )

    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=max_results)
        return [
            {
                "title": r.get("title", ""),
                "href": r.get("href", ""),
                "body": r.get("body", ""),
            }
            for r in results
        ]


def tavily_search(query: str, max_results: int = 5) -> List[dict]:
    """
    Tavily 搜索，AI 专用搜索 API，结果质量更高

    需要设置环境变量: TAVILY_API_KEY
    免费额度: 1000 credits/月
    """
    try:
        import requests
    except ImportError:
        raise ImportError("请先安装 requests: pip install requests")

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "Tavily 搜索需要设置 TAVILY_API_KEY 环境变量\n"
            "获取方式: https://app.tavily.com/home"
        )

    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    return [
        {
            "title": r.get("title", ""),
            "href": r.get("url", ""),
            "body": r.get("content", ""),
        }
        for r in data.get("results", [])
    ]


def extract_keywords(text: str, max_keywords: int = 2) -> List[str]:
    """
    从笔记中提取搜索关键词

    策略：取标题/主题句，简化为 3-6 个词的短语，更适合搜索。
    """
    lines = text.strip().split("\n")
    candidates = []

    for line in lines[:20]:
        line = line.strip()
        # 过滤掉格式行
        if len(line) < 5 or line.startswith(("#", "-", "*", "```", "|", "[", "!", "【", "】")):
            continue

        # 去掉常见语气词，提取实体词
        # 简单策略：取前 15-30 字符作为关键词
        clean = line[:40].replace("我", "").replace("了", "").replace("的", "")
        if len(clean) >= 8:
            candidates.append(clean)

    # 去重并取前 N 个
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    if unique:
        return unique[:max_keywords]
    else:
        # 备用：取前 50 字
        return [text[:50]]


def research_notes(
    notes_text: str,
    search_engine: str = "duckduckgo",
    max_results: int = 3,
    verbose: bool = True,
) -> str:
    """
    对笔记进行搜索增强，返回拼接了搜索结果的增强笔记

    Args:
        notes_text: 原始笔记内容
        search_engine: 搜索引擎，duckduckgo 或 tavily
        max_results: 每次搜索最大返回结果数
        verbose: 是否打印搜索过程

    Returns:
        增强后的笔记（原始笔记 + 搜索到的背景资料）
    """
    queries = extract_keywords(notes_text)

    if verbose:
        print(f"\n🔍 开始搜索增强，提取关键词: {queries}")

    all_results = []
    for query in queries:
        try:
            if search_engine == "tavily":
                results = tavily_search(query, max_results=max_results)
            else:
                results = duckduckgo_search(query, max_results=max_results)
            all_results.extend(results)
            if verbose:
                print(f"   ✅ '{query[:30]}...' 搜到 {len(results)} 条结果")
        except Exception as e:
            if verbose:
                print(f"   ⚠️ '{query[:30]}...' 搜索失败: {e}")
            continue

    if not all_results:
        if verbose:
            print("   ⚠️ 未搜索到任何结果，使用原始笔记")
        return notes_text

    # 去重（按 href 去重）
    seen = set()
    unique_results = []
    for r in all_results:
        if r["href"] not in seen:
            seen.add(r["href"])
            unique_results.append(r)

    # 拼接搜索结果到笔记前面
    research_section = (
        "【以下是通过搜索补充的相关背景资料，"
        "供改写时参考。请基于这些资料丰富内容，"
        "但保持原笔记的核心观点和个人体验】\n\n"
    )

    for i, r in enumerate(unique_results[:max_results], 1):
        body = r["body"][:250] if r["body"] else "暂无摘要"
        research_section += (
            f"{i}. {r['title']}\n"
            f"   摘要: {body}...\n\n"
        )

    enhanced_notes = research_section + "--- 原始笔记 ---\n\n" + notes_text

    if verbose:
        print(f"   ✅ 搜索增强完成，拼接了 {len(unique_results[:max_results])} 条资料")

    return enhanced_notes
