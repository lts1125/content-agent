"""
搜索工具
"""

from .base import BaseTool, ToolResult


class SearchTool(BaseTool):
    """搜索工具 - 搜索网络资料"""

    def __init__(self):
        super().__init__(
            name="search",
            description="搜索网络资料，获取最新信息。参数: query(搜索关键词)"
        )

    def execute(self, query: str) -> ToolResult:
        """执行搜索"""
        try:
            # 使用项目内的搜索模块
            from content_agent.research import duckduckgo_search

            items = duckduckgo_search(query, max_results=3)

            summaries = []
            for item in items:
                title = item.get("title", "")
                desc = item.get("body", "")
                url = item.get("href", "")
                summaries.append(f"[{title}] {desc}\nURL: {url}")

            return ToolResult(
                success=True,
                data="\n\n".join(summaries) if summaries else "未找到相关结果",
            )
        except Exception as e:
            # 降级：使用 requests 直接调用搜索 API
            try:
                import requests
                # 使用 DuckDuckGo 或 Bing API
                response = requests.get(
                    "https://duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10
                )
                return ToolResult(
                    success=True,
                    data=f"搜索 '{query}' 结果（DuckDuckGo）:\n{response.text[:500]}..."
                )
            except Exception as e2:
                return ToolResult(
                    success=False,
                    data="",
                    error=f"搜索失败: {str(e)}; 降级也失败: {str(e2)}"
                )
