"""
工具测试

测试 agents/tools.py 中的工具函数
"""

import unittest
import sys
import os

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
    
    def test_execute_search(self):
        # 注意：这个测试需要网络连接，可能因网络问题失败
        result = execute_tool("search", query="Python programming")
        # 不强制要求成功，但要求有结果
        self.assertIsNotNone(result)
        if result.success:
            self.assertGreater(len(result.data), 0)


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
    
    def test_analyze_data(self):
        result = execute_tool("analyze", data="1, 2, 3, 4, 5", analysis_type="trend")
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
        self.assertGreater(len(result.data), 0)


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
