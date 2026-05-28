"""
工具测试

测试 agents/tools/ 中的工具函数
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.tools import (
    ToolResult,
    SearchTool,
    BrowseTool,
    FileReadTool,
    GenerateTool,
    EvaluateTool,
    DataAnalysisTool,
    CodeExecutionTool,
    execute_tool,
    get_tool,
    list_tools,
)


class TestToolResult(unittest.TestCase):
    """测试 ToolResult 数据类"""
    
    def test_success_result(self):
        result = ToolResult(success=True, data="test data", error="")
        self.assertTrue(result.success)
        self.assertEqual(result.data, "test data")
        self.assertEqual(result.error, "")
    
    def test_error_result(self):
        result = ToolResult(success=False, data="", error="test error")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "test error")
        self.assertEqual(result.data, "")


class TestSearchTool(unittest.TestCase):
    """测试搜索工具"""

    def test_tool_info(self):
        tool = SearchTool()
        self.assertEqual(tool.name, "search")
        self.assertIn("搜索", tool.description)

    @patch("content_agent.research.duckduckgo_search")
    def test_execute_search(self, mock_search):
        """mock 外部搜索，只验证工具封装和参数传递"""
        mock_search.return_value = [
            {"title": "Python 入门", "body": "Python 是一门简洁的语言", "href": "https://example.com/python"}
        ]
        result = execute_tool("search", query="Python programming")
        self.assertTrue(result.success)
        self.assertIn("Python 入门", result.data)
        mock_search.assert_called_once_with("Python programming", max_results=3)

    @patch("content_agent.research.duckduckgo_search")
    @patch("requests.get")
    def test_execute_search_fallback(self, mock_requests_get, mock_search):
        """测试搜索失败时的降级逻辑（mock 掉所有网络请求）"""
        mock_search.side_effect = Exception("网络错误")
        mock_requests_get.return_value = MagicMock(text="<html>fallback result</html>")
        result = execute_tool("search", query="test")
        self.assertTrue(result.success)
        self.assertIn("fallback result", result.data)

    @patch("content_agent.research.duckduckgo_search")
    @patch("requests.get")
    def test_execute_search_fallback_failure(self, mock_requests_get, mock_search):
        """测试搜索和降级都失败时的错误处理"""
        mock_search.side_effect = Exception("搜索失败")
        mock_requests_get.side_effect = Exception("降级也失败")
        result = execute_tool("search", query="test")
        self.assertFalse(result.success)
        self.assertIn("搜索失败", result.error)
        self.assertIn("降级也失败", result.error)


class TestFileReadTool(unittest.TestCase):
    """测试文件读取工具"""
    
    def test_read_existing_file(self):
        # 读取 README.md
        result = execute_tool("read", path="README.md")
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
        self.assertGreater(len(result.data), 0)
    
    def test_read_nonexistent_file(self):
        result = execute_tool("read", path="nonexistent_file.txt")
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)


class TestDataAnalysisTool(unittest.TestCase):
    """测试数据分析工具"""

    @patch("agents.tools.analysis.ModelConfig.from_env")
    @patch("agents.tools.analysis.Agent")
    def test_analyze_data(self, mock_agent_cls, mock_config):
        """mock LLM 调用，只验证工具封装和参数传递"""
        mock_config.return_value = ("fake-model", None)
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = MagicMock(output="## 数据概览\n数据表明一个上升趋势。")
        mock_agent_cls.return_value = mock_agent

        tool = DataAnalysisTool()
        result = tool.execute(data="1, 2, 3, 4, 5", analysis_type="trend")
        self.assertTrue(result.success)
        self.assertIn("数据概览", result.data)
        mock_agent.run_sync.assert_called_once()

    @patch("agents.tools.analysis.ModelConfig.from_env")
    @patch("agents.tools.analysis.Agent")
    def test_analyze_data_error_handling(self, mock_agent_cls, mock_config):
        """测试分析失败时的错误处理"""
        mock_config.return_value = ("fake-model", None)
        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = Exception("模型调用失败")
        mock_agent_cls.return_value = mock_agent

        tool = DataAnalysisTool()
        result = tool.execute(data="1, 2, 3", analysis_type="summary")
        self.assertFalse(result.success)
        self.assertIn("模型调用失败", result.error)


class TestCodeExecutionTool(unittest.TestCase):
    """测试代码执行工具"""
    
    def test_execute_safe_code(self):
        result = execute_tool("execute", code="print('Hello World')")
        self.assertTrue(result.success)
        self.assertIn("Hello World", result.data)
    
    def test_execute_dangerous_code(self):
        result = execute_tool("execute", code="import os")
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)


class TestToolRegistry(unittest.TestCase):
    """测试工具注册表"""
    
    def test_list_tools(self):
        tools = list_tools()
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)
    
    def test_get_tool(self):
        tool = get_tool("search")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "search")
    
    def test_get_nonexistent_tool(self):
        tool = get_tool("nonexistent")
        self.assertIsNone(tool)


if __name__ == "__main__":
    unittest.main()
