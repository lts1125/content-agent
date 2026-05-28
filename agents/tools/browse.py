"""
浏览工具
"""

from .base import BaseTool, ToolResult


class BrowseTool(BaseTool):
    """浏览工具 - 读取网页内容"""

    def __init__(self):
        super().__init__(
            name="browse",
            description="浏览网页内容，获取详细信息。参数: url(网页地址)"
        )

    def execute(self, url: str) -> ToolResult:
        """执行浏览"""
        try:
            # 直接使用 requests 获取网页内容
            import requests
            from bs4 import BeautifulSoup

            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15
            )
            response.raise_for_status()

            # 解析 HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()

            # 获取文本
            text = soup.get_text(separator='\n', strip=True)

            # 截断过长的内容
            if len(text) > 3000:
                text = text[:3000] + "..."

            return ToolResult(success=True, data=text)
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))
