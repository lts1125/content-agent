"""
搜索增强模块 - 在生成文案前自动搜索相关背景资料

支持的搜索引擎：
- DuckDuckGo (默认，免费，无需 API key)
- Tavily (需要 TAVILY_API_KEY，效果更好)
"""

import os
from typing import List

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False


def duckduckgo_search(query: str, max_results: int = 5) -> List[dict]:
    """DuckDuckGo 搜索，免费，无需 API key"""
    if not HAS_DDGS:
        raise ImportError("请先安装 ddgs: pip install ddgs")

    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=max_results)
        return [
            {"title": r.get("title", ""), "href": r.get("href", ""), "body": r.get("body", "")}
            for r in results
        ]


def tavily_search(query: str, max_results: int = 5) -> List[dict]:
    """Tavily 搜索，AI 专用搜索 API"""
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
            "include_answer": False,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    return [
        {"title": r.get("title", ""), "href": r.get("url", ""), "body": r.get("content", "")}
        for r in data.get("results", [])
    ]


def extract_keywords_with_llm(notes_text: str, keyword_agent) -> List[str]:
    """
    用 LLM 从笔记中提取搜索关键词

    比启发式提取更精准，能捕捉技术概念和专业术语。
    """
    prompt = f"""从以下技术笔记中提取 2-3 个最适合搜索的关键词或短语。

要求：
- 关键词应该是具体的技术概念、框架名、方法论，而不是描述性语句
- 例如「PydanticAI 教程」「AI Agent 框架对比」「内容多平台分发工具」
- 避免太通用的词，如「技术」「学习」「方法」
- 每个关键词 3-8 个字
- 只返回关键词列表，不要解释

笔记内容：
---
{notes_text[:800]}
---

请返回 JSON 格式：{{"keywords": ["关键词1", "关键词2"]}}
"""

    try:
        result = keyword_agent.run_sync(prompt)
        import json
        text = result.output.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        data = json.loads(text)
        keywords = data.get("keywords", [])
        if keywords and isinstance(keywords, list):
            return [k for k in keywords if isinstance(k, str) and len(k) >= 3]
    except Exception as e:
        print(f"   ⚠️ LLM 关键词提取失败: {e}")

    return heuristic_extract_keywords(notes_text)


def heuristic_extract_keywords(text: str, max_keywords: int = 2) -> List[str]:
    """启发式关键词提取（回退方案）"""
    lines = text.strip().split("\n")
    candidates = []

    for line in lines[:20]:
        line = line.strip()
        if len(line) < 5 or line.startswith(("#", "-", "*", "```", "|", "[", "!", "【", "】")):
            continue
        clean = line[:40].replace("我", "").replace("了", "").replace("的", "")
        if len(clean) >= 8:
            candidates.append(clean)

    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    return unique[:max_keywords] if unique else [text[:50]]


def research_notes(
    notes_text: str,
    search_engine: str = "duckduckgo",
    max_results: int = 3,
    verbose: bool = True,
    keywords: List[str] = None,
) -> str:
    """
    对笔记进行搜索增强

    Args:
        notes_text: 原始笔记内容
        search_engine: 搜索引擎
        max_results: 最大返回结果数
        verbose: 是否打印过程
        keywords: 传入的关键词（如为 None 则启发式提取）
    """
    if keywords is None:
        keywords = heuristic_extract_keywords(notes_text)

    if verbose:
        print(f"\n🔍 开始搜索增强，关键词: {keywords}")

    all_results = []
    for query in keywords[:2]:
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

    # 按 href 去重
    seen = set()
    unique_results = []
    for r in all_results:
        if r["href"] not in seen:
            seen.add(r["href"])
            unique_results.append(r)

    # 拼接搜索结果
    research_section = (
        "【以下是通过搜索补充的相关背景资料，"
        "供改写时参考。请基于这些资料丰富内容，"
        "但保持原笔记的核心观点和个人体验】\n\n"
    )

    for i, r in enumerate(unique_results[:max_results], 1):
        body = r["body"][:300] if r["body"] else "暂无摘要"
        research_section += f"{i}. {r['title']}\n   摘要: {body}...\n\n"

    enhanced_notes = research_section + "--- 原始笔记 ---\n\n" + notes_text

    if verbose:
        print(f"   ✅ 搜索增强完成，拼接了 {len(unique_results[:max_results])} 条资料")

    return enhanced_notes
