"""
工具系统 - ReAct Agent 的工具定义

支持：搜索、浏览、生成、评估、发布
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic_ai import Agent
from content_agent.config.model_config import ModelConfig


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


class FileReadTool(BaseTool):
    """文件读取工具 - 读取本地文件"""
    
    def __init__(self):
        super().__init__(
            name="read",
            description="读取本地文件内容。参数: path(文件路径)"
        )
    
    def execute(self, path: str) -> ToolResult:
        """执行文件读取"""
        try:
            # 安全检查：限制文件路径在项目目录下
            project_root = Path(__file__).resolve().parent.parent
            resolved_path = Path(path).expanduser().resolve()
            
            # 检查是否在项目目录或用户笔记目录下
            allowed_roots = [
                project_root,
                Path.home() / "notes",
                Path.home() / "wechat_doc",
            ]
            
            # 检查是否在允许的路径下
            allowed = any(
                resolved_path == root or resolved_path.is_relative_to(root)
                for root in allowed_roots
            )
            if not allowed:
                return ToolResult(
                    success=False,
                    data="",
                    error=f"文件路径不在允许范围内: {path}"
                )
            
            # 读取文件
            with open(resolved_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 截断过长的内容
            if len(content) > 5000:
                content = content[:5000] + "..."
            
            return ToolResult(success=True, data=content)
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
                from content_agent.config.model_config import ModelConfig
                from agents.editor_agent import EditorAgent
                model, _ = ModelConfig.from_env()
                self.editor_agent = EditorAgent(model)

            if len(kwargs) == 1:
                platform, content = list(kwargs.items())[0]
                result = self.editor_agent.run_single(platform, content)
                return ToolResult(success=True, data=result)

            # 多平台评估
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
            # 使用项目内 RAG 模块的 VaultIndexer
            from content_agent.rag.indexer import VaultIndexer
            
            indexer = VaultIndexer()
            results = indexer.search(query, n_results=top_k)
            
            summaries = []
            for r in results:
                title = r.get("metadata", {}).get("title", "")
                content = r.get("document", "")[:200]
                summaries.append(f"[{title}] {content}...")
            
            return ToolResult(
                success=True,
                data="\n\n".join(summaries) if summaries else "未找到相关笔记",
            )
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))


class DataAnalysisTool(BaseTool):
    """数据分析工具 - 分析数据并生成洞察"""
    
    def __init__(self):
        super().__init__(
            name="analyze",
            description="分析数据并生成洞察。参数: data(数据内容), analysis_type(分析类型: summary/trend/comparison)"
        )
        self.model, _ = ModelConfig.from_env()
        self._agent = Agent(
            self.model,
            system_prompt="""你是一位数据分析师，擅长从数据中提取洞察。

任务：
1. 分析提供的数据
2. 提取关键趋势和模式
3. 生成结构化分析报告

输出格式：
## 数据概览
[总体描述]

## 关键发现
- [发现1]
- [发现2]

## 趋势分析
[趋势描述]

## 建议
[基于数据的建议]
""",
        )
    
    def execute(self, data: str, analysis_type: str = "summary") -> ToolResult:
        """执行数据分析"""
        try:
            prompt = f"""请对以下数据进行{analysis_type}分析：

数据：
{data[:3000]}

请输出结构化分析报告。"""
            
            result = self._agent.run_sync(prompt)
            return ToolResult(success=True, data=result.output)
        except Exception as e:
            return ToolResult(success=False, data="", error=str(e))


class CodeExecutionTool(BaseTool):
    """代码执行工具 - 安全执行 Python 代码"""
    
    def __init__(self):
        super().__init__(
            name="execute",
            description="执行 Python 代码并返回结果。参数: code(代码字符串)"
        )
    
    def execute(self, code: str) -> ToolResult:
        """安全执行代码"""
        try:
            # 安全检查：禁止危险操作
            dangerous_keywords = [
                'import os', 'import sys', 'open(', 'eval(', 'exec(',
                '__import__', 'subprocess', 'shell', 'rm -rf',
                'import socket', 'import urllib',
            ]
            
            code_lower = code.lower()
            for keyword in dangerous_keywords:
                if keyword in code_lower:
                    return ToolResult(
                        success=False,
                        data="",
                        error=f"代码包含危险操作: {keyword}"
                    )
            
            # 在受限环境中执行
            import io
            import contextlib
            
            # 捕获输出
            output_buffer = io.StringIO()
            
            # 创建受限的全局命名空间
            safe_globals = {
                '__builtins__': {
                    'print': print,
                    'len': len,
                    'range': range,
                    'enumerate': enumerate,
                    'zip': zip,
                    'map': map,
                    'filter': filter,
                    'sum': sum,
                    'min': min,
                    'max': max,
                    'abs': abs,
                    'round': round,
                    'str': str,
                    'int': int,
                    'float': float,
                    'list': list,
                    'dict': dict,
                    'tuple': tuple,
                    'set': set,
                    'sorted': sorted,
                    'reversed': reversed,
                }
            }
            
            safe_locals = {}
            
            with contextlib.redirect_stdout(output_buffer):
                exec(code, safe_globals, safe_locals)
            
            output = output_buffer.getvalue()
            
            return ToolResult(success=True, data=output or "代码执行成功，无输出")
            
        except Exception as e:
            return ToolResult(success=False, data="", error=f"代码执行错误: {e}")


# 工具注册表
TOOL_REGISTRY: Dict[str, BaseTool] = {
    "search": SearchTool(),
    "browse": BrowseTool(),
    "read": FileReadTool(),
    "generate": GenerateTool(),
    "evaluate": EvaluateTool(),
    "publish": PublishTool(),
    "rag": RAGTool(),
    "analyze": DataAnalysisTool(),
    "execute": CodeExecutionTool(),
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
