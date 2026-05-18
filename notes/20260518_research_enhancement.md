# 搜索增强功能实现笔记

## 背景/需求

Roadmap P0-6：用户的笔记可能比较简略，缺少背景信息。如果能在生成文案前自动搜索相关资料并注入 prompt，文案质量会更高，尤其是公众号的深度文章。

## 设计思路

1. **搜索引擎抽象** — 支持多个搜索后端，默认 DuckDuckGo（免费），可选 Tavily（效果更好）
2. **关键词提取** — 用 LLM 从笔记中提取 2-3 个最适合搜索的关键词，比规则提取更准确
3. **结果注入** — 将搜索结果拼接成文本，注入到生成 Agent 的 system prompt 中作为背景资料

## 核心实现

### 1. 搜索引擎接口

```python
def duckduckgo_search(query: str, max_results: int = 5) -> List[dict]:
    """DuckDuckGo 搜索，免费，无需 API key"""
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=max_results)
        return [
            {"title": r["title"], "href": r["href"], "body": r["body"]}
            for r in results
        ]

def tavily_search(query: str, max_results: int = 5) -> List[dict]:
    """Tavily 搜索，AI 专用搜索 API"""
    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": os.getenv("TAVILY_API_KEY"),
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        },
        timeout=30,
    )
    # 返回 ...
```

### 2. 关键词提取（LLM 驱动）

```python
def extract_keywords_with_llm(notes_text: str, keyword_agent) -> List[str]:
    prompt = """从以下技术笔记中提取 2-3 个最适合搜索的关键词或短语。

要求：
- 关键词应该是具体的技术概念、框架名、方法论
- 避免太通用的词，如「技术」「学习」「方法」
- 每个关键词 3-8 个字
- 只返回 JSON 格式：{"keywords": [...]}
"""
    result = keyword_agent.run_sync(prompt)
    # 解析 JSON ...
```

### 3. 研究注入（research_notes）

```python
def research_notes(notes_text: str, search_engine="duckduckgo", max_results=5):
    # 1. 提取关键词
    keywords = extract_keywords_with_llm(notes_text, keyword_agent)
    
    # 2. 搜索每个关键词
    all_results = []
    for kw in keywords:
        results = search_fn(kw, max_results)
        all_results.extend(results)
    
    # 3. 拼接成背景资料文本
    context = "\n\n".join(
        f"[来源: {r['title']}]\n{r['body'][:300]}"
        for r in all_results
    )
    return context
```

### 4. 与生成流程集成

在 `generate_content` 中，如果 `enable_research=True`：

```python
if enable_research:
    research_context = research_notes(note_text, search_engine)
    # 将搜索结果注入 system prompt
    enhanced_prompt = f"""以下是相关背景资料（来自网络搜索），请参考这些信息让文案更深入：

{research_context}

---

原始笔记：
{note_text}
"""
```

## 踩坑记录

1. **DuckDuckGo 搜索可能被限速** — 频繁调用时会遇到 rate limit。解决：只搜索前 2-3 个关键词，每个只取前 5 条结果。

2. **Tavily 需要单独的 API Key** — 需要用户另外注册。在 UI 中增加了 Tavily Key 的配置入口，不填则自动 fallback 到 DuckDuckGo。

3. **搜索结果过长会撑爆 token 上限** — 每条结果只取前 300 字，总背景资料控制在 2000-3000 token 以内。

4. **关键词提取可能失败** — LLM 有时不按指定格式返回 JSON。解决：增加强壮的 JSON 解析逻辑（处理 ```json 代码块、尾部多余字符等）。

5. **搜索增强与原笔记的权重** — 有时候搜索结果会"带偏"文案方向，要在 prompt 中明确告诉 LLM"参考但不要偏离原笔记主题"。

## 使用方法

CLI：
```bash
# 使用 DuckDuckGo（免费）
python main.py -i notes.md -r

# 使用 Tavily（效果更好，需配置 TAVILY_API_KEY）
python main.py -i notes.md -r --search-engine tavily
```

Web UI：
- 勾选「启用搜索增强」
- 选择搜索引擎（DuckDuckGo / Tavily）

## 下一步

- 考虑支持更多搜索引擎（如 Google Custom Search、Bing API）
- 搜索结果缓存（相同关键词一天内不重复搜索）
