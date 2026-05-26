"""
集成测试

测试完整流程
"""

import unittest
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.schemas import WriterOutput
from agents.tools import execute_tool


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_topic_to_content_flow(self):
        """测试从主题到内容的完整流程"""
        # 1. 搜索资料
        search_result = execute_tool("search", query="Python programming")
        self.assertIsNotNone(search_result)
        
        # 2. 生成内容（使用模拟数据）
        raw_notes = "# Python Programming\n\nPython is a great language."
        generate_result = execute_tool("generate", raw_notes=raw_notes, platforms=["gongzhonghao"])
        self.assertTrue(generate_result.success)
        self.assertIsInstance(generate_result.data, WriterOutput)
        self.assertGreater(len(generate_result.data.gongzhonghao), 0)
    
    def test_evaluate_content(self):
        """测试内容评估"""
        # 生成内容
        raw_notes = "# Test\n\nThis is a test note."
        generate_result = execute_tool("generate", raw_notes=raw_notes, platforms=["xiaohongshu"])
        self.assertTrue(generate_result.success)
        
        # 评估内容
        content = generate_result.data.xiaohongshu
        evaluate_result = execute_tool("evaluate", xiaohongshu=content)
        self.assertTrue(evaluate_result.success)
        self.assertIsNotNone(evaluate_result.data)
    
    def test_file_read_write(self):
        """测试文件读写"""
        # 使用项目目录下的文件
        test_path = "README.md"
        
        # 读取文件
        read_result = execute_tool("read", path=test_path)
        self.assertTrue(read_result.success)
        self.assertIn("Content Agent", read_result.data)


if __name__ == "__main__":
    unittest.main()
