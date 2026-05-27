# MCP 搜索增强实现记录

## 背景/需求

前面实现了质量检查和重试机制后，用户说"E，要接入 MCP 工具协议，自动搜索补充资料"。

目标是让 Agent 在生成文案前，自动搜索相关背景资料，让输出的内容更有深度。

## 设计思路

最开始想的是真正的 MCP 协议集成：用 `mcp` Python SDK 做 Client，连接到 Tavily MCP Server，然后让 PydanticAI Agent 通过 tool calling 调用。

但调研后发现：
1. MCP 对于单脚本工具来说太重了（需要启动 MCP Server、处理 stdio/HTTP transport、async 客户端）
2. Tavily MCP Server 实际上也只是封装了 Tavily API，跟直接调用 API 效果一样
3. 直接调用 API 更简单、更可靠、更容易维护

**最终方案**：只做"搜索增强"功能，不纠缠协议层。在生成文案前，程序自动搜索相关资料并拼接到笔记前面。

```
读取笔记 → 提取关键词 → 搜索相关资料 → 拼接到笔记 → 生成三平台文案
```

## 核心实现

### 1. 新增模块 `content_agent/research.py`

封装两种搜索引擎：

**DuckDuckGo** (默认)：免费，无需 API key
```python
from ddgs import DDGS

with DDGS() as ddgs:
    results = ddgs.text(query, max_results=5)
```

**Tavily** (可选)：AI 专用搜索，效果更好，需 `TAVILY_API_KEY`
```python
requests.post("https://api.tavily.com/search", json={
    "api_key": api_key,
    "query": query,
    "max_results": max_results,
    "search_depth": "basic",
})
```

**关键词提取**：不用 LLM (省 token)，用启发式方法提取：
- 取前 20 行非格式化文本
- 去掉"我"、"了"、"的"等常见词
- 去重后取前 2 个作为搜索查询

**搜索增强主函数** `research_notes()`：
- 接收原始笔记文本
- 提取关键词搜索
- 去重并拼接搜索结果到笔记前面
- 搜索失败时自动回退到原始笔记

### 2. 修改 `main.py`

新增 CLI 参数：
- `-r, --research` 启用搜索增强
- `--search-engine` 选择引擎（duckduckgo / tavily）

在读取笔记后、生成文案前插入搜索步骤：
```python
if args.research:
    raw_notes = research_notes(raw_notes, search_engine=args.search_engine)
```

### 3. 配置更新

`.env.example` 新增 Tavily 配置说明：
```
TAVILY_API_KEY=tvly-you...-key
```

## 踩坑记录

1. **`duckduckgo_search` 包已被弃用**：安装时报 `RuntimeWarning: This package has been renamed to ddgs!`，需改用 `pip install ddgs`，导入也改为 `from ddgs import DDGS`。

2. **中文长句搜索效果差**：初始关键词是整句中文，DuckDuckGo 返回 0 条结果。优化后去掉常见语气词、提取短片段，效果改善。

3. **`一个文章发三个平台，花 2 小时。`这种带标点的句子搜索效果也不好**，后续可以考虑用 LLM 提取关键词（更准确但花 token）。

4. **DuckDuckGo 搜索偶尔报错 `Unsupported protocol version 0x304`**：多次搜索时偶尔出现，原因是网络或库本身的稳定性问题。代码里已加 try/except 处理，单个查询失败不影响整体。

## 使用方法

```bash
# 启用搜索增强（默认 DuckDuckGo，无需 key）
python main.py -i notes/my_note.md -r

# 用 Tavily （需先设置 TAVILY_API_KEY）
python main.py -i notes/my_note.md -r --search-engine tavily
```

## 测试结果

用 `notes/ai_invades_daily.md` 测试：
- 关键词提取：2 个查询
- 第一个查询偶尔失败，第二个成功返回 3 条结果
- 拼接资料后生成，质量检查通过（82/100）
- 生成的文案引用了搜索到的背景信息

## 下一步

- [​]用 LLM 提取更精准的搜索关键词
- [​]支持多次搜索查询的并行执行
- [​]考虑真正的 MCP 协议集成（如果有更复杂的工具调用需求）
