"""
工具系统 - ReAct Agent 的工具定义

支持：搜索、浏览、生成、评估、发布
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any
    error: str = ""


class BaseTool(ABC):
    """工具基类"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        pass
    
    def to_prompt(self) -> str:
        """生成工具描述（用于 prompt）"""
        return f"- {self.name}: {self.description}"


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
            # 直接使用项目内的 web_search 工具
            import sys
            sys.path.insert(0, '/Users/lee/content-agent')
            from web_search import web_search
            
            result = web_search(query, limit=3)
            items = result.get("data", {}).get("web", [])
            
            summaries = []
            for item in items:
                title = item.get("title", "")
                desc = item.get("description", "")
                url = item.get("url", "")
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


class GenerateTool(BaseTool):
    """生成工具 - 生成内容"""
    
    def __init__(self, writer_agent=None):
        super().__init__(
            name="generate",
            description="生成内容。参数: raw_notes(原始笔记), platforms(平台列表), style(风格)"
        )
        self.writer_agent = writer_agent
    
    def execute(self, **kwargs) -> ToolResult:
        """执行生成"""
        try:
            if self.writer_agent is None:
                from agents.writer_agent import WriterAgent
                self.writer_agent = WriterAgent()
            
            raw_notes = kwargs.get("raw_notes", "")
            platforms = kwargs.get("platforms", ["gongzhonghao"])
            style = kwargs.get("style", "default")
            
            result = self.writer_agent.run(raw_notes, platforms, style=style)
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))


class EvaluateTool(BaseTool):
    """评估工具 - 评估内容质量"""
    
    def __init__(self, editor_agent=None):
        super().__init__(
            name="evaluate",
            description="评估内容质量。参数: xiaohongshu(小红书内容), gongzhonghao(公众号内容), douyin(抖音内容)"
        )
        self.editor_agent = editor_agent
    
    def execute(self, **kwargs) -> ToolResult:
        """执行评估"""
        try:
            if self.editor_agent is None:
                from agents.editor_agent import EditorAgent
                from agents.writer_agent import _ModelConfig
                model, _ = _ModelConfig.from_env()
                self.editor_agent = EditorAgent(model)
            
            xiaohongshu = kwargs.get("xiaohongshu", "")
            gongzhonghao = kwargs.get("gongzhonghao", "")
            douyin = kwargs.get("douyin", "")
            
            result = self.editor_agent.run(xiaohongshu, gongzhonghao, douyin)
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))


class PublishTool(BaseTool):
    """发布工具 - 发布内容"""
    
    def __init__(self):
        super().__init__(
            name="publish",
            description="发布内容到平台。参数: queue_id(队列项ID)"
        )
    
    def execute(self, queue_id: str) -> ToolResult:
        """执行发布"""
        try:
            from automation.executor import PublishExecutor
            executor = PublishExecutor()
            result = executor.execute_one(queue_id)
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))


class RAGTool(BaseTool):
    """RAG 工具 - 检索相关笔记"""
    
    def __init__(self):
        super().__init__(
            name="rag",
            description="检索相关笔记。参数: query(查询内容), top_k(返回数量)"
        )
    
    def execute(self, query: str, top_k: int = 3) -> ToolResult:
        """执行检索"""
        try:
            # 直接使用项目内的 RAGPipeline
            import sys
            sys.path.insert(0, '/Users/lee/content-agent')
            from content_agent.rag_pipeline import RAGPipeline
            
            rag = RAGPipeline()
            results = rag.search(query, top_k=top_k)
            
            summaries = []
            for r in results:
                title = r.get("title", "")
                content = r.get("content", "")[:200]
                summaries.append(f"[{title}] {content}...")
            
            return ToolResult(
                success=True,
                data="\n\n".join(summaries) if summaries else "未找到相关笔记",
            )
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))


# 工具注册表
TOOL_REGISTRY: Dict[str, BaseTool] = {
    "search": SearchTool(),
    "browse": BrowseTool(),
    "generate": GenerateTool(),
    "evaluate": EvaluateTool(),
    "publish": PublishTool(),
    "rag": RAGTool(),
}


def get_tool(name: str) -> Optional[BaseTool]:
    """获取工具实例"""
    return TOOL_REGISTRY.get(name)


def list_tools() -> list:
    """列出所有可用工具"""
    return [tool.to_prompt() for tool in TOOL_REGISTRY.values()]


def execute_tool(name: str, **kwargs) -> ToolResult:
    """执行指定工具"""
    tool = get_tool(name)
    if tool is None:
        return ToolResult(success=False, data="", error=f"未知工具: {name}")
    return tool.execute(**kwargs)
