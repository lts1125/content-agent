"""
平台名称映射测试

测试中文平台名称映射功能
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import parse_platforms


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
        self.assertEqual(parse_platforms("公众号,小红书"), ["gongzhonghao", "xiaohongshu"])
    
    def test_single_platform(self):
        """测试单平台解析"""
        self.assertEqual(parse_platforms("抖音"), ["douyin"])

    def test_all_expands_to_real_platforms(self):
        """测试 all 展开为真实平台列表"""
        self.assertEqual(
            parse_platforms("all"),
            ["xiaohongshu", "gongzhonghao", "douyin"],
        )

    def test_react_platform_alias_overrides_default_all(self):
        """测试 ReAct 模式下 --platform 可作为 --platforms 的兼容别名"""
        self.assertEqual(parse_platforms("all", "xiaohongshu"), ["xiaohongshu"])

    def test_invalid_platform_rejected(self):
        """测试无效平台会报错"""
        with self.assertRaises(ValueError):
            parse_platforms("all,unknown")


if __name__ == "__main__":
    unittest.main()
