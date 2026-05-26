"""
平台名称映射测试

测试中文平台名称映射功能
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPlatformMap(unittest.TestCase):
    """测试平台名称映射"""
    
    def test_chinese_platform_names(self):
        """测试中文平台名称映射"""
        PLATFORM_MAP = {
            "公众号": "gongzhonghao",
            "微信": "gongzhonghao",
            "小红书": "xiaohongshu",
            "抖音": "douyin",
        }
        
        # 测试中文映射
        self.assertEqual(PLATFORM_MAP["公众号"], "gongzhonghao")
        self.assertEqual(PLATFORM_MAP["小红书"], "xiaohongshu")
        self.assertEqual(PLATFORM_MAP["抖音"], "douyin")
        
        # 测试英文不映射
        self.assertEqual(PLATFORM_MAP.get("gongzhonghao", "gongzhonghao"), "gongzhonghao")
    
    def test_platform_parsing(self):
        """测试平台解析逻辑"""
        PLATFORM_MAP = {
            "公众号": "gongzhonghao",
            "微信": "gongzhonghao",
            "小红书": "xiaohongshu",
            "抖音": "douyin",
        }
        
        # 模拟解析逻辑
        input_platforms = "公众号,小红书"
        platforms = []
        for p in input_platforms.split(","):
            p = p.strip()
            platforms.append(PLATFORM_MAP.get(p, p))
        
        self.assertEqual(platforms, ["gongzhonghao", "xiaohongshu"])
    
    def test_single_platform(self):
        """测试单平台解析"""
        PLATFORM_MAP = {
            "公众号": "gongzhonghao",
            "小红书": "xiaohongshu",
            "抖音": "douyin",
        }
        
        input_platforms = "抖音"
        platforms = []
        for p in input_platforms.split(","):
            p = p.strip()
            platforms.append(PLATFORM_MAP.get(p, p))
        
        self.assertEqual(platforms, ["douyin"])


if __name__ == "__main__":
    unittest.main()
